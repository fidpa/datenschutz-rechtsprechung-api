"""
Celery Tasks für Crawler und Verarbeitung.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional

from celery import Task
from celery.utils.log import get_task_logger

from src.tasks.celery_app import app
from src.database import get_async_session
from src.collectors.gdprhub import GDPRhubCollector
from src.collectors.openlegaldata import OpenLegalDataCollector
from src.processors.deduplicator import DecisionDeduplicator
from src.utils.logging import get_logger

# Claude Code Logging Integration
from src.logging.middleware.celery_middleware import claude_task_monitor

# Celery Task Logger
task_logger = get_task_logger(__name__)
logger = get_logger("tasks.crawler")


class AsyncTask(Task):
    """Basis-Klasse für async Tasks."""

    def run(self, *args, **kwargs):
        """Wrapper für async Ausführung."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(self.async_run(*args, **kwargs))
        finally:
            loop.close()

    async def async_run(self, *args, **kwargs):
        """Zu implementierende async Methode."""
        raise NotImplementedError


@app.task(base=AsyncTask, bind=True, max_retries=3)
@claude_task_monitor
class CrawlGDPRhubTask(AsyncTask):
    """Task für GDPRhub Crawling."""

    async def async_run(self, full_crawl: bool = False, max_pages: int = 100):
        """
        Crawlt GDPRhub Wiki.

        Args:
            full_crawl: Vollständiger Crawl statt incremental
            max_pages: Maximale Anzahl zu crawlender Seiten

        Returns:
            Crawl-Statistiken
        """
        task_logger.info(f"Starting GDPRhub crawl (full={full_crawl}, max_pages={max_pages})")

        async with get_async_session() as session:
            collector = GDPRhubCollector(session, max_pages=max_pages)

            async with collector:
                # Validiere Zugang
                if not await collector.validate_access():
                    raise Exception("GDPRhub not accessible")

                # Sammle Entscheidungen
                decisions_count = 0
                async for decision in collector.collect(full_crawl=full_crawl):
                    decisions_count += 1

                    # Progress Update alle 10 Entscheidungen
                    if decisions_count % 10 == 0:
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "current": decisions_count,
                                "status": f"Processed {decisions_count} decisions",
                            },
                        )

                # Hole Statistiken
                stats = collector.calculate_progress()

                task_logger.info(f"GDPRhub crawl completed: {stats}")
                return {
                    "source": "gdprhub",
                    "decisions_collected": decisions_count,
                    "stats": stats,
                    "timestamp": datetime.now().isoformat(),
                }


@app.task(base=AsyncTask, bind=True, max_retries=3)
@claude_task_monitor
class CrawlOpenLegalDataTask(AsyncTask):
    """Task für OpenLegalData Crawling."""

    async def async_run(
        self, full_crawl: bool = False, max_pages: int = 50, api_key: Optional[str] = None
    ):
        """
        Crawlt OpenLegalData API.

        Args:
            full_crawl: Vollständiger Crawl statt incremental
            max_pages: Maximale Anzahl zu crawlender Seiten
            api_key: Optional API Key für höhere Limits

        Returns:
            Crawl-Statistiken
        """
        task_logger.info(f"Starting OpenLegalData crawl (full={full_crawl}, max_pages={max_pages})")

        async with get_async_session() as session:
            collector = OpenLegalDataCollector(session, max_pages=max_pages, api_key=api_key)

            async with collector:
                # Validiere Zugang
                if not await collector.validate_access():
                    raise Exception("OpenLegalData API not accessible")

                # Sammle Entscheidungen
                decisions_count = 0
                async for decision in collector.collect(full_crawl=full_crawl):
                    decisions_count += 1

                    # Progress Update alle 25 Entscheidungen
                    if decisions_count % 25 == 0:
                        self.update_state(
                            state="PROGRESS",
                            meta={
                                "current": decisions_count,
                                "status": f"Processed {decisions_count} decisions",
                                "gdpr_relevant": collector.gdpr_relevant_cases,
                            },
                        )

                # Hole Statistiken
                stats = collector.calculate_progress()

                task_logger.info(f"OpenLegalData crawl completed: {stats}")
                return {
                    "source": "openlegaldata",
                    "decisions_collected": decisions_count,
                    "gdpr_relevant": collector.gdpr_relevant_cases,
                    "total_found": collector.total_cases_found,
                    "stats": stats,
                    "timestamp": datetime.now().isoformat(),
                }


