#!/usr/bin/env python3
"""
Swiss Court Rulings Import Script mit Parquet-Support.

Löst das Hugging Face trust_remote_code Problem durch direkten Parquet-Download.
"""

import click
import pandas as pd
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
from tqdm import tqdm
import time

from src.importers.swiss_datasets import SwissDatasetImporter
from src.utils.logging import get_logger

logger = get_logger("SwissImportScript")


class SwissParquetLoader:
    """Lädt Schweizer Gerichtsentscheidungen direkt von Hugging Face Parquet-Files."""

    # Direkte Parquet-URLs (umgeht trust_remote_code Problem)
    PARQUET_URLS = {
        "swiss_rulings": [
            "https://huggingface.co/datasets/rcds/swiss_rulings/resolve/main/data/train-00000-of-00001.parquet"
        ],
        "swiss_judgment_prediction": [
            "https://huggingface.co/datasets/rcds/swiss_judgment_prediction/resolve/main/train.parquet",
            "https://huggingface.co/datasets/rcds/swiss_judgment_prediction/resolve/main/test.parquet",
        ],
        "swiss_judgment_prediction_xl": [
            "https://huggingface.co/datasets/rcds/swiss_judgment_prediction_xl/resolve/main/data/train-00000-of-00002.parquet",
            "https://huggingface.co/datasets/rcds/swiss_judgment_prediction_xl/resolve/main/data/train-00001-of-00002.parquet",
        ],
    }

    # Alternative: SwissLegalBench URLs
    SWISS_LEGAL_BENCH = {
        "criticality_prediction": "https://huggingface.co/datasets/rcds/swiss_legal_criticality/resolve/main/data.parquet",
        "citation_extraction": "https://huggingface.co/datasets/rcds/swiss_legal_citation/resolve/main/data.parquet",
    }

    @staticmethod
    def download_parquet(url: str, cache_dir: Path = Path("data/cache")) -> Optional[Path]:
        """
        Lädt Parquet-Datei herunter mit Caching.

        Args:
            url: URL der Parquet-Datei
            cache_dir: Cache-Verzeichnis

        Returns:
            Pfad zur heruntergeladenen Datei oder None bei Fehler
        """
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache-Dateiname aus URL
        filename = url.split("/")[-1]
        cache_path = cache_dir / filename

        # Prüfe Cache
        if cache_path.exists():
            logger.info(f"Verwende gecachte Datei: {cache_path}")
            return cache_path

        # Download mit Progress
        try:
            logger.info(f"Lade herunter: {url}")
            response = requests.get(url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(cache_path, "wb") as f:
                with tqdm(total=total_size, unit="iB", unit_scale=True, desc=filename) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))

            logger.info(f"Download abgeschlossen: {cache_path}")
            return cache_path

        except Exception as e:
            logger.error(f"Download-Fehler: {e}")
            if cache_path.exists():
                cache_path.unlink()  # Lösche unvollständige Datei
            return None

    @staticmethod
    def load_dataset(dataset_name: str, limit: int = 0) -> List[Dict[str, Any]]:
        """
        Lädt Dataset von Parquet-Files.

        Args:
            dataset_name: Name des Datasets
            limit: Maximale Anzahl von Dokumenten (0 = alle)

        Returns:
            Liste von Dokumenten als Dictionaries
        """
        urls = SwissParquetLoader.PARQUET_URLS.get(dataset_name, [])

        if not urls:
            logger.error(f"Unbekanntes Dataset: {dataset_name}")
            return []

        all_documents = []

        for url in urls:
            # Download Parquet
            parquet_path = SwissParquetLoader.download_parquet(url)
            if not parquet_path:
                continue

            try:
                # Lade mit Pandas
                logger.info(f"Lade Parquet-Datei: {parquet_path}")
                df = pd.read_parquet(parquet_path)

                # Konvertiere zu Dict-Format
                documents = df.to_dict("records")
                all_documents.extend(documents)

                logger.info(f"Geladen: {len(documents)} Dokumente aus {parquet_path.name}")

                # Limit prüfen
                if limit > 0 and len(all_documents) >= limit:
                    all_documents = all_documents[:limit]
                    break

            except Exception as e:
                logger.error(f"Fehler beim Laden von {parquet_path}: {e}")
                continue

        return all_documents

    @staticmethod
    def transform_to_standard_format(documents: List[Dict]) -> List[Dict]:
        """
        Transformiert verschiedene Dataset-Formate in Standard-Format.

        Args:
            documents: Rohdokumente aus Parquet

        Returns:
            Standardisierte Dokumente
        """
        standardized = []

        for doc in documents:
            # Mapping verschiedener Feldnamen
            std_doc = {
                "id": doc.get("id") or doc.get("uuid") or doc.get("decision_id"),
                "text": doc.get("text") or doc.get("facts") or doc.get("considerations"),
                "title": doc.get("title") or doc.get("header") or "Unbekannte Entscheidung",
                "court": doc.get("court") or doc.get("chamber") or doc.get("origin_court"),
                "canton": doc.get("canton") or doc.get("origin_canton"),
                "date": doc.get("date") or doc.get("decision_date"),
                "legal_area": doc.get("legal_area") or doc.get("law_area"),
                "language": doc.get("language") or doc.get("lang") or "de",
                "file_number": doc.get("file_number") or doc.get("file_name"),
                # Zusätzliche Felder beibehalten
                "metadata": {
                    k: v
                    for k, v in doc.items()
                    if k not in ["text", "title", "court", "date", "id"]
                },
            }

            # Nur Dokumente mit Text behalten
            if std_doc["text"]:
                standardized.append(std_doc)

        return standardized


