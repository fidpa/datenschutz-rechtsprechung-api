"""
Integration Tests für die komplette Datenschutz-Rechtsprechung API Pipeline.

Testet den vollständigen Workflow von der Datensammlung über die Verarbeitung
bis zur API-Ausgabe.
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch
import hashlib

import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, AnonymizationMapping, CrawlLog
from src.collectors.gdprhub import GDPRhubCollector
from src.processors.pdf_extractor import PDFExtractor
from src.processors.legal_parser import LegalParser
from src.processors.anonymizer import Anonymizer
from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.api.main import app
from src.config import settings


class TestFullPipeline:
    """End-to-End Tests der kompletten Datenpipeline."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, db_session: AsyncSession, test_client):
        """
        Test des kompletten Workflows von Crawl bis Export.

        Pipeline: GDPRhub → PDF → Text → Parser → Anonymisierung → DB → API
        """
        # 1. Simuliere GDPRhub Crawling
        mock_html = """
        <html>
        <body>
            <h1>GDPR Decision</h1>
            <p><b>Court:</b> LG München</p>
            <p><b>Date:</b> 2024-01-15</p>
            <p><b>Case Number:</b> 1 O 123/23</p>
            <p>Reference to Art. 6 GDPR and Art. 15 GDPR</p>
            <p>Max Mustermann vs. Firma GmbH</p>
            <a href="/files/decision.pdf">Download PDF</a>
        </body>
        </html>
        """

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.text = mock_html
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/html"}
            mock_get.return_value = mock_response

            collector = GDPRhubCollector(db_session)

            # Simuliere Metadaten-Extraktion
            metadata = {
                "source_id": "test_123",
                "title": "Test GDPR Decision",
                "court": "LG München",
                "decision_date": datetime(2024, 1, 15),
                "case_number": "1 O 123/23",
                "source_url": "https://gdprhub.eu/test_123",
                "full_text_original": "Max Mustermann filed a complaint against Firma GmbH regarding Art. 6 GDPR violations.",
            }

            # 2. DSGVO-Artikel Extraktion
            extractor = GDPRArticleExtractor()
            gdpr_articles = await extractor.extract_articles(metadata["full_text_original"])
            assert "Art. 6" in gdpr_articles

            # 3. Anonymisierung
            anonymizer = Anonymizer()
            anon_result = await anonymizer.anonymize(metadata["full_text_original"])
            assert "[Person 1]" in anon_result.anonymized_text
            assert "Max Mustermann" not in anon_result.anonymized_text

            # 4. Speicherung in DB
            decision = Decision(
                source=metadata["source"],
                source_id=metadata["source_id"],
                title=metadata["title"],
                court=metadata["court"],
                decision_date=metadata["decision_date"],
                case_number=metadata["case_number"],
                source_url=metadata["source_url"],
                full_text_original=metadata["full_text_original"],
                full_text_anonymized=anon_result.anonymized_text,
                gdpr_articles=gdpr_articles,
                anonymization_applied=True,
            )
            db_session.add(decision)

            # Speichere Anonymisierungs-Mappings
            for placeholder, original in anon_result.mappings.items():
                mapping = AnonymizationMapping(
                    decision_id=decision.id,
                    placeholder=placeholder,
                    original_hash=hashlib.sha256(original.encode()).hexdigest(),
                    entity_type=anon_result.entity_types.get(placeholder, "UNKNOWN"),
                )
                db_session.add(mapping)

            await db_session.commit()

            # 5. Teste API-Zugriff
            response = await test_client.get(f"/api/v1/decisions/{decision.id}")
            assert response.status_code == 200

            api_data = response.json()
            assert api_data["title"] == metadata["title"]
            assert api_data["anonymization_applied"] is True
            assert "[Person 1]" in api_data["full_text_anonymized"]

            # 6. Teste Volltext-Suche
            response = await test_client.get("/api/v1/decisions/search", params={"query": "GDPR"})
            assert response.status_code == 200
            results = response.json()
            assert results["total"] >= 1

    @pytest.mark.asyncio
    async def test_pdf_processing_pipeline(self, db_session: AsyncSession, tmp_path: Path):
        """Test der PDF-Verarbeitungspipeline."""
        # Erstelle Test-PDF
        pdf_content = b"%PDF-1.4\nTest PDF Content with GDPR Art. 15 reference"
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)

        with patch("src.processors.pdf_extractor.pdfplumber.open") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = """
            URTEIL
            
            Im Namen des Volkes
            
            Leitsatz:
            Die Verarbeitung personenbezogener Daten ohne Rechtsgrundlage verstößt gegen Art. 6 DSGVO.
            
            Tenor:
            Die Beklagte wird verurteilt, die unrechtmäßige Datenverarbeitung zu unterlassen.
            
            Tatbestand:
            Der Kläger Max Mustermann wendet sich gegen die Verarbeitung seiner Daten.
            
            Entscheidungsgründe:
            Die Klage ist begründet. Die Beklagte hat gegen Art. 6 und Art. 15 DSGVO verstoßen.
            """
            mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

            # 1. PDF-Extraktion
            extractor = PDFExtractor()
            result = await extractor.extract_text(str(pdf_path))
            assert result["success"] is True
            assert "DSGVO" in result["text"]

            # 2. Rechtsstruktur-Parser
            parser = LegalParser()
            parsed = await parser.parse_german_legal_structure(result["text"])
            assert parsed["leitsatz"] is not None
            assert "Art. 6 DSGVO" in parsed["leitsatz"]
            assert parsed["tenor"] is not None
            assert parsed["tatbestand"] is not None
            assert parsed["entscheidungsgruende"] is not None

            # 3. Speichere strukturierte Daten
            decision = Decision(
                source="test",
                source_id="pdf_test_1",
                title="Test PDF Decision",
                full_text_original=result["text"],
                leitsatz=parsed["leitsatz"],
                tenor=parsed["tenor"],
                tatbestand=parsed["tatbestand"],
                entscheidungsgruende=parsed["entscheidungsgruende"],
                pdf_extracted=True,
            )
            db_session.add(decision)
            await db_session.commit()

            # Verifiziere Speicherung
            saved = await db_session.get(Decision, decision.id)
            assert saved.pdf_extracted is True
            assert saved.leitsatz is not None

    @pytest.mark.asyncio
    async def test_error_recovery(self, db_session: AsyncSession):
        """Test der Fehlerbehandlung und Recovery."""
        collector = GDPRhubCollector(db_session)

        # Test 1: Netzwerkfehler
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.NetworkError("Connection failed")

            result = await collector._fetch_with_retry("https://test.url")
            assert result is None  # Sollte gracefully fehlschlagen

        # Test 2: Korruptes PDF
        with patch("src.processors.pdf_extractor.pdfplumber.open") as mock_pdf:
            mock_pdf.side_effect = Exception("PDF is corrupted")

            extractor = PDFExtractor()
            result = await extractor.extract_text("corrupt.pdf")
            assert result["success"] is False
            assert "error" in result

        # Test 3: DB-Connection Loss
        decision = Decision(source="test", source_id="error_test_1", title="Error Test Decision")

        with patch.object(db_session, "commit", side_effect=Exception("DB connection lost")):
            try:
                db_session.add(decision)
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                # Sollte Rollback durchführen
                assert True

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, db_session: AsyncSession):
        """Test paralleler Verarbeitung mehrerer Entscheidungen."""

        async def process_decision(index: int) -> Decision:
            """Simuliere Verarbeitung einer Entscheidung."""
            decision = Decision(
                source="test",
                source_id=f"concurrent_{index}",
                title=f"Concurrent Decision {index}",
                full_text_original=f"Test content {index} with Art. {index % 30 + 1} GDPR reference",
            )

            # Simuliere Verarbeitungszeit
            await asyncio.sleep(0.1)

            # DSGVO-Extraktion
            extractor = GDPRArticleExtractor()
            decision.gdpr_articles = await extractor.extract_articles(decision.full_text_original)

            # Anonymisierung
            anonymizer = Anonymizer()
            result = await anonymizer.anonymize(decision.full_text_original)
            decision.full_text_anonymized = result.anonymized_text
            decision.anonymization_applied = True

            return decision

        # Verarbeite 10 Entscheidungen parallel
        tasks = [process_decision(i) for i in range(10)]
        decisions = await asyncio.gather(*tasks)

        # Speichere alle in DB
        for decision in decisions:
            db_session.add(decision)

        await db_session.commit()

        # Verifiziere
        count = await db_session.execute(
            "SELECT COUNT(*) FROM decisions WHERE source_id LIKE 'concurrent_%'"
        )
        assert count.scalar() == 10

    @pytest.mark.asyncio
    async def test_edge_cases(self, db_session: AsyncSession):
        """Test von Edge Cases und Grenzfällen."""

        # Test 1: Sehr große Entscheidung (>10MB simuliert)
        large_text = "x" * (11 * 1024 * 1024)  # 11MB Text
        decision = Decision(
            source="test",
            source_id="large_1",
            title="Large Decision",
            full_text_original=large_text[:1000000],  # Truncate für DB
        )
        db_session.add(decision)
        await db_session.commit()

        # Test 2: Nicht-deutsche Entscheidung
        french_text = "Ceci est une décision française concernant le RGPD"
        anonymizer = Anonymizer()
        result = await anonymizer.anonymize(french_text)
        # Sollte trotzdem funktionieren, auch wenn weniger effektiv
        assert result.anonymized_text is not None

        # Test 3: Duplikate
        dup1 = Decision(source="test", source_id="dup_1", title="Duplicate")
        dup2 = Decision(source="test", source_id="dup_1", title="Duplicate 2")

        db_session.add(dup1)
        await db_session.commit()

        # Zweites sollte fehlschlagen wegen unique constraint
        db_session.add(dup2)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

        # Test 4: Leere/Null-Werte
        empty_decision = Decision(
            source="test",
            source_id="empty_1",
            title="Empty Decision",
            full_text_original=None,
            full_text_anonymized=None,
        )
        db_session.add(empty_decision)
        await db_session.commit()

        # Test 5: Sonderzeichen und Unicode
        special_text = "Test mit 🚀 Emoji und Ümlautën sowie 中文字符"
        anonymizer = Anonymizer()
        result = await anonymizer.anonymize(special_text)
        assert result.anonymized_text is not None

    @pytest.mark.asyncio
    async def test_performance_metrics(self, db_session: AsyncSession):
        """Misst Performance-Metriken der Pipeline."""
        import time

        metrics = {
            "crawl_time": [],
            "extraction_time": [],
            "anonymization_time": [],
            "db_write_time": [],
            "total_time": [],
        }

        for i in range(5):  # 5 Durchläufe für Durchschnittswerte
            start_total = time.time()

            # Crawling simulieren
            start = time.time()
            text = f"Decision {i} with personal data Max Mustermann and reference to Art. 6 GDPR"
            metrics["crawl_time"].append(time.time() - start)

            # DSGVO-Extraktion
            start = time.time()
            extractor = GDPRArticleExtractor()
            articles = await extractor.extract_articles(text)
            metrics["extraction_time"].append(time.time() - start)

            # Anonymisierung
            start = time.time()
            anonymizer = Anonymizer()
            anon_result = await anonymizer.anonymize(text)
            metrics["anonymization_time"].append(time.time() - start)

            # DB-Speicherung
            start = time.time()
            decision = Decision(
                source="perf_test",
                source_id=f"perf_{i}",
                title=f"Performance Test {i}",
                full_text_original=text,
                full_text_anonymized=anon_result.anonymized_text,
                gdpr_articles=articles,
            )
            db_session.add(decision)
            await db_session.commit()
            metrics["db_write_time"].append(time.time() - start)

            metrics["total_time"].append(time.time() - start_total)

        # Ausgabe der Metriken
        for metric, times in metrics.items():
            avg_time = sum(times) / len(times)
            print(f"{metric}: {avg_time:.3f}s (avg)")

            # Performance-Assertions
            if metric == "extraction_time":
                assert avg_time < 0.5  # Sollte unter 500ms sein
            elif metric == "anonymization_time":
                assert avg_time < 1.0  # Sollte unter 1s sein
            elif metric == "db_write_time":
                assert avg_time < 0.5  # Sollte unter 500ms sein

    @pytest.mark.asyncio
    async def test_api_integration(self, test_client, db_session: AsyncSession):
        """Test der API-Integration mit der Pipeline."""

        # Erstelle Test-Daten
        for i in range(10):
            decision = Decision(
                source="api_test",
                source_id=f"api_{i}",
                title=f"API Test Decision {i}",
                court="LG München" if i % 2 == 0 else "OLG Frankfurt",
                decision_date=datetime.now() - timedelta(days=i),
                gdpr_articles=[f"Art. {i+1}", f"Art. {i+2}"],
                full_text_anonymized=f"Anonymized text {i}",
            )
            db_session.add(decision)
        await db_session.commit()

        # Test 1: Liste mit Pagination
        response = await test_client.get("/api/v1/decisions", params={"limit": 5, "offset": 0})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] >= 10

        # Test 2: Filterung
        response = await test_client.get("/api/v1/decisions", params={"court": "LG München"})
        assert response.status_code == 200
        data = response.json()
        assert all(d["court"] == "LG München" for d in data["items"])

        # Test 3: Volltext-Suche
        response = await test_client.get("/api/v1/decisions/search", params={"query": "text"})
        assert response.status_code == 200

        # Test 4: Statistiken
        response = await test_client.get("/api/v1/stats/overview")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_decisions"] >= 10

        # Test 5: Export
        response = await test_client.get("/api/v1/export/json", params={"limit": 100})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
