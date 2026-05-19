#!/usr/bin/env python3
"""
Unit-Tests für das modularisierte Import-System.

Testet die neuen Module aus der Modularisierung.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import der zu testenden Module
from src.processors.performance_monitor import PerformanceMonitor
from src.processors.resume_manager import ResumeManager
from src.utils.file_handlers import DumpFileHandler
from src.importers.base import BaseImporter
from src.importers.openlegaldata import OpenLegalDataImporter
from src.importers.swiss_datasets import SwissDatasetImporter
from src.converters.csv_converter import CSVConverter
from src.converters.xml_converter import XMLConverter


class TestPerformanceMonitor:
    """Tests für den Performance Monitor."""

    def test_init(self):
        """Test Initialisierung."""
        monitor = PerformanceMonitor()
        assert monitor.performance_stats["total_duration"] == 0
        assert monitor.performance_stats["db_operations"] == 0
        assert len(monitor.performance_stats["processing_times"]) == 0

    def test_tracking(self):
        """Test Performance-Tracking."""
        monitor = PerformanceMonitor()

        # Start tracking
        monitor.start_tracking()
        assert monitor.performance_stats["start_time"] is not None

        # Track processing time
        monitor.track_processing_time(0.5)
        assert len(monitor.performance_stats["processing_times"]) == 1
        assert monitor.performance_stats["processing_times"][0] == 0.5

        # Track component time
        monitor.track_component_time("anonymization", 0.2)
        assert monitor.performance_stats["component_times"]["anonymization"] == 0.2

        # DB operations
        monitor.increment_db_operations(5)
        assert monitor.performance_stats["db_operations"] == 5

    def test_report_generation(self):
        """Test Report-Generierung."""
        monitor = PerformanceMonitor()
        monitor.start_tracking()
        monitor.track_processing_time(0.1)
        monitor.track_processing_time(0.2)
        monitor.track_component_time("extraction", 0.3)
        monitor.increment_db_operations(10)
        monitor.performance_stats["total_duration"] = 5.0

        report = monitor.generate_report()

        assert report["total_duration"] == 5.0
        assert report["db_operations"] == 10
        assert "processing" in report
        assert abs(report["processing"]["avg_ms"] - 150) < 0.01  # (0.1 + 0.2) / 2 * 1000
        assert "throughput" in report
        assert report["throughput"]["docs_per_sec"] == 0.4  # 2 docs / 5 sec


class TestResumeManager:
    """Tests für den Resume Manager."""

    def test_init(self):
        """Test Initialisierung."""
        with tempfile.NamedTemporaryFile(suffix=".json") as f:
            input_file = Path(f.name)
            manager = ResumeManager(input_file)

            assert manager.input_file == input_file
            assert manager.state == {}

    def test_save_and_load_state(self):
        """Test State speichern und laden."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            input_file = Path(f.name)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            resume_file = Path(f.name)

        try:
            manager = ResumeManager(input_file, resume_file)

            # State speichern
            stats = {"imported": 100, "total_processed": 200}
            manager.save_state(position=150, stats=stats, case_id="test-123")

            # Neuer Manager lädt State
            manager2 = ResumeManager(input_file, resume_file)
            loaded_state = manager2.load_state()

            assert loaded_state["position"] == 150
            assert loaded_state["stats"]["imported"] == 100
            assert loaded_state["last_case_id"] == "test-123"

        finally:
            # Cleanup
            input_file.unlink(missing_ok=True)
            resume_file.unlink(missing_ok=True)

    def test_cleanup(self):
        """Test Resume-Datei Cleanup."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            resume_file = Path(f.name)

        manager = ResumeManager(Path("dummy.json"), resume_file)

        # Datei existiert
        assert resume_file.exists()

        # Cleanup
        manager.cleanup()

        # Datei gelöscht
        assert not resume_file.exists()


class TestDumpFileHandler:
    """Tests für den Dump File Handler."""

    def test_detect_format(self):
        """Test Format-Erkennung."""
        assert DumpFileHandler.detect_format(Path("test.json")) == "json"
        assert DumpFileHandler.detect_format(Path("test.jsonl")) == "jsonl"
        assert DumpFileHandler.detect_format(Path("test.json.gz")) == "json.gz"
        assert DumpFileHandler.detect_format(Path("test.jsonl.gz")) == "jsonl.gz"

        with pytest.raises(ValueError):
            DumpFileHandler.detect_format(Path("test.txt"))

    def test_read_json(self):
        """Test JSON-Datei lesen."""
        data = [{"id": 1, "text": "Test 1"}, {"id": 2, "text": "Test 2"}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            handler = DumpFileHandler()
            documents = list(handler.open_file(temp_path))

            assert len(documents) == 2
            assert documents[0]["id"] == 1
            assert documents[1]["text"] == "Test 2"

        finally:
            temp_path.unlink()

    def test_read_jsonl(self):
        """Test JSONL-Datei lesen."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"id": 1, "text": "Test 1"}\n')
            f.write('{"id": 2, "text": "Test 2"}\n')
            temp_path = Path(f.name)

        try:
            handler = DumpFileHandler()
            documents = list(handler.open_file(temp_path))

            assert len(documents) == 2
            assert documents[0]["id"] == 1
            assert documents[1]["text"] == "Test 2"

        finally:
            temp_path.unlink()