@click.command()
@click.option(
    "--dataset",
    type=click.Choice(
        ["swiss_rulings", "swiss_judgment_prediction", "swiss_judgment_prediction_xl"]
    ),
    default="swiss_rulings",
    help="Dataset zum Importieren",
)
@click.option("--limit", default=0, type=int, help="Maximale Anzahl zu importierender Dokumente")
@click.option("--offset", default=0, type=int, help="Anzahl zu überspringender Dokumente")
@click.option("--min-score", default=3, type=int, help="Minimaler Relevanz-Score (0-50)")
@click.option("--batch-size", default=50, type=int, help="Batch-Größe für DB-Inserts")
@click.option("--dry-run", is_flag=True, help="Simulation ohne DB-Änderungen")
@click.option("--export-json", type=Path, help="Exportiere gefilterte Daten als JSON")
@click.option("--verbose", "-v", is_flag=True, help="Verbose Output")
def import_swiss_datasets(
    dataset: str,
    limit: int,
    offset: int,
    min_score: int,
    batch_size: int,
    dry_run: bool,
    export_json: Optional[Path],
    verbose: bool,
):
    """
    Importiert Schweizer Gerichtsentscheidungen mit Datenschutz-Relevanz.

    Umgeht das Hugging Face trust_remote_code Problem durch direkten Parquet-Download.
    """
    click.echo(click.style(f"\n🇨🇭 Swiss Dataset Import: {dataset}", fg="red", bold=True))
    click.echo("=" * 70)

    # 1. Dataset laden
    click.echo("\n📥 Lade Dataset von Hugging Face...")
    loader = SwissParquetLoader()
    documents = loader.load_dataset(dataset, limit=limit + offset)

    if not documents:
        click.echo(click.style("❌ Keine Dokumente geladen!", fg="red"))
        return

    click.echo(f"✅ {len(documents)} Dokumente geladen")

    # 2. Format standardisieren
    click.echo("\n🔄 Standardisiere Dokumente...")
    standardized = loader.transform_to_standard_format(documents)
    click.echo(f"✅ {len(standardized)} Dokumente mit Text")

    # 3. Offset anwenden
    if offset > 0:
        standardized = standardized[offset:]
        click.echo(f"⏭️ Überspringe erste {offset} Dokumente")

    # 4. Limit anwenden
    if limit > 0:
        standardized = standardized[:limit]
        click.echo(f"📊 Limitiere auf {limit} Dokumente")

    # 5. Als temporäre JSON speichern für Import
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(standardized, f, ensure_ascii=False, indent=2)
        temp_file = Path(f.name)

    try:
        # 6. Import mit SwissDatasetImporter
        click.echo(f"\n🚀 Starte Import (Min-Score: {min_score})...")
        importer = SwissDatasetImporter(verbose=verbose, min_score=min_score)

        # Verwende optimierte Basis-Klasse wenn verfügbar
        if hasattr(importer, "import_from_file"):
            stats = importer.import_from_file(
                temp_file, batch_size=batch_size, dry_run=dry_run, filter_relevant=True
            )
        else:
            click.echo("⚠️ Legacy-Import ohne Batch-Processing")
            stats = {"error": "Legacy importer"}

        # 7. Optional: Export gefilterter Daten
        if export_json:
            click.echo(f"\n💾 Exportiere gefilterte Daten nach {export_json}...")

            # Filtere relevante Dokumente
            relevant_docs = []
            for doc in standardized:
                if importer.is_relevant(doc):
                    doc["relevance_score"] = importer.calculate_relevance_score(doc)
                    relevant_docs.append(doc)

            # Speichere als JSON
            export_json.parent.mkdir(parents=True, exist_ok=True)
            with open(export_json, "w", encoding="utf-8") as f:
                json.dump(relevant_docs, f, ensure_ascii=False, indent=2)

            click.echo(f"✅ {len(relevant_docs)} relevante Dokumente exportiert")

        # 8. Zeige Statistiken
        if "error" not in stats:
            click.echo("\n" + "=" * 70)
            click.echo(click.style("📊 Import-Ergebnis:", fg="green", bold=True))
            click.echo(f"  • Verarbeitet: {stats.get('total_processed', 0):,}")
            click.echo(f"  • DSG/FADP-relevant: {stats.get('gdpr_relevant', 0):,}")
            click.echo(f"  • Importiert: {stats.get('imported', 0):,}")
            click.echo(f"  • Übersprungen: {stats.get('skipped_existing', 0):,}")

            # Sprachverteilung analysieren
            languages = {}
            for doc in standardized[:100]:  # Sample first 100
                lang = doc.get("language", "unknown")
                languages[lang] = languages.get(lang, 0) + 1

            if languages:
                click.echo("\n🌐 Sprachverteilung (Sample):")
                for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
                    click.echo(f"  • {lang}: {count}")

    finally:
        # Cleanup
        temp_file.unlink(missing_ok=True)

    click.echo("\n✅ Swiss Dataset Import abgeschlossen!")


