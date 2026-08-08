#!/usr/bin/env python3
"""
Script zum Anwenden der Staging-Tabellen-Migration für zweistufige Filterung.

Dieses Script:
1. Erstellt die neue Staging-Tabelle
2. Migriert optional bestehende Daten zur Neu-Bewertung
3. Initialisiert Filter-Statistiken

Author: Datenschutz-Rechtsprechung API Team
Date: 21.08.2025
"""

import json
import sys
import click
from pathlib import Path
from datetime import datetime
from typing import Optional

from sqlalchemy import text

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db_manager
from src.filters.two_stage_filter import GDPRTwoStageFilter, FilterConfig
from src.utils.logging import get_logger

logger = get_logger("staging_migration")


def apply_migration(dry_run: bool = False):
    """
    Wendet die Staging-Tabellen-Migration an.

    Args:
        dry_run: Wenn True, wird nur simuliert
    """
    migration_file = Path(__file__).parent / "migrations" / "add_staging_table.sql"

    if not migration_file.exists():
        logger.error(f"Migration-Datei nicht gefunden: {migration_file}")
        return False

    logger.info(f"Lese Migration von {migration_file}")

    with open(migration_file, "r") as f:
        migration_sql = f.read()

    if dry_run:
        logger.info("DRY-RUN Modus - keine Änderungen werden durchgeführt")
        logger.info(f"Würde folgende Migration ausführen:\n{migration_sql[:500]}...")
        return True

    # Migration ausführen
    try:
        with db_manager.get_sync_session() as session:
            logger.info("Führe Migration aus...")
            session.execute(migration_sql)
            session.commit()
            logger.info("✅ Migration erfolgreich angewendet!")
            return True
    except Exception as e:
        logger.error(f"❌ Migration fehlgeschlagen: {e}")
        return False


def migrate_existing_decisions(
    limit: Optional[int] = None, source_filter: Optional[str] = None, dry_run: bool = False
):
    """
    Migriert bestehende Entscheidungen zur Neu-Bewertung.

    Args:
        limit: Maximale Anzahl zu migrierender Entscheidungen
        source_filter: Nur Entscheidungen dieser Quelle migrieren
        dry_run: Wenn True, wird nur simuliert
    """
    from sqlalchemy import text

    logger.info("Starte Migration bestehender Entscheidungen...")

    # SQL für Migration
    select_sql = """
    SELECT 
        id,
        source,
        source_id,
        source_url,
        title,
        court,
        case_number,
        decision_date,
        full_text_anonymized,
        gdpr_articles
    FROM decisions
    WHERE 1=1
    """

    params = {}

    if source_filter:
        select_sql += " AND source = :source"
        params["source"] = source_filter

    if limit:
        select_sql += " LIMIT :limit"
        params["limit"] = limit

    try:
        with db_manager.get_sync_session() as session:
            result = session.execute(text(select_sql), params)
            decisions = result.fetchall()

            logger.info(f"Gefunden: {len(decisions)} Entscheidungen zur Migration")

            if dry_run:
                logger.info("DRY-RUN: Würde Entscheidungen zu decision_candidates migrieren")
                return

            # Filter initialisieren
            filter_config = FilterConfig()
            gdpr_filter = GDPRTwoStageFilter(filter_config)

            migrated_count = 0

            for decision in decisions:
                # Dokument für Filter vorbereiten
                document = {
                    "id": decision.source_id,
                    "source": decision.source,
                    "title": decision.title,
                    "court": decision.court,
                    "case_number": decision.case_number,
                    "decision_date": decision.decision_date,
                    "content": decision.full_text_anonymized or "",
                }

                # Durch Filter laufen lassen
                status, metadata = gdpr_filter.process_document(document)

                # In Staging-Tabelle einfügen
                insert_sql = """
                INSERT INTO decision_candidates (
                    source,
                    source_id,
                    source_url,
                    raw_data,
                    title,
                    court,
                    case_number,
                    decision_date,
                    stage1_score,
                    stage1_keywords,
                    stage2_confidence,
                    stage2_context_score,
                    stage2_structure_score,
                    stage2_metadata_score,
                    stage2_patterns,
                    status,
                    decision_id,
                    created_at
                ) VALUES (
                    :source,
                    :source_id,
                    :source_url,
                    :raw_data,
                    :title,
                    :court,
                    :case_number,
                    :decision_date,
                    :stage1_score,
                    :stage1_keywords,
                    :stage2_confidence,
                    :stage2_context_score,
                    :stage2_structure_score,
                    :stage2_metadata_score,
                    :stage2_patterns,
                    :status,
                    :decision_id,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (source, source_id) DO UPDATE SET
                    stage1_score = EXCLUDED.stage1_score,
                    stage2_confidence = EXCLUDED.stage2_confidence,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """

                session.execute(
                    text(insert_sql),
                    {
                        "source": decision.source,
                        "source_id": decision.source_id,
                        "source_url": decision.source_url,
                        "raw_data": "{}",  # Minimal für Migration
                        "title": decision.title,
                        "court": decision.court,
                        "case_number": decision.case_number,
                        "decision_date": decision.decision_date,
                        "stage1_score": metadata.get("stage1_score", 0),
                        "stage1_keywords": metadata.get("stage1_keywords", []),
                        "stage2_confidence": metadata.get("stage2_confidence"),
                        "stage2_context_score": metadata.get("stage2_context_score"),
                        "stage2_structure_score": metadata.get("stage2_structure_score"),
                        "stage2_metadata_score": metadata.get("stage2_metadata_score"),
                        "stage2_patterns": json.dumps(metadata.get("stage2_patterns", {})),
                        "status": status.value,
                        "decision_id": decision.id,
                    },
                )

                migrated_count += 1

                if migrated_count % 10 == 0:
                    logger.info(f"Migriert: {migrated_count}/{len(decisions)}")
                    session.commit()

            session.commit()
            logger.info(f"✅ Migration abgeschlossen: {migrated_count} Entscheidungen migriert")

            # Statistiken ausgeben
            stats = gdpr_filter.get_statistics()
            logger.info(f"Filter-Statistiken:")
            logger.info(f"  - Stage 1 Pass Rate: {stats['stage1_pass_rate']:.1f}%")
            logger.info(f"  - Stage 2 Approval Rate: {stats['stage2_approval_rate']:.1f}%")
            logger.info(f"  - Overall Approval Rate: {stats['overall_approval_rate']:.1f}%")

    except Exception as e:
        logger.error(f"Migration fehlgeschlagen: {e}")
        raise


