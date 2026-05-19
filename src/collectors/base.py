"""
Abstrakte Basisklasse für alle Datensammler (Collectors).
Implementiert Rate-Limiting, Retry-Logik und Progress-Tracking.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, AsyncIterator
from enum import Enum
import hashlib

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config import settings
from src.database import Decision, CrawlLog, CrawlState
from src.utils.logging import get_logger


class CollectorStatus(Enum):
    """Status für Collector-Operationen."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RateLimiter:
    """Rate-Limiter für HTTP-Anfragen."""

    def __init__(self, rate_limit: float):
        """
        Args:
            rate_limit: Maximale Anfragen pro Sekunde
        """
        self.rate_limit = rate_limit
        self.min_interval = 1.0 / rate_limit if rate_limit > 0 else 0
        self.last_request_time = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wartet falls nötig, um Rate-Limit einzuhalten."""
        async with self._lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time

            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                await asyncio.sleep(sleep_time)

            self.last_request_time = time.time()


class BaseCollector(ABC):
    """
    Abstrakte Basisklasse für alle Datensammler.
    Stellt gemeinsame Funktionalität für Rate-Limiting, Retry und Progress bereit.
    """

    def __init__(
        self,
        source: str,
        session: AsyncSession,
        rate_limit: Optional[float] = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        """
        Initialisiert den Collector.

        Args:
            source: Name der Datenquelle (z.B. "gdprhub")
            session: SQLAlchemy Async Session
            rate_limit: Anfragen pro Sekunde (überschreibt Config)
            max_retries: Maximale Anzahl von Wiederholungen
            timeout: HTTP Timeout in Sekunden
        """
        self.source = source
        self.session = session
        self.logger = get_logger(f"collector.{source}")

        # Rate Limiting
        if rate_limit is None:
            rate_limit = settings.rate_limits.get(source, 1.0)
        self.rate_limiter = RateLimiter(rate_limit)

        # HTTP Client
        self.timeout = timeout
        self.max_retries = max_retries
        self.http_client: Optional[httpx.AsyncClient] = None

        # Status Tracking
        self.status = CollectorStatus.IDLE
        self.current_crawl_log: Optional[CrawlLog] = None
        self.stats = {
            "total_fetched": 0,
            "total_processed": 0,
            "total_errors": 0,
            "start_time": None,
            "errors": [],
        }

    async def __aenter__(self):
        """Context Manager Entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context Manager Exit."""
        await self.cleanup()

    async def initialize(self):
        """Initialisiert den Collector (HTTP Client, etc.)."""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": "datenschutz-rechtsprechung-api/1.0 (Academic Research; +https://github.com/fidpa/datenschutz-rechtsprechung-api)"
            },
            follow_redirects=True,
        )

        self.logger.info(
            "collector_initialized", source=self.source, rate_limit=self.rate_limiter.rate_limit
        )

    async def cleanup(self):
        """Räumt Ressourcen auf."""
        if self.http_client:
            await self.http_client.aclose()

        # Finalisiere Crawl-Log
        if self.current_crawl_log:
            await self._finalize_crawl_log()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(get_logger("retry"), "WARNING"),
    )
    async def fetch_with_retry(self, url: str, **kwargs) -> httpx.Response:
        """
        Führt HTTP-Request mit Retry-Logik aus.

        Args:
            url: Ziel-URL
            **kwargs: Zusätzliche Argumente für httpx.get

        Returns:
            HTTP Response
        """
        await self.rate_limiter.acquire()

        self.logger.debug("fetching_url", url=url)
        response = await self.http_client.get(url, **kwargs)
        response.raise_for_status()

        return response

    async def start_crawl(self, crawl_type: str = "incremental") -> CrawlLog:
        """
        Startet einen neuen Crawl-Vorgang.

        Args:
            crawl_type: "full" oder "incremental"

        Returns:
            CrawlLog Objekt
        """
        self.status = CollectorStatus.RUNNING
        self.stats["start_time"] = datetime.now()

        # Erstelle Crawl-Log Eintrag
        self.current_crawl_log = CrawlLog(
            source=self.source, crawl_type=crawl_type, started_at=datetime.now(), status="running"
        )

        self.session.add(self.current_crawl_log)
        await self.session.commit()

        self.logger.info(
            "crawl_started",
            source=self.source,
            crawl_type=crawl_type,
            crawl_log_id=self.current_crawl_log.id,
        )

        return self.current_crawl_log

    async def _finalize_crawl_log(self):
        """Finalisiert den aktuellen Crawl-Log."""
        if not self.current_crawl_log:
            return

        self.current_crawl_log.finished_at = datetime.now()
        self.current_crawl_log.total_fetched = self.stats["total_fetched"]
        self.current_crawl_log.total_processed = self.stats["total_processed"]
        self.current_crawl_log.total_errors = self.stats["total_errors"]

        if self.status == CollectorStatus.COMPLETED:
            self.current_crawl_log.status = "completed"
        elif self.status == CollectorStatus.FAILED:
            self.current_crawl_log.status = "failed"
            self.current_crawl_log.error_details = {
                "errors": self.stats["errors"][:10]  # Erste 10 Fehler
            }

        await self.session.commit()

        duration = (
            self.current_crawl_log.finished_at - self.current_crawl_log.started_at
        ).total_seconds()

        self.logger.info(
            "crawl_completed",
            source=self.source,
            duration_seconds=duration,
            total_fetched=self.stats["total_fetched"],
            total_processed=self.stats["total_processed"],
            total_errors=self.stats["total_errors"],
        )

    async def save_crawl_state(self, state_data: Dict[str, Any]):
        """
        Speichert den aktuellen Crawl-Zustand für Resume-Funktionalität.

        Args:
            state_data: Zustandsdaten als Dictionary
        """
        # Prüfe ob State bereits existiert
        stmt = select(CrawlState).where(CrawlState.source == self.source)
        result = await self.session.execute(stmt)
        crawl_state = result.scalar_one_or_none()

        if crawl_state:
            # Update existierenden State
            crawl_state.state_data = state_data
            crawl_state.updated_at = datetime.now()
        else:
            # Erstelle neuen State
            crawl_state = CrawlState(source=self.source, state_data=state_data)
            self.session.add(crawl_state)

        await self.session.commit()

        self.logger.debug("crawl_state_saved", state_data=state_data)

    async def load_crawl_state(self) -> Optional[Dict[str, Any]]:
        """
        Lädt den gespeicherten Crawl-Zustand.

        Returns:
            Gespeicherte Zustandsdaten oder None
        """
        stmt = select(CrawlState).where(CrawlState.source == self.source)
        result = await self.session.execute(stmt)
        crawl_state = result.scalar_one_or_none()

        if crawl_state and crawl_state.state_data:
            self.logger.info("crawl_state_loaded", state_data=crawl_state.state_data)
            return crawl_state.state_data

        return None

    async def check_duplicate(self, source_id: str) -> bool:
        """
        Prüft ob eine Entscheidung bereits existiert.

        Args:
            source_id: Eindeutige ID der Quelle

        Returns:
            True wenn bereits vorhanden
        """
        stmt = select(Decision).where(
            Decision.source == self.source, Decision.source_id == source_id
        )
        result = await self.session.execute(stmt)
        exists = result.scalar_one_or_none() is not None

        if exists:
            self.logger.debug("duplicate_found", source_id=source_id)

        return exists

    async def save_decision(self, decision: Decision) -> bool:
        """
        Speichert eine Entscheidung in der Datenbank.

        Args:
            decision: Decision Objekt

        Returns:
            True bei Erfolg
        """
        try:
            # Setze Source wenn nicht gesetzt
            if not decision.source:
                decision.source = self.source

            # Setze Crawl-Zeitstempel
            decision.last_crawled_at = datetime.now()

            # Generiere ID falls nicht vorhanden
            if not decision.source_id:
                # Verwende Hash von Titel und Datum als Fallback
                content = f"{decision.title}_{decision.decision_date}"
                decision.source_id = hashlib.md5(content.encode()).hexdigest()

            self.session.add(decision)
            await self.session.commit()

            self.stats["total_processed"] += 1

            self.logger.debug(
                "decision_saved", source_id=decision.source_id, title=decision.title[:100]
            )

            return True

        except Exception as e:
            self.logger.error("save_decision_failed", error=str(e), source_id=decision.source_id)
            self.stats["total_errors"] += 1
            self.stats["errors"].append(
                {"type": "save_error", "source_id": decision.source_id, "error": str(e)}
            )
            await self.session.rollback()
            return False

    def calculate_progress(self) -> Dict[str, Any]:
        """
        Berechnet Fortschritts-Statistiken.

        Returns:
            Dictionary mit Statistiken
        """
        if not self.stats["start_time"]:
            return {}

        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
        rate = self.stats["total_fetched"] / elapsed if elapsed > 0 else 0

        return {
            "elapsed_seconds": elapsed,
            "fetch_rate": round(rate, 2),
            "success_rate": round(
                self.stats["total_processed"] / max(self.stats["total_fetched"], 1) * 100, 2
            ),
            "total_fetched": self.stats["total_fetched"],
            "total_processed": self.stats["total_processed"],
            "total_errors": self.stats["total_errors"],
        }

    # =============================================================================
    # ABSTRAKTE METHODEN - Müssen von Subklassen implementiert werden
    # =============================================================================

    @abstractmethod
    async def collect(self, full_crawl: bool = False) -> AsyncIterator[Decision]:
        """
        Hauptmethode zum Sammeln von Entscheidungen.

        Args:
            full_crawl: Wenn True, sammle alle Daten (nicht nur neue)

        Yields:
            Decision Objekte
        """

    @abstractmethod
    async def parse_decision(self, raw_data: Any) -> Optional[Decision]:
        """
        Parst Rohdaten zu einer Decision.

        Args:
            raw_data: Rohdaten von der Quelle

        Returns:
            Decision Objekt oder None bei Fehler
        """

    @abstractmethod
    async def validate_access(self) -> bool:
        """
        Prüft ob die Datenquelle erreichbar ist.

        Returns:
            True wenn erreichbar
        """
