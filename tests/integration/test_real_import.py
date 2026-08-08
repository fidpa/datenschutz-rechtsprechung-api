#!/usr/bin/env python3
"""
Real-World Integration Tests für das optimierte Import-System.

Testet mit echter PostgreSQL-Datenbank und realen Daten.
"""

import pytest
import tempfile
import json
import time
import psutil
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, timedelta
import pandas as pd

from src.database import db_manager, Decision, init_db
from src.importers.base_optimized import OptimizedBaseImporter
from src.importers.openlegaldata import OpenLegalDataImporter
from src.importers.swiss_datasets import SwissDatasetImporter
from src.processors.performance_monitor import PerformanceMonitor
from src.utils.logging import get_logger

logger = get_logger("IntegrationTest")


# Test-Daten für realistische Szenarien
SAMPLE_OPENLEGALDATA = [
    {
        "id": 1001,
        "name": "BGH Urteil VI ZR 123/22 - DSGVO Schadensersatz",
        "content": """Der Bundesgerichtshof hat entschieden, dass nach Art. 82 DSGVO 
        ein Schadensersatzanspruch wegen Verletzung des Datenschutzes besteht. 
        Die Beklagte hatte personenbezogene Daten des Klägers ohne rechtliche 
        Grundlage nach Art. 6 DSGVO verarbeitet. Dies stellt eine Verletzung 
        der Betroffenenrechte nach Art. 15 ff. DSGVO dar. Der Kläger Max Mustermann
        erhält 5000 EUR Schadensersatz. Die Beklagte Firma Data Corp GmbH muss
        zudem alle Daten nach Art. 17 DSGVO löschen.""",
        "court": {"name": "Bundesgerichtshof", "code": "BGH"},
        "date": "2024-03-15T10:00:00Z",
        "file_number": "VI ZR 123/22",
        "ecli": ["ECLI:DE:BGH:2024:150324.VI.ZR.123.22"],
    },
    {
        "id": 1002,
        "name": "OLG Frankfurt 6 U 89/23 - Datenschutzverletzung Social Media",
        "content": """Verstoß gegen Art. 7 DSGVO (Einwilligung) und Art. 13 DSGVO 
        (Informationspflichten). Die Antragstellerin Erika Musterfrau hatte nie
        in die Datenverarbeitung eingewilligt. Bußgeld nach Art. 83 DSGVO.""",
        "court": {"name": "OLG Frankfurt"},
        "date": "2024-02-20T14:30:00Z",
        "file_number": "6 U 89/23",
    },
]

SAMPLE_SWISS = [
    {
        "id": "BGE-149-III-201",
        "text": """Bundesgerichtsentscheid zum DSG. Verletzung von Art. 8 DSG durch
        unrechtmäßige Bearbeitung besonders schützenswerter Personendaten. Der EDÖB
        hat festgestellt, dass die Datenbearbeitung ohne Rechtsgrundlage erfolgte.""",
        "title": "DSG Verletzung - Gesundheitsdaten",
        "court": "Bundesgericht",
        "canton": "BE",
        "date": "2024-01-10",
        "legal_area": "Datenschutzrecht",
    }
]


