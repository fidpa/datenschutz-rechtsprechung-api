"""
Dependencies für die FastAPI Endpoints.
Stellt wiederverwendbare Abhängigkeiten für Routen bereit.
"""

from typing import Optional, AsyncGenerator
from fastapi import Query, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
import time

from src.database import db_manager
from src.api.schemas import PaginationParams, DecisionFilter
from src.config import settings


# =============================================================================
# DATABASE DEPENDENCIES
# =============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency für Datenbank-Session.
    Gibt eine async Session zurück und schließt sie automatisch.
    """
    if not db_manager.async_session_maker:
        await db_manager.initialize()

    async with db_manager.async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


# =============================================================================
# PAGINATION DEPENDENCIES
# =============================================================================


def get_pagination_params(
    page: int = Query(default=1, ge=1, description="Seitennummer"),
    page_size: int = Query(default=20, ge=1, le=100, description="Elemente pro Seite"),
    sort_by: Optional[str] = Query(default="created_at", description="Sortierfeld"),
    sort_order: str = Query(
        default="desc", pattern="^(asc|desc)$", description="Sortierreihenfolge"
    ),
) -> PaginationParams:
    """
    Dependency für Pagination-Parameter.
    Validiert und gibt strukturierte Pagination-Params zurück.
    """
    # Validiere sort_by gegen erlaubte Felder
    allowed_sort_fields = {
        "created_at",
        "updated_at",
        "decision_date",
        "publication_date",
        "title",
        "court",
        "source",
    }

    if sort_by and sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiges Sortierfeld: {sort_by}. Erlaubt sind: {', '.join(allowed_sort_fields)}",
        )

    return PaginationParams(page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order)


# =============================================================================
# FILTER DEPENDENCIES
# =============================================================================


def get_decision_filter(
    source: Optional[str] = Query(None, description="Filter nach Datenquelle"),
    court: Optional[str] = Query(None, description="Filter nach Gericht"),
    gdpr_article: Optional[str] = Query(None, description="Filter nach DSGVO-Artikel"),
    date_from: Optional[str] = Query(None, description="Entscheidungen ab Datum (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Entscheidungen bis Datum (YYYY-MM-DD)"),
    has_anonymization: Optional[bool] = Query(None, description="Nur anonymisierte Dokumente"),
    has_pdf: Optional[bool] = Query(None, description="Nur Dokumente mit PDF-Extraktion"),
    keyword: Optional[str] = Query(None, description="Keyword-Filter"),
) -> DecisionFilter:
    """
    Dependency für Decision-Filter.
    Parst Query-Parameter und gibt strukturierte Filter zurück.
    """
    from datetime import datetime

    # Parse Datumsangaben
    parsed_date_from = None
    parsed_date_to = None

    if date_from:
        try:
            parsed_date_from = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges Datumsformat für date_from: {date_from}. Erwartet: YYYY-MM-DD",
            )

    if date_to:
        try:
            parsed_date_to = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges Datumsformat für date_to: {date_to}. Erwartet: YYYY-MM-DD",
            )

    # Validiere Datumsbereich
    if parsed_date_from and parsed_date_to and parsed_date_from > parsed_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from darf nicht nach date_to liegen",
        )

    # Validiere source gegen Enum
    if source:
        valid_sources = ["gdprhub", "openlegaldata", "ris_austria", "ris_germany", "manual"]
        if source.lower() not in valid_sources:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültige Datenquelle: {source}. Erlaubt sind: {', '.join(valid_sources)}",
            )

    return DecisionFilter(
        source=source.lower() if source else None,
        court=court,
        gdpr_article=gdpr_article,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
        has_anonymization=has_anonymization,
        has_pdf=has_pdf,
        keyword=keyword,
    )


# =============================================================================
# SEARCH DEPENDENCIES
# =============================================================================


def validate_search_query(
    q: str = Query(..., min_length=3, description="Suchbegriff (min. 3 Zeichen)")
) -> str:
    """
    Dependency für Suchanfragen.
    Validiert und bereinigt den Suchbegriff.
    """
    # Bereinige Suchbegriff
    q = q.strip()

    # Entferne gefährliche Zeichen für SQL
    dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]
    for char in dangerous_chars:
        q = q.replace(char, "")

    # Prüfe Mindestlänge nach Bereinigung
    if len(q) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Suchbegriff muss mindestens 3 Zeichen haben (nach Bereinigung)",
        )

    # Prüfe Maximallänge
    if len(q) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Suchbegriff darf maximal 200 Zeichen haben",
        )

    return q


# =============================================================================
# AUTH DEPENDENCIES (für zukünftige Erweiterung)
# =============================================================================


async def get_current_user_optional():
    """
    Optional: Dependency für authentifizierten Benutzer.
    Aktuell gibt None zurück (keine Auth implementiert).
    """
    return None


# =============================================================================
# RATE LIMITING (für zukünftige Erweiterung)
# =============================================================================


class RateLimiter:
    """
    Rate Limiter für API-Endpoints mit Redis-Backend.
    Verwendet Sliding Window Algorithmus.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.redis_client = None
        self.window_seconds = 60  # 1 Minute

    async def _get_redis(self) -> redis.Redis:
        """Lazy-Initialize Redis Client."""
        if not self.redis_client:
            self.redis_client = await redis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
        return self.redis_client

    async def __call__(self, request: Request) -> bool:
        """
        Prüft Rate Limit für die aktuelle Anfrage.

        Args:
            request: FastAPI Request Objekt

        Returns:
            True wenn Request erlaubt ist

        Raises:
            HTTPException: Wenn Rate Limit überschritten
        """
        try:
            redis_client = await self._get_redis()

            # Verwende Client IP als Identifier
            client_ip = request.client.host if request.client else "unknown"
            key = f"rate_limit:{client_ip}"

            # Aktuelle Zeit in Sekunden
            now = time.time()
            window_start = now - self.window_seconds

            # Entferne alte Einträge außerhalb des Fensters
            await redis_client.zremrangebyscore(key, 0, window_start)

            # Zähle Requests im aktuellen Fenster
            current_requests = await redis_client.zcard(key)

            if current_requests >= self.requests_per_minute:
                # Rate Limit überschritten
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    headers={"Retry-After": "60"},
                )

            # Füge neuen Request hinzu
            await redis_client.zadd(key, {str(now): now})

            # Setze TTL auf das Fenster
            await redis_client.expire(key, self.window_seconds)

            return True

        except redis.RedisError:
            # Bei Redis-Fehler: Rate Limiting deaktivieren statt Request blockieren
            # Dies stellt sicher, dass die API auch ohne Redis funktioniert
            return True


# Standard Rate Limiter
rate_limiter = RateLimiter(requests_per_minute=60)
