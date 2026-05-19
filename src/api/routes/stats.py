"""
API Routes für Statistiken und Analytics.
Stellt aggregierte Daten und Metriken bereit.
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta
import structlog

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision, CrawlLog
from src.api import schemas
from src.api.deps import get_db

logger = structlog.get_logger()

router = APIRouter()


# =============================================================================
# GET /stats - Hauptstatistiken
# =============================================================================


@router.get(
    "/",
    response_model=schemas.StatsResponse,
    summary="Gesamtstatistiken",
    description="""
    Gibt umfassende Statistiken über alle Gerichtsentscheidungen zurück.
    
    **Enthält:**
    - Gesamtanzahl Entscheidungen
    - Verteilung nach Quellen, Gerichten, Jahren
    - Top DSGVO-Artikel und Keywords
    - Neueste Entscheidungen
    """,
)
async def get_statistics(db: AsyncSession = Depends(get_db)) -> schemas.StatsResponse:
    """Gesamtstatistiken abrufen."""

    # Gesamtanzahl Entscheidungen
    total_query = select(func.count(Decision.id))
    total_result = await db.execute(total_query)
    total_decisions = total_result.scalar() or 0

    # Anzahl anonymisierter Dokumente
    anon_query = select(func.count(Decision.id)).where(Decision.anonymization_applied == True)
    anon_result = await db.execute(anon_query)
    total_anonymized = anon_result.scalar() or 0

    # Dokumente mit DSGVO-Referenz
    gdpr_query = select(func.count(Decision.id)).where(func.cardinality(Decision.gdpr_articles) > 0)
    gdpr_result = await db.execute(gdpr_query)
    total_with_gdpr = gdpr_result.scalar() or 0

    # Verteilung nach Quellen
    source_query = (
        select(Decision.source, func.count(Decision.id).label("count"))
        .group_by(Decision.source)
        .order_by(text("count DESC"))
    )
    source_result = await db.execute(source_query)
    by_source = {row[0]: row[1] for row in source_result.all()}

    # Verteilung nach Gerichten (Top 20)
    court_query = (
        select(Decision.court, func.count(Decision.id).label("count"))
        .where(Decision.court.isnot(None))
        .group_by(Decision.court)
        .order_by(text("count DESC"))
        .limit(20)
    )
    court_result = await db.execute(court_query)
    by_court = {row[0]: row[1] for row in court_result.all() if row[0]}

    # Verteilung nach Jahren
    year_query = (
        select(
            func.extract("year", Decision.decision_date).label("year"),
            func.count(Decision.id).label("count"),
        )
        .where(Decision.decision_date.isnot(None))
        .group_by(text("year"))
        .order_by(text("year DESC"))
        .limit(10)
    )
    year_result = await db.execute(year_query)
    by_year = {int(row[0]): row[1] for row in year_result.all() if row[0]}

    # Top DSGVO-Artikel (mit Raw SQL für Array-Aggregation)
    dsr_articles_query = text(
        """
        SELECT article, COUNT(*) as count
        FROM (
            SELECT unnest(gdpr_articles) as article
            FROM decisions
            WHERE gdpr_articles IS NOT NULL AND cardinality(gdpr_articles) > 0
        ) as articles
        GROUP BY article
        ORDER BY count DESC
        LIMIT 15
    """
    )
    dsr_articles_result = await db.execute(dsr_articles_query)
    top_gdpr_articles = [{"article": row[0], "count": row[1]} for row in dsr_articles_result.all()]

    # Top Keywords
    keywords_query = text(
        """
        SELECT keyword, COUNT(*) as count
        FROM (
            SELECT unnest(keywords) as keyword
            FROM decisions
            WHERE keywords IS NOT NULL AND cardinality(keywords) > 0
        ) as kw
        GROUP BY keyword
        ORDER BY count DESC
        LIMIT 20
    """
    )
    keywords_result = await db.execute(keywords_query)
    top_keywords = [{"keyword": row[0], "count": row[1]} for row in keywords_result.all()]

    # Neueste Entscheidungen
    recent_query = (
        select(
            Decision.id,
            Decision.title,
            Decision.court,
            Decision.decision_date,
            Decision.source,
            Decision.created_at,
        )
        .order_by(Decision.created_at.desc())
        .limit(10)
    )
    recent_result = await db.execute(recent_query)
    recent_decisions = [
        {
            "id": str(row[0]),
            "title": row[1],
            "court": row[2],
            "decision_date": row[3].isoformat() if row[3] else None,
            "source": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
        for row in recent_result.all()
    ]

    logger.info("statistics_generated", total_decisions=total_decisions)

    return schemas.StatsResponse(
        total_decisions=total_decisions,
        total_anonymized=total_anonymized,
        total_with_gdpr=total_with_gdpr,
        by_source=by_source,
        by_court=by_court,
        by_year=by_year,
        top_gdpr_articles=top_gdpr_articles,
        top_keywords=top_keywords,
        recent_decisions=recent_decisions,
        last_updated=datetime.now(),
    )


# =============================================================================
# GET /stats/timeline - Zeitliche Entwicklung
# =============================================================================


@router.get(
    "/timeline",
    summary="Zeitliche Entwicklung",
    description="Zeigt die zeitliche Entwicklung der Entscheidungen.",
)
async def get_timeline(
    period: str = Query(default="month", pattern="^(day|week|month|year)$"),
    days: int = Query(default=365, ge=7, le=3650),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Zeitliche Entwicklung der Entscheidungen."""

    # Berechne Startdatum
    start_date = datetime.now() - timedelta(days=days)

    # SQL für verschiedene Perioden
    if period == "day":
        date_format = "YYYY-MM-DD"
    elif period == "week":
        date_format = "YYYY-IW"  # ISO Week
    elif period == "month":
        date_format = "YYYY-MM"
    else:  # year
        date_format = "YYYY"

    timeline_query = text(
        f"""
        SELECT 
            TO_CHAR(decision_date, :format) as period,
            COUNT(*) as count,
            COUNT(DISTINCT court) as unique_courts,
            COUNT(DISTINCT source) as unique_sources
        FROM decisions
        WHERE decision_date >= :start_date
            AND decision_date IS NOT NULL
        GROUP BY period
        ORDER BY period ASC
    """
    )

    result = await db.execute(timeline_query, {"format": date_format, "start_date": start_date})

    timeline_data = [
        {"period": row[0], "count": row[1], "unique_courts": row[2], "unique_sources": row[3]}
        for row in result.all()
    ]

    return {"period_type": period, "start_date": start_date.isoformat(), "data": timeline_data}


