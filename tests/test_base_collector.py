"""
Tests für die BaseCollector Klasse.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import httpx

from src.collectors.base import BaseCollector, RateLimiter, CollectorStatus
from src.database import Decision, CrawlLog, CrawlState


# =============================================================================
# RATE LIMITER TESTS
# =============================================================================


@pytest.mark.unit
class TestRateLimiter:
    """Tests für RateLimiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_initialization(self):
        """Test RateLimiter Initialisierung."""
        limiter = RateLimiter(2.0)  # 2 Anfragen pro Sekunde

        assert limiter.rate_limit == 2.0
        assert limiter.min_interval == 0.5
        assert limiter.last_request_time == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_delays_requests(self):
        """Test dass RateLimiter Anfragen verzögert."""
        limiter = RateLimiter(10.0)  # 10 Anfragen pro Sekunde = 0.1s Interval

        start_time = asyncio.get_event_loop().time()

        # Erste Anfrage sollte sofort durchgehen
        await limiter.acquire()
        first_duration = asyncio.get_event_loop().time() - start_time
        assert first_duration < 0.01  # Fast sofort

        # Zweite Anfrage sollte verzögert werden
        await limiter.acquire()
        second_duration = asyncio.get_event_loop().time() - start_time
        assert second_duration >= 0.09  # Mindestens 0.1s Verzögerung

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent_access(self):
        """Test Thread-Safety des RateLimiters."""
        limiter = RateLimiter(5.0)  # 5 Anfragen pro Sekunde

        async def make_request():
            await limiter.acquire()
            return asyncio.get_event_loop().time()

        # Starte 3 parallele Anfragen
        times = await asyncio.gather(make_request(), make_request(), make_request())

        # Prüfe dass Anfragen sequenziell verarbeitet wurden
        for i in range(1, len(times)):
            time_diff = times[i] - times[i - 1]
            assert time_diff >= 0.19  # ~0.2s Interval


# =============================================================================
# BASE COLLECTOR TESTS
# =============================================================================


