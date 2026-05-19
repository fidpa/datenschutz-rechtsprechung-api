#!/usr/bin/env python
"""
Vereinfachtes OpenLegalData Crawler Script.
Nutzt die Standard-DSGVO-Suchbegriffe des Collectors.
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

logger = get_logger("run_openlegaldata_simple")


async def run_openlegaldata_crawler(max_decisions: int = 100, show_progress: bool = True):
    """
    Führt den OpenLegalData Crawler aus.

    Args:
        max_decisions: Maximale Anzahl zu sammelnder Entscheidungen
        show_progress: Zeige Fortschrittsbalken

    Returns:
        Liste gesammelter Entscheidungen
    """
    logger.info("openlegaldata_crawler_starting", max_decisions=max_decisions)

    # Initialisiere Datenbank
    await db_manager.initialize()

    decisions_collected = []

    try:
        async with db_manager.get_session() as session:
            # Erstelle Collector
            collector = OpenLegalDataCollector(
                session,
                max_pages=10,  # Begrenzen auf 10 Seiten
                page_size=50,  # 50 Entscheidungen pro Seite
            )

            async with collector:
                # Validiere Zugriff
                if not await collector.validate_access():
                    logger.error("OpenLegalData not accessible")
                    click.echo(click.style("❌ OpenLegalData nicht erreichbar!", fg="red"))
                    return []

                click.echo(click.style("✅ OpenLegalData erreichbar", fg="green"))
                click.echo(f"📊 Starte Crawl (max. {max_decisions} Entscheidungen)...")

                # Progress Bar
                if show_progress:
                    pbar = tqdm(
                        total=max_decisions, desc="Sammle DSGVO-Entscheidungen", unit="Entscheidung"
                    )

                # Sammle Entscheidungen
                async for decision in collector.collect(full_crawl=False):
                    if len(decisions_collected) >= max_decisions:
                        break

                    # Speichere in Datenbank
                    try:
                        async with db_manager.get_session() as save_session:
                            # Prüfe ob bereits existiert
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
                                continue

                            # Speichere Decision
                            save_session.add(decision)
                            await save_session.flush()

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
                                    save_session.add(mapping)

                            await save_session.commit()
                            decisions_collected.append(decision)

                            # Zeige Info
                            click.echo(f"  ✅ {decision.title[:60]}..." f" ({decision.court_name})")

                    except Exception as e:
                        logger.error(f"Fehler beim Speichern: {e}")
                        click.echo(f"  ❌ Fehler: {str(e)[:60]}...")

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

    except Exception as e:
        logger.error("crawler_failed", error=str(e))
        click.echo(click.style(f"❌ Fehler: {e}", fg="red"))
        raise

    finally:
        await db_manager.close()

    return decisions_collected


@click.command()
@click.option(
    "--max-decisions", type=int, default=100, help="Maximale Anzahl zu sammelnder Entscheidungen"
)
@click.option("--no-progress", is_flag=True, help="Keine Fortschrittsanzeige")
def main(max_decisions: int, no_progress: bool):
    """
    OpenLegalData Crawler - DSGVO-Entscheidungen

    Sammelt DSGVO-relevante Gerichtsentscheidungen von OpenLegalData.
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
    click.echo("🔍 Verwende Standard-DSGVO-Suchbegriffe")
    click.echo("")

    try:
        decisions = asyncio.run(
            run_openlegaldata_crawler(max_decisions=max_decisions, show_progress=not no_progress)
        )

        if decisions:
            click.echo(
                click.style(
                    f"\n✅ Erfolgreich {len(decisions)} Entscheidungen gesammelt!",
                    fg="green",
                    bold=True,
                )
            )

            # Zeige Gerichte-Statistik
            if decisions:
                courts = {}
                for dec in decisions:
                    court = dec.court_name or "Unbekannt"
                    courts[court] = courts.get(court, 0) + 1

                click.echo("\n📋 Top Gerichte:")
                for court, count in sorted(courts.items(), key=lambda x: x[1], reverse=True)[:5]:
                    click.echo(f"  • {court}: {count}x")
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