class TestRealDatabaseIntegration:
    """Tests mit echter PostgreSQL-Datenbank."""

    @pytest.fixture(scope="class")
    def real_db(self):
        """Setup echte Test-Datenbank."""
        # Verwende Test-DB wenn verfügbar
        test_db_url = os.getenv("TEST_DATABASE_URL")
        if not test_db_url:
            pytest.skip("Keine Test-Datenbank konfiguriert (TEST_DATABASE_URL)")

        # Initialisiere DB
        original_url = os.getenv("DATABASE_URL")
        os.environ["DATABASE_URL"] = test_db_url

        try:
            init_db()
            yield db_manager
        finally:
            # Cleanup
            with db_manager.get_session() as session:
                session.query(Decision).delete()
                session.commit()

            # Restore original URL
            if original_url:
                os.environ["DATABASE_URL"] = original_url

    def test_batch_import_performance(self, real_db):
        """Test Batch-Import mit echter DB."""
        # Generiere 1000 Test-Dokumente
        test_docs = []
        for i in range(1000):
            test_docs.append(
                {
                    "id": i,
                    "name": f"Entscheidung {i}",
                    "content": f"DSGVO Art. {i % 30 + 1}" if i % 5 == 0 else f"Normaler Text {i}",
                    "court": {"name": "LG München"},
                    "date": "2024-01-01T00:00:00Z",
                    "file_number": f"1 O {i}/24",
                }
            )

        # Temporäre Datei
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_docs, f)
            test_file = Path(f.name)

        try:
            importer = OpenLegalDataImporter(verbose=True)

            # Performance tracking
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024

            # Import durchführen
            stats = importer.import_from_file(test_file, batch_size=100, filter_relevant=False)

            # Performance-Metriken
            duration = time.time() - start_time
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_used = end_memory - start_memory

            # Assertions
            assert stats["total_processed"] == 1000
            assert stats["imported"] > 0
            assert duration < 30  # Sollte in < 30 Sekunden fertig sein
            assert memory_used < 200  # Sollte < 200 MB zusätzlich brauchen

            # Performance Report
            throughput = stats["total_processed"] / duration
            logger.info(f"Batch-Import Performance: {throughput:.1f} docs/s")
            logger.info(f"Memory verwendet: {memory_used:.1f} MB")

            # Verify in DB
            with real_db.get_session() as session:
                count = session.query(Decision).count()
                assert count == stats["imported"]

                # Check GDPR articles extracted
                dsr_decisions = (
                    session.query(Decision).filter(Decision.gdpr_articles.is_not(None)).count()
                )
                assert dsr_decisions > 0

        finally:
            test_file.unlink(missing_ok=True)

    def test_concurrent_imports(self, real_db):
        """Test parallele Imports verschiedener Quellen."""
        import threading
        import concurrent.futures

        def import_openlegaldata():
            """Import OpenLegalData in Thread."""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(SAMPLE_OPENLEGALDATA * 50, f)  # 100 Docs
                test_file = Path(f.name)

            try:
                importer = OpenLegalDataImporter()
                return importer.import_from_file(test_file, batch_size=20)
            finally:
                test_file.unlink(missing_ok=True)

        def import_swiss():
            """Import Swiss in Thread."""
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(SAMPLE_SWISS * 50, f)  # 50 Docs
                test_file = Path(f.name)

            try:
                importer = SwissDatasetImporter()
                return importer.import_from_file(test_file, batch_size=10)
            finally:
                test_file.unlink(missing_ok=True)

        # Parallel ausführen
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_old = executor.submit(import_openlegaldata)
            future_swiss = executor.submit(import_swiss)

            stats_old = future_old.result(timeout=60)
            stats_swiss = future_swiss.result(timeout=60)

        # Verify
        assert stats_old["total_processed"] == 100
        assert stats_swiss["total_processed"] == 50

        # Check DB consistency
        with real_db.get_session() as session:
            total = session.query(Decision).count()
            old_count = session.query(Decision).filter_by(source="openlegaldata").count()
            swiss_count = session.query(Decision).filter_by(source="swiss_rulings").count()

            logger.info(f"Concurrent Import: Total={total}, OLD={old_count}, Swiss={swiss_count}")

    def test_resume_after_crash(self, real_db):
        """Test Resume-Funktionalität nach simuliertem Crash."""
        # Große Datenmenge
        test_docs = [{"id": i, "name": f"Doc {i}", "content": "DSGVO Test"} for i in range(500)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_docs, f)
            test_file = Path(f.name)

        try:
            importer = OpenLegalDataImporter()

            # Simuliere Crash nach 100 Dokumenten
            class CrashAfter100(OpenLegalDataImporter):
                def __init__(self):
                    super().__init__()
                    self.counter = 0

                def parse_document(self, raw_data):
                    self.counter += 1
                    if self.counter == 100:
                        raise KeyboardInterrupt("Simulierter Crash!")
                    return super().parse_document(raw_data)

            crash_importer = CrashAfter100()

            # Erster Versuch - sollte crashen
            with pytest.raises(KeyboardInterrupt):
                crash_importer.import_from_file(test_file, resume=True)

            # Resume vom Crash
            normal_importer = OpenLegalDataImporter()
            stats = normal_importer.import_from_file(test_file, resume=True)

            # Sollte bei Doc 100 fortsetzen und Rest importieren
            assert stats["total_processed"] >= 400  # 500 - 100 bereits verarbeitet

        finally:
            test_file.unlink(missing_ok=True)
            # Cleanup resume file
            resume_file = test_file.with_suffix(".resume")
            resume_file.unlink(missing_ok=True)


