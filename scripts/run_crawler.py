#!/usr/bin/env python
"""
CLI-Script für manuellen Crawler-Start.
Ermöglicht das Testen und manuelle Ausführen der Crawler.
"""

import asyncio
import sys
from pathlib import Path
import click
from datetime import datetime
from typing import Optional
from tqdm.asyncio import tqdm

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db_manager, Decision, AnonymizationMapping
from src.collectors.gdprhub import GDPRhubCollector
from src.config import settings
from src.utils.logging import get_logger
import hashlib

logger = get_logger("run_crawler")


async def run_gdprhub_crawler(
    max_pages: int = 10,
    full_crawl: bool = False,
    show_progress: bool = True,
    mode: str = GDPRhubCollector.MODE_CATEGORIES,
    years: tuple = None,
):
    """
    Führt den GDPRhub Crawler aus.

    Args:
        max_pages: Maximale Anzahl zu sammelnder Entscheidungen
        full_crawl: Vollständiger Crawl (ignoriert gespeicherten State)
        show_progress: Zeige Fortschrittsbalken
        mode: "categories" (Default, mehrere Jahre via Category:YYYY) oder
              "newpages" (Special:NewPages, ~85 jüngste Wiki-Einträge)
        years: Jahre für Modus "categories" (Default: 2026..2018)
    """
    logger.info(
        "gdprhub_crawler_starting",
        max_pages=max_pages,
        full_crawl=full_crawl,
        mode=mode,
        years=years,
    )

    # Initialisiere Datenbank
    await db_manager.initialize()

    decisions_collected = []

    try:
        async with db_manager.get_session() as session:
            # Erstelle Collector
            collector = GDPRhubCollector(session, max_pages=max_pages, mode=mode, years=years)

            async with collector:
                # Validiere Zugriff
                if not await collector.validate_access():
                    logger.error("gdprhub_not_accessible")
                    click.echo(click.style("❌ GDPRhub ist nicht erreichbar!", fg="red"))
                    return

                click.echo(click.style("✅ GDPRhub ist erreichbar", fg="green"))
                click.echo(f"📊 Starte Crawl (max. {max_pages} Seiten)...")

                # Progress Bar
                if show_progress:
                    pbar = tqdm(total=max_pages, desc="Sammle Entscheidungen", unit="Entscheidung")

                # Sammle Entscheidungen
                async for decision in collector.collect(full_crawl=full_crawl):
                    # Speichere in Datenbank
                    try:
                        async with db_manager.get_session() as save_session:
                            # Prüfe ob Entscheidung bereits existiert
                            from sqlalchemy import select

                            existing = await save_session.execute(
                                select(Decision).where(
                                    Decision.source == decision.source,
                                    Decision.source_id == decision.source_id,
                                )
                            )
                            if existing.scalar_one_or_none():
                                click.echo(f"  ⏭️  {decision.title[:60]}... (bereits vorhanden)")
                                if show_progress:
                                    pbar.update(1)
                                break

                            # Speichere Decision
                            save_session.add(decision)
                            await save_session.flush()  # Generiere ID

                            # Speichere Anonymisierungs-Mappings wenn vorhanden
                            if (
                                hasattr(decision, "_anonymization_result")
                                and decision._anonymization_result
                            ):
                                result = decision._anonymization_result
                                for placeholder, original in result.mappings.items():
                                    mapping = AnonymizationMapping(
                                        decision_id=decision.id,
                                        placeholder=placeholder,
                                        original_hash=hashlib.sha256(original.encode()).hexdigest(),
                                        entity_type=result.entity_types.get(placeholder, "UNKNOWN"),
                                    )
                                    save_session.add(mapping)

                            await save_session.commit()
                            decisions_collected.append(decision)

                            # Zeige Info
                            click.echo(
                                f"  ✅ {decision.title[:80]}..."
                                f" ({len(decision.gdpr_articles or [])} DSGVO-Artikel)"
                            )
                            break
                    except Exception as e:
                        logger.error(f"Fehler beim Speichern: {e}")
                        click.echo(f"  ❌ Fehler beim Speichern: {decision.title[:60]}...")

                    if show_progress:
                        pbar.update(1)

                if show_progress:
                    pbar.close()

                # Zeige Statistiken
                stats = collector.calculate_progress()

                click.echo("\n" + "=" * 60)
                click.echo(click.style("📈 Crawl-Statistiken:", fg="cyan", bold=True))
                click.echo(f"  • Entscheidungen gesammelt: {len(decisions_collected)}")
                click.echo(f"  • Seiten abgerufen: {stats.get('total_fetched', 0)}")
                click.echo(f"  • Erfolgreich verarbeitet: {stats.get('total_processed', 0)}")
                click.echo(f"  • Fehler: {stats.get('total_errors', 0)}")
                click.echo(f"  • Laufzeit: {stats.get('elapsed_seconds', 0):.1f} Sekunden")
                click.echo(f"  • Rate: {stats.get('fetch_rate', 0):.2f} Seiten/Sekunde")
                click.echo("=" * 60)

                # Zeige DSGVO-Artikel Statistik
                if decisions_collected:
                    all_articles = []
                    for dec in decisions_collected:
                        if dec.gdpr_articles:
                            all_articles.extend(dec.gdpr_articles)

                    if all_articles:
                        from collections import Counter

                        article_counts = Counter(all_articles)

                        click.echo("\n" + click.style("📋 Top DSGVO-Artikel:", fg="cyan", bold=True))
                        for article, count in article_counts.most_common(5):
                            click.echo(f"  • {article}: {count}x")

    except Exception as e:
        logger.error("crawler_failed", error=str(e))
        click.echo(click.style(f"❌ Fehler: {e}", fg="red"))
        raise

    finally:
        await db_manager.close()

    return decisions_collected


