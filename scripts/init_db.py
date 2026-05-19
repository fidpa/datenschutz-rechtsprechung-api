#!/usr/bin/env python3
"""
Datenbank-Initialisierungsskript für den Datenschutz-Rechtsprechung API.
Erstellt Tabellen, Indizes und Trigger für die deutsche Volltext-Suche.
"""

import asyncio
import sys
import os
from pathlib import Path

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
import asyncpg

from src.config import settings
from src.database import Base, db_manager, create_search_vector_trigger


async def check_database_exists() -> bool:
    """Prüft ob die Datenbank existiert."""
    # Parse Database URL
    db_url_parts = settings.database_url.split("/")
    db_name = db_url_parts[-1].split("?")[0]
    server_url = "/".join(db_url_parts[:-1]) + "/postgres"

    try:
        # Verbinde zu postgres DB um zu prüfen
        engine = create_async_engine(server_url, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(
                text(f"SELECT 1 FROM pg_database WHERE datname = :dbname"), {"dbname": db_name}
            )
            exists = result.scalar() is not None
        await engine.dispose()
        return exists
    except Exception as e:
        print(f"❌ Fehler beim Prüfen der Datenbank: {e}")
        return False


async def create_database():
    """Erstellt die Datenbank falls sie nicht existiert."""
    # Parse Database URL
    db_url_parts = settings.database_url.split("/")
    db_name = db_url_parts[-1].split("?")[0]
    server_url = "/".join(db_url_parts[:-1]) + "/postgres"

    print(f"📊 Erstelle Datenbank '{db_name}'...")

    try:
        # Verbinde zu postgres DB für CREATE DATABASE
        conn = await asyncpg.connect(server_url.replace("postgresql+asyncpg://", ""))

        # Erstelle Datenbank mit deutschen Einstellungen
        await conn.execute(
            f"""
            CREATE DATABASE {db_name}
            WITH 
            ENCODING = 'UTF8'
            LC_COLLATE = 'de_DE.UTF-8'
            LC_CTYPE = 'de_DE.UTF-8'
            TEMPLATE = template0;
        """
        )

        await conn.close()
        print(f"✅ Datenbank '{db_name}' erfolgreich erstellt")
        return True

    except asyncpg.exceptions.DuplicateDatabaseError:
        print(f"ℹ️  Datenbank '{db_name}' existiert bereits")
        return True
    except Exception as e:
        print(f"❌ Fehler beim Erstellen der Datenbank: {e}")
        print("💡 Tipp: Stelle sicher, dass PostgreSQL läuft (docker-compose up -d postgres)")
        return False


async def init_extensions():
    """Initialisiert PostgreSQL Extensions."""
    print("🔧 Initialisiere PostgreSQL Extensions...")

    try:
        async with db_manager.engine.begin() as conn:
            # UUID Extension
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
            print("  ✅ uuid-ossp Extension aktiviert")

            # Volltext-Suche Extensions
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "unaccent";'))
            print("  ✅ unaccent Extension aktiviert")

            # Trigram für Fuzzy-Suche (optional aber nützlich)
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pg_trgm";'))
            print("  ✅ pg_trgm Extension aktiviert")

    except Exception as e:
        print(f"⚠️  Warnung bei Extensions: {e}")
        print("   (Extensions könnten bereits existieren)")


async def create_tables():
    """Erstellt alle Datenbank-Tabellen."""
    print("📋 Erstelle Tabellen...")

    try:
        # Initialisiere db_manager falls noch nicht geschehen
        if not db_manager.engine:
            await db_manager.initialize()

        # Prüfe ob Tabellen bereits existieren
        async with db_manager.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'decisions' AND schemaname = 'public')"
                )
            )
            tables_exist = result.scalar()

            if not tables_exist:
                # Tabellen existieren nicht, erstelle sie
                await db_manager.create_all_tables()
                print("✅ Alle Tabellen erfolgreich erstellt")
            else:
                print("  ℹ️  Tabellen existieren bereits")
    except Exception as e:
        # Ignoriere Fehler wenn Tabellen/Indizes bereits existieren
        if "already exists" in str(e).lower():
            print("  ℹ️  Einige Objekte existieren bereits (ignoriert)")
        else:
            print(f"❌ Fehler beim Erstellen der Tabellen: {e}")
            raise