@click.group()
def cli():
    """Swiss Dataset Management CLI."""
    pass


@cli.command()
@click.option("--cache-dir", type=Path, default=Path("data/cache"), help="Cache-Verzeichnis")
def list_cached():
    """Zeigt gecachte Parquet-Dateien."""
    cache_dir = Path("data/cache")
    if not cache_dir.exists():
        click.echo("Kein Cache-Verzeichnis gefunden")
        return

    parquet_files = list(cache_dir.glob("*.parquet"))

    if not parquet_files:
        click.echo("Keine gecachten Dateien")
        return

    click.echo("\n📦 Gecachte Parquet-Dateien:")
    total_size = 0
    for f in parquet_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        total_size += size_mb
        click.echo(f"  • {f.name}: {size_mb:.1f} MB")

    click.echo(f"\nGesamt: {total_size:.1f} MB")


@cli.command()
@click.option("--cache-dir", type=Path, default=Path("data/cache"), help="Cache-Verzeichnis")
def clear_cache():
    """Löscht gecachte Parquet-Dateien."""
    cache_dir = Path("data/cache")
    if not cache_dir.exists():
        click.echo("Kein Cache-Verzeichnis gefunden")
        return

    parquet_files = list(cache_dir.glob("*.parquet"))

    if not parquet_files:
        click.echo("Cache bereits leer")
        return

    if click.confirm(f"Wirklich {len(parquet_files)} Dateien löschen?"):
        for f in parquet_files:
            f.unlink()
        click.echo(f"✅ {len(parquet_files)} Dateien gelöscht")


# Füge Haupt-Command zur CLI hinzu
cli.add_command(import_swiss_datasets, name="import")


if __name__ == "__main__":
    # Importiere tempfile hier für temp_file usage
    import tempfile

    # Verwende Click CLI oder direkter Import
    import sys

    if len(sys.argv) > 1:
        cli()
    else:
        # Default: Import swiss_rulings mit Standard-Optionen
        import_swiss_datasets.invoke(
            click.Context(import_swiss_datasets),
            dataset="swiss_rulings",
            limit=100,
            min_score=5,
            verbose=True,
        )
