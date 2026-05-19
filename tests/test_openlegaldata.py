"""
Unit-Tests für OpenLegalData Collector.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.collectors.openlegaldata import OpenLegalDataCollector
from src.database import Decision, DocumentType


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy Session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def collector(mock_session):
    """OpenLegalData Collector Instanz."""
    return OpenLegalDataCollector(session=mock_session, max_pages=2, page_size=10)


@pytest.fixture
def sample_api_response():
    """Beispiel API-Response von OpenLegalData."""
    return {
        "count": 100,
        "next": "https://de.openlegaldata.io/api/cases/?page=2",
        "previous": None,
        "results": [
            {
                "id": 12345,
                "slug": "lg-berlin-2023-10-15-1-o-123-23",
                "court": {
                    "id": 1,
                    "name": "Landgericht Berlin",
                    "slug": "lg-berlin",
                    "city": "Berlin",
                    "state": "Berlin",
                    "jurisdiction": "Ordentliche Gerichtsbarkeit",
                    "level_of_appeal": "Landgericht",
                },
                "file_number": "1 O 123/23",
                "date": "2023-10-15",
                "created_date": "2023-10-20T10:00:00Z",
                "updated_date": "2023-10-20T10:00:00Z",
                "type": "Urteil",
                "ecli": "ECLI:DE:LGBERLIN:2023:1015.1O123.23.00",
                "content": """Die Beklagte wird verurteilt, der Klägerin Auskunft über die 
                             verarbeiteten personenbezogenen Daten gemäß Art. 15 DSGVO zu erteilen.
                             Der Verstoß gegen Art. 6 DSGVO und Art. 7 DSGVO wurde festgestellt.""",
            },
            {
                "id": 12346,
                "slug": "olg-muenchen-2023-09-20-29-u-1234-23",
                "court": {
                    "id": 2,
                    "name": "Oberlandesgericht München",
                    "slug": "olg-muenchen",
                    "city": "München",
                    "state": "Bayern",
                    "jurisdiction": "Ordentliche Gerichtsbarkeit",
                    "level_of_appeal": "Oberlandesgericht",
                },
                "file_number": "29 U 1234/23",
                "date": "2023-09-20",
                "created_date": "2023-09-25T14:30:00Z",
                "updated_date": "2023-09-25T14:30:00Z",
                "type": "Beschluss",
                "ecli": "ECLI:DE:OLGMUEN:2023:0920.29U1234.23.00",
                "content": """Die Berufung gegen das Urteil des Landgerichts München I wird zurückgewiesen.
                             Die Verarbeitung personenbezogener Daten ohne Einwilligung verstößt gegen die DSGVO.""",
            },
        ],
    }


@pytest.mark.asyncio
async def test_validate_access(collector):
    """Test: API-Zugang validieren."""
    with patch.object(collector, "fetch_with_retry") as mock_fetch:
        # Mock erfolgreiche Response
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [], "count": 0}
        mock_fetch.return_value = mock_response

        # Initialisiere Collector
        await collector.initialize()

        # Teste Validierung
        is_valid = await collector.validate_access()

        assert is_valid is True
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_validate_access_failure(collector):
    """Test: API-Zugang Fehler."""
    with patch.object(collector, "fetch_with_retry") as mock_fetch:
        # Mock Fehler
        mock_fetch.side_effect = Exception("Connection error")

        await collector.initialize()
        is_valid = await collector.validate_access()

        assert is_valid is False


@pytest.mark.asyncio
async def test_parse_decision(collector, sample_api_response):
    """Test: Parse Decision aus API-Response."""
    await collector.initialize()

    # Parse erste Entscheidung
    case_data = sample_api_response["results"][0]
    decision = await collector.parse_decision(case_data)

    assert decision is not None
    assert decision.source == "openlegaldata"
    assert decision.source_id == "12345"
    assert decision.title == "Landgericht Berlin Urteil (1 O 123/23) vom 2023-10-15"
    assert decision.case_number == "1 O 123/23"
    assert decision.court == "Landgericht Berlin"
    assert decision.document_type == DocumentType.COURT_DECISION.value

    # Prüfe Metadaten
    assert decision.extra_metadata["ecli"] == "ECLI:DE:LGBERLIN:2023:1015.1O123.23.00"
    assert decision.extra_metadata["type"] == "Urteil"
    assert decision.extra_metadata["court_jurisdiction"] == "Ordentliche Gerichtsbarkeit"


@pytest.mark.asyncio
async def test_gdpr_extraction(collector, sample_api_response):
    """Test: DSGVO-Artikel Extraktion."""
    await collector.initialize()

    case_data = sample_api_response["results"][0]
    decision = await collector.parse_decision(case_data)

    # Prüfe DSGVO-Artikel
    assert decision.gdpr_articles is not None
    assert any("15" in art for art in decision.gdpr_articles)  # Art. 15 DSGVO
    assert any("6" in art for art in decision.gdpr_articles)  # Art. 6 DSGVO
    assert any("7" in art for art in decision.gdpr_articles)  # Art. 7 DSGVO


@pytest.mark.asyncio
async def test_is_gdpr_relevant(collector):
    """Test: DSGVO-Relevanz-Prüfung."""
    await collector.initialize()

    # Entscheidung mit DSGVO-Artikeln
    decision1 = Decision(
        source="openlegaldata",
        source_id="1",
        title="Test",
        gdpr_articles=["Art. 15 DSGVO", "Art. 6 DSGVO"],
        full_text_original="Text mit DSGVO",
    )
    assert collector._is_gdpr_relevant(decision1) is True

    # Entscheidung mit DSGVO-Keywords
    decision2 = Decision(
        source="openlegaldata",
        source_id="2",
        title="Test",
        gdpr_articles=[],
        full_text_original="Text über Datenschutz-Grundverordnung und Art. 6 DSGVO",
    )
    assert collector._is_gdpr_relevant(decision2) is True

    # Nicht-relevante Entscheidung
    decision3 = Decision(
        source="openlegaldata",
        source_id="3",
        title="Test",
        gdpr_articles=[],
        full_text_original="Text ohne Bezug zum Datenschutz",
    )
    assert collector._is_gdpr_relevant(decision3) is False


@pytest.mark.asyncio
async def test_generate_title(collector, sample_api_response):
    """Test: Titel-Generierung."""
    case_data = sample_api_response["results"][0]
    title = collector._generate_title(case_data)

    assert "Landgericht Berlin" in title
    assert "Urteil" in title
    assert "1 O 123/23" in title
    assert "2023-10-15" in title


@pytest.mark.asyncio
async def test_parse_date(collector):
    """Test: Datum-Parsing."""
    # Verschiedene Formate
    date1 = collector._parse_date("2023-10-15")
    assert date1.year == 2023
    assert date1.month == 10
    assert date1.day == 15

    date2 = collector._parse_date("2023-10-15T10:30:00Z")
    assert date2.year == 2023
    assert date2.hour == 10
    assert date2.minute == 30

    date3 = collector._parse_date("2023-10-15T10:30:00.123456Z")
    assert date3.year == 2023

    # Ungültiges Format
    date4 = collector._parse_date("15.10.2023")
    assert date4 is None

    # None
    date5 = collector._parse_date(None)
    assert date5 is None


@pytest.mark.asyncio
async def test_extract_keywords(collector):
    """Test: Keyword-Extraktion."""
    decision = Decision(
        source="openlegaldata",
        source_id="1",
        title="Bundesgerichtshof Urteil vom 15.10.2023",
        court="BGH",
        gdpr_articles=["Art. 15 DSGVO", "Art. 6 DSGVO", "Art. 7 DSGVO"],
        full_text_original="",
    )

    keywords = collector._extract_keywords(decision)

    assert "Bundesgerichtshof" in keywords
    assert "DSGVO" in keywords
    assert "Art. 15 DSGVO" in keywords
    assert len(keywords) <= 10  # Max 10 Keywords


@pytest.mark.asyncio
async def test_collect_with_pagination(collector, sample_api_response, mock_session):
    """Test: Collect mit Pagination."""
    with patch.object(collector, "fetch_with_retry") as mock_fetch:
        # Mock API Responses
        response1 = MagicMock()
        response1.json.return_value = sample_api_response

        response2 = MagicMock()
        response2.json.return_value = {
            "count": 100,
            "next": None,
            "previous": "https://de.openlegaldata.io/api/cases/?page=1",
            "results": [],
        }

        mock_fetch.side_effect = [response1, response2]

        # Mock check_duplicate
        with patch.object(collector, "check_duplicate", return_value=False):
            # Mock save_decision
            with patch.object(collector, "save_decision", return_value=True):
                await collector.initialize()

                # Sammle Entscheidungen
                decisions = []
                async for decision in collector.collect(full_crawl=True):
                    decisions.append(decision)

                # Prüfe Ergebnisse
                assert len(decisions) == 2  # 2 aus sample_api_response
                assert mock_fetch.call_count == 2  # 2 Seiten


@pytest.mark.asyncio
async def test_crawl_search_term(collector, sample_api_response):
    """Test: Crawl für spezifischen Suchbegriff."""
    with patch.object(collector, "fetch_with_retry") as mock_fetch:
        # Mock Response
        mock_response = MagicMock()
        mock_response.json.return_value = sample_api_response
        mock_fetch.return_value = mock_response

        # Mock check_duplicate und save_decision
        with patch.object(collector, "check_duplicate", return_value=False):
            with patch.object(collector, "save_decision", return_value=True):
                await collector.initialize()

                # Crawle für "DSGVO"
                decisions = []
                async for decision in collector._crawl_search_term("DSGVO", start_page=1):
                    decisions.append(decision)
                    if len(decisions) >= 2:
                        break

                # Prüfe API-Call
                mock_fetch.assert_called()
                call_args = mock_fetch.call_args
                assert call_args[1]["params"]["q"] == "DSGVO"
                assert call_args[1]["params"]["page"] == 1


@pytest.mark.asyncio
async def test_stats_tracking(collector, sample_api_response):
    """Test: Statistik-Tracking."""
    with patch.object(collector, "fetch_with_retry") as mock_fetch:
        mock_response = MagicMock()
        mock_response.json.return_value = sample_api_response
        mock_fetch.return_value = mock_response

        with patch.object(collector, "check_duplicate", return_value=False):
            with patch.object(collector, "save_decision", return_value=True):
                await collector.initialize()

                # Sammle einige Entscheidungen
                count = 0
                async for decision in collector._crawl_search_term("DSGVO"):
                    count += 1
                    if count >= 2:
                        break

                # Prüfe Statistiken
                assert collector.stats["total_fetched"] > 0
                assert collector.stats["total_processed"] > 0
                assert collector.total_cases_found > 0
                assert collector.gdpr_relevant_cases >= 0

                # Berechne Progress
                progress = collector.calculate_progress()
                assert "total_fetched" in progress
                assert "total_processed" in progress
                assert "success_rate" in progress