@pytest.mark.unit
class TestBaseCollector:
    """Tests für BaseCollector Abstrakte Klasse."""

    @pytest.fixture
    def concrete_collector(self, test_session):
        """Erstellt eine konkrete Implementierung von BaseCollector."""

        class TestCollector(BaseCollector):
            async def collect(self, full_crawl: bool = False):
                for i in range(3):
                    yield Decision(source="test", source_id=f"test-{i}", title=f"Test Decision {i}")

            async def parse_decision(self, raw_data):
                return Decision(
                    source="test", source_id=raw_data.get("id"), title=raw_data.get("title")
                )

            async def validate_access(self) -> bool:
                return True

        return TestCollector("test", test_session)

    @pytest.mark.asyncio
    async def test_collector_initialization(self, concrete_collector):
        """Test Collector Initialisierung."""
        assert concrete_collector.source == "test"
        assert concrete_collector.status == CollectorStatus.IDLE
        assert concrete_collector.max_retries == 3
        assert concrete_collector.timeout == 30
        assert concrete_collector.stats["total_fetched"] == 0

    @pytest.mark.asyncio
    async def test_collector_context_manager(self, concrete_collector):
        """Test Collector als Context Manager."""
        async with concrete_collector as collector:
            assert collector.http_client is not None
            assert isinstance(collector.http_client, httpx.AsyncClient)

        # Nach Exit sollte Client geschlossen sein
        assert collector.http_client._closed

    @pytest.mark.asyncio
    async def test_start_crawl(self, concrete_collector, test_session):
        """Test Crawl-Start und Log-Erstellung."""
        await concrete_collector.initialize()

        crawl_log = await concrete_collector.start_crawl("incremental")

        assert crawl_log is not None
        assert crawl_log.source == "test"
        assert crawl_log.crawl_type == "incremental"
        assert crawl_log.status == "running"
        assert concrete_collector.status == CollectorStatus.RUNNING

    @pytest.mark.asyncio
    async def test_save_decision(self, concrete_collector, test_session, sample_decision_data):
        """Test Speichern einer Entscheidung."""
        await concrete_collector.initialize()

        decision = Decision(**sample_decision_data)
        success = await concrete_collector.save_decision(decision)

        assert success is True
        assert concrete_collector.stats["total_processed"] == 1
        assert decision.last_crawled_at is not None

    @pytest.mark.asyncio
    async def test_check_duplicate(self, concrete_collector, test_session, sample_decision):
        """Test Duplikat-Prüfung."""
        # Prüfe existierende Entscheidung
        is_duplicate = await concrete_collector.check_duplicate(sample_decision.source_id)
        assert is_duplicate is True

        # Prüfe nicht-existierende Entscheidung
        is_duplicate = await concrete_collector.check_duplicate("non-existent-id")
        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_save_and_load_crawl_state(self, concrete_collector, test_session):
        """Test Speichern und Laden des Crawl-Zustands."""
        test_state = {"last_page": 5, "last_id": "test-123", "custom_data": {"foo": "bar"}}

        # Speichere Zustand
        await concrete_collector.save_crawl_state(test_state)

        # Lade Zustand
        loaded_state = await concrete_collector.load_crawl_state()

        assert loaded_state == test_state
        assert loaded_state["last_page"] == 5
        assert loaded_state["custom_data"]["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_calculate_progress(self, concrete_collector):
        """Test Fortschritts-Berechnung."""
        # Setze Start-Zeit und Stats
        concrete_collector.stats["start_time"] = datetime.now() - timedelta(seconds=10)
        concrete_collector.stats["total_fetched"] = 20
        concrete_collector.stats["total_processed"] = 18
        concrete_collector.stats["total_errors"] = 2

        progress = concrete_collector.calculate_progress()

        assert progress["total_fetched"] == 20
        assert progress["total_processed"] == 18
        assert progress["total_errors"] == 2
        assert progress["success_rate"] == 90.0
        assert progress["fetch_rate"] > 0

    @pytest.mark.asyncio
    async def test_fetch_with_retry_success(self, concrete_collector):
        """Test erfolgreicher HTTP-Request mit Retry."""
        await concrete_collector.initialize()

        # Mock erfolgreiche Response
        with patch.object(concrete_collector.http_client, "get") as mock_get:
            mock_response = AsyncMock()
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            response = await concrete_collector.fetch_with_retry("http://example.com")

            assert response == mock_response
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_with_retry_failure(self, concrete_collector):
        """Test HTTP-Request mit Retry bei Fehler."""
        await concrete_collector.initialize()
        concrete_collector.max_retries = 2

        # Mock fehlgeschlagene Requests
        with patch.object(concrete_collector.http_client, "get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection failed")

            with pytest.raises(httpx.HTTPError):
                await concrete_collector.fetch_with_retry("http://example.com")

            # Sollte 3 Mal versucht haben (1 + 2 Retries)
            assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_finalize_crawl_log(self, concrete_collector, test_session):
        """Test Finalisierung des Crawl-Logs."""
        await concrete_collector.initialize()
        await concrete_collector.start_crawl()

        # Setze Stats
        concrete_collector.stats["total_fetched"] = 10
        concrete_collector.stats["total_processed"] = 9
        concrete_collector.stats["total_errors"] = 1
        concrete_collector.status = CollectorStatus.COMPLETED

        # Finalisiere
        await concrete_collector._finalize_crawl_log()

        # Prüfe Log
        crawl_log = concrete_collector.current_crawl_log
        assert crawl_log.status == "completed"
        assert crawl_log.total_fetched == 10
        assert crawl_log.total_processed == 9
        assert crawl_log.total_errors == 1
        assert crawl_log.finished_at is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


@pytest.mark.integration
@pytest.mark.requires_db
class TestBaseCollectorIntegration:
    """Integration Tests für BaseCollector mit echter DB."""

    @pytest.mark.asyncio
    async def test_full_crawl_workflow(self, mock_collector_class, test_session):
        """Test kompletter Crawl-Workflow."""
        collector = mock_collector_class("test", test_session)

        async with collector:
            # Starte Crawl
            await collector.start_crawl("full")

            # Sammle Entscheidungen
            decisions_collected = []
            async for decision in collector.collect(full_crawl=True):
                saved = await collector.save_decision(decision)
                if saved:
                    decisions_collected.append(decision)

            # Finalisiere
            collector.status = CollectorStatus.COMPLETED

        # Prüfe Ergebnisse
        assert len(decisions_collected) == 3
        assert collector.stats["total_processed"] == 3

        # Prüfe dass Crawl-Log finalisiert wurde
        assert collector.current_crawl_log.status == "completed"
