"""
API Routes für Volltext-Suche.
Nutzt PostgreSQL Full-Text Search mit deutschem Stemmer.
"""

from typing import List, Dict, Any
from datetime import datetime
import time
import re
import structlog

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision
from src.api import schemas
from src.api.deps import get_db, validate_search_query
from src.config import settings

logger = structlog.get_logger()

router = APIRouter()


# =============================================================================
# GET /search - Volltext-Suche
# =============================================================================


def clean_query_for_tsquery(query: str) -> str:
    """
    Bereinigt Query-String für PostgreSQL to_tsquery.
    Entfernt problematische Sonderzeichen und normalisiert Whitespace.
    Konvertiert zu tsquery-Format mit & für AND-Verknüpfung.
    """
    # Entferne oder ersetze problematische Zeichen
    # Behalte Buchstaben, Zahlen und wichtige Operatoren (&, |, !)
    cleaned = re.sub(r"[^\w\s&|!äöüÄÖÜß-]", " ", query)

    # Normalisiere mehrfache Leerzeichen
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Trimme
    cleaned = cleaned.strip()

    # Wenn kein expliziter Operator vorhanden ist, verbinde Wörter mit & (AND)
    if cleaned and "&" not in cleaned and "|" not in cleaned and "!" not in cleaned:
        # Splitte nach Leerzeichen und verbinde mit &
        words = cleaned.split()
        if len(words) > 1:
            cleaned = " & ".join(words)

    # Fallback auf einfache Suche wenn String leer wird
    if not cleaned:
        cleaned = "datenschutz"  # Sinnvoller Default statt '*'

    return cleaned


@router.get(
    "/",
    response_model=schemas.SearchResponse,
    summary="Volltext-Suche",
    description="""
    Durchsucht alle anonymisierten Gerichtsentscheidungen.
    
    **Features:**
    - PostgreSQL Full-Text Search mit deutschem Stemmer
    - Relevanz-basierte Sortierung
    - Snippet-Generierung mit Kontext
    - Facetten für Filter
    - Optionale Filter nach Quelle, Gericht, DSGVO-Artikeln
    """,
)
async def search_decisions(
    q: str = Depends(validate_search_query),
    sources: List[str] = Query(default=None, description="Filter nach Datenquellen"),
    courts: List[str] = Query(default=None, description="Filter nach Gerichten"),
    gdpr_articles: List[str] = Query(default=None, description="Filter nach DSGVO-Artikeln"),
    date_from: datetime = Query(default=None, description="Entscheidungen ab Datum"),
    date_to: datetime = Query(default=None, description="Entscheidungen bis Datum"),
    limit: int = Query(default=20, ge=1, le=100, description="Max. Anzahl Ergebnisse"),
    offset: int = Query(default=0, ge=0, description="Offset für Pagination"),
    db: AsyncSession = Depends(get_db),
) -> schemas.SearchResponse:
    """Volltext-Suche in Entscheidungen."""

    start_time = time.time()

    # Bereinige Query-String für tsquery
    cleaned_query = clean_query_for_tsquery(q)

    # Erstelle ts_query für deutsche Volltextsuche
    ts_query = func.to_tsquery(settings.postgres_text_search_config, cleaned_query)

    # Basis-Query mit Relevanz-Score
    search_query = select(
        Decision,
        func.ts_rank(Decision.search_vector, ts_query).label("rank"),
        func.ts_headline(
            settings.postgres_text_search_config,
            Decision.full_text_anonymized,
            ts_query,
            "MaxWords=50, MinWords=25, ShortWord=3, HighlightAll=false, StartSel=<mark>, StopSel=</mark>",
        ).label("snippet"),
    ).where(Decision.search_vector.op("@@")(ts_query))

    # Filter anwenden
    conditions = []

    if sources:
        conditions.append(Decision.source.in_(sources))

    if courts:
        court_conditions = [Decision.court.ilike(f"%{court}%") for court in courts]
        conditions.append(or_(*court_conditions))

    if gdpr_articles:
        # Normalisiere Artikel-Format
        normalized_articles = []
        for article in gdpr_articles:
            if not article.startswith("Art"):
                normalized_articles.append(f"Art. {article}")
            else:
                normalized_articles.append(article)

        article_conditions = [Decision.gdpr_articles.contains([art]) for art in normalized_articles]
        conditions.append(or_(*article_conditions))

    if date_from:
        conditions.append(Decision.decision_date >= date_from)

    if date_to:
        conditions.append(Decision.decision_date <= date_to)

    if conditions:
        search_query = search_query.where(and_(*conditions))

    # Nach Relevanz sortieren
    search_query = search_query.order_by(text("rank DESC"))

    # Gesamtanzahl ermitteln (ohne Limit)
    count_query = (
        select(func.count()).select_from(Decision).where(Decision.search_vector.op("@@")(ts_query))
    )
    if conditions:
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination anwenden
    search_query = search_query.offset(offset).limit(limit)

    # Suche ausführen
    result = await db.execute(search_query)
    rows = result.all()

    # Ergebnisse formatieren
    search_results = []
    for row in rows:
        decision = row[0]
        rank = row[1]
        snippet = row[2] or "..."

        # Bereinige Snippet von HTML falls nötig
        if snippet and not snippet.strip():
            snippet = decision.title[:200] + "..."

        search_results.append(
            schemas.SearchResult(
                id=decision.id,
                title=decision.title,
                court=decision.court,
                decision_date=decision.decision_date,
                snippet=snippet,
                relevance=min(rank, 1.0) if rank else 0.0,  # Normalisiere auf 0-1
                gdpr_articles=decision.gdpr_articles or [],
                source=decision.source,
                source_url=decision.source_url,
            )
        )

    # Facetten generieren (für Filter-UI) - mit bereinigtem Query-String
    facets = await generate_facets(db, cleaned_query, conditions)

    # Response-Zeit berechnen
    took_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "search_performed",
        query=q,
        total=total,
        returned=len(search_results),
        took_ms=took_ms,
        filters={
            "sources": sources,
            "courts": courts,
            "gdpr_articles": gdpr_articles,
            "date_from": date_from,
            "date_to": date_to,
        },
    )

    return schemas.SearchResponse(
        query=q, results=search_results, total=total, took_ms=took_ms, facets=facets
    )


