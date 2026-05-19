#!/usr/bin/env python
"""
Setup-Skript für PostgreSQL Volltext-Suche.
Erstellt Trigger und Indizes für deutsche Volltextsuche.
"""

import asyncio
import sys
from pathlib import Path

# Füge src zum Python-Path hinzu
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import text
import structlog

from src.database import db_manager
from src.config import settings

# Logging initialisieren
import structlog

logger = structlog.get_logger()


async def setup_fulltext_search():
    """
    Richtet PostgreSQL Volltext-Suche ein.
    Erstellt Trigger und Indizes für deutsche Volltextsuche.
    """

    logger.info("fulltext_setup_starting")

    try:
        # Initialisiere Datenbank
        await db_manager.initialize()

        async with db_manager.engine.begin() as conn:
            # 1. Prüfe ob deutsche Text-Konfiguration existiert
            check_config = await conn.execute(
                text("SELECT cfgname FROM pg_ts_config WHERE cfgname = 'german'")
            )
            if not check_config.fetchone():
                logger.warning(
                    "german_config_not_found",
                    message="Deutsche Text-Konfiguration nicht gefunden. Verwende 'simple'.",
                )
                text_config = "simple"
            else:
                text_config = "german"
                logger.info("german_config_found")

            # 2. Erstelle Funktion für search_vector Update
            logger.info("creating_search_vector_function")
            await conn.execute(
                text(
                    f"""
                CREATE OR REPLACE FUNCTION update_search_vector() 
                RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := 
                        setweight(to_tsvector('{text_config}', COALESCE(NEW.title, '')), 'A') ||
                        setweight(to_tsvector('{text_config}', COALESCE(NEW.leitsatz, '')), 'B') ||
                        setweight(to_tsvector('{text_config}', COALESCE(NEW.full_text_anonymized, '')), 'C') ||
                        setweight(to_tsvector('{text_config}', COALESCE(array_to_string(NEW.keywords, ' '), '')), 'B') ||
                        setweight(to_tsvector('{text_config}', COALESCE(NEW.case_number, '')), 'B') ||
                        setweight(to_tsvector('{text_config}', COALESCE(NEW.court, '')), 'B');
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """
                )
            )
            logger.info("search_vector_function_created")

            # 3. Erstelle Trigger für automatisches Update
            logger.info("creating_trigger")
            await conn.execute(
                text(
                    """
                DROP TRIGGER IF EXISTS update_search_vector_trigger ON decisions;
                
                CREATE TRIGGER update_search_vector_trigger
                    BEFORE INSERT OR UPDATE OF 
                        title, leitsatz, full_text_anonymized, keywords, case_number, court
                    ON decisions
                    FOR EACH ROW
                    EXECUTE FUNCTION update_search_vector();
            """
                )
            )
            logger.info("trigger_created")

            # 4. Erstelle GIN Index für Performance
            logger.info("creating_gin_index")
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_search_vector 
                ON decisions USING gin(search_vector);
            """
                )
            )
            logger.info("gin_index_created")

            # 5. Erstelle zusätzliche Indizes für häufige Abfragen
            logger.info("creating_additional_indexes")

            # Index für GDPR-Artikel (GIN für Array)
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_gdpr_articles_gin
                ON decisions USING gin(gdpr_articles);
            """
                )
            )

            # Index für Keywords (GIN für Array)
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_keywords_gin
                ON decisions USING gin(keywords);
            """
                )
            )

            # Composite Index für häufige Filter
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_source_date
                ON decisions(source, decision_date DESC);
            """
                )
            )

            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_court_date
                ON decisions(court, decision_date DESC)
                WHERE court IS NOT NULL;
            """
                )
            )

            logger.info("additional_indexes_created")

            # 6. Update existing records (nur wenn Tabelle nicht leer)
            count_result = await conn.execute(text("SELECT COUNT(*) FROM decisions"))
            count = count_result.scalar()

            if count > 0:
                logger.info("updating_existing_records", count=count)

                # Update in Batches für bessere Performance
                batch_size = 1000
                for offset in range(0, count, batch_size):
                    await conn.execute(
                        text(
                            f"""
                        UPDATE decisions 
                        SET search_vector = 
                            setweight(to_tsvector('{text_config}', COALESCE(title, '')), 'A') ||
                            setweight(to_tsvector('{text_config}', COALESCE(leitsatz, '')), 'B') ||
                            setweight(to_tsvector('{text_config}', COALESCE(full_text_anonymized, '')), 'C') ||
                            setweight(to_tsvector('{text_config}', COALESCE(array_to_string(keywords, ' '), '')), 'B') ||
                            setweight(to_tsvector('{text_config}', COALESCE(case_number, '')), 'B') ||
                            setweight(to_tsvector('{text_config}', COALESCE(court, '')), 'B')
                        WHERE id IN (
                            SELECT id FROM decisions 
                            ORDER BY id 
                            LIMIT {batch_size} OFFSET {offset}
                        )
                    """
                        )
                    )

                    processed = min(offset + batch_size, count)
                    logger.info("batch_updated", processed=processed, total=count)

                logger.info("existing_records_updated")

            # 7. Analyze Tabelle für optimale Query-Pläne
            logger.info("analyzing_table")
            await conn.execute(text("ANALYZE decisions;"))

            # 8. Zeige Statistiken
            stats_result = await conn.execute(
                text(
                    """
                SELECT 
                    pg_size_pretty(pg_relation_size('decisions')) as table_size,
                    pg_size_pretty(pg_relation_size('idx_decisions_search_vector')) as index_size,
                    (SELECT COUNT(*) FROM decisions) as row_count,
                    (SELECT COUNT(*) FROM decisions WHERE search_vector IS NOT NULL) as indexed_count
            """
                )
            )
            stats = stats_result.fetchone()

            logger.info(
                "fulltext_setup_completed",
                table_size=stats[0],
                index_size=stats[1],
                row_count=stats[2],
                indexed_count=stats[3],
            )

            print("\n" + "=" * 60)
            print("✅ PostgreSQL Volltext-Suche erfolgreich eingerichtet!")
            print("=" * 60)
            print(f"📊 Statistiken:")
            print(f"   - Tabellengröße: {stats[0]}")
            print(f"   - Index-Größe: {stats[1]}")
            print(f"   - Anzahl Zeilen: {stats[2]}")
            print(f"   - Indizierte Zeilen: {stats[3]}")
            print(f"   - Text-Konfiguration: {text_config}")
            print("=" * 60 + "\n")

    except Exception as e:
        logger.error("fulltext_setup_failed", error=str(e), exc_info=True)
        print(f"\n❌ Fehler beim Einrichten der Volltext-Suche: {e}")
        raise
    finally:
        await db_manager.close()


async def test_fulltext_search():
    """
    Testet die Volltext-Suche mit Beispiel-Queries.
    """

    logger.info("testing_fulltext_search")

    try:
        await db_manager.initialize()

        async with db_manager.engine.begin() as conn:
            # Test 1: Einfache Suche
            test_queries = [
                ("Datenschutz", "Einfache Suche nach 'Datenschutz'"),
                ("Datenschutz & Verarbeitung", "Bool'sche AND-Suche"),
                ("Datenschutz | Privatsphäre", "Bool'sche OR-Suche"),
                ("!Einwilligung", "Negation (NOT)"),
                ("Art:* & 6", "Prefix-Suche mit Artikel 6"),
            ]

            print("\n" + "=" * 60)
            print("🔍 Teste Volltext-Suche...")
            print("=" * 60)

            for query, description in test_queries:
                result = await conn.execute(
                    text(
                        """
                    SELECT 
                        COUNT(*) as matches,
                        AVG(ts_rank(search_vector, to_tsquery('german', :query))) as avg_rank
                    FROM decisions
                    WHERE search_vector @@ to_tsquery('german', :query)
                """
                    ),
                    {"query": query},
                )

                row = result.fetchone()
                print(f"\n📝 {description}")
                print(f"   Query: {query}")
                print(f"   Treffer: {row[0]}")
                print(
                    f"   Durchschn. Relevanz: {row[1]:.4f}"
                    if row[1]
                    else "   Durchschn. Relevanz: N/A"
                )

            print("\n" + "=" * 60)
            print("✅ Volltext-Suche funktioniert!")
            print("=" * 60 + "\n")

    except Exception as e:
        logger.error("fulltext_test_failed", error=str(e))
        print(f"\n❌ Fehler beim Testen der Volltext-Suche: {e}")
    finally:
        await db_manager.close()


async def main():
    """Hauptfunktion."""

    print("\n" + "=" * 60)
    print("🚀 PostgreSQL Volltext-Suche Setup")
    print("=" * 60)
    print(f"📊 Datenbank: {settings.database_url.split('@')[1]}")
    print("=" * 60 + "\n")

    # Setup ausführen
    await setup_fulltext_search()

    # Optional: Tests ausführen
    response = input("\n🔍 Möchten Sie die Volltext-Suche testen? (j/n): ")
    if response.lower() in ["j", "ja", "yes", "y"]:
        await test_fulltext_search()

    print("\n✨ Setup abgeschlossen!")


if __name__ == "__main__":
    asyncio.run(main())