async def setup_search_triggers():
    """Richtet Volltext-Such-Trigger ein."""
    print("🔍 Richte Volltext-Suche ein...")

    try:
        # Prüfe zuerst ob Tabellen existieren
        async with db_manager.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'decisions' AND schemaname = 'public')"
                )
            )
            if not result.scalar():
                print("  ⚠️  Tabellen existieren noch nicht, überspringe Trigger-Setup")
                return

        async with db_manager.engine.begin() as conn:
            # Teile SQL-Statements auf für asyncpg
            # 1. Erstelle Funktion
            await conn.execute(
                text(
                    """
                CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := 
                        setweight(to_tsvector('german', COALESCE(NEW.title, '')), 'A') ||
                        setweight(to_tsvector('german', COALESCE(NEW.leitsatz, '')), 'B') ||
                        setweight(to_tsvector('german', COALESCE(NEW.full_text_anonymized, '')), 'C') ||
                        setweight(to_tsvector('german', COALESCE(array_to_string(NEW.keywords, ' '), '')), 'B');
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """
                )
            )

            # 2. Lösche alten Trigger falls vorhanden
            await conn.execute(
                text("DROP TRIGGER IF EXISTS update_search_vector_trigger ON decisions")
            )

            # 3. Erstelle neuen Trigger
            await conn.execute(
                text(
                    """
                CREATE TRIGGER update_search_vector_trigger
                    BEFORE INSERT OR UPDATE ON decisions
                    FOR EACH ROW
                    EXECUTE FUNCTION update_search_vector()
            """
                )
            )

            # 4. Erstelle Index
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_search_vector 
                    ON decisions USING gin(search_vector)
            """
                )
            )

            print("✅ Volltext-Such-Trigger erfolgreich eingerichtet")

            # Zusätzliche Indizes für Performance
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_created_at 
                ON decisions(created_at DESC);
            """
                )
            )

            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_decisions_source_created 
                ON decisions(source, created_at DESC);
            """
                )
            )

            print("✅ Performance-Indizes erstellt")

    except Exception as e:
        print(f"❌ Fehler beim Einrichten der Volltext-Suche: {e}")
        raise


async def insert_test_data():
    """Fügt optionale Test-Daten ein (nur für Development)."""
    if not settings.is_development:
        return

    print("\n📝 Füge Test-Daten ein (Development-Modus)...")

    from src.database import Decision, SourceType, DocumentType
    from datetime import datetime, timedelta
    import uuid

    async with db_manager.async_session_maker() as session:
        try:
            # Prüfe ob bereits Test-Daten existieren
            result = await session.execute(
                text("SELECT COUNT(*) FROM decisions WHERE source = 'test'")
            )
            if result.scalar() > 0:
                print("ℹ️  Test-Daten existieren bereits")
                return

            # Erstelle Test-Entscheidung
            test_decision = Decision(
                id=uuid.uuid4(),
                source="test",
                source_id="test-001",
                source_url="https://example.com/test-decision",
                document_type=DocumentType.COURT_DECISION.value,
                title="Test-Entscheidung: Verletzung von Art. 6 DSGVO",
                case_number="1 ZR 123/22",
                court="BGH",
                decision_date=datetime.now() - timedelta(days=30),
                gdpr_articles=["Art. 6 DSGVO", "Art. 32 DSGVO"],
                keywords=["Rechtmäßigkeit", "Datensicherheit", "Schadensersatz"],
                full_text_original="Dies ist eine Test-Entscheidung mit Max Mustermann als Kläger.",
                full_text_anonymized="Dies ist eine Test-Entscheidung mit [Person 1] als Kläger.",
                anonymization_applied=True,
                language="de",
            )

            session.add(test_decision)
            await session.commit()

            print("✅ Test-Daten erfolgreich eingefügt")

        except Exception as e:
            print(f"⚠️  Fehler beim Einfügen von Test-Daten: {e}")
            await session.rollback()


async def verify_setup():
    """Verifiziert die Datenbank-Einrichtung."""
    print("\n🔍 Verifiziere Datenbank-Setup...")

    try:
        async with db_manager.engine.connect() as conn:
            # Prüfe Tabellen
            result = await conn.execute(
                text(
                    """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """
                )
            )

            tables = [row[0] for row in result]
            print(f"\n📋 Gefundene Tabellen: {', '.join(tables)}")

            expected_tables = {"decisions", "anonymization_mappings", "crawl_logs", "crawl_states"}
            missing_tables = expected_tables - set(tables)

            if missing_tables:
                print(f"⚠️  Fehlende Tabellen: {', '.join(missing_tables)}")
                return False

            # Prüfe Extensions
            result = await conn.execute(
                text(
                    """
                SELECT extname 
                FROM pg_extension 
                WHERE extname IN ('uuid-ossp', 'unaccent', 'pg_trgm');
            """
                )
            )

            extensions = [row[0] for row in result]
            print(f"📦 Aktivierte Extensions: {', '.join(extensions)}")

            # Prüfe Volltext-Konfiguration
            result = await conn.execute(
                text(
                    """
                SELECT cfgname 
                FROM pg_ts_config 
                WHERE cfgname = 'german';
            """
                )
            )

            if result.scalar():
                print("🇩🇪 Deutsche Volltext-Konfiguration verfügbar")

            print("\n✅ Datenbank-Setup erfolgreich verifiziert!")
            return True

    except Exception as e:
        print(f"❌ Fehler bei der Verifikation: {e}")
        return False


async def main():
    """Hauptfunktion für Datenbank-Initialisierung."""
    print("🚀 Datenschutz-Rechtsprechung API - Datenbank-Initialisierung")
    print("=" * 50)

    # Prüfe ob Docker läuft (optional)
    if os.system("docker ps > /dev/null 2>&1") != 0:
        print("⚠️  Docker scheint nicht zu laufen.")
        print("💡 Tipp: Starte Docker oder nutze eine externe PostgreSQL-Instanz")

    # Initialisiere DB Manager
    await db_manager.initialize()

    try:
        # Prüfe und erstelle Datenbank
        db_exists = await check_database_exists()
        if not db_exists:
            success = await create_database()
            if not success:
                print("\n❌ Datenbank konnte nicht erstellt werden.")
                print("💡 Bitte prüfe die Verbindungseinstellungen in .env")
                return

            # Re-initialisiere nach DB-Erstellung
            await db_manager.close()
            await db_manager.initialize()

        # Initialisiere Extensions
        await init_extensions()

        # Erstelle Tabellen
        await create_tables()

        # Richte Volltext-Suche ein
        await setup_search_triggers()

        # Füge Test-Daten ein (nur Development)
        await insert_test_data()

        # Verifiziere Setup
        success = await verify_setup()

        if success:
            print("\n" + "=" * 50)
            print("🎉 Datenbank-Initialisierung erfolgreich abgeschlossen!")
            print("\nNächste Schritte:")
            print("1. Kopiere .env.example nach .env und passe die Werte an")
            print("2. Installiere Python-Pakete: pip install -r requirements.txt")
            print("3. Lade spaCy Modell: python -m spacy download de_core_news_sm")
            print("4. Starte die API: uvicorn src.api.main:app --reload")
        else:
            print("\n⚠️  Setup abgeschlossen, aber mit Warnungen.")

    except Exception as e:
        print(f"\n❌ Kritischer Fehler: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await db_manager.close()


if __name__ == "__main__":
    # Führe async main aus
    asyncio.run(main())