class TestOpenLegalDataImporter:
    """Tests für den OpenLegalData Importer."""

    def test_relevance_scoring(self):
        """Test DSGVO-Relevanz-Scoring."""
        importer = OpenLegalDataImporter()

        # Hoch-relevantes Dokument
        doc_high = {"content": "Dies ist ein Fall zur DSGVO Art. 6 und Datenschutz-Grundverordnung"}
        score_high = importer.calculate_relevance_score(doc_high)
        assert score_high >= 10  # Mindestens high_relevance Score

        # Mittel-relevantes Dokument
        doc_medium = {"content": "Verarbeitung personenbezogener Daten und Betroffenenrechte"}
        score_medium = importer.calculate_relevance_score(doc_medium)
        assert score_medium >= 7  # Mindestens medium_relevance Score

        # Nicht-relevantes Dokument
        doc_low = {"content": "Dies ist ein Kaufvertrag ohne Datenschutzbezug"}
        score_low = importer.calculate_relevance_score(doc_low)
        assert score_low < 3  # Unter Mindest-Score

    @patch("src.importers.openlegaldata.get_anonymizer")
    @patch("src.importers.openlegaldata.GDPRArticleExtractor")
    def test_parse_document(self, mock_extractor, mock_anonymizer):
        """Test Dokument-Parsing."""
        # Mocks konfigurieren
        mock_anon = Mock()
        mock_anon.anonymize.return_value = Mock(anonymized_text="[Anonymisiert]")
        mock_anonymizer.return_value = mock_anon

        mock_ext = Mock()
        mock_ext.extract_all.return_value = (["Art. 6 DSGVO"], {})
        mock_extractor.return_value = mock_ext

        importer = OpenLegalDataImporter()

        # Test-Dokument
        raw_doc = {
            "id": "12345",
            "name": "Test-Entscheidung",
            "content": "Original Text",
            "date": "2024-01-15",
            "court": {"name": "BGH"},
            "file_number": "VI ZR 123/23",
            "url": "https://example.com/12345",
        }

        decision = importer.parse_document(raw_doc)

        assert decision is not None
        assert decision.source == "openlegaldata_dump"
        assert decision.source_id == "12345"
        assert decision.title == "Test-Entscheidung"
        assert decision.court == "BGH"
        assert decision.case_number == "VI ZR 123/23"
        assert decision.full_text_anonymized == "[Anonymisiert]"
        assert decision.gdpr_articles == ["Art. 6 DSGVO"]


