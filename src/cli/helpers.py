#!/usr/bin/env python3
"""
CLI Helper-Funktionen.

Utility-Funktionen für CLI-Commands.
"""

import click
from pathlib import Path
from typing import List, Optional


def show_usage_examples():
    """Zeigt detaillierte Verwendungsbeispiele."""
    click.echo(click.style("\n📚 VERWENDUNGSBEISPIELE - OpenLegalData Import", fg="cyan", bold=True))
    click.echo("=" * 60)

    examples = [
        {
            "title": "1. 🚀 Schnellstart (500 Dokumente)",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --limit 500",
            "description": "Importiert die ersten 500 DSGVO-relevanten Entscheidungen",
        },
        {
            "title": "2. 🧪 Testlauf ohne DB-Änderungen",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --limit 100 --dry-run",
            "description": "Simuliert Import und zeigt nur Statistiken",
        },
        {
            "title": "3. 🔄 Resume nach Unterbrechung",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --limit 5000 --resume",
            "description": "Setzt unterbrochenen Import fort (nutzt .resume.json)",
        },
        {
            "title": "4. ⏭️ Mit Offset (große Dumps)",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --offset 10000 --limit 2000",
            "description": "Überspringt erste 10.000 Dokumente, importiert nächste 2.000",
        },
        {
            "title": "5. 🔍 Alle DSGVO-relevanten (unbegrenzt)",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --limit 0 --filter-gdpr",
            "description": "Importiert ALLE DSGVO-relevanten Dokumente (kann lange dauern!)",
        },
        {
            "title": "6. 📊 Nur hochrelevante (Score 8+)",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --min-score 8 --limit 1000",
            "description": "Importiert nur Dokumente mit hoher DSGVO-Relevanz",
        },
        {
            "title": "7. 💬 Verbose-Modus für Debugging",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --verbose --limit 50",
            "description": "Zeigt detaillierte Debug-Informationen",
        },
        {
            "title": "8. ⚡ Performance-optimiert (große Mengen)",
            "command": "python -m src.cli.commands import-openlegaldata --input cases.json --no-filter --limit 10000",
            "description": "Importiert ohne DSGVO-Filter für maximale Geschwindigkeit",
        },
    ]

    for example in examples:
        click.echo(f"\n{click.style(example['title'], fg='green', bold=True)}")
        click.echo(f"  {example['description']}")
        click.echo(f"  {click.style('$ ' + example['command'], fg='blue')}")

    click.echo("\n" + click.style("💡 TIPPS:", fg="yellow", bold=True))
    click.echo("  • Starte immer mit kleinem --limit zum Testen")
    click.echo("  • Nutze --dry-run um Daten vor Import zu prüfen")
    click.echo("  • --resume ist sicher bei Crashes oder Keyboard-Interrupt")
    click.echo("  • Performance-Metriken helfen bei der Optimierung")
    click.echo("  • Verwende 'examples' für diese Hilfe")

    click.echo("\n" + click.style("⚠️ WARNUNG:", fg="red", bold=True))
    click.echo("  • --limit 0 kann bei großen Dumps (1M+ Docs) sehr lange dauern")
    click.echo("  • Backup der DB vor großen Importen empfohlen")
    click.echo("  • Monitoring des Speicherverbrauchs während langer Läufe")