@app.task(base=AsyncTask, bind=True)
@claude_task_monitor
class DeduplicateDecisionsTask(AsyncTask):
    """Task für Deduplizierung."""

    async def async_run(self, check_content: bool = False):
        """
        Dedupliziert Entscheidungen in der Datenbank.

        Args:
            check_content: Ob auch Content-Similarity geprüft werden soll

        Returns:
            Deduplizierungs-Statistiken
        """
        task_logger.info("Starting deduplication process")

        async with get_async_session() as session:
            deduplicator = DecisionDeduplicator(session)

            # Hole alle Entscheidungen der letzten 7 Tage
            from sqlalchemy import select
            from src.database import Decision

            stmt = (
                select(Decision)
                .where(Decision.created_at >= datetime.now() - timedelta(days=7))
                .limit(1000)
            )  # Limitiere für Performance

            result = await session.execute(stmt)
            recent_decisions = result.scalars().all()

            task_logger.info(f"Checking {len(recent_decisions)} recent decisions")

            total_duplicates = 0
            merged_groups = []

            for idx, decision in enumerate(recent_decisions):
                # Find duplicates
                duplicates = await deduplicator.find_duplicates(
                    decision, check_content=check_content
                )

                if duplicates:
                    # Merge duplicates
                    all_dups = [decision] + duplicates
                    master = await deduplicator.merge_duplicates(all_dups)

                    total_duplicates += len(duplicates)
                    merged_groups.append(
                        {"master_id": str(master.id), "merged_count": len(duplicates)}
                    )

                # Progress Update
                if idx % 50 == 0:
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "current": idx,
                            "total": len(recent_decisions),
                            "duplicates_found": total_duplicates,
                        },
                    )

            # Hole finale Statistiken
            stats = await deduplicator.get_statistics()

            task_logger.info(f"Deduplication completed: {stats}")
            return {
                "decisions_checked": len(recent_decisions),
                "duplicates_found": total_duplicates,
                "merged_groups": len(merged_groups),
                "stats": stats,
                "timestamp": datetime.now().isoformat(),
            }


@app.task(bind=True)
def crawl_all_sources(self, full_crawl: bool = False):
    """
    Crawlt alle konfigurierten Datenquellen.

    Args:
        full_crawl: Vollständiger Crawl statt incremental

    Returns:
        Kombinierte Statistiken
    """
    task_logger.info(f"Starting crawl of all sources (full={full_crawl})")

    # Starte alle Crawler als Subtasks
    from celery import group

    job = group(
        crawl_gdprhub.s(full_crawl=full_crawl),
        crawl_openlegaldata.s(full_crawl=full_crawl, max_pages=25),
    )

    result = job.apply_async()
    results = result.get(timeout=7200)  # 2 Stunden Timeout

    # Deduplizierung nach Crawl
    dedup_result = deduplicate_decisions.apply_async().get(timeout=3600)

    return {
        "crawl_results": results,
        "deduplication": dedup_result,
        "timestamp": datetime.now().isoformat(),
    }


@app.task(base=AsyncTask)
@claude_task_monitor
class UpdateStatisticsTask(AsyncTask):
    """Task für Statistik-Updates."""

    async def async_run(self):
        """
        Aktualisiert Statistiken in der Datenbank.

        Returns:
            Aktuelle Statistiken
        """
        task_logger.info("Updating statistics")

        async with get_async_session() as session:
            from sqlalchemy import select, func
            from src.database import Decision

            # Sammle Statistiken
            stats_queries = {
                "total_decisions": select(func.count(Decision.id)),
                "total_gdprhub": select(func.count(Decision.id)).where(
                    Decision.source == "gdprhub"
                ),
                "total_openlegaldata": select(func.count(Decision.id)).where(
                    Decision.source == "openlegaldata"
                ),
                "decisions_with_gdpr": select(func.count(Decision.id)).where(
                    Decision.gdpr_articles.isnot(None)
                ),
                "decisions_anonymized": select(func.count(Decision.id)).where(
                    Decision.anonymization_applied == True
                ),
                "unique_courts": select(func.count(func.distinct(Decision.court))),
                "latest_decision": select(func.max(Decision.decision_date)),
            }

            stats = {}
            for key, query in stats_queries.items():
                result = await session.execute(query)
                stats[key] = result.scalar()

            # Speichere in Redis für schnellen Zugriff
            from src.utils.cache import get_redis_client

            redis = await get_redis_client()

            await redis.setex(
                "crawler:stats:latest", 3600, json.dumps(stats, default=str)  # 1 Stunde TTL
            )

            task_logger.info(f"Statistics updated: {stats}")
            return stats


# Task-Aliase für einfacheren Import
crawl_gdprhub = CrawlGDPRhubTask()
crawl_openlegaldata = CrawlOpenLegalDataTask()
deduplicate_decisions = DeduplicateDecisionsTask()
update_statistics = UpdateStatisticsTask()
