#!/usr/bin/env python
"""
Umfassendes Script zum Befüllen der Datenbank mit DSGVO-Entscheidungen.
Kombiniert GDPRhub und OpenLegalData für maximale Datenvielfalt.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import click
from tqdm.asyncio import tqdm
from collections import Counter
import hashlib

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db_manager, Decision, AnonymizationMapping, get_async_session
from src.collectors.gdprhub import GDPRhubCollector
from src.collectors.openlegaldata import OpenLegalDataCollector
from src.processors.deduplicator import DecisionDeduplicator
from src.utils.logging import get_logger
from sqlalchemy import select, func

logger = get_logger("fill_database")


async def collect_gdprhub_decisions(max_pages: int = 50):
    """
    Sammelt Entscheidungen von GDPRhub.

    Args:
        max_pages: Maximale Anzahl zu crawlender Seiten

    Returns:
        Anzahl gesammelter Entscheidungen
    """
    logger.info(f"Starting GDPRhub collection (max {max_pages} pages)")
    decisions_collected = 0

    async with get_async_session() as session:
        collector = GDPRhubCollector(session, max_pages=max_pages)

        async with collector:
            if not await collector.validate_access():
                logger.error("GDPRhub not accessible")
                return 0

            click.echo(click.style("✅ GDPRhub ist erreichbar", fg="green"))

            # Progress Bar
            pbar = tqdm(total=max_pages, desc="GDPRhub Entscheidungen", unit="Seite")

            async for decision in collector.collect(full_crawl=False):
                try:
                    # Prüfe ob bereits vorhanden
                    existing = await session.execute(
                        select(Decision).where(
                            Decision.source == decision.source,
                            Decision.source_id == decision.source_id,
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    # Speichere Decision
                    session.add(decision)
                    await session.flush()

                    # Speichere Anonymisierungs-Mappings
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
                            session.add(mapping)

                    await session.commit()
                    decisions_collected += 1

                except Exception as e:
                    logger.error(f"Error saving decision: {e}")

                pbar.update(1)

            pbar.close()

            # Statistiken
            stats = collector.calculate_progress()
            click.echo(f"  📊 GDPRhub: {decisions_collected} neue Entscheidungen")
            click.echo(f"  ⏱️ Rate: {stats.get('fetch_rate', 0):.2f} Seiten/s")

    return decisions_collected


async def collect_openlegaldata_decisions(max_decisions: int = 100):
    """
    Sammelt DSGVO-relevante Entscheidungen von OpenLegalData.

    Args:
        max_decisions: Maximale Anzahl zu sammelnder Entscheidungen

    Returns:
        Anzahl gesammelter Entscheidungen
    """
    logger.info(f"Starting OpenLegalData collection (max {max_decisions} decisions)")
    decisions_collected = 0

    async with get_async_session() as session:
        # Mehrere Durchläufe mit verschiedenen Keywords für bessere Abdeckung
        keywords = [
            "DSGVO",
            "Datenschutz-Grundverordnung",
            "Art. 6 DSGVO",
            "Art. 13 DSGVO",
            "Art. 15 DSGVO",
            "personenbezogene Daten",
            "Betroffenenrechte",
        ]

        decisions_per_keyword = max_decisions // len(keywords)

        for keyword in keywords:
            if decisions_collected >= max_decisions:
                break

            click.echo(f"\n🔍 Suche nach: {keyword}")

            collector = OpenLegalDataCollector(
                session,
                max_pages=2,  # 2 Seiten pro Keyword
                page_size=decisions_per_keyword,
                search_query=keyword,
            )

            async with collector:
                if not await collector.validate_access():
                    logger.error("OpenLegalData not accessible")
                    continue

                # Progress Bar
                pbar = tqdm(
                    total=decisions_per_keyword,
                    desc=f"OpenLegalData [{keyword[:20]}]",
                    unit="Entscheidung",
                )

                keyword_collected = 0
                async for decision in collector.collect(full_crawl=False):
                    try:
                        # Prüfe ob bereits vorhanden
                        existing = await session.execute(
                            select(Decision).where(
                                Decision.source == decision.source,
                                Decision.source_id == decision.source_id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            continue

                        # Speichere Decision
                        session.add(decision)
                        await session.flush()

                        # Speichere Anonymisierungs-Mappings
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
                                session.add(mapping)

                        await session.commit()
                        decisions_collected += 1
                        keyword_collected += 1

                    except Exception as e:
                        logger.error(f"Error saving decision: {e}")

                    pbar.update(1)

                    if keyword_collected >= decisions_per_keyword:
                        break

                pbar.close()

                # Statistiken pro Keyword
                stats = collector.calculate_progress()
                click.echo(f"  ✅ {keyword}: {keyword_collected} Entscheidungen")

    click.echo(f"\n📊 OpenLegalData Gesamt: {decisions_collected} neue Entscheidungen")
    return decisions_collected


async def deduplicate_database():
    """Führt Deduplizierung der Datenbank durch."""
    click.echo("\n🔍 Starte Deduplizierung...")

    async with get_async_session() as session:
        deduplicator = DecisionDeduplicator(session)

        # Dedupliziere nach Aktenzeichen
        duplicates_removed = await deduplicator.deduplicate_by_case_number()
        click.echo(f"  ✅ {duplicates_removed} Duplikate entfernt")

        # Statistiken
        stats = await deduplicator.get_statistics()
        click.echo(f"  📊 Gesamt: {stats['database_stats']['total_decisions']} Entscheidungen")
        click.echo(f"  📊 Eindeutig: {stats['database_stats']['unique_case_numbers']} Aktenzeichen")


async def show_statistics():
    """Zeigt detaillierte Datenbankstatistiken."""
    click.echo("\n" + "=" * 60)
    click.echo(click.style("📊 DATENBANKSTATISTIKEN", fg="cyan", bold=True))
    click.echo("=" * 60)

    async with get_async_session() as session:
        # Gesamt
        total = await session.scalar(select(func.count(Decision.id)))
        click.echo(f"\n📈 Gesamt: {total} Entscheidungen")

        # Nach Quelle
        by_source = await session.execute(
            select(Decision.source, func.count(Decision.id)).group_by(Decision.source)
        )
        click.echo("\n🌐 Nach Datenquelle:")
        for source, count in by_source.all():
            click.echo(f"  • {source}: {count}")

        # Nach Gericht (Top 10)
        by_court = await session.execute(
            select(Decision.court, func.count(Decision.id))
            .group_by(Decision.court)
            .order_by(func.count(Decision.id).desc())
            .limit(10)
        )
        click.echo("\n⚖️ Top 10 Gerichte:")
        for court, count in by_court.all():
            click.echo(f"  • {court}: {count}")

        # DSGVO-Artikel Statistik
        all_articles = []
        decisions = await session.execute(select(Decision.gdpr_articles))
        for (articles,) in decisions:
            if articles:
                all_articles.extend(articles)

        if all_articles:
            article_counts = Counter(all_articles)
            click.echo("\n📋 Top 10 DSGVO-Artikel:")
            for article, count in article_counts.most_common(10):
                click.echo(f"  • {article}: {count}x")

        # Zeitliche Verteilung
        date_range = await session.execute(
            select(func.min(Decision.decision_date), func.max(Decision.decision_date))
        )
        min_date, max_date = date_range.one()
        if min_date and max_date:
            click.echo(f"\n📅 Zeitraum: {min_date} bis {max_date}")


@click.command()
@click.option("--gdprhub-pages", default=50, help="Anzahl GDPRhub Seiten")
@click.option("--openlegaldata-count", default=100, help="Anzahl OpenLegalData Entscheidungen")
@click.option("--skip-gdprhub", is_flag=True, help="GDPRhub überspringen")
@click.option("--skip-openlegaldata", is_flag=True, help="OpenLegalData überspringen")
@click.option("--no-dedup", is_flag=True, help="Keine Deduplizierung")
def main(gdprhub_pages, openlegaldata_count, skip_gdprhub, skip_openlegaldata, no_dedup):
    """
    Befüllt die Datenschutz-Rechtsprechung API Datenbank mit vielfältigen Entscheidungen.

    Sammelt Daten von GDPRhub und OpenLegalData für optimale Test-Coverage.
    """
    click.echo(
        click.style(
            """
    ╔════════════════════════════════════════════════╗
    ║        GDPR CRAWLER - DATABASE FILLER          ║
    ║         Umfassende Datenbankbefüllung          ║
    ╚════════════════════════════════════════════════╝
    """,
            fg="cyan",
            bold=True,
        )
    )

    click.echo(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"🎯 Ziel: Mindestens 150 Entscheidungen sammeln")
    click.echo("")

    async def run():
        # Initialisiere Datenbank
        await db_manager.initialize()

        total_collected = 0

        try:
            # 1. GDPRhub
            if not skip_gdprhub:
                click.echo(click.style("\n1️⃣ GDPRhub Collection", fg="yellow", bold=True))
                dsr_count = await collect_gdprhub_decisions(gdprhub_pages)
                total_collected += dsr_count

            # 2. OpenLegalData
            if not skip_openlegaldata:
                click.echo(click.style("\n2️⃣ OpenLegalData Collection", fg="yellow", bold=True))
                old_count = await collect_openlegaldata_decisions(openlegaldata_count)
                total_collected += old_count

            # 3. Deduplizierung
            if not no_dedup:
                click.echo(click.style("\n3️⃣ Deduplizierung", fg="yellow", bold=True))
                await deduplicate_database()

            # 4. Statistiken
            await show_statistics()

            click.echo(
                click.style(
                    f"\n✅ Erfolgreich {total_collected} neue Entscheidungen gesammelt!",
                    fg="green",
                    bold=True,
                )
            )

        except Exception as e:
            click.echo(click.style(f"\n❌ Fehler: {e}", fg="red"))
            logger.error("Database filling failed", error=str(e), exc_info=True)
            raise

        finally:
            await db_manager.close()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        click.echo(click.style("\n\n⚠️ Befüllung durch Benutzer abgebrochen.", fg="yellow"))
        sys.exit(1)


if __name__ == "__main__":
    main()
