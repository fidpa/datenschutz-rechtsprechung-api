#!/usr/bin/env python3
"""
Tests für das zweistufige Filter-System.

Author: Datenschutz-Rechtsprechung API Team
Date: 21.08.2025
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.filters.two_stage_filter import (
    GDPRTwoStageFilter,
    FilterConfig,
    FilterStatus,
    Stage1Result,
    Stage2Result,
)


class TestGDPRTwoStageFilter:
    """Tests für GDPRTwoStageFilter."""

    @pytest.fixture
    def filter_config(self):
        """Standard Filter-Konfiguration."""
        return FilterConfig(
            stage1_min_score=2, stage2_auto_approve_threshold=80.0, stage2_review_threshold=50.0
        )

    @pytest.fixture
    def gdpr_filter(self, filter_config):
        """GDPR Filter Instanz."""
        return GDPRTwoStageFilter(filter_config)

    @pytest.fixture
    def relevant_document(self):
        """Eindeutig DSGVO-relevantes Dokument."""
        return {
            "id": "12345",
            "title": "Urteil zur DSGVO-Verletzung",
            "court": "VG München",
            "case_number": "M 7 K 19.1234",
            "decision_date": datetime(2023, 6, 15),
            "content": """
                <h2>Tenor</h2>
                <p>Die Beklagte wird verurteilt, ein Bußgeld in Höhe von 50.000 EUR 
                wegen Verstoßes gegen Art. 6 DSGVO zu zahlen.</p>
                
                <h2>Gründe</h2>
                <p>Die Beklagte hat personenbezogene Daten ohne Rechtsgrundlage verarbeitet.
                Dies stellt einen Verstoß gegen die Datenschutz-Grundverordnung dar.
                Die Betroffenen wurden nicht über die Datenverarbeitung informiert.</p>
            """,
        }

    @pytest.fixture
    def irrelevant_document(self):
        """Eindeutig irrelevantes Dokument."""
        return {
            "id": "67890",
            "title": "Urteil zum Mietrecht",
            "court": "AG München",
            "case_number": "432 C 12345/23",
            "decision_date": datetime(2023, 7, 20),
            "content": """
                <h2>Tenor</h2>
                <p>Die Klage wird abgewiesen. Die Klägerin trägt die Kosten des Verfahrens.</p>
                
                <h2>Gründe</h2>
                <p>Die Klägerin hat keinen Anspruch auf Mietminderung. 
                Der Mangel war bereits bei Einzug bekannt.</p>
            """,
        }

    @pytest.fixture
    def borderline_document(self):
        """Grenzfall-Dokument mit generischen Rechtsbegriffen."""
        return {
            "id": "11111",
            "title": "Beschluss zum Widerspruchsrecht",
            "court": "OLG Frankfurt",
            "case_number": "6 U 123/23",
            "decision_date": datetime(2023, 8, 10),
            "content": """
                <h2>Tenor</h2>
                <p>Dem Antragsteller steht ein Widerspruchsrecht zu.</p>
                
                <h2>Gründe</h2>
                <p>Der Antragsteller kann der Entscheidung widersprechen.
                Die Informationspflicht wurde erfüllt.</p>
            """,
        }

    def test_stage1_filter_relevant(self, gdpr_filter, relevant_document):
        """Test: Stage 1 erkennt relevantes Dokument."""
        result = gdpr_filter.stage1_filter(relevant_document)

        assert result.passed is True
        assert result.score >= gdpr_filter.config.stage1_min_score
        assert len(result.keywords_found) > 0
        assert any("dsgvo" in kw.lower() for kw in result.keywords_found)

    def test_stage1_filter_irrelevant(self, gdpr_filter, irrelevant_document):
        """Test: Stage 1 filtert irrelevantes Dokument."""
        result = gdpr_filter.stage1_filter(irrelevant_document)

        assert result.passed is False
        assert result.score < gdpr_filter.config.stage1_min_score
        assert len(result.keywords_found) == 0

    def test_stage1_filter_borderline(self, gdpr_filter, borderline_document):
        """Test: Stage 1 bei Grenzfall."""
        result = gdpr_filter.stage1_filter(borderline_document)

        # Sollte durchkommen wegen "Widerspruchsrecht" und "Informationspflicht"
        assert result.passed is True
        assert result.score >= gdpr_filter.config.stage1_min_score

    def test_stage2_filter_high_confidence(self, gdpr_filter, relevant_document):
        """Test: Stage 2 mit hoher Confidence."""
        stage1_result = Stage1Result(
            passed=True,
            score=25,
            keywords_found=["DSGVO", "personenbezogene Daten"],
            processing_time_ms=10.0,
        )

        result = gdpr_filter.stage2_filter(relevant_document, stage1_result)

        assert result.confidence >= 80.0
        assert result.recommendation == FilterStatus.APPROVED
        assert result.rejection_reason is None
        assert result.context_score > 0

    def test_stage2_filter_low_confidence(self, gdpr_filter, borderline_document):
        """Test: Stage 2 mit niedriger Confidence."""
        stage1_result = Stage1Result(
            passed=True, score=4, keywords_found=["Widerspruchsrecht"], processing_time_ms=10.0
        )

        result = gdpr_filter.stage2_filter(borderline_document, stage1_result)

        # Sollte niedrige Confidence haben wegen fehlendem Datenschutz-Kontext
        assert result.confidence < 50.0
        assert result.recommendation == FilterStatus.REJECTED
        assert result.rejection_reason is not None

    def test_stage2_filter_review_required(self, gdpr_filter):
        """Test: Stage 2 empfiehlt manuelle Review."""
        document = {
            "id": "22222",
            "title": "Verfahren zur Datenverarbeitung",
            "court": "VG Berlin",
            "content": """
                <h2>Tenor</h2>
                <p>Die Klage wird teilweise stattgegeben.</p>
                
                <h2>Gründe</h2>
                <p>Die Verarbeitung der Daten erfolgte teilweise rechtswidrig.
                Eine Einwilligung lag nicht vor.</p>
            """,
        }

        stage1_result = Stage1Result(
            passed=True,
            score=10,
            keywords_found=["Datenverarbeitung", "Einwilligung"],
            processing_time_ms=10.0,
        )

        result = gdpr_filter.stage2_filter(document, stage1_result)

        # Sollte zwischen 50-80% liegen
        assert 50.0 <= result.confidence < 80.0
        assert result.recommendation == FilterStatus.REVIEW_REQUIRED

    def test_process_document_full_pipeline(self, gdpr_filter, relevant_document):
        """Test: Vollständige Pipeline mit relevantem Dokument."""
        status, metadata = gdpr_filter.process_document(relevant_document)

        assert status == FilterStatus.APPROVED
        assert "stage1_score" in metadata
        assert "stage2_confidence" in metadata
        assert metadata["stage2_confidence"] >= 80.0
        assert "total_time_ms" in metadata

    def test_process_document_rejected_stage1(self, gdpr_filter, irrelevant_document):
        """Test: Dokument wird in Stage 1 abgelehnt."""
        status, metadata = gdpr_filter.process_document(irrelevant_document)

        assert status == FilterStatus.REJECTED
        assert "rejection_reason" in metadata
        assert "Stage 1" in metadata["rejection_reason"]
        # Stage 2 Metriken sollten nicht vorhanden sein
        assert "stage2_confidence" not in metadata or metadata["stage2_confidence"] is None

    def test_context_analysis(self, gdpr_filter):
        """Test: Kontext-Analyse funktioniert korrekt."""
        content = """
            Die Beklagte hat personenbezogene Daten ohne Einwilligung verarbeitet.
            Dies verstößt gegen Art. 6 DSGVO. Die Betroffenen haben ein Recht auf
            Löschung ihrer Daten gemäß Art. 17 DSGVO.
        """

        score, patterns = gdpr_filter._analyze_context(content, ["personenbezogene Daten", "DSGVO"])

        assert score > 0
        assert len(patterns) > 0
        assert any("dsgvo_artikel" in p for p in patterns)

    def test_structure_analysis(self, gdpr_filter, relevant_document):
        """Test: Struktur-Analyse erkennt Rechtsdokument-Struktur."""
        score, patterns = gdpr_filter._analyze_structure(relevant_document)

        assert score > 0
        assert len(patterns) > 0
        assert any("Tenor" in p for p in patterns)

    def test_metadata_analysis(self, gdpr_filter):
        """Test: Metadaten-Analyse funktioniert."""
        document = {
            "court": "Landesbeauftragte für Datenschutz Bayern",
            "case_number": "DSB-2023-001",
            "decision_date": datetime(2023, 10, 1),
            "title": "Bußgeldverfahren wegen DSGVO-Verstoß",
        }

        score = gdpr_filter._analyze_metadata(document)

        assert score > 50  # Datenschutzbehörde sollte hohen Score haben

    def test_statistics_tracking(self, gdpr_filter, relevant_document, irrelevant_document):
        """Test: Statistiken werden korrekt getrackt."""
        # Verarbeite mehrere Dokumente
        gdpr_filter.process_document(relevant_document)
        gdpr_filter.process_document(irrelevant_document)

        stats = gdpr_filter.get_statistics()

        assert stats["stage1_processed"] == 2
        assert stats["stage1_passed"] == 1
        assert stats["stage2_processed"] == 1
        assert stats["stage2_approved"] == 1
        assert "stage1_pass_rate" in stats
        assert "overall_approval_rate" in stats

    def test_reset_statistics(self, gdpr_filter, relevant_document):
        """Test: Statistiken können zurückgesetzt werden."""
        gdpr_filter.process_document(relevant_document)
        assert gdpr_filter.stats["stage1_processed"] > 0

        gdpr_filter.reset_statistics()

        assert gdpr_filter.stats["stage1_processed"] == 0
        assert gdpr_filter.stats["stage2_approved"] == 0

    def test_negative_patterns(self, gdpr_filter):
        """Test: Negative Patterns reduzieren Confidence."""
        # Dokument mit generischem "Widerspruchsrecht" ohne Daten-Kontext
        content = """
            Der Antragsteller hat ein Widerspruchsrecht gegen den Bescheid.
            Die Frist beträgt einen Monat.
        """

        score_with_negative, _ = gdpr_filter._analyze_context(content, ["Widerspruchsrecht"])

        # Score sollte reduziert sein wegen negativem Pattern
        assert score_with_negative < 50.0

    def test_performance_requirements(self, gdpr_filter, relevant_document):
        """Test: Performance-Anforderungen werden erfüllt."""
        import time

        # Stage 1 sollte schnell sein
        start = time.time()
        stage1_result = gdpr_filter.stage1_filter(relevant_document)
        stage1_time = (time.time() - start) * 1000

        assert stage1_time < gdpr_filter.config.stage1_timeout_ms

        # Stage 2 darf länger dauern
        start = time.time()
        stage2_result = gdpr_filter.stage2_filter(relevant_document, stage1_result)
        stage2_time = (time.time() - start) * 1000

        assert stage2_time < gdpr_filter.config.stage2_timeout_ms


class TestFilterConfig:
    """Tests für FilterConfig."""

    def test_default_config(self):
        """Test: Default-Konfiguration hat sinnvolle Werte."""
        config = FilterConfig()

        assert config.stage1_min_score == 2
        assert config.stage2_auto_approve_threshold == 80.0
        assert config.stage2_review_threshold == 50.0
        assert config.enable_context_analysis is True

    def test_custom_config(self):
        """Test: Custom-Konfiguration funktioniert."""
        config = FilterConfig(
            stage1_min_score=5, stage2_auto_approve_threshold=90.0, context_window_size=100
        )

        assert config.stage1_min_score == 5
        assert config.stage2_auto_approve_threshold == 90.0
        assert config.context_window_size == 100
