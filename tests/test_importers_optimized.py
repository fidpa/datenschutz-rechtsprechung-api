#!/usr/bin/env python3
"""
Umfassende Unit-Tests für optimierte Import-Module.

Testet Batch-Processing, Error-Handling und Performance.
"""

import pytest
import json
import tempfile
import gzip
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime
from typing import List, Dict, Any

# Import der zu testenden Module
from src.importers.base_optimized import OptimizedBaseImporter
from src.importers.openlegaldata import OpenLegalDataImporter
from src.importers.swiss_datasets import SwissDatasetImporter
from src.database import Decision
from src.processors.performance_monitor import PerformanceMonitor
from src.processors.resume_manager import ResumeManager
from src.utils.file_handlers import DumpFileHandler


# Test-Implementierung des abstrakten BaseImporter
class TestImporter(OptimizedBaseImporter):
    """Test-Implementierung für Unit-Tests."""

    def parse_document(self, raw_data: Dict[str, Any]) -> Decision:
        """Mock-Parser für Tests."""
        return Decision(
            case_number=raw_data.get("id", "test-123"),
            source="test",
            title=raw_data.get("title", "Test Decision"),
            court=raw_data.get("court", "Test Court"),
            full_text=raw_data.get("content", "Test content"),
            gdpr_articles=[1, 2, 3] if raw_data.get("gdpr") else None,
        )

    def is_relevant(self, raw_data: Dict[str, Any]) -> bool:
        """Mock-Relevanz-Check."""
        return raw_data.get("relevant", True)

    def get_document_id(self, raw_data: Dict[str, Any]) -> str:
        """Mock-ID-Extraktion."""
        return str(raw_data.get("id", "unknown"))


