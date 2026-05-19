#!/usr/bin/env python
"""
OpenLegalData Crawler Script mit verbesserter Fehlerbehandlung.
Sammelt gezielt DSGVO-relevante Entscheidungen.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import click
from tqdm.asyncio import tqdm
import hashlib

# Füge src zum Python-Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import db_manager, Decision, AnonymizationMapping
from src.collectors.openlegaldata import OpenLegalDataCollector
from src.utils.logging import get_logger
from sqlalchemy import select

logger = get_logger("run_openlegaldata")


async def run_openlegaldata_crawler(
    search_terms: list = None, max_decisions: int = 100, show_progress: bool = True
):
    """
    Führt den OpenLegalData Crawler aus.

    Args:
        search_terms: Liste von Suchbegriffen (DSGVO-bezogen)
        max_decisions: Maximale Anzahl zu sammelnder Entscheidungen
        show_progress: Zeige Fortschrittsbalken

    Returns:
        Liste gesammelter Entscheidungen
    """
    if search_terms is None:
        search_terms = [
            "DSGVO",
            "Datenschutz-Grundverordnung",
            "Art. 6 DSGVO",
            "Art. 13 DSGVO",
            "Art. 15 DSGVO",
            "Art. 17 DSGVO",
            "personenbezogene Daten",
            "Betroffenenrechte",
            "Datenschutzverstoß",
            "GDPR",
        ]

    logger.info(
        "openlegaldata_crawler_starting", max_decisions=max_decisions, search_terms=search_terms
    )

    # Initialisiere Datenbank
    await db_manager.initialize()

    decisions_collected = []
    decisions_per_term = max_decisions // len(search_terms)

    try:
        for search_term in search_terms:
            if len(decisions_collected) >= max_decisions:
                break

            click.echo(f"\n🔍 Suche nach: '{search_term}'")

            async with db_manager.get_session() as session:
                # Erstelle Collector
                collector = OpenLegalDataCollector(
                    session, max_pages=3, page_size=20  # Mehrere Seiten pro Begriff  # 20 pro Seite
                )

                async with collector:
                    # Validiere Zugriff
                    if not await collector.validate_access():
                        logger.error(f"OpenLegalData not accessible for term: {search_term}")
                        click.echo(click.style(f"❌ OpenLegalData nicht erreichbar!", fg="red"))
                        continue

                    click.echo(click.style(f"✅ OpenLegalData erreichbar", fg="green"))

                    # Progress Bar
                    if show_progress:
                        pbar = tqdm(
                            total=decisions_per_term,
                            desc=f"Sammle [{search_term[:20]}]",
                            unit="Entscheidung",
                        )

                    term_collected = 0

                    # Sammle Entscheidungen
                    async for decision in collector.collect(full_crawl=False):
                        if term_collected >= decisions_per_term:
                            break

                        # Speichere in Datenbank
                        try:
                            async with db_manager.get_session() as db_session:
                                # Prüfe ob bereits existiert
                                existing = await db_session.execute(
                                    select(Decision).where(
                                        Decision.source == decision.source,
                                        Decision.source_id == decision.source_id,
                                    )
                                )
                                if existing.scalar_one_or_none():
                                    if show_progress:
                                        pbar.update(1)
                                    continue

                                # Speichere Decision
                                db_session.add(decision)
                                await db_session.flush()

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
                                            original_hash=hashlib.sha256(
                                                original.encode()
                                            ).hexdigest(),
                                            entity_type=result.entity_types.get(
                                                placeholder, "UNKNOWN"
                                            ),
                                        )
                                        db_session.add(mapping)

                                await db_session.commit()
                                decisions_collected.append(decision)
                                term_collected += 1

                                # Zeige Info
                                click.echo(f"  ✅ {decision.title[:60]}..." f" ({decision.court})")

                        except Exception as e:
                            logger.error(f"Fehler beim Speichern: {e}")
                            click.echo(f"  ❌ Fehler: {str(e)[:60]}...")

                        if show_progress:
                            pbar.update(1)

                    if show_progress:
                        pbar.close()

                    # Zeige Statistiken für diesen Begriff
                    stats = collector.calculate_progress()
                    click.echo(f"  📊 '{search_term}': {term_collected} neue Entscheidungen")
                    click.echo(f"  ⏱️ Rate: {stats.get('fetch_rate', 0):.2f} Seiten/s")

    except Exception as e:
        logger.error("crawler_failed", error=str(e))
        click.echo(click.style(f"❌ Fehler: {e}", fg="red"))
        raise

    finally:
        await db_manager.close()

    # Zeige Gesamtstatistik
    click.echo("\n" + "=" * 60)
    click.echo(click.style("📈 Crawler-Gesamtstatistiken:", fg="cyan", bold=True))
    click.echo(f"  • Entscheidungen gesammelt: {len(decisions_collected)}")
    click.echo(f"  • Suchbegriffe verwendet: {len(search_terms)}")

    if decisions_collected:
        # Gerichte-Statistik
        courts = {}
        for dec in decisions_collected:
            court = dec.court or "Unbekannt"
            courts[court] = courts.get(court, 0) + 1

        click.echo("\n📋 Top Gerichte:")
        for court, count in sorted(courts.items(), key=lambda x: x[1], reverse=True)[:5]:
            click.echo(f"  • {court}: {count}x")

    click.echo("=" * 60)

    return decisions_collected


@click.command()
@click.option(
    "--max-decisions", type=int, default=100, help="Maximale Anzahl zu sammelnder Entscheidungen"
)
@click.option("--search-term", multiple=True, help="Suchbegriffe (mehrfach verwendbar)")
@click.option("--no-progress", is_flag=True, help="Keine Fortschrittsanzeige")
def main(max_decisions: int, search_term: tuple, no_progress: bool):
    """
    OpenLegalData Crawler - DSGVO-Entscheidungen

    Sammelt gezielt DSGVO-relevante Gerichtsentscheidungen von OpenLegalData.
    """
    click.echo(
        click.style(
            """
    ╔══════════════════════════════════════════╗
    ║      OPENLEGALDATA CRAWLER               ║
    ║   DSGVO-Entscheidungen sammeln           ║
    ╚══════════════════════════════════════════╝
    """,
            fg="cyan",
            bold=True,
        )
    )

    click.echo(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"🎯 Quelle: OpenLegalData API")
    click.echo(f"📊 Max. Entscheidungen: {max_decisions}")

    # Verwende eigene Suchbegriffe wenn angegeben
    search_terms = list(search_term) if search_term else None

    if search_terms:
        click.echo(f"🔍 Suchbegriffe: {', '.join(search_terms)}")
    else:
        click.echo("🔍 Verwende Standard-DSGVO-Suchbegriffe")

    click.echo("")

    try:
        decisions = asyncio.run(
            run_openlegaldata_crawler(
                search_terms=search_terms,
                max_decisions=max_decisions,
                show_progress=not no_progress,
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