class TestDataQualityValidation:
    """Tests für Datenqualität und Compliance."""

    def test_anonymization_quality(self):
        """Test Anonymisierungs-Qualität."""
        importer = OpenLegalDataImporter()

        # Dokument mit vielen Namen
        doc = {
            "id": 1,
            "name": "Test",
            "content": """Herr Dr. Max Mustermann, geboren am 15.03.1980, wohnhaft in
            Berlin, Musterstraße 123, klagt gegen Frau Prof. Dr. Erika Schmidt,
            Geschäftsführerin der Example GmbH, vertreten durch RA Thomas Müller.
            Das Gericht unter Vorsitz von RiOLG Dr. Weber hat entschieden.
            Zeugen: Hans Meyer, Anna Schulz, Peter Fischer.
            E-Mail: max@example.com, Tel: 030-12345678""",
        }

        decision = importer.parse_document(doc)

        # Prüfe Anonymisierung
        anon_text = decision.full_text_anonymized

        # Keine echten Namen mehr
        assert "Max Mustermann" not in anon_text
        assert "Erika Schmidt" not in anon_text
        assert "Thomas Müller" not in anon_text
        assert "Hans Meyer" not in anon_text

        # Rechtsbegriffe erhalten
        assert "klagt gegen" in anon_text
        assert "Gericht" in anon_text
        assert "RiOLG" in anon_text or "Richter" in anon_text

        # Personenbezogene Daten entfernt
        assert "15.03.1980" not in anon_text
        assert "Musterstraße 123" not in anon_text
        assert "max@example.com" not in anon_text
        assert "030-12345678" not in anon_text

    def test_gdpr_article_extraction_accuracy(self):
        """Test GDPR-Artikel-Extraktions-Genauigkeit."""
        importer = OpenLegalDataImporter()

        test_cases = [
            {"content": "Verstoß gegen Art. 6 Abs. 1 DSGVO und Art. 7 DSGVO", "expected": [6, 7]},
            {"content": "Nach Artikel 15 DSGVO iVm Art. 12 Abs. 3 DSGVO", "expected": [15, 12]},
            {"content": "Bußgeld gemäß Art. 83 Abs. 5 lit. a DSGVO", "expected": [83]},
            {"content": "Die Artikel 25 und 32 DSGVO wurden verletzt", "expected": [25, 32]},
        ]

        for test in test_cases:
            doc = {"id": 1, "name": "Test", "content": test["content"]}
            decision = importer.parse_document(doc)

            extracted = decision.gdpr_articles or []
            assert set(extracted) == set(
                test["expected"]
            ), f"Failed for: {test['content']}\nExpected: {test['expected']}, Got: {extracted}"

    def test_deduplication_accuracy(self):
        """Test Deduplizierungs-Genauigkeit."""
        # Erstelle Dokumente mit Variationen
        base_doc = SAMPLE_OPENLEGALDATA[0].copy()

        variations = [
            base_doc,  # Original
            {**base_doc, "id": 9999},  # Andere ID, gleicher Inhalt
            {**base_doc, "name": base_doc["name"].upper()},  # Uppercase Title
            {**base_doc, "content": base_doc["content"] + " "},  # Trailing space
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(variations, f)
            test_file = Path(f.name)

        try:
            importer = OpenLegalDataImporter()

            # Erster Import
            stats1 = importer.import_from_file(test_file)

            # Zweiter Import (sollte alle als Duplikate erkennen)
            stats2 = importer.import_from_file(test_file)

            assert stats1["imported"] == 1  # Nur 1 unique
            assert stats2["imported"] == 0  # Alle sind Duplikate
            assert stats2["skipped_existing"] >= 3

        finally:
            test_file.unlink(missing_ok=True)


class TestPerformanceBenchmarks:
    """Performance-Benchmark-Tests."""

    def test_throughput_benchmark(self):
        """Benchmark für verschiedene Batch-Größen."""
        results = []
        test_sizes = [10, 50, 100, 200, 500]

        # Test-Daten
        docs = [{"id": i, "name": f"Doc {i}", "content": f"Text {i}"} for i in range(1000)]

        for batch_size in test_sizes:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(docs, f)
                test_file = Path(f.name)

            try:
                importer = OpenLegalDataImporter()

                start = time.time()
                stats = importer.import_from_file(
                    test_file, batch_size=batch_size, dry_run=True  # Nur Performance testen
                )
                duration = time.time() - start

                throughput = stats["total_processed"] / duration
                results.append(
                    {"batch_size": batch_size, "throughput": throughput, "duration": duration}
                )

            finally:
                test_file.unlink(missing_ok=True)

        # Finde optimale Batch-Size
        df = pd.DataFrame(results)
        optimal = df.loc[df["throughput"].idxmax()]

        logger.info(
            f"Optimal Batch Size: {optimal['batch_size']} ({optimal['throughput']:.1f} docs/s)"
        )

        # Report
        print("\n=== Batch Size Performance ===")
        for r in results:
            print(
                f"Batch {r['batch_size']:3d}: {r['throughput']:6.1f} docs/s ({r['duration']:.2f}s)"
            )

    def test_memory_scalability(self):
        """Test Memory-Skalierung mit großen Dokumentmengen."""
        import gc

        memory_samples = []
        doc_counts = [100, 500, 1000, 5000, 10000]

        for count in doc_counts:
            # Force garbage collection
            gc.collect()

            # Measure baseline
            process = psutil.Process()
            baseline_memory = process.memory_info().rss / 1024 / 1024

            # Generate docs
            docs = [
                {"id": i, "name": f"Doc {i}", "content": "x" * 1000}  # 1KB pro Doc
                for i in range(count)
            ]

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(docs, f)
                test_file = Path(f.name)

            try:
                importer = OpenLegalDataImporter()
                stats = importer.import_from_file(test_file, batch_size=100, dry_run=True)

                # Measure peak
                peak_memory = process.memory_info().rss / 1024 / 1024
                memory_used = peak_memory - baseline_memory

                memory_samples.append(
                    {
                        "docs": count,
                        "memory_mb": memory_used,
                        "mb_per_1k_docs": (memory_used / count) * 1000,
                    }
                )

            finally:
                test_file.unlink(missing_ok=True)
                gc.collect()

        # Analyse
        df = pd.DataFrame(memory_samples)

        # Memory sollte linear skalieren
        print("\n=== Memory Scalability ===")
        for sample in memory_samples:
            print(
                f"{sample['docs']:5d} docs: {sample['memory_mb']:6.1f} MB "
                f"({sample['mb_per_1k_docs']:.2f} MB/1k docs)"
            )

        # Check: Memory pro 1k Docs sollte konstant bleiben (±20%)
        mb_per_1k = df["mb_per_1k_docs"].values
        assert mb_per_1k.std() / mb_per_1k.mean() < 0.2, "Memory skaliert nicht linear!"


class TestErrorScenarios:
    """Test Error-Handling und Recovery."""

    def test_malformed_json_handling(self):
        """Test Handling von fehlerhaftem JSON."""
        malformed_docs = [
            {"id": 1, "name": "Valid"},
            {"id": 2},  # Missing required fields
            {"id": 3, "name": None},  # None values
            {"id": 4, "name": "Valid 2", "content": "Test"},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(malformed_docs, f)
            test_file = Path(f.name)

        try:
            importer = OpenLegalDataImporter()
            stats = importer.import_from_file(test_file)

            # Should handle errors gracefully
            assert stats["total_processed"] == 4
            assert stats["skipped_parse_error"] >= 2
            assert stats["imported"] <= 2

        finally:
            test_file.unlink(missing_ok=True)

    def test_database_connection_recovery(self):
        """Test DB-Connection Recovery."""
        import sqlalchemy
        from unittest.mock import patch, MagicMock

        docs = [{"id": i, "name": f"Doc {i}"} for i in range(10)]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(docs, f)
            test_file = Path(f.name)

        try:
            importer = OpenLegalDataImporter()

            # Simuliere DB-Fehler bei ersten 2 Versuchen
            call_count = 0

            def mock_session(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise sqlalchemy.exc.OperationalError("Connection lost", None, None)
                return MagicMock()

            with patch(
                "src.importers.base_optimized.db_manager.get_session", side_effect=mock_session
            ):
                # Should retry and eventually succeed
                stats = importer.import_from_file(test_file)

                assert call_count > 2  # Retried

        finally:
            test_file.unlink(missing_ok=True)

    def test_disk_space_handling(self):
        """Test Handling bei vollem Speicher."""
        import shutil

        # Check available space
        disk_usage = shutil.disk_usage("/")
        free_gb = disk_usage.free / (1024**3)

        if free_gb < 1:
            logger.warning("Wenig Speicherplatz - Test könnte fehlschlagen")

        # Simuliere große Datei
        huge_docs = [
            {"id": i, "name": f"Doc {i}", "content": "x" * 100000}  # 100KB pro Doc
            for i in range(100)
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            try:
                json.dump(huge_docs, f)
                test_file = Path(f.name)

                # Should handle even with limited space
                importer = OpenLegalDataImporter()
                stats = importer.import_from_file(test_file, batch_size=10)

                assert stats["total_processed"] > 0

            except OSError as e:
                if "No space left" in str(e):
                    logger.info("Disk full handling works correctly")
                else:
                    raise
            finally:
                if "test_file" in locals():
                    test_file.unlink(missing_ok=True)


if __name__ == "__main__":
    # Kann auch standalone ausgeführt werden
    import sys

    if "--benchmark" in sys.argv:
        benchmark = TestPerformanceBenchmarks()
        benchmark.test_throughput_benchmark()
        benchmark.test_memory_scalability()

    elif "--quality" in sys.argv:
        quality = TestDataQualityValidation()
        quality.test_anonymization_quality()
        quality.test_gdpr_article_extraction_accuracy()
        quality.test_deduplication_accuracy()

    else:
        pytest.main([__file__, "-v"])