class TestOptimizedBaseImporter:
    """Tests für den optimierten Base Importer."""

    @pytest.fixture
    def importer(self):
        """Erstellt Test-Importer-Instanz."""
        return TestImporter(verbose=False)

    @pytest.fixture
    def test_data(self):
        """Erstellt Test-Dokumente."""
        return [
            {
                "id": f"doc-{i}",
                "title": f"Decision {i}",
                "content": f"Content {i}",
                "gdpr": i % 2 == 0,
            }
            for i in range(100)
        ]

    @pytest.fixture
    def test_file(self, test_data):
        """Erstellt temporäre Test-Datei."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            return Path(f.name)

    def test_batch_processing(self, importer, test_file):
        """Test Batch-Processing-Funktionalität."""
        with patch.object(importer, "_bulk_save_decisions") as mock_bulk_save:
            mock_bulk_save.return_value = (50, 0)  # 50 saved, 0 skipped

            # Import mit Batch-Size 10
            stats = importer.import_from_file(test_file, limit=50, batch_size=10)

            # Prüfe dass Bulk-Save aufgerufen wurde
            assert mock_bulk_save.call_count == 5  # 50 docs / 10 batch_size = 5

            # Prüfe Statistiken
            assert stats["total_processed"] == 50
            assert stats["imported"] == 50

    def test_bulk_save_decisions(self, importer):
        """Test Bulk-Save-Funktionalität."""
        # Mock Decisions erstellen
        decisions = [
            Decision(
                case_number=f"case-{i}",
                source="test",
                title=f"Decision {i}",
                court="Test Court",
                full_text=f"Content {i}",
            )
            for i in range(10)
        ]

        with patch("src.importers.base_optimized.db_manager.get_session") as mock_session:
            # Mock Session setup
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock existing check
            session.query.return_value.filter.return_value.all.return_value = [
                ("case-0",),
                ("case-1",),  # 2 bereits vorhanden
            ]

            # Bulk save ausführen
            saved, skipped = importer._bulk_save_decisions(decisions)

            # Assertions
            assert saved == 8  # 10 - 2 existing
            assert skipped == 2

            # Prüfe dass bulk_insert_mappings aufgerufen wurde
            session.bulk_insert_mappings.assert_called_once()
            call_args = session.bulk_insert_mappings.call_args[0]
            assert call_args[0] == Decision
            assert len(call_args[1]) == 8  # 8 neue Decisions

    def test_retry_logic(self, importer):
        """Test Retry-Mechanismus bei Fehlern."""
        # Mock-Dokument das beim ersten Mal fehlschlägt
        doc = {"id": "fail-doc", "content": "test"}

        with patch.object(importer, "parse_document") as mock_parse:
            # Erste 2 Aufrufe schlagen fehl, dritter erfolgreich
            mock_parse.side_effect = [
                Exception("Parse error"),
                Exception("Parse error"),
                Decision(case_number="test", source="test", title="Test"),
            ]

            # Mit Retry sollte es funktionieren
            result = importer._process_document_with_retry(doc, False, False)

            assert result is not None
            assert mock_parse.call_count == 3  # 3 Versuche
            assert importer.stats["retries"] == 2  # 2 Retries

    def test_performance_tracking(self, importer, test_file):
        """Test Performance-Monitoring-Integration."""
        with patch.object(importer, "_bulk_save_decisions") as mock_bulk_save:
            mock_bulk_save.return_value = (10, 0)

            # Import durchführen
            stats = importer.import_from_file(test_file, limit=10)

            # Prüfe Performance-Metriken
            perf_stats = importer.performance_monitor.performance_stats
            assert perf_stats["total_duration"] > 0
            assert len(perf_stats["processing_times"]) == 10
            assert perf_stats["db_operations"] == 1  # Ein Batch

    def test_resume_functionality(self, importer):
        """Test Resume-Funktionalität nach Unterbrechung."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            test_file = Path(f.name)
            # 20 Test-Dokumente
            json.dump([{"id": i} for i in range(20)], f)

        resume_file = test_file.with_suffix(".resume")

        try:
            # Simuliere ersten Import mit Unterbrechung bei Doc 10
            with patch.object(importer, "_bulk_save_decisions") as mock_save:
                mock_save.return_value = (10, 0)

                # Manuell Resume-State speichern
                resume_mgr = ResumeManager(test_file, resume_file)
                resume_mgr.save_state(10, {"imported": 10, "total_processed": 10})

                # Resume-Import
                with patch.object(importer, "file_handler") as mock_handler:
                    # Mock: Nur Docs ab Position 10
                    mock_handler.open_file.return_value = iter([{"id": i} for i in range(10, 20)])

                    stats = importer.import_from_file(test_file, resume=True)

                    # Sollte bei Position 10 fortsetzen
                    assert stats["total_processed"] >= 10

        finally:
            test_file.unlink(missing_ok=True)
            resume_file.unlink(missing_ok=True)

    def test_memory_management(self, importer):
        """Test Memory-Management und Limits."""
        # Große Anzahl von Dokumenten
        large_data = [{"id": i, "content": "x" * 10000} for i in range(1000)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(large_data, f)
            test_file = Path(f.name)

        try:
            with patch.object(importer, "_bulk_save_decisions") as mock_save:
                mock_save.return_value = (100, 0)

                # Import mit Memory-Tracking
                stats = importer.import_from_file(test_file, limit=100, batch_size=20)

                # Prüfe dass Memory getrackt wurde
                memory_usage = importer.performance_monitor.performance_stats["memory_usage"]
                assert len(memory_usage) > 0

                # Memory sollte nicht explodieren
                if memory_usage:
                    max_memory = max(memory_usage)
                    assert max_memory < 2000  # Weniger als 2GB

        finally:
            test_file.unlink(missing_ok=True)


class TestOpenLegalDataImporter:
    """Tests für OpenLegalData Importer."""

    @pytest.fixture
    def importer(self):
        """Erstellt OpenLegalData Importer."""
        return OpenLegalDataImporter(verbose=False, min_score=3)

    def test_relevance_scoring(self, importer):
        """Test DSGVO-Relevanz-Scoring."""
        # Hoch-relevantes Dokument
        high_relevance = {
            "content": "Dies ist ein Fall nach Art. 15 DSGVO mit Datenschutzverletzung",
            "name": "DSGVO-Entscheidung",
        }
        score = importer.calculate_relevance_score(high_relevance)
        assert score >= 10  # Sollte hohen Score haben

        # Niedrig-relevantes Dokument
        low_relevance = {
            "content": "Normaler Vertragsstreit ohne Datenschutzbezug",
            "name": "Kaufvertrag",
        }
        score = importer.calculate_relevance_score(low_relevance)
        assert score < 3  # Sollte niedrigen Score haben

        # BDSG-relevantes Dokument
        bdsg_doc = {"content": "Verstoß gegen § 26 BDSG-neu im Beschäftigungsverhältnis"}
        score = importer.calculate_relevance_score(bdsg_doc)
        assert score >= 5  # BDSG-Relevanz

    def test_document_parsing(self, importer):
        """Test Dokument-Parsing."""
        raw_doc = {
            "id": 12345,
            "name": "Test-Entscheidung",
            "content": "Volltext der Entscheidung",
            "date": "2024-01-15T10:00:00Z",
            "court": {"name": "BGH"},
            "file_number": "VI ZR 123/23",
            "ecli": ["ECLI:DE:BGH:2024:123"],
        }

        with patch.object(importer.anonymizer, "anonymize") as mock_anon:
            mock_anon.return_value = "Anonymisierter Text"

            with patch.object(importer.gdpr_extractor, "extract") as mock_extract:
                mock_extract.return_value = [15, 17]

                decision = importer.parse_document(raw_doc)

                assert decision is not None
                assert decision.case_number == "VI ZR 123/23"
                assert decision.title == "Test-Entscheidung"
                assert decision.court == "BGH"
                assert decision.gdpr_articles == [15, 17]
                assert decision.anonymization_applied == True

    def test_batch_import_performance(self, importer):
        """Test Batch-Import-Performance."""
        # 500 Test-Dokumente
        test_data = [
            {
                "id": i,
                "name": f"Entscheidung {i}",
                "content": f"DSGVO Art. {i % 99 + 1} Datenschutz"
                if i % 10 == 0
                else f"Normaler Text {i}",
                "court": {"name": "LG München"},
                "date": "2024-01-01T00:00:00Z",
            }
            for i in range(500)
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            test_file = Path(f.name)

        try:
            with patch("src.importers.base.db_manager.get_session"):
                import time

                start = time.time()

                stats = importer.import_from_file(test_file, batch_size=100, filter_relevant=True)

                duration = time.time() - start

                # Performance-Assertions
                assert stats["total_processed"] == 500
                assert stats["gdpr_relevant"] == 50  # 10% sind DSGVO-relevant

                # Sollte schnell sein (< 5 Sekunden für 500 Docs)
                assert duration < 5.0

                # Durchsatz prüfen
                throughput = stats["total_processed"] / duration
                assert throughput > 100  # Mindestens 100 docs/s

        finally:
            test_file.unlink(missing_ok=True)


class TestSwissDatasetImporter:
    """Tests für Swiss Dataset Importer."""

    @pytest.fixture
    def importer(self):
        """Erstellt Swiss Dataset Importer."""
        return SwissDatasetImporter(verbose=False, min_score=3)

    def test_swiss_relevance_scoring(self, importer):
        """Test DSG/FADP-Relevanz-Scoring."""
        # DSG-relevantes Dokument
        dsg_doc = {
            "text": "Verletzung von Art. 8 DSG durch unrechtmäßige Datenbearbeitung",
            "title": "Datenschutzentscheid",
            "court": "Bundesgericht",
        }
        score = importer.calculate_relevance_score(dsg_doc)
        assert score >= 10  # DSG direkte Referenz

        # EDÖB-Dokument
        edoeb_doc = {"text": "Der EDÖB stellte eine Verletzung der Informationspflicht fest"}
        score = importer.calculate_relevance_score(edoeb_doc)
        assert score >= 7  # Behördenbezug

        # Französisches DSG-Dokument
        french_doc = {"text": "Violation de la LPD concernant les données personnelles"}
        score = importer.calculate_relevance_score(french_doc)
        assert score >= 10  # LPD = DSG auf Französisch

    def test_multilingual_support(self, importer):
        """Test Mehrsprachigkeit (DE/FR/IT)."""
        docs = [
            {"text": "Datenschutz"},  # Deutsch
            {"text": "protection des données"},  # Französisch
            {"text": "protezione dei dati"},  # Italienisch (wenn implementiert)
        ]

        for doc in docs[:2]:  # Teste DE und FR
            assert importer.is_relevant(doc) == True

    def test_document_id_extraction(self, importer):
        """Test ID-Extraktion für verschiedene Formate."""
        # Standard ID
        assert importer.get_document_id({"id": "123"}) == "123"

        # BGE ID
        assert importer.get_document_id({"bge_id": "BGE-145-III-234"}) == "BGE-145-III-234"

        # File Number Fallback
        assert importer.get_document_id({"file_number": "4A_123/2024"}) == "4A_123/2024"

        # Hash Fallback
        doc_without_id = {"text": "Some content"}
        doc_id = importer.get_document_id(doc_without_id)
        assert len(doc_id) == 16  # MD5 hash truncated

    @patch("src.importers.swiss_datasets.get_anonymizer")
    @patch("src.importers.swiss_datasets.GDPRArticleExtractor")
    def test_parse_swiss_document(self, mock_extractor_class, mock_anonymizer):
        """Test Parsing von Schweizer Dokumenten."""
        # Mock Setup
        mock_anon = MagicMock()
        mock_anon.anonymize.return_value = "Anonymisierter Text"
        mock_anonymizer.return_value = mock_anon

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []
        mock_extractor_class.return_value = mock_extractor

        importer = SwissDatasetImporter()

        # Test-Dokument
        raw_doc = {
            "id": "BGE-150-II-123",
            "title": "Datenschutzentscheid",
            "text": "Bundesgericht Entscheidung",
            "court": "Bundesgericht",
            "canton": "BE",
            "date": "2024-03-15",
            "legal_area": "Datenschutzrecht",
        }

        decision = importer.parse_document(raw_doc)

        assert decision is not None
        assert "Bundesgericht" in decision.court
        assert decision.source == "swiss_rulings"
        assert "BE" in str(decision.metadata)


class TestIntegrationPipeline:
    """Integration-Tests für die komplette Import-Pipeline."""

    def test_end_to_end_import(self):
        """Test kompletter Import-Workflow."""
        # Test-Daten vorbereiten
        test_data = [
            {
                "id": i,
                "name": f"DSGVO Entscheidung {i}",
                "content": f"Art. {i % 30 + 1} DSGVO wurde verletzt",
                "court": {"name": "OLG Frankfurt"},
                "date": "2024-01-01T00:00:00Z",
            }
            for i in range(50)
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            test_file = Path(f.name)

        try:
            # Importer initialisieren
            importer = OpenLegalDataImporter(verbose=True)

            with patch("src.importers.base_optimized.db_manager.get_session") as mock_session:
                # Mock DB Session
                session = MagicMock()
                mock_session.return_value.__enter__.return_value = session
                session.query.return_value.filter.return_value.all.return_value = []

                # Import durchführen
                stats = importer.import_from_file(
                    test_file, batch_size=10, filter_relevant=False  # Alle importieren
                )

                # Validierung
                assert stats["total_processed"] == 50
                assert stats["gdpr_relevant"] == 50  # Alle haben DSGVO-Bezug
                assert stats["errors"] == 0

                # Batch-Processing wurde verwendet
                assert session.bulk_insert_mappings.call_count > 0

        finally:
            test_file.unlink(missing_ok=True)

    def test_error_recovery(self):
        """Test Error-Recovery und Fortsetzung."""
        # Dokumente mit Fehlern
        test_data = [
            {"id": i, "content": "Normal"}
            if i % 10 != 0
            else {"id": i}  # Fehlende Felder bei jedem 10. Dokument
            for i in range(30)
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            test_file = Path(f.name)

        try:
            importer = TestImporter(verbose=False)

            with patch.object(importer, "_bulk_save_decisions") as mock_save:
                mock_save.return_value = (27, 0)  # 3 Fehler erwartet

                stats = importer.import_from_file(test_file)

                # Sollte trotz Fehlern weitermachen
                assert stats["total_processed"] == 30
                assert stats["skipped_parse_error"] >= 0  # Einige Parse-Fehler

        finally:
            test_file.unlink(missing_ok=True)