# =============================================================================
# GET /stats/crawl-status - Crawler Status
# =============================================================================


@router.get(
    "/crawl-status",
    response_model=List[schemas.CrawlStatusResponse],
    summary="Crawler-Status",
    description="Zeigt den Status aller Crawler und deren letzte Aktivitäten.",
)
async def get_crawl_status(db: AsyncSession = Depends(get_db)) -> List[schemas.CrawlStatusResponse]:
    """Status aller Crawler abrufen."""

    # Hole letzte Crawl-Logs für jede Quelle
    sources = ["gdprhub", "openlegaldata", "ris_austria"]
    crawl_statuses = []

    for source in sources:
        # Letzter Crawl
        last_crawl_query = (
            select(CrawlLog)
            .where(CrawlLog.source == source)
            .order_by(CrawlLog.started_at.desc())
            .limit(1)
        )
        last_crawl_result = await db.execute(last_crawl_query)
        last_crawl = last_crawl_result.scalar_one_or_none()

        if last_crawl:
            # Berechne next_run basierend auf Standard-Intervall (täglich)
            # Später kann dies aus Celery Beat Schedule gelesen werden
            last_run_time = last_crawl.finished_at or last_crawl.started_at
            if last_run_time:
                # Standard: Täglicher Crawl um 02:00 Uhr
                next_run = last_run_time.replace(hour=2, minute=0, second=0, microsecond=0)
                # Wenn bereits vorbei, nächster Tag
                if next_run <= datetime.utcnow():
                    next_run += timedelta(days=1)
            else:
                next_run = None

            status = schemas.CrawlStatusResponse(
                source=source,
                status=last_crawl.status,
                last_run=last_run_time,
                next_run=next_run,
                total_fetched=last_crawl.total_fetched,
                total_processed=last_crawl.total_processed,
                total_errors=last_crawl.total_errors,
            )
        else:
            # Noch nie gecrawlt
            status = schemas.CrawlStatusResponse(
                source=source,
                status="never_run",
                last_run=None,
                next_run=None,
                total_fetched=0,
                total_processed=0,
                total_errors=0,
            )

        crawl_statuses.append(status)

    return crawl_statuses


