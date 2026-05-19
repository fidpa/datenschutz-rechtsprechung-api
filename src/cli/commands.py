#!/usr/bin/env python3
"""
CLI Commands für Dump-Import-Operationen.

Zentrale Click-Commands für verschiedene Import-Szenarien.
"""

import click
from pathlib import Path
from typing import Optional

from src.importers.openlegaldata import OpenLegalDataImporter
from src.cli.helpers import (
    show_usage_examples,
    show_download_instructions,
    validate_input_parameters,
)


@click.group()
def cli():
    """DSGVO-Gerichtsentscheidungs-Import Tool."""


@cli.command()
@click.option(
    "--input",
    "-i",
    "input_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Pfad zur JSON/JSONL-Dump-Datei (unterstützt .gz)",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=100,
    help="Maximale Anzahl zu importierender Dokumente (0 = unbegrenzt)",
)
@click.option("--offset", "-o", type=int, default=0, help="Anzahl der zu überspringenden Dokumente")
@click.option(
    "--filter-gdpr/--no-filter",
    "filter_gdpr",
    default=True,
    help="Nur DSGVO-relevante Entscheidungen importieren",
)
@click.option("--min-score", "-s", type=int, default=3, help="Minimaler Relevanz-Score (0-50)")
@click.option("--resume/--no-resume", default=False, help="Von letzter Position fortsetzen")
@click.option("--resume-file", type=click.Path(path_type=Path), help="Pfad zur Resume-State-Datei")
@click.option("--dry-run", is_flag=True, help="Simulation ohne Datenbank-Änderungen")
@click.option("--batch-size", type=int, default=50, help="Anzahl Dokumente pro Batch")
@click.option("--verbose", "-v", is_flag=True, help="Detaillierte Debug-Ausgabe")
def import_openlegaldata(
    input_file: Path,
    limit: int,
    offset: int,
    filter_gdpr: bool,
    min_score: int,
    resume: bool,
    resume_file: Optional[Path],
    dry_run: bool,
    batch_size: int,
    verbose: bool,
):
    """
    Importiert DSGVO-relevante Entscheidungen aus OpenLegalData Dumps.

    \b
    Beispiele:
      # Schnellstart mit 500 Dokumenten
      python -m src.cli.commands import-openlegaldata --input cases.json --limit 500

      # Dry-Run zum Testen
      python -m src.cli.commands import-openlegaldata --input cases.json --dry-run --limit 100

      # Resume nach Unterbrechung
      python -m src.cli.commands import-openlegaldata --input cases.json --resume
    """
    # Parameter validieren
    errors = validate_input_parameters(
        input_file=input_file,
        filter_gdpr=filter_gdpr,
        min_score=min_score,
        limit=limit,
        offset=offset,
        resume=resume,
        resume_file=resume_file,
        dry_run=dry_run,
    )

    if errors:
        click.echo(click.style("❌ Validierungsfehler:", fg="red", bold=True))
        for error in errors:
            click.echo(f"  • {error}")
        raise click.Abort()

    # Header anzeigen
    click.echo(click.style("\n🚀 OpenLegalData Dump Import", fg="cyan", bold=True))
    click.echo("=" * 60)
    click.echo(f"📁 Input: {input_file}")
    click.echo(f"🎯 Limit: {limit if limit > 0 else 'Unbegrenzt'}")
    click.echo(f"📊 Min-Score: {min_score}")
    click.echo(f"🔍 DSGVO-Filter: {'Aktiv' if filter_gdpr else 'Inaktiv'}")

    if dry_run:
        click.echo(click.style("🧪 DRY-RUN MODUS - Keine DB-Änderungen", fg="yellow"))
    if resume:
        click.echo(click.style("🔄 RESUME MODUS - Fortsetzung von letzter Position", fg="yellow"))

    click.echo("=" * 60 + "\n")

    # Importer initialisieren und ausführen
    importer = OpenLegalDataImporter(verbose=verbose, min_score=min_score)

    try:
        importer.import_from_file(
            file_path=input_file,
            limit=limit,
            offset=offset,
            filter_relevant=filter_gdpr,
            resume=resume,
            dry_run=dry_run,
            batch_size=batch_size,
        )

        # Erfolg!
        click.echo(click.style("\n✅ Import erfolgreich abgeschlossen!", fg="green", bold=True))

    except KeyboardInterrupt:
        click.echo(click.style("\n⚠️ Import unterbrochen - Resume-State gespeichert", fg="yellow"))
        raise click.Abort()

    except Exception as e:
        click.echo(click.style(f"\n❌ Import-Fehler: {e}", fg="red"))
        raise


@cli.command()
def examples():
    """Zeigt detaillierte Verwendungsbeispiele."""
    show_usage_examples()


@cli.command()
def download():
    """Zeigt Download-Anweisungen für OpenLegalData Dumps."""
    show_download_instructions()


@cli.command()
@click.option(
    "--input",
    "-i",
    "input_file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Pfad zur JSON/JSONL-Dump-Datei",
)
@click.option("--sample-size", type=int, default=1000, help="Anzahl zu analysierender Dokumente")
def analyze_scores(input_file: Path, sample_size: int):
    """
    Analysiert DSGVO-Relevanz-Score-Verteilung in einer Dump-Datei.

    Hilfreich um optimalen --min-score Wert zu bestimmen.
    """
    click.echo(click.style("\n📊 Score-Analyse", fg="cyan", bold=True))
    click.echo("=" * 60)
    click.echo(f"📁 Input: {input_file}")
    click.echo(f"📈 Sample: {sample_size} Dokumente\n")

    importer = OpenLegalDataImporter()
    distribution = importer.get_score_distribution(input_file, sample_size)

    # Statistiken berechnen
    total_docs = sum(distribution.values())
    cumulative = 0

    click.echo(click.style("Score-Verteilung:", fg="green", bold=True))
    click.echo("-" * 40)

    for score, count in distribution.items():
        cumulative += count
        percentage = (count / total_docs) * 100
        cumulative_pct = (cumulative / total_docs) * 100

        # Visualisierung mit Balken
        bar_length = int(percentage / 2)
        bar = "█" * bar_length

        click.echo(f"Score {score:2d}: {count:4d} ({percentage:5.1f}%) {bar}")

        # Wichtige Schwellenwerte hervorheben
        if score in [3, 5, 8, 10]:
            click.echo(
                f"         → Kumulativ bis Score {score}: {cumulative} ({cumulative_pct:.1f}%)"
            )

    click.echo("-" * 40)
    click.echo(f"Gesamt analysiert: {total_docs} Dokumente")

    # Empfehlungen
    click.echo(click.style("\n💡 Empfehlungen:", fg="yellow", bold=True))

    high_score_docs = sum(count for score, count in distribution.items() if score >= 8)
    medium_score_docs = sum(count for score, count in distribution.items() if score >= 5)

    if high_score_docs > 0:
        click.echo(f"  • Für hochrelevante Fälle: --min-score 8 ({high_score_docs} Dokumente)")
    if medium_score_docs > 0:
        click.echo(f"  • Für breite Abdeckung: --min-score 5 ({medium_score_docs} Dokumente)")
    click.echo(f"  • Für alle potenziell relevanten: --min-score 3 (Standard)")


if __name__ == "__main__":
    cli()