def show_download_instructions():
    """Zeigt Download-Anweisungen für OpenLegalData Dumps."""
    click.echo(click.style("\n📥 DOWNLOAD-ANWEISUNGEN - OpenLegalData Dumps", fg="cyan", bold=True))
    click.echo("=" * 60)

    click.echo("\n" + click.style("1. Vollständiger Deutschland-Dump:", fg="green", bold=True))
    click.echo("   wget https://static.openlegaldata.io/dumps/de/cases.json.gz")
    click.echo("   gunzip cases.json.gz")
    click.echo("   # Größe: ~5-10 GB entpackt, ~250.000 Entscheidungen")

    click.echo("\n" + click.style("2. Gefilterte Dumps (kleiner):", fg="green", bold=True))
    click.echo("   # Bundesgerichtshof")
    click.echo("   wget https://static.openlegaldata.io/dumps/de/bgh.json.gz")
    click.echo("   ")
    click.echo("   # Bundesverfassungsgericht")
    click.echo("   wget https://static.openlegaldata.io/dumps/de/bverfg.json.gz")

    click.echo("\n" + click.style("3. Alternative Formate:", fg="green", bold=True))
    click.echo("   # JSONL-Format (eine JSON pro Zeile)")
    click.echo("   wget https://static.openlegaldata.io/dumps/de/cases.jsonl.gz")

    click.echo("\n" + click.style("📊 Dump-Eigenschaften:", fg="yellow", bold=True))
    click.echo("   • Format: JSON-Array oder JSONL")
    click.echo("   • Encoding: UTF-8")
    click.echo("   • Kompression: gzip")
    click.echo("   • Update-Zyklus: Monatlich")
    click.echo("   • Lizenz: CC0 (Public Domain)")

    click.echo("\n" + click.style("💡 Empfehlungen:", fg="blue", bold=True))
    click.echo("   • Teste mit kleinem Sample erst:")
    click.echo("     head -n 1000 cases.json > sample.json")
    click.echo("   • Prüfe Speicherplatz vor Download (10+ GB)")
    click.echo("   • Nutze --dry-run für ersten Test")

    click.echo("\n" + click.style("🔗 Weitere Informationen:", fg="magenta"))
    click.echo("   https://de.openlegaldata.io/")
    click.echo("   https://static.openlegaldata.io/dumps/")


def validate_input_parameters(
    input_file: Path,
    filter_gdpr: bool,
    min_score: int,
    limit: int,
    offset: int,
    resume: bool,
    resume_file: Optional[Path],
    dry_run: bool,
) -> List[str]:
    """
    Validiert alle Input-Parameter.

    Args:
        Verschiedene CLI-Parameter

    Returns:
        Liste von Fehlermeldungen (leer wenn alles OK)
    """
    errors = []

    # Datei-Validierung
    try:
        if not input_file.exists():
            errors.append(f"Input-Datei nicht gefunden: {input_file}")
        elif input_file.stat().st_size == 0:
            errors.append(f"Input-Datei ist leer: {input_file}")
        elif input_file.stat().st_size > 50 * 1024 * 1024 * 1024:  # 50GB
            size_gb = input_file.stat().st_size / 1024 / 1024 / 1024
            errors.append(f"Input-Datei sehr groß ({size_gb:.1f}GB) - Überprüfung empfohlen")
    except Exception as e:
        errors.append(f"Fehler beim Prüfen der Input-Datei: {e}")

    # Format-Validierung
    valid_extensions = {".json", ".jsonl", ".gz"}
    file_extensions = set(input_file.suffixes)
    if not any(ext in valid_extensions for ext in file_extensions):
        errors.append(f"Unbekanntes Dateiformat. Unterstützt: .json, .jsonl, .json.gz, .jsonl.gz")

    # Parameter-Bereich prüfen
    if min_score < 0 or min_score > 50:
        errors.append(f"Min-Score muss zwischen 0 und 50 liegen (aktuell: {min_score})")

    if limit < 0:
        errors.append(f"Limit kann nicht negativ sein (aktuell: {limit})")

    if offset < 0:
        errors.append(f"Offset kann nicht negativ sein (aktuell: {offset})")

    # Parameter-Kombinationen prüfen
    if resume and offset > 0:
        errors.append("--resume und --offset sind nicht kompatibel (Resume überschreibt Offset)")

    # Warnungen (keine Fehler, aber wichtige Hinweise)
    if limit == 0 and not dry_run:
        click.echo(
            click.style(
                "⚠️ WARNUNG: --limit 0 (unbegrenzt) ohne --dry-run kann sehr lange dauern!",
                fg="yellow",
                bold=True,
            )
        )

    return errors