class TestSwissDatasetImporter:
    """Tests für den Swiss Dataset Importer."""

    def test_relevance_scoring(self):
        """Test Schweizer Datenschutz-Relevanz-Scoring."""
        importer = SwissDatasetImporter()

        # DSG/FADP relevantes Dokument
        doc_dsg = {"text": "Bundesgesetz über den Datenschutz DSG Art. 12"}
        score_dsg = importer.calculate_relevance_score(doc_dsg)
        assert score_dsg >= 10  # FADP high relevance

        # EDÖB relevantes Dokument
        doc_edoeb = {"text": "Der EDÖB hat entschieden bezüglich Personendaten"}
        score_edoeb = importer.calculate_relevance_score(doc_edoeb)
        assert score_edoeb >= 7  # Authority relevance

        # Bundesgericht Bonus
        doc_bg = {"text": "Datenschutz", "court": "Bundesgericht"}
        score_bg = importer.calculate_relevance_score(doc_bg)
        assert score_bg >= 4  # Mindestens privacy_terms + Bundesgericht Bonus

    def test_parse_swiss_date(self):
        """Test Schweizer Datum-Parsing."""
        importer = SwissDatasetImporter()

        # Deutsches Format
        doc_de = {"date": "15.01.2024"}
        date_de = importer._parse_date(doc_de)
        assert date_de.year == 2024
        assert date_de.month == 1
        assert date_de.day == 15

        # ISO Format
        doc_iso = {"date": "2024-01-15"}
        date_iso = importer._parse_date(doc_iso)
        assert date_iso.year == 2024
        assert date_iso.month == 1
        assert date_iso.day == 15

    def test_extract_court(self):
        """Test Gericht-Extraktion."""
        importer = SwissDatasetImporter()

        # Explizites Feld
        doc1 = {"court": "Bundesgericht"}
        assert importer._extract_court(doc1) == "Bundesgericht"

        # Aus Text
        doc2 = {"text": "Das Tribunal fédéral hat entschieden..."}
        assert importer._extract_court(doc2) == "Bundesgericht"

        # Aus Kanton
        doc3 = {"canton": "Zürich"}
        assert importer._extract_court(doc3) == "Kantonsgericht Zürich"


class TestCSVConverter:
    """Tests für den CSV Converter."""

    def test_convert_csv(self):
        """Test CSV zu JSON Konvertierung."""
        csv_content = """id,title,date,score
1,"Test Case",2024-01-15,85
2,"Another Case",2024-01-16,92"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            input_path = Path(f.name)

        output_path = input_path.with_suffix(".json")

        try:
            converter = CSVConverter()
            success = converter.convert_file(input_path, output_path)

            assert success
            assert output_path.exists()

            # Prüfe konvertierte Daten
            with open(output_path, "r") as f:
                data = json.load(f)

            assert len(data) == 2
            assert data[0]["id"] == 1  # Automatisch zu int konvertiert
            assert data[0]["title"] == "Test Case"
            assert data[1]["score"] == 92

        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def test_type_conversion(self):
        """Test automatische Typ-Konvertierung."""
        converter = CSVConverter()

        assert converter._convert_type("123") == 123
        assert converter._convert_type("45.67") == 45.67
        assert converter._convert_type("true") == True
        assert converter._convert_type("false") == False
        assert converter._convert_type('["a", "b"]') == ["a", "b"]
        assert converter._convert_type("text") == "text"


class TestXMLConverter:
    """Tests für den XML Converter."""

    def test_convert_xml(self):
        """Test XML zu JSON Konvertierung."""
        xml_content = """<?xml version="1.0"?>
<decisions>
    <decision id="1">
        <title>Test Case</title>
        <date>2024-01-15</date>
        <court>BGH</court>
    </decision>
    <decision id="2">
        <title>Another Case</title>
        <date>2024-01-16</date>
        <court>BVerfG</court>
    </decision>
</decisions>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            input_path = Path(f.name)

        output_path = input_path.with_suffix(".json")

        try:
            converter = XMLConverter()
            success = converter.convert_file(input_path, output_path)

            assert success
            assert output_path.exists()

            # Prüfe konvertierte Daten
            with open(output_path, "r") as f:
                data = json.load(f)

            assert "decision" in data
            decisions = data["decision"]
            assert len(decisions) == 2
            assert decisions[0]["title"] == "Test Case"
            assert decisions[0]["@attributes"]["id"] == "1"
            assert decisions[1]["court"] == "BVerfG"

        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def test_element_to_dict(self):
        """Test XML-Element zu Dictionary Konvertierung."""
        import xml.etree.ElementTree as ET

        converter = XMLConverter()

        # Einfaches Element
        elem = ET.fromstring('<test attr="value">Content</test>')
        result = converter._element_to_dict(elem)

        assert result["@attributes"]["attr"] == "value"
        assert result["text"] == "Content"

        # Verschachteltes Element
        elem2 = ET.fromstring("<parent><child>Text</child></parent>")
        result2 = converter._element_to_dict(elem2)

        assert result2["child"] == "Text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
