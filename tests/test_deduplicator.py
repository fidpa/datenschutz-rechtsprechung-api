"""
Unit-Tests für den Decision Deduplicator.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from src.processors.deduplicator import DecisionDeduplicator
from src.database import Decision


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy Session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def deduplicator(mock_session):
    """Deduplicator Instanz."""
    return DecisionDeduplicator(session=mock_session)


@pytest.fixture
def sample_decision():
    """Beispiel-Entscheidung."""
    return Decision(
        id=uuid.uuid4(),
        source="gdprhub",
        source_id="gdpr-123",
        title="LG Berlin - Urteil vom 15.10.2023 - 1 O 123/23",
        case_number="1 O 123/23",
        court="Landgericht Berlin",
        decision_date=datetime(2023, 10, 15),
        full_text_original="Dies ist der vollständige Text der Entscheidung über DSGVO Art. 15.",
        gdpr_articles=["15", "6"],
        keywords=["DSGVO", "Auskunft"],
    )


@pytest.fixture
def duplicate_decision():
    """Duplikat-Entscheidung mit kleinen Abweichungen."""
    return Decision(
        id=uuid.uuid4(),
        source="openlegaldata",
        source_id="old-456",
        title="Landgericht Berlin - Urteil v. 15.10.2023 (1 O 123/23)",
        case_number="1 O 123/23",
        court="Landgericht Berlin",
        decision_date=datetime(2023, 10, 15),
        full_text_original="Dies ist der vollständige Text der Entscheidung über DSGVO Art. 15.",
        gdpr_articles=["15"],
        keywords=["Datenschutz"],
    )


@pytest.mark.asyncio
async def test_find_exact_matches(deduplicator, sample_decision, duplicate_decision, mock_session):
    """Test: Finde exakte Duplikate."""
    # Mock Query-Result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [duplicate_decision]
    mock_session.execute.return_value = mock_result

    # Finde Duplikate
    matches = await deduplicator._find_exact_matches(sample_decision)

    assert len(matches) == 1
    assert matches[0].case_number == sample_decision.case_number
    assert matches[0].court == sample_decision.court

    # Prüfe Statistiken
    assert deduplicator.stats["exact_matches"] == 0  # Wird in find_duplicates gezählt


@pytest.mark.asyncio
async def test_find_exact_matches_no_case_number(deduplicator):
    """Test: Keine exakten Matches ohne case_number."""
    decision = Decision(
        id=uuid.uuid4(), source="test", source_id="1", title="Test", court="Test Court"
    )

    matches = await deduplicator._find_exact_matches(decision)
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_find_fuzzy_matches(deduplicator, sample_decision, mock_session):
    """Test: Finde Fuzzy-Matches basierend auf Titel."""
    # Mock ähnliche Entscheidung
    similar_decision = Decision(
        id=uuid.uuid4(),
        source="openlegaldata",
        source_id="789",
        title="LG Berlin - Urteil vom 15.10.2023 - 1 O 123/23",  # Sehr ähnlich
        case_number="1 O 124/23",  # Andere Nummer
        court="Landgericht Berlin",
    )

    # Mock Query-Result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [similar_decision]
    mock_session.execute.return_value = mock_result

    # Finde Fuzzy-Matches
    matches = await deduplicator._find_fuzzy_matches(sample_decision)

    assert len(matches) == 1


@pytest.mark.asyncio
async def test_calculate_similarity(deduplicator):
    """Test: Berechne Text-Ähnlichkeit."""
    text1 = "Dies ist ein Test-Text"
    text2 = "Dies ist ein Test-Text"

    similarity = deduplicator._calculate_similarity(text1, text2)
    assert similarity == 1.0  # Identisch

    text3 = "Dies ist ein anderer Text"
    similarity2 = deduplicator._calculate_similarity(text1, text3)
    assert 0.5 < similarity2 < 1.0  # Teilweise ähnlich

    text4 = "Komplett unterschiedlich"
    similarity3 = deduplicator._calculate_similarity(text1, text4)
    assert similarity3 < 0.5  # Unähnlich


@pytest.mark.asyncio
async def test_normalize_text(deduplicator):
    """Test: Text-Normalisierung."""
    text = "Dies IST ein   Test-Text!!! Mit Sonderzeichen: §123"
    normalized = deduplicator._normalize_text(text)

    assert normalized == "dies ist ein test text mit sonderzeichen 123"
    assert "!" not in normalized
    assert "§" not in normalized


@pytest.mark.asyncio
async def test_extract_court_type(deduplicator):
    """Test: Extrahiere Gerichtstyp."""
    assert deduplicator._extract_court_type("Bundesgerichtshof") == "BGH"
    assert deduplicator._extract_court_type("OLG München") == "OLG"
    assert deduplicator._extract_court_type("Landgericht Berlin") == "LG"
    assert deduplicator._extract_court_type("Amtsgericht Hamburg") == "AG"
    assert deduplicator._extract_court_type("Unbekanntes Gericht") is None


@pytest.mark.asyncio
async def test_generate_content_hash(deduplicator):
    """Test: Content-Hash Generierung."""
    text1 = "Dies ist ein Test-Text mit DSGVO Bezug."
    text2 = "Dies ist ein Test-Text mit DSGVO Bezug."
    text3 = "Ein anderer Text."

    hash1 = deduplicator._generate_content_hash(text1)
    hash2 = deduplicator._generate_content_hash(text2)
    hash3 = deduplicator._generate_content_hash(text3)

    assert hash1 == hash2  # Identische Texte
    assert hash1 != hash3  # Unterschiedliche Texte
    assert len(hash1) == 32  # MD5 Hash Länge


@pytest.mark.asyncio
async def test_calculate_completeness(deduplicator):
    """Test: Berechne Vollständigkeits-Score."""
    # Vollständige Entscheidung
    complete = Decision(
        id=uuid.uuid4(),
        source="test",
        source_id="1",
        title="Test Title",
        case_number="123/23",
        court="Test Court",
        decision_date=datetime.now(),
        full_text_original="A" * 5000,  # Langer Text
        full_text_anonymized="B" * 5000,
        leitsatz="Leitsatz",
        tenor="Tenor",
        tatbestand="Tatbestand",
        entscheidungsgruende="Gründe",
        gdpr_articles=["15", "6"],
        keywords=["Test"],
    )

    score1 = deduplicator._calculate_completeness(complete)

    # Minimale Entscheidung
    minimal = Decision(id=uuid.uuid4(), source="test", source_id="2", title="Test")

    score2 = deduplicator._calculate_completeness(minimal)

    assert score1 > score2
    assert score1 > 20  # Hoher Score für vollständige Entscheidung
    assert score2 < 5  # Niedriger Score für minimale Entscheidung


@pytest.mark.asyncio
async def test_merge_duplicates(deduplicator, sample_decision, duplicate_decision, mock_session):
    """Test: Merge Duplikate."""
    duplicates = [sample_decision, duplicate_decision]

    # Merge mit Prioritäts-Strategie
    master = await deduplicator.merge_duplicates(duplicates, keep_strategy="priority")

    assert master == sample_decision  # gdprhub hat höhere Priorität
    assert "15" in master.gdpr_articles
    assert "6" in master.gdpr_articles  # Union der GDPR-Artikel

    # Prüfe Metadaten
    assert "merged_sources" in master.extra_metadata
    assert len(master.extra_metadata["merged_sources"]) == 1

    # Prüfe Statistiken
    assert deduplicator.stats["merged"] == 1


@pytest.mark.asyncio
async def test_merge_duplicates_completeness(deduplicator, mock_session):
    """Test: Merge mit Vollständigkeits-Strategie."""
    # Weniger vollständige Entscheidung
    decision1 = Decision(
        id=uuid.uuid4(), source="openlegaldata", source_id="1", title="Test", case_number="123/23"
    )

    # Vollständigere Entscheidung
    decision2 = Decision(
        id=uuid.uuid4(),
        source="gdprhub",
        source_id="2",
        title="Test Decision",
        case_number="123/23",
        court="Test Court",
        full_text_original="Full text here",
        leitsatz="Leitsatz",
        tenor="Tenor",
    )

    duplicates = [decision1, decision2]
    master = await deduplicator.merge_duplicates(duplicates, keep_strategy="complete")

    assert master == decision2  # Vollständigere Entscheidung


@pytest.mark.asyncio
async def test_find_duplicates_integration(deduplicator, sample_decision, mock_session):
    """Test: Integrierter Duplikat-Check."""
    # Mock verschiedene Match-Typen
    exact_match = Decision(id=uuid.uuid4(), source="test", source_id="exact")
    fuzzy_match = Decision(id=uuid.uuid4(), source="test", source_id="fuzzy")

    with patch.object(deduplicator, "_find_exact_matches", return_value=[exact_match]):
        with patch.object(deduplicator, "_find_fuzzy_matches", return_value=[fuzzy_match]):
            with patch.object(deduplicator, "_find_content_matches", return_value=[]):
                duplicates = await deduplicator.find_duplicates(
                    sample_decision, check_content=False
                )

                assert len(duplicates) == 2
                assert exact_match in duplicates
                assert fuzzy_match in duplicates

                # Prüfe Statistiken
                assert deduplicator.stats["total_checked"] == 1
                assert deduplicator.stats["exact_matches"] == 1
                assert deduplicator.stats["fuzzy_matches"] == 1


@pytest.mark.asyncio
async def test_get_statistics(deduplicator, mock_session):
    """Test: Statistik-Abfrage."""
    # Mock DB-Statistiken
    mock_result = MagicMock()
    mock_result.first.return_value = MagicMock(total_decisions=1000, unique_case_numbers=950)
    mock_session.execute.return_value = mock_result

    stats = await deduplicator.get_statistics()

    assert "session_stats" in stats
    assert "database_stats" in stats
    assert stats["database_stats"]["total_decisions"] == 1000
    assert stats["database_stats"]["unique_case_numbers"] == 950
    assert stats["database_stats"]["potential_duplicates"] == 50


@pytest.mark.asyncio
async def test_reset_stats(deduplicator):
    """Test: Statistiken zurücksetzen."""
    # Setze einige Statistiken
    deduplicator.stats["total_checked"] = 10
    deduplicator.stats["exact_matches"] = 5

    # Reset
    deduplicator.reset_stats()

    assert deduplicator.stats["total_checked"] == 0
    assert deduplicator.stats["exact_matches"] == 0
    assert deduplicator.stats["fuzzy_matches"] == 0
    assert deduplicator.stats["content_matches"] == 0
    assert deduplicator.stats["merged"] == 0
