#!/usr/bin/env python
"""
Datenbank-Migration: Fügt neue Felder zur bestehenden DB hinzu.

Neue Felder:
- quality_score: Bewertung 1-5 Sterne
- user_feedback: Textuelle Kommentare
- feedback_count: Anzahl Bewertungen
- avg_quality_score: Durchschnittsbewertung
- rechtskraft_status: Status der Rechtskraft
- rechtskraft_datum: Datum der Rechtskraft
- nachfolge_entscheidung_id: Verweis auf Berufungsentscheidung

Verwendung:
    python scripts/migrate_db.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Projekt-Root zum Python-Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
import structlog
from src.database import db_manager
from src.config import settings

logger = structlog.get_logger()


async def check_column_exists(conn, table_name: str, column_name: str) -> bool:
    """Prüft, ob eine Spalte bereits existiert."""
    result = await conn.execute(
        text(
            f"""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_name = :table_name
        AND column_name = :column_name
    """
        ),
        {"table_name": table_name, "column_name": column_name},
    )

    count = result.scalar()
    return count > 0


async def migrate_database():
    """Führt die Datenbank-Migration durch."""

    logger.info("migration_started", database=settings.database_url.split("@")[-1])

    try:
        # Initialisiere Datenbank-Manager
        await db_manager.initialize()

        # Migrations-Befehle
        migrations = [
            # Feedback & Qualität
            {
                "name": "quality_score",
                "check": "quality_score",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS quality_score INTEGER
                    CHECK (quality_score >= 1 AND quality_score <= 5)
                """,
            },
            {
                "name": "user_feedback",
                "check": "user_feedback",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS user_feedback TEXT
                """,
            },
            {
                "name": "feedback_count",
                "check": "feedback_count",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS feedback_count INTEGER DEFAULT 0
                """,
            },
            {
                "name": "avg_quality_score",
                "check": "avg_quality_score",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS avg_quality_score FLOAT
                """,
            },
            # Rechtskraft-Status
            {
                "name": "rechtskraft_status",
                "check": "rechtskraft_status",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS rechtskraft_status VARCHAR(50)
                """,
            },
            {
                "name": "rechtskraft_datum",
                "check": "rechtskraft_datum",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS rechtskraft_datum DATE
                """,
            },
            {
                "name": "nachfolge_entscheidung_id",
                "check": "nachfolge_entscheidung_id",
                "sql": """
                    ALTER TABLE decisions 
                    ADD COLUMN IF NOT EXISTS nachfolge_entscheidung_id UUID
                    REFERENCES decisions(id) ON DELETE SET NULL
                """,
            },
            # Kommentare für bessere Dokumentation
            {
                "name": "rechtskraft_status_comment",
                "check": None,  # Immer ausführen
                "sql": """
                    COMMENT ON COLUMN decisions.rechtskraft_status IS 
                    'rechtskräftig, berufung_möglich, berufung_eingelegt, aufgehoben, vergleich, unbekannt'
                """,
            },
            {
                "name": "nachfolge_comment",
                "check": None,  # Immer ausführen
                "sql": """
                    COMMENT ON COLUMN decisions.nachfolge_entscheidung_id IS 
                    'Verweis auf Berufungs-/Revisionsentscheidung'
                """,
            },
        ]

        # Führe Migrationen aus
        async with db_manager.engine.begin() as conn:
            success_count = 0
            skip_count = 0

            for migration in migrations:
                try:
                    # Prüfe ob Spalte bereits existiert
                    if migration["check"]:
                        exists = await check_column_exists(conn, "decisions", migration["check"])
                        if exists:
                            logger.info("column_exists", column=migration["name"])
                            skip_count += 1
                            continue

                    # Führe Migration aus
                    await conn.execute(text(migration["sql"]))
                    logger.info("migration_applied", migration=migration["name"])
                    success_count += 1

                except Exception as e:
                    logger.error("migration_failed", migration=migration["name"], error=str(e))
                    raise

            # Erstelle Index für Rechtskraft-Status
            try:
                await conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS ix_decisions_rechtskraft_status 
                    ON decisions(rechtskraft_status)
                    WHERE rechtskraft_status IS NOT NULL
                """
                    )
                )
                logger.info("index_created", index="ix_decisions_rechtskraft_status")
            except Exception as e:
                logger.warning("index_creation_failed", error=str(e))

            # Erstelle Index für Qualitätsbewertung
            try:
                await conn.execute(
                    text(
                        """
                    CREATE INDEX IF NOT EXISTS ix_decisions_quality 
                    ON decisions(avg_quality_score)
                    WHERE avg_quality_score IS NOT NULL
                """
                    )
                )
                logger.info("index_created", index="ix_decisions_quality")
            except Exception as e:
                logger.warning("index_creation_failed", error=str(e))

            # Commit wird automatisch durch 'begin()' context manager ausgeführt

        logger.info(
            "migration_completed", success=success_count, skipped=skip_count, total=len(migrations)
        )

        print(
            f"""
╔══════════════════════════════════════════════════════════════╗
║                 🎉 MIGRATION ERFOLGREICH!                     ║
╠══════════════════════════════════════════════════════════════╣
║ ✅ {success_count:2d} Migrationen angewendet                               ║
║ ⏭️  {skip_count:2d} Spalten bereits vorhanden                             ║
║ 📊 Neue Features verfügbar:                                  ║
║    - Qualitätsbewertung (1-5 Sterne)                        ║
║    - User-Feedback                                          ║
║    - Rechtskraft-Status                                     ║
║    - Verweise auf Folgeentscheidungen                       ║
╚══════════════════════════════════════════════════════════════╝
        """
        )

    except Exception as e:
        logger.error("migration_error", error=str(e), exc_info=True)
        print(f"\n❌ Migration fehlgeschlagen: {e}")
        sys.exit(1)

    finally:
        await db_manager.close()


async def verify_migration():
    """Verifiziert die erfolgreiche Migration."""

    await db_manager.initialize()

    try:
        async with db_manager.engine.connect() as conn:
            # Prüfe alle neuen Spalten
            result = await conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'decisions'
                AND column_name IN (
                    'quality_score', 'user_feedback', 'feedback_count',
                    'avg_quality_score', 'rechtskraft_status', 
                    'rechtskraft_datum', 'nachfolge_entscheidung_id'
                )
                ORDER BY column_name
            """
                )
            )

            columns = result.fetchall()

            if len(columns) == 7:
                print("\n✅ Alle neuen Spalten erfolgreich angelegt:")
                for col_name, data_type, nullable in columns:
                    print(
                        f"   - {col_name:30s} {data_type:20s} {'NULL' if nullable == 'YES' else 'NOT NULL'}"
                    )
                return True
            else:
                print(f"\n⚠️ Nur {len(columns)} von 7 Spalten gefunden")
                return False

    finally:
        await db_manager.close()


if __name__ == "__main__":
    print(
        """
╔══════════════════════════════════════════════════════════════╗
║            GDPR CRAWLER - DATENBANK MIGRATION                ║
║                     Phase 4 Features                         ║
╚══════════════════════════════════════════════════════════════╝
    """
    )

    # Führe Migration aus
    asyncio.run(migrate_database())

    # Verifiziere Ergebnis
    print("\n🔍 Verifiziere Migration...")
    success = asyncio.run(verify_migration())

    if success:
        print("\n🎯 Nächster Schritt: Export-API testen")
        print("   curl http://localhost:8000/api/v1/export/json?limit=1")
    else:
        print("\n⚠️ Migration unvollständig - bitte Logs prüfen")