async def test_components():
    """Testet einzelne Komponenten."""
    click.echo(click.style("\n🧪 Teste Komponenten...\n", fg="cyan", bold=True))

    # Test DSGVO-Extraktor
    click.echo("1️⃣ Teste DSGVO-Artikel-Extraktor...")
    from src.analyzers.gdpr_extractor import GDPRArticleExtractor

    extractor = GDPRArticleExtractor()
    test_text = """
    Die Verarbeitung nach Art. 6 Abs. 1 lit. a DSGVO ist nur mit Einwilligung zulässig.
    Siehe auch Art. 13 DSGVO und § 26 BDSG für weitere Informationen.
    Das OLG München entschied mit Urteil vom 15.03.2024 (Az. 6 U 5042/19).
    """

    gdpr_articles, bdsg_sections = extractor.extract_all(test_text)
    click.echo(f"   ✅ DSGVO-Artikel gefunden: {gdpr_articles}")
    click.echo(f"   ✅ BDSG-Paragraphen gefunden: {bdsg_sections}")

    # Test Anonymisierer
    click.echo("\n2️⃣ Teste Anonymisierer...")

    # Prüfe ob spaCy Modell installiert ist
    try:
        from src.processors.anonymizer import GermanLegalAnonymizer

        anonymizer = GermanLegalAnonymizer()
        test_text = (
            "Der Kläger Max Mustermann verklagt die Beklagte Erika Musterfrau vor dem OLG München."
        )

        result = anonymizer.anonymize(test_text)
        click.echo(f"   Original: {test_text}")
        click.echo(f"   ✅ Anonymisiert: {result.anonymized_text}")

    except Exception as e:
        click.echo(
            click.style(
                f"   ⚠️ Anonymisierer nicht verfügbar: {e}\n"
                f"   Installiere mit: python -m spacy download de_core_news_sm",
                fg="yellow",
            )
        )

    # Test Datenbankverbindung
    click.echo("\n3️⃣ Teste Datenbankverbindung...")
    try:
        await db_manager.initialize()
        async for session in db_manager.get_session():
            # Teste Verbindung
            from sqlalchemy import select, func

            result = await session.execute(select(func.count()).select_from(Decision))
            count = result.scalar()
            click.echo(f"   ✅ Datenbankverbindung OK ({count} Entscheidungen vorhanden)")
            break
    except Exception as e:
        click.echo(click.style(f"   ❌ Datenbankfehler: {e}", fg="red"))
    finally:
        await db_manager.close()

    click.echo(click.style("\n✨ Komponententest abgeschlossen!\n", fg="green", bold=True))


@click.command()
@click.option(
    "--source",
    type=click.Choice(["gdprhub", "test"], case_sensitive=False),
    default="gdprhub",
    help="Datenquelle für Crawl",
)
@click.option("--max-pages", type=int, default=10, help="Maximale Anzahl zu crawlender Seiten")
@click.option("--full", is_flag=True, help="Vollständiger Crawl (ignoriert gespeicherten State)")
@click.option("--no-progress", is_flag=True, help="Keine Fortschrittsanzeige")
@click.option(
    "--mode",
    type=click.Choice(["categories", "newpages"], case_sensitive=False),
    default="categories",
    help="GDPRhub-Crawl-Strategie (categories: mehrere Jahre, newpages: ~85 jüngste)",
)
@click.option(
    "--years",
    type=str,
    default=None,
    help='Komma-separierte Jahre für mode=categories (z. B. "2025,2024,2023"). '
    "Default: 2026..2018",
)
def main(
    source: str,
    max_pages: int,
    full: bool,
    no_progress: bool,
    mode: str,
    years: str,
):
    """
    Datenschutz-Rechtsprechung API - Manueller Start

    Sammelt DSGVO-Gerichtsentscheidungen aus verschiedenen Quellen.
    """
    click.echo(
        click.style(
            """
    ╔══════════════════════════════════════════╗
    ║         GDPR CRAWLER - Phase 2           ║
    ║     DSGVO-Entscheidungen sammeln         ║
    ╚══════════════════════════════════════════╝
    """,
            fg="cyan",
            bold=True,
        )
    )

    years_tuple = None
    if years:
        years_tuple = tuple(int(y.strip()) for y in years.split(",") if y.strip())

    click.echo(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"🎯 Quelle: {source.upper()}")
    click.echo(f"📊 Max. Seiten: {max_pages}")
    click.echo(f"🔄 Modus: {'Vollständig' if full else 'Inkrementell'}")
    if source == "gdprhub":
        click.echo(f"🗺️  GDPRhub-Strategie: {mode}")
        if mode == "categories":
            click.echo(f"📆 Jahre: {years_tuple or 'Default (2026..2018)'}")
    click.echo("")

    try:
        if source == "test":
            # Führe Komponententests aus
            asyncio.run(test_components())
        elif source == "gdprhub":
            # Führe GDPRhub Crawler aus
            decisions = asyncio.run(
                run_gdprhub_crawler(
                    max_pages=max_pages,
                    full_crawl=full,
                    show_progress=not no_progress,
                    mode=mode,
                    years=years_tuple,
                )
            )

            if decisions:
                click.echo(
                    click.style(
                        f"\n✅ Erfolgreich {len(decisions)} Entscheidungen gesammelt!",
                        fg="green",
                        bold=True,
                    )
                )
            else:
                click.echo(click.style("\n⚠️ Keine neuen Entscheidungen gefunden.", fg="yellow"))

    except KeyboardInterrupt:
        click.echo(click.style("\n\n⚠️ Crawl durch Benutzer abgebrochen.", fg="yellow"))
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"\n❌ Fehler: {e}", fg="red"))
        logger.error("crawler_error", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