# =============================================================================
# GET /stats/gdpr-articles - DSGVO-Artikel Statistiken
# =============================================================================


@router.get(
    "/gdpr-articles",
    summary="DSGVO-Artikel Statistiken",
    description="Detaillierte Statistiken zu DSGVO-Artikeln.",
)
async def get_gdpr_article_stats(
    limit: int = Query(default=50, le=200), db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Detaillierte DSGVO-Artikel Statistiken."""

    # Artikel-Häufigkeit mit Details
    article_stats_query = text(
        """
        WITH article_counts AS (
            SELECT 
                unnest(gdpr_articles) as article,
                id,
                source,
                court,
                decision_date
            FROM decisions
            WHERE gdpr_articles IS NOT NULL 
                AND cardinality(gdpr_articles) > 0
        )
        SELECT 
            article,
            COUNT(DISTINCT id) as decision_count,
            COUNT(DISTINCT court) as court_count,
            COUNT(DISTINCT source) as source_count,
            MIN(decision_date) as first_decision,
            MAX(decision_date) as last_decision,
            array_agg(DISTINCT court ORDER BY court) FILTER (WHERE court IS NOT NULL) as courts
        FROM article_counts
        GROUP BY article
        ORDER BY decision_count DESC
        LIMIT :limit
    """
    )

    result = await db.execute(article_stats_query, {"limit": limit})

    article_stats = []
    for row in result.all():
        courts_list = row[6] if row[6] else []
        # Limitiere Anzahl der Gerichte in der Anzeige
        if len(courts_list) > 5:
            courts_list = courts_list[:5] + [f"... und {len(courts_list)-5} weitere"]

        article_stats.append(
            {
                "article": row[0],
                "decision_count": row[1],
                "court_count": row[2],
                "source_count": row[3],
                "first_decision": row[4].isoformat() if row[4] else None,
                "last_decision": row[5].isoformat() if row[5] else None,
                "top_courts": courts_list,
            }
        )

    # Artikel-Kombinationen (welche Artikel werden oft zusammen zitiert)
    combination_query = text(
        """
        WITH article_pairs AS (
            SELECT 
                a1.article as article1,
                a2.article as article2,
                COUNT(*) as count
            FROM 
                (SELECT id, unnest(gdpr_articles) as article FROM decisions) a1
            JOIN 
                (SELECT id, unnest(gdpr_articles) as article FROM decisions) a2
            ON a1.id = a2.id AND a1.article < a2.article
            GROUP BY a1.article, a2.article
            ORDER BY count DESC
            LIMIT 20
        )
        SELECT * FROM article_pairs
    """
    )

    combination_result = await db.execute(combination_query)
    article_combinations = [
        {"article1": row[0], "article2": row[1], "count": row[2]}
        for row in combination_result.all()
    ]

    return {
        "total_unique_articles": len(article_stats),
        "article_stats": article_stats,
        "frequent_combinations": article_combinations,
    }


# =============================================================================
# GET /stats/courts - Gerichts-Statistiken
# =============================================================================


@router.get(
    "/courts",
    summary="Gerichts-Statistiken",
    description="Detaillierte Statistiken zu Gerichten und Behörden.",
)
async def get_court_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Detaillierte Gerichts-Statistiken."""

    # Gerichts-Hierarchie und Statistiken
    court_stats_query = text(
        """
        SELECT 
            court,
            COUNT(*) as decision_count,
            COUNT(DISTINCT source) as source_count,
            MIN(decision_date) as first_decision,
            MAX(decision_date) as last_decision,
            AVG(CASE WHEN anonymization_applied THEN 1 ELSE 0 END) as anonymization_rate,
            array_agg(DISTINCT unnest(gdpr_articles) ORDER BY unnest) 
                FILTER (WHERE gdpr_articles IS NOT NULL) as top_articles
        FROM decisions
        WHERE court IS NOT NULL
        GROUP BY court
        ORDER BY decision_count DESC
        LIMIT 50
    """
    )

    result = await db.execute(court_stats_query)

    court_stats = []
    for row in result.all():
        # Top 5 DSGVO-Artikel für dieses Gericht
        articles = row[6][:5] if row[6] else []

        court_stats.append(
            {
                "court": row[0],
                "decision_count": row[1],
                "source_count": row[2],
                "first_decision": row[3].isoformat() if row[3] else None,
                "last_decision": row[4].isoformat() if row[4] else None,
                "anonymization_rate": float(row[5]) if row[5] else 0.0,
                "top_gdpr_articles": articles,
            }
        )

    # Gerichtstypen identifizieren
    court_types = {
        "BGH": [],
        "OLG": [],
        "LG": [],
        "AG": [],
        "VG": [],
        "OVG": [],
        "BVerwG": [],
        "Datenschutzbehörde": [],
        "Sonstige": [],
    }

    for stat in court_stats:
        court_name = stat["court"]
        categorized = False

        for court_type in court_types.keys():
            if court_type in court_name:
                court_types[court_type].append(stat)
                categorized = True
                break

        if not categorized:
            if "Datenschutz" in court_name or "DSB" in court_name:
                court_types["Datenschutzbehörde"].append(stat)
            else:
                court_types["Sonstige"].append(stat)

    # Zusammenfassung nach Gerichtstyp
    type_summary = {}
    for court_type, courts in court_types.items():
        if courts:
            type_summary[court_type] = {
                "count": len(courts),
                "total_decisions": sum(c["decision_count"] for c in courts),
                "courts": [c["court"] for c in courts[:5]],  # Top 5 Gerichte pro Typ
            }

    return {
        "total_courts": len(court_stats),
        "court_stats": court_stats[:20],  # Top 20 für Response
        "by_type": type_summary,
    }


# =============================================================================
# GET /stats/summary - Kompakte Zusammenfassung
# =============================================================================


@router.get(
    "/summary",
    summary="Kompakte Zusammenfassung",
    description="Gibt eine kompakte Übersicht der wichtigsten Metriken zurück.",
)
async def get_summary_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Kompakte Statistik-Zusammenfassung."""

    # Eine optimierte Query für alle Basis-Metriken
    summary_query = text(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT source) as sources,
            COUNT(DISTINCT court) as courts,
            COUNT(CASE WHEN anonymization_applied THEN 1 END) as anonymized,
            COUNT(CASE WHEN cardinality(gdpr_articles) > 0 THEN 1 END) as with_gdpr,
            COUNT(CASE WHEN decision_date >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as last_week,
            COUNT(CASE WHEN decision_date >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as last_month,
            MAX(created_at) as last_update
        FROM decisions
    """
    )

    result = await db.execute(summary_query)
    row = result.one()

    return {
        "overview": {
            "total_decisions": row[0],
            "unique_sources": row[1],
            "unique_courts": row[2],
            "anonymized_percentage": round((row[3] / row[0] * 100) if row[0] > 0 else 0, 1),
            "with_gdpr_percentage": round((row[4] / row[0] * 100) if row[0] > 0 else 0, 1),
        },
        "recent_activity": {
            "last_7_days": row[5],
            "last_30_days": row[6],
            "last_update": row[7].isoformat() if row[7] else None,
        },
        "status": "operational",
        "version": "1.0.0",
    }