# =============================================================================
# GET /search/suggest - Auto-Complete / Suggestions
# =============================================================================


@router.get(
    "/suggest",
    summary="Such-Vorschläge",
    description="Gibt Vorschläge für Suchbegriffe basierend auf häufigen Keywords zurück.",
)
async def search_suggestions(
    q: str = Query(..., min_length=2, description="Suchbegriff-Anfang"),
    limit: int = Query(default=10, le=50),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Such-Vorschläge generieren."""

    # Suche in Keywords
    keyword_query = (
        select(func.unnest(Decision.keywords).label("keyword"))
        .distinct()
        .where(func.unnest(Decision.keywords).ilike(f"{q}%"))
        .limit(limit)
    )

    result = await db.execute(keyword_query)
    suggestions = [row[0] for row in result.all()]

    # Zusätzlich: Häufige DSGVO-Artikel vorschlagen
    if "art" in q.lower() or "artikel" in q.lower():
        article_query = (
            select(
                func.unnest(Decision.gdpr_articles).label("article"), func.count().label("count")
            )
            .group_by(text("article"))
            .order_by(text("count DESC"))
            .limit(5)
        )

        article_result = await db.execute(article_query)
        article_suggestions = [row[0] for row in article_result.all()]
        suggestions.extend(article_suggestions)

    return {"query": q, "suggestions": list(set(suggestions))[:limit]}


# =============================================================================
# GET /search/advanced - Erweiterte Suche
# =============================================================================


@router.post(
    "/advanced",
    response_model=schemas.SearchResponse,
    summary="Erweiterte Suche",
    description="""
    Erweiterte Suche mit komplexen Filtern und Bool'schen Operatoren.
    Unterstützt AND, OR, NOT Operatoren in der Suchanfrage.
    """,
)
async def advanced_search(
    search_request: schemas.SearchRequest, db: AsyncSession = Depends(get_db)
) -> schemas.SearchResponse:
    """Erweiterte Suche mit komplexen Filtern."""

    start_time = time.time()

    # Parse erweiterte Suchanfrage (unterstützt &, |, ! Operatoren)
    # Konvertiere zu PostgreSQL tsquery Format
    query_text = search_request.query
    query_text = query_text.replace(" AND ", " & ")
    query_text = query_text.replace(" OR ", " | ")
    query_text = query_text.replace(" NOT ", " ! ")

    # Bereinige Query-String für tsquery
    cleaned_query = clean_query_for_tsquery(query_text)

    ts_query = func.to_tsquery(settings.postgres_text_search_config, cleaned_query)

    # Basis-Query
    search_query = select(
        Decision,
        func.ts_rank_cd(Decision.search_vector, ts_query, 32).label(  # Cover density ranking
            "rank"
        ),
        func.ts_headline(
            settings.postgres_text_search_config,
            func.coalesce(Decision.full_text_anonymized, Decision.title),
            ts_query,
            "MaxWords=100, MinWords=50, ShortWord=3, HighlightAll=false, StartSel=<mark>, StopSel=</mark>",
        ).label("snippet"),
    ).where(Decision.search_vector.op("@@")(ts_query))

    # Alle Filter aus SearchRequest anwenden
    conditions = []

    if search_request.sources:
        conditions.append(Decision.source.in_([s.value for s in search_request.sources]))

    if search_request.courts:
        court_conditions = [Decision.court.ilike(f"%{court}%") for court in search_request.courts]
        conditions.append(or_(*court_conditions))

    if search_request.gdpr_articles:
        conditions.append(
            or_(*[Decision.gdpr_articles.contains([art]) for art in search_request.gdpr_articles])
        )

    if search_request.date_from:
        conditions.append(Decision.decision_date >= search_request.date_from)

    if search_request.date_to:
        conditions.append(Decision.decision_date <= search_request.date_to)

    if conditions:
        search_query = search_query.where(and_(*conditions))

    # Sortierung und Pagination
    search_query = (
        search_query.order_by(text("rank DESC"))
        .offset(search_request.offset)
        .limit(search_request.limit)
    )

    # Gesamtanzahl
    count_query = (
        select(func.count()).select_from(Decision).where(Decision.search_vector.op("@@")(ts_query))
    )
    if conditions:
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Suche ausführen
    result = await db.execute(search_query)
    rows = result.all()

    # Ergebnisse formatieren
    search_results = []
    for row in rows:
        decision = row[0]
        rank = row[1]
        snippet = row[2] or decision.title[:200] + "..."

        search_results.append(
            schemas.SearchResult(
                id=decision.id,
                title=decision.title,
                court=decision.court,
                decision_date=decision.decision_date,
                snippet=snippet,
                relevance=min(rank, 1.0) if rank else 0.0,
                gdpr_articles=decision.gdpr_articles or [],
                source=decision.source,
                source_url=decision.source_url,
            )
        )

    took_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "advanced_search_performed",
        query=search_request.query,
        total=total,
        returned=len(search_results),
        took_ms=took_ms,
    )

    return schemas.SearchResponse(
        query=search_request.query,
        results=search_results,
        total=total,
        took_ms=took_ms,
        facets=None,
    )


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================


async def generate_facets(
    db: AsyncSession, query_string: str, conditions: List[Any]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Generiert Facetten für Filter-UI.
    Zeigt verfügbare Filter-Optionen mit Anzahl.
    """
    facets = {}

    # Erstelle ts_query für Facetten
    ts_query = func.to_tsquery(settings.postgres_text_search_config, query_string)

    # Base conditions für Facetten (ohne den jeweiligen Filter selbst)
    base_conditions = [Decision.search_vector.op("@@")(ts_query)]

    # Quellen-Facette
    source_query = (
        select(Decision.source, func.count().label("count"))
        .where(and_(*base_conditions) if base_conditions else True)
        .group_by(Decision.source)
        .order_by(text("count DESC"))
        .limit(10)
    )

    source_result = await db.execute(source_query)
    facets["sources"] = [{"value": row[0], "count": row[1]} for row in source_result.all()]

    # Gerichts-Facette (Top 10)
    court_query = (
        select(Decision.court, func.count().label("count"))
        .where(and_(*base_conditions, Decision.court.isnot(None)))
        .group_by(Decision.court)
        .order_by(text("count DESC"))
        .limit(10)
    )

    court_result = await db.execute(court_query)
    facets["courts"] = [
        {"value": row[0], "count": row[1]}
        for row in court_result.all()
        if row[0]  # Filter None-Werte
    ]

    # DSGVO-Artikel Facette (Top 10)
    gdpr_query = text(
        """
        SELECT article, COUNT(*) as count
        FROM (
            SELECT unnest(gdpr_articles) as article
            FROM decisions
            WHERE search_vector @@ to_tsquery(:config, :query)
        ) as articles
        WHERE article IS NOT NULL
        GROUP BY article
        ORDER BY count DESC
        LIMIT 10
    """
    )

    gdpr_result = await db.execute(
        gdpr_query, {"config": settings.postgres_text_search_config, "query": query_string}
    )
    facets["gdpr_articles"] = [{"value": row[0], "count": row[1]} for row in gdpr_result.all()]

    return facets
