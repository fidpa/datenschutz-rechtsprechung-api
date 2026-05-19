#!/usr/bin/env python3
"""
PostgreSQL Performance-Optimierungs-Script für Datenschutz-Rechtsprechung API.
Führt Index-Optimierungen und Analyse durch.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Projekt-Root zum Python-Path hinzufügen
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.database import db_manager

# Logging
logger = structlog.get_logger()


class DatabaseOptimizer:
    """Klasse für Datenbank-Performance-Optimierungen."""

    def __init__(self):
        self.engine = None
        self.stats = {
            "indices_created": 0,
            "indices_failed": 0,
            "tables_analyzed": 0,
            "cache_hit_ratio": 0.0,
        }

    async def connect(self):
        """Verbindung zur Datenbank herstellen."""
        self.engine = create_async_engine(settings.database_url, echo=False)
        logger.info("database_connected")

    async def disconnect(self):
        """Verbindung trennen."""
        if self.engine:
            await self.engine.dispose()
            logger.info("database_disconnected")

    async def create_index(self, index_name: str, index_sql: str):
        """Erstellt einen Index wenn er noch nicht existiert."""
        try:
            async with self.engine.begin() as conn:
                # Prüfe ob Index existiert
                check_sql = text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes 
                        WHERE indexname = :index_name
                    )
                """
                )
                result = await conn.execute(check_sql, {"index_name": index_name})
                exists = result.scalar()

                if not exists:
                    logger.info(f"creating_index", index=index_name)
                    await conn.execute(text(index_sql))
                    self.stats["indices_created"] += 1
                    logger.info(f"index_created", index=index_name)
                else:
                    logger.info(f"index_exists", index=index_name)

        except Exception as e:
            logger.error(f"index_creation_failed", index=index_name, error=str(e))
            self.stats["indices_failed"] += 1

    async def optimize_indices(self):
        """Erstellt alle Performance-Indizes."""
        logger.info("starting_index_optimization")

        indices = [
            (
                "idx_decisions_created_at_desc",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_created_at_desc
                ON decisions(created_at DESC)
                WHERE deleted_at IS NULL
            """,
            ),
            (
                "idx_decisions_source_date",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_source_date
                ON decisions(source, decision_date DESC)
                WHERE deleted_at IS NULL
            """,
            ),
            (
                "idx_decisions_court_date",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_court_date
                ON decisions(court, decision_date DESC)
                WHERE deleted_at IS NULL
            """,
            ),
            (
                "idx_recent_decisions",
                """
                CREATE INDEX CONCURRENTLY idx_recent_decisions
                ON decisions(created_at)
                WHERE created_at > NOW() - INTERVAL '30 days'
                AND deleted_at IS NULL
            """,
            ),
            (
                "idx_decisions_gdpr_articles_gin",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_gdpr_articles_gin
                ON decisions USING gin(gdpr_articles)
                WHERE gdpr_articles IS NOT NULL
            """,
            ),
            (
                "idx_decisions_status",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_status
                ON decisions(processing_status)
                WHERE processing_status != 'completed'
            """,
            ),
            (
                "idx_decisions_quality",
                """
                CREATE INDEX CONCURRENTLY idx_decisions_quality
                ON decisions(quality_score DESC)
                WHERE quality_score IS NOT NULL
            """,
            ),
            (
                "idx_crawl_logs_created_at",
                """
                CREATE INDEX CONCURRENTLY idx_crawl_logs_created_at
                ON crawl_logs(created_at DESC)
            """,
            ),
            (
                "idx_crawl_logs_source_status",
                """
                CREATE INDEX CONCURRENTLY idx_crawl_logs_source_status
                ON crawl_logs(source, status, created_at DESC)
            """,
            ),
        ]

        for index_name, index_sql in indices:
            await self.create_index(index_name, index_sql)

    async def analyze_tables(self):
        """Analysiert alle wichtigen Tabellen für bessere Query-Planung."""
        logger.info("analyzing_tables")

        tables = ["decisions", "crawl_logs", "decision_documents"]

        async with self.engine.begin() as conn:
            for table in tables:
                try:
                    await conn.execute(text(f"ANALYZE {table}"))
                    self.stats["tables_analyzed"] += 1
                    logger.info(f"table_analyzed", table=table)
                except Exception as e:
                    logger.error(f"table_analysis_failed", table=table, error=str(e))

    async def vacuum_tables(self):
        """Führt VACUUM auf allen Tabellen aus."""
        logger.info("vacuuming_tables")

        # VACUUM kann nicht in einer Transaktion ausgeführt werden
        async with self.engine.connect() as conn:
            await conn.execute(text("COMMIT"))  # Beende aktuelle Transaktion

            tables = ["decisions", "crawl_logs"]
            for table in tables:
                try:
                    await conn.execute(text(f"VACUUM ANALYZE {table}"))
                    logger.info(f"table_vacuumed", table=table)
                except Exception as e:
                    logger.error(f"vacuum_failed", table=table, error=str(e))

    async def check_cache_hit_ratio(self):
        """Prüft die Cache-Hit-Ratio."""
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                SELECT 
                    sum(heap_blks_read) as heap_read,
                    sum(heap_blks_hit) as heap_hit,
                    CASE 
                        WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
                        THEN round(sum(heap_blks_hit) / 
                            (sum(heap_blks_hit) + sum(heap_blks_read))::numeric * 100, 2)
                        ELSE 0
                    END as cache_hit_ratio
                FROM pg_statio_user_tables
            """
                )
            )

            row = result.fetchone()
            if row:
                self.stats["cache_hit_ratio"] = float(row.cache_hit_ratio or 0)
                logger.info(f"cache_hit_ratio", ratio=self.stats["cache_hit_ratio"])

                if self.stats["cache_hit_ratio"] < 95:
                    logger.warning("low_cache_hit_ratio", ratio=self.stats["cache_hit_ratio"])

    async def show_table_sizes(self):
        """Zeigt die Größe aller Tabellen."""
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                SELECT 
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                    n_live_tup AS row_count
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """
                )
            )

            print("\n📊 Tabellen-Größen:")
            print("-" * 60)
            for row in result:
                print(f"  {row.tablename:30} {row.size:>15} ({row.row_count:,} Zeilen)")

    async def show_index_usage(self):
        """Zeigt Index-Nutzungs-Statistiken."""
        async with self.engine.begin() as conn:
            # Ungenutzte Indizes
            result = await conn.execute(
                text(
                    """
                SELECT
                    indexname,
                    idx_scan,
                    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                AND indexname NOT LIKE '%_pkey'
                ORDER BY pg_relation_size(indexrelid) DESC
                LIMIT 5
            """
                )
            )

            unused_indices = result.fetchall()
            if unused_indices:
                print("\n⚠️  Ungenutzte Indizes (Kandidaten zum Löschen):")
                print("-" * 60)
                for row in unused_indices:
                    print(f"  {row.indexname:40} {row.index_size:>10}")

    async def run_optimization(self):
        """Führt alle Optimierungen aus."""
        try:
            await self.connect()

            print("\n🚀 Starte Datenbank-Optimierung...")
            print("=" * 60)

            # 1. Indizes erstellen
            print("\n📌 Erstelle Performance-Indizes...")
            await self.optimize_indices()

            # 2. Tabellen analysieren
            print("\n📊 Analysiere Tabellen...")
            await self.analyze_tables()

            # 3. Cache-Hit-Ratio prüfen
            print("\n💾 Prüfe Cache-Effizienz...")
            await self.check_cache_hit_ratio()

            # 4. Tabellen-Größen anzeigen
            await self.show_table_sizes()

            # 5. Index-Nutzung anzeigen
            await self.show_index_usage()

            # 6. Optional: VACUUM (kann lange dauern)
            # print("\n🧹 Führe VACUUM aus...")
            # await self.vacuum_tables()

            # Zusammenfassung
            print("\n✅ Optimierung abgeschlossen!")
            print("=" * 60)
            print(f"  Indizes erstellt:    {self.stats['indices_created']}")
            print(f"  Indizes fehlgeschlagen: {self.stats['indices_failed']}")
            print(f"  Tabellen analysiert: {self.stats['tables_analyzed']}")
            print(f"  Cache-Hit-Ratio:     {self.stats['cache_hit_ratio']}%")

            if self.stats["cache_hit_ratio"] < 95:
                print("\n⚠️  WARNUNG: Cache-Hit-Ratio ist niedrig!")
                print("  Empfehlung: Erhöhen Sie shared_buffers in PostgreSQL")

        finally:
            await self.disconnect()


async def main():
    """Hauptfunktion."""
    optimizer = DatabaseOptimizer()
    await optimizer.run_optimization()


if __name__ == "__main__":
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║          Datenschutz-Rechtsprechung API - Datenbank-Optimierung               ║
╚══════════════════════════════════════════════════════════════╝
    """
    )

    asyncio.run(main())