@click.command()
@click.option(
    "--apply-migration/--skip-migration", default=True, help="Migration anwenden (Standard: ja)"
)
@click.option(
    "--migrate-existing/--no-migrate-existing",
    default=False,
    help="Bestehende Entscheidungen migrieren",
)
@click.option(
    "--limit", type=int, default=None, help="Maximale Anzahl zu migrierender Entscheidungen"
)
@click.option("--source", type=str, default=None, help="Nur Entscheidungen dieser Quelle migrieren")
@click.option("--dry-run", is_flag=True, help="Simulation ohne Änderungen")
def main(
    apply_migration: bool,
    migrate_existing: bool,
    limit: Optional[int],
    source: Optional[str],
    dry_run: bool,
):
    """
    Wendet Staging-Tabellen-Migration an und migriert optional bestehende Daten.

    Beispiele:
        # Nur Migration anwenden
        python scripts/apply_staging_migration.py

        # Migration + bestehende Daten migrieren
        python scripts/apply_staging_migration.py --migrate-existing

        # Nur OpenLegalData migrieren (max 100)
        python scripts/apply_staging_migration.py --migrate-existing --source openlegaldata_dump --limit 100

        # Dry-Run
        python scripts/apply_staging_migration.py --dry-run
    """
    import json

    logger.info("🚀 Starte Staging-Migration für zweistufige Filterung")
    logger.info("=" * 60)

    if dry_run:
        logger.info("🧪 DRY-RUN MODUS - Keine Änderungen werden durchgeführt")

    # Schritt 1: Migration anwenden
    if apply_migration:
        logger.info("\n📋 Schritt 1: Wende Datenbank-Migration an...")
        success = apply_migration(dry_run)
        if not success and not dry_run:
            logger.error("Migration fehlgeschlagen - Abbruch")
            sys.exit(1)

    # Schritt 2: Bestehende Daten migrieren
    if migrate_existing:
        logger.info("\n📊 Schritt 2: Migriere bestehende Entscheidungen...")
        logger.info(f"  - Quelle: {source or 'Alle'}")
        logger.info(f"  - Limit: {limit or 'Unbegrenzt'}")

        migrate_existing_decisions(limit, source, dry_run)

    logger.info("\n✅ Migration erfolgreich abgeschlossen!")

    if not dry_run:
        # Dashboard-View testen
        logger.info("\n📈 Teste Dashboard-View...")
        try:
            with db_manager.get_sync_session() as session:
                result = session.execute(text("SELECT * FROM v_filter_pipeline"))
                rows = result.fetchall()

                if rows:
                    logger.info("Pipeline-Status:")
                    for row in rows:
                        logger.info(f"  - {row.status}: {row.count} Dokumente")
                else:
                    logger.info("  Keine Daten in Pipeline")
        except Exception as e:
            logger.warning(f"Dashboard-View Test fehlgeschlagen: {e}")


if __name__ == "__main__":
    main()
