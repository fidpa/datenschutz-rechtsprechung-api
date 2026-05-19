#!/usr/bin/env python3
"""
Praxis-Test und Qualitäts-Validierung für Import-System.

Führt einen realen Import durch und erstellt detaillierten Report.
"""

import click
import json
import time
import psutil
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import Counter
import requests
from tqdm import tqdm

from src.database import db_manager, Decision, init_db
from src.importers.openlegaldata import OpenLegalDataImporter
from src.importers.swiss_datasets import SwissDatasetImporter, SwissParquetLoader
from src.processors.performance_monitor import PerformanceMonitor
from src.utils.logging import get_logger

logger = get_logger("QualityValidation")

# Setze Style für Visualisierungen
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (12, 8)


class ImportQualityValidator:
    """Validiert Import-Qualität und erstellt Reports."""

    def __init__(self, output_dir: Path = Path("reports")):
        """
        Initialisiert den Validator.

        Args:
            output_dir: Verzeichnis für Reports
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = {"performance": {}, "quality": {}, "compliance": {}, "errors": []}
        self.decisions = []

    def download_sample_data(self, source: str = "openlegaldata", count: int = 500) -> Path:
        """
        Lädt echte Sample-Daten herunter.

        Args:
            source: Datenquelle ('openlegaldata' oder 'swiss')
            count: Anzahl der Dokumente

        Returns:
            Pfad zur Datei
        """
        if source == "openlegaldata":
            # Option 1: Von OpenLegalData API (langsam aber aktuell)
            # return self._download_from_api(count)

            # Option 2: Sample aus gecachtem Dump
            return self._extract_from_dump(count)

        elif source == "swiss":
            # Verwende Swiss Parquet Loader
            loader = SwissParquetLoader()
            docs = loader.load_dataset("swiss_rulings", limit=count)

            sample_file = self.output_dir / f"swiss_sample_{count}.json"
            with open(sample_file, "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)

            return sample_file

    def _extract_from_dump(self, count: int) -> Path:
        """Extrahiert Sample aus OpenLegalData Dump."""
        dump_file = Path("data/cache/cases.json")

        if not dump_file.exists():
            logger.info("Lade OpenLegalData Dump herunter...")
            self._download_dump()

        logger.info(f"Extrahiere {count} Dokumente aus Dump...")

        # Streaming-Parse für große Datei
        sample = []
        with open(dump_file, "r", encoding="utf-8") as f:
            # Assume JSON array format
            import ijson

            parser = ijson.items(f, "item")

            for i, item in enumerate(parser):
                if i >= count:
                    break

                # Filtere nach DSGVO-Relevanz
                content = str(item.get("content", ""))
                if any(term in content.lower() for term in ["dsgvo", "datenschutz", "gdpr"]):
                    sample.append(item)

                if len(sample) >= count:
                    break

        # Fallback: Wenn nicht genug DSGVO-relevante gefunden
        if len(sample) < count:
            logger.warning(f"Nur {len(sample)} DSGVO-relevante Dokumente gefunden")
            with open(dump_file, "r") as f:
                data = json.load(f)
                sample.extend(data[: count - len(sample)])

        # Speichere Sample
        sample_file = self.output_dir / f"openlegaldata_sample_{count}.json"
        with open(sample_file, "w", encoding="utf-8") as f:
            json.dump(sample[:count], f, ensure_ascii=False, indent=2)

        logger.info(f"Sample gespeichert: {sample_file}")
        return sample_file

    def _download_dump(self):
        """Lädt OpenLegalData Dump herunter."""
        url = "https://static.openlegaldata.io/dumps/de/cases.json.gz"
        cache_dir = Path("data/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)

        gz_file = cache_dir / "cases.json.gz"
        json_file = cache_dir / "cases.json"

        if not gz_file.exists():
            logger.info(f"Lade herunter: {url}")
            response = requests.get(url, stream=True)
            total_size = int(response.headers.get("content-length", 0))

            with open(gz_file, "wb") as f:
                with tqdm(total=total_size, unit="iB", unit_scale=True) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))

        if not json_file.exists():
            logger.info("Entpacke Dump...")
            import gzip

            with gzip.open(gz_file, "rb") as f_in:
                with open(json_file, "wb") as f_out:
                    f_out.write(f_in.read())

        logger.info(f"Dump bereit: {json_file}")

    def run_import_test(self, data_file: Path, source: str = "openlegaldata") -> Dict:
        """
        Führt Import-Test durch und sammelt Metriken.

        Args:
            data_file: Pfad zur Testdaten-Datei
            source: Datenquelle

        Returns:
            Import-Statistiken
        """
        logger.info(f"Starte Import-Test mit {data_file}")

        # Wähle Importer
        if source == "openlegaldata":
            importer = OpenLegalDataImporter(verbose=True)
        else:
            importer = SwissDatasetImporter(verbose=True)

        # Performance Monitoring
        process = psutil.Process()
        start_time = time.time()
        start_memory = process.memory_info().rss / 1024 / 1024

        # Import durchführen
        stats = importer.import_from_file(
            data_file, batch_size=100, filter_relevant=True  # Nur relevante
        )

        # Performance-Metriken
        duration = time.time() - start_time
        peak_memory = process.memory_info().rss / 1024 / 1024
        memory_used = peak_memory - start_memory

        # Erweitere Statistiken
        stats["duration"] = duration
        stats["memory_used_mb"] = memory_used
        stats["throughput"] = stats["total_processed"] / duration if duration > 0 else 0
        stats["source"] = source

        # Speichere Metriken
        self.metrics["performance"] = {
            "duration_seconds": duration,
            "documents_processed": stats["total_processed"],
            "documents_imported": stats["imported"],
            "throughput_docs_per_sec": stats["throughput"],
            "memory_used_mb": memory_used,
            "batch_performance": importer.performance_monitor.generate_report()
            if hasattr(importer, "performance_monitor")
            else {},
        }

        logger.info(f"Import abgeschlossen: {stats['imported']} importiert in {duration:.2f}s")
        return stats

    def analyze_data_quality(self) -> Dict:
        """
        Analysiert Datenqualität der importierten Dokumente.

        Returns:
            Qualitäts-Metriken
        """
        logger.info("Analysiere Datenqualität...")

        with db_manager.get_session() as session:
            # Lade alle Decisions
            self.decisions = session.query(Decision).all()
            total = len(self.decisions)

            if total == 0:
                logger.warning("Keine Decisions in Datenbank")
                return {}

            # Qualitäts-Metriken
            quality_metrics = {
                "total_decisions": total,
                "with_gdpr_articles": 0,
                "with_anonymization": 0,
                "with_court_info": 0,
                "with_date": 0,
                "with_keywords": 0,
                "avg_text_length": 0,
                "gdpr_article_distribution": Counter(),
                "court_distribution": Counter(),
                "year_distribution": Counter(),
                "anonymization_quality": [],
            }

            text_lengths = []

            for decision in self.decisions:
                # GDPR-Artikel
                if decision.gdpr_articles:
                    quality_metrics["with_gdpr_articles"] += 1
                    for article in decision.gdpr_articles:
                        quality_metrics["gdpr_article_distribution"][article] += 1

                # Anonymisierung
                if decision.anonymization_applied:
                    quality_metrics["with_anonymization"] += 1

                    # Prüfe Anonymisierungs-Qualität
                    if decision.full_text_anonymized:
                        quality_score = self._check_anonymization_quality(
                            decision.full_text, decision.full_text_anonymized
                        )
                        quality_metrics["anonymization_quality"].append(quality_score)

                # Metadaten
                if decision.court:
                    quality_metrics["with_court_info"] += 1
                    quality_metrics["court_distribution"][decision.court] += 1

                if decision.decision_date:
                    quality_metrics["with_date"] += 1
                    year = decision.decision_date.year
                    quality_metrics["year_distribution"][year] += 1

                if decision.keywords:
                    quality_metrics["with_keywords"] += 1

                # Text-Länge
                if decision.full_text:
                    text_lengths.append(len(decision.full_text))

            # Durchschnitte berechnen
            if text_lengths:
                quality_metrics["avg_text_length"] = sum(text_lengths) / len(text_lengths)

            if quality_metrics["anonymization_quality"]:
                quality_metrics["avg_anonymization_score"] = sum(
                    quality_metrics["anonymization_quality"]
                ) / len(quality_metrics["anonymization_quality"])

            # Prozentsätze
            quality_metrics["gdpr_coverage"] = (quality_metrics["with_gdpr_articles"] / total) * 100
            quality_metrics["anonymization_coverage"] = (
                quality_metrics["with_anonymization"] / total
            ) * 100
            quality_metrics["metadata_completeness"] = (
                (quality_metrics["with_court_info"] + quality_metrics["with_date"]) / (total * 2)
            ) * 100

            self.metrics["quality"] = quality_metrics
            return quality_metrics

    def _check_anonymization_quality(self, original: str, anonymized: str) -> float:
        """
        Prüft Qualität der Anonymisierung.

        Args:
            original: Original-Text
            anonymized: Anonymisierter Text

        Returns:
            Qualitäts-Score (0-100)
        """
        import re

        score = 100.0

        # Prüfe auf verbleibende persönliche Daten
        personal_patterns = [
            r"\b[A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+\b",  # Namen
            r"\b\d{2}\.\d{2}\.\d{4}\b",  # Geburtsdaten
            r"\b[a-z]+@[a-z]+\.[a-z]+\b",  # E-Mails
            r"\b\d{5}\b",  # PLZ
            r"\b\d{2,4}[-/]\d{4,8}\b",  # Telefonnummern
        ]

        for pattern in personal_patterns:
            matches = re.findall(pattern, anonymized, re.IGNORECASE)
            if matches:
                score -= len(matches) * 5  # -5 Punkte pro Match

        # Prüfe ob wichtige rechtliche Begriffe erhalten
        legal_terms = ["Gericht", "Kläger", "Beklagter", "Urteil", "DSGVO"]
        preserved = sum(1 for term in legal_terms if term in anonymized)
        score += preserved * 2  # +2 Punkte pro erhaltenem Begriff

        return max(0, min(100, score))

    def check_compliance(self) -> Dict:
        """
        Prüft DSGVO-Compliance der Verarbeitung.

        Returns:
            Compliance-Metriken
        """
        logger.info("Prüfe DSGVO-Compliance...")

        compliance = {
            "all_names_anonymized": True,
            "no_email_addresses": True,
            "no_phone_numbers": True,
            "no_social_security": True,
            "processing_lawful": True,
            "issues": [],
        }

        import re

        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        phone_pattern = r"(\+49|0)[1-9]\d{1,14}"
        ssn_pattern = (
            r"\b\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{2}\b"  # Deutsche Sozialversicherungsnummer
        )

        for decision in self.decisions[:100]:  # Sample first 100
            if decision.full_text_anonymized:
                text = decision.full_text_anonymized

                # Check for emails
                if re.search(email_pattern, text):
                    compliance["no_email_addresses"] = False
                    compliance["issues"].append(f"E-Mail in Decision {decision.id}")

                # Check for phone numbers
                if re.search(phone_pattern, text):
                    compliance["no_phone_numbers"] = False
                    compliance["issues"].append(f"Telefonnummer in Decision {decision.id}")

                # Check for SSN
                if re.search(ssn_pattern, text):
                    compliance["no_social_security"] = False
                    compliance["issues"].append(
                        f"Sozialversicherungsnummer in Decision {decision.id}"
                    )

        compliance["compliant"] = all(
            [
                compliance["all_names_anonymized"],
                compliance["no_email_addresses"],
                compliance["no_phone_numbers"],
                compliance["no_social_security"],
            ]
        )

        self.metrics["compliance"] = compliance
        return compliance

    def generate_visualizations(self):
        """Erstellt Visualisierungen der Metriken."""
        logger.info("Erstelle Visualisierungen...")

        # 1. Performance Metrics
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # Throughput über Zeit (wenn verfügbar)
        if "batch_performance" in self.metrics["performance"]:
            perf = self.metrics["performance"]["batch_performance"]
            if "processing" in perf:
                axes[0, 0].bar(
                    ["Durchsatz"], [self.metrics["performance"]["throughput_docs_per_sec"]]
                )
                axes[0, 0].set_ylabel("Dokumente/Sekunde")
                axes[0, 0].set_title("Import-Geschwindigkeit")

        # Memory Usage
        axes[0, 1].bar(["Memory"], [self.metrics["performance"]["memory_used_mb"]])
        axes[0, 1].set_ylabel("MB")
        axes[0, 1].set_title("Speicherverbrauch")

        # GDPR Article Distribution
        if self.metrics["quality"]["gdpr_article_distribution"]:
            articles = list(self.metrics["quality"]["gdpr_article_distribution"].keys())[:10]
            counts = [self.metrics["quality"]["gdpr_article_distribution"][a] for a in articles]
            axes[1, 0].bar(articles, counts)
            axes[1, 0].set_xlabel("DSGVO Artikel")
            axes[1, 0].set_ylabel("Häufigkeit")
            axes[1, 0].set_title("Top 10 DSGVO-Artikel")

        # Quality Metrics
        quality_data = {
            "GDPR-Artikel": self.metrics["quality"]["gdpr_coverage"],
            "Anonymisiert": self.metrics["quality"]["anonymization_coverage"],
            "Metadaten": self.metrics["quality"]["metadata_completeness"],
        }
        axes[1, 1].bar(quality_data.keys(), quality_data.values())
        axes[1, 1].set_ylabel("Prozent (%)")
        axes[1, 1].set_title("Datenqualität")
        axes[1, 1].set_ylim(0, 100)

        plt.tight_layout()
        plt.savefig(self.output_dir / "import_metrics.png", dpi=150)
        plt.close()

        # 2. Court Distribution
        if self.metrics["quality"]["court_distribution"]:
            fig, ax = plt.subplots(figsize=(12, 6))
            courts = list(self.metrics["quality"]["court_distribution"].keys())[:15]
            counts = [self.metrics["quality"]["court_distribution"][c] for c in courts]
            ax.barh(courts, counts)
            ax.set_xlabel("Anzahl Entscheidungen")
            ax.set_title("Verteilung nach Gerichten")
            plt.tight_layout()
            plt.savefig(self.output_dir / "court_distribution.png", dpi=150)
            plt.close()

        # 3. Timeline
        if self.metrics["quality"]["year_distribution"]:
            fig, ax = plt.subplots(figsize=(12, 6))
            years = sorted(self.metrics["quality"]["year_distribution"].keys())
            counts = [self.metrics["quality"]["year_distribution"][y] for y in years]
            ax.plot(years, counts, marker="o")
            ax.set_xlabel("Jahr")
            ax.set_ylabel("Anzahl Entscheidungen")
            ax.set_title("Zeitliche Verteilung")
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(self.output_dir / "timeline.png", dpi=150)
            plt.close()

        logger.info(f"Visualisierungen gespeichert in {self.output_dir}")

    def generate_report(self) -> Path:
        """
        Generiert umfassenden HTML-Report.

        Returns:
            Pfad zum Report
        """
        logger.info("Generiere Report...")

        report_file = self.output_dir / f"import_quality_report_{datetime.now():%Y%m%d_%H%M%S}.html"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <title>Import Quality Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; }}
                .metric {{ background: #ecf0f1; padding: 10px; margin: 10px 0; border-radius: 5px; }}
                .success {{ color: #27ae60; }}
                .warning {{ color: #f39c12; }}
                .error {{ color: #e74c3c; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #bdc3c7; padding: 8px; text-align: left; }}
                th {{ background-color: #34495e; color: white; }}
                img {{ max-width: 100%; height: auto; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <h1>📊 Import Quality Report</h1>
            <p>Generiert: {datetime.now():%Y-%m-%d %H:%M:%S}</p>
            
            <h2>1. Performance-Metriken</h2>
            <div class="metric">
                <strong>Durchsatz:</strong> {self.metrics['performance'].get('throughput_docs_per_sec', 0):.2f} docs/s<br>
                <strong>Import-Dauer:</strong> {self.metrics['performance'].get('duration_seconds', 0):.2f} Sekunden<br>
                <strong>Dokumente verarbeitet:</strong> {self.metrics['performance'].get('documents_processed', 0):,}<br>
                <strong>Dokumente importiert:</strong> {self.metrics['performance'].get('documents_imported', 0):,}<br>
                <strong>Speicherverbrauch:</strong> {self.metrics['performance'].get('memory_used_mb', 0):.1f} MB
            </div>
            
            <h2>2. Datenqualität</h2>
            <div class="metric">
                <strong>Gesamt Entscheidungen:</strong> {self.metrics['quality'].get('total_decisions', 0):,}<br>
                <strong>Mit DSGVO-Artikeln:</strong> {self.metrics['quality'].get('with_gdpr_articles', 0):,} 
                ({self.metrics['quality'].get('gdpr_coverage', 0):.1f}%)<br>
                <strong>Anonymisiert:</strong> {self.metrics['quality'].get('with_anonymization', 0):,} 
                ({self.metrics['quality'].get('anonymization_coverage', 0):.1f}%)<br>
                <strong>Durchschn. Textlänge:</strong> {self.metrics['quality'].get('avg_text_length', 0):.0f} Zeichen<br>
                <strong>Metadaten-Vollständigkeit:</strong> {self.metrics['quality'].get('metadata_completeness', 0):.1f}%
            </div>
            
            <h2>3. DSGVO-Compliance</h2>
            <div class="metric">
                <strong>Status:</strong> 
                <span class="{'success' if self.metrics['compliance'].get('compliant', False) else 'error'}">
                    {'✅ Compliant' if self.metrics['compliance'].get('compliant', False) else '❌ Issues gefunden'}
                </span><br>
                <strong>Alle Namen anonymisiert:</strong> 
                {'✅' if self.metrics['compliance'].get('all_names_anonymized', False) else '❌'}<br>
                <strong>Keine E-Mail-Adressen:</strong> 
                {'✅' if self.metrics['compliance'].get('no_email_addresses', False) else '❌'}<br>
                <strong>Keine Telefonnummern:</strong> 
                {'✅' if self.metrics['compliance'].get('no_phone_numbers', False) else '❌'}<br>
                {self._format_compliance_issues()}
            </div>
            
            <h2>4. Visualisierungen</h2>
            <img src="import_metrics.png" alt="Import Metriken">
            <img src="court_distribution.png" alt="Gerichtsverteilung">
            <img src="timeline.png" alt="Zeitliche Verteilung">
            
            <h2>5. Top DSGVO-Artikel</h2>
            <table>
                <tr><th>Artikel</th><th>Häufigkeit</th><th>Prozent</th></tr>
                {self._format_gdpr_table()}
            </table>
            
            <h2>6. Empfehlungen</h2>
            <ul>
                {self._generate_recommendations()}
            </ul>
            
            <hr>
            <p><small>Report generiert mit Datenschutz-Rechtsprechung API Quality Validator</small></p>
        </body>
        </html>
        """

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Report gespeichert: {report_file}")
        return report_file

    def _format_compliance_issues(self) -> str:
        """Formatiert Compliance-Issues für HTML."""
        issues = self.metrics["compliance"].get("issues", [])
        if not issues:
            return ""

        html = "<strong>Gefundene Issues:</strong><ul>"
        for issue in issues[:10]:  # Max 10 anzeigen
            html += f"<li class='warning'>{issue}</li>"
        if len(issues) > 10:
            html += f"<li>... und {len(issues) - 10} weitere</li>"
        html += "</ul>"
        return html

    def _format_gdpr_table(self) -> str:
        """Formatiert GDPR-Artikel-Tabelle für HTML."""
        distribution = self.metrics["quality"].get("gdpr_article_distribution", {})
        if not distribution:
            return "<tr><td colspan='3'>Keine Daten</td></tr>"

        total = sum(distribution.values())
        html = ""
        for article, count in sorted(distribution.items(), key=lambda x: x[1], reverse=True)[:10]:
            percent = (count / total) * 100 if total > 0 else 0
            html += f"<tr><td>Art. {article}</td><td>{count}</td><td>{percent:.1f}%</td></tr>"

        return html

    def _generate_recommendations(self) -> str:
        """Generiert Empfehlungen basierend auf Metriken."""
        recommendations = []

        # Performance
        throughput = self.metrics["performance"].get("throughput_docs_per_sec", 0)
        if throughput < 50:
            recommendations.append(
                "Performance optimieren: Batch-Size erhöhen oder Parallelisierung nutzen"
            )
        elif throughput > 150:
            recommendations.append("Exzellente Performance! Aktuelle Konfiguration beibehalten")

        # Qualität
        gdpr_coverage = self.metrics["quality"].get("gdpr_coverage", 0)
        if gdpr_coverage < 10:
            recommendations.append("GDPR-Artikel-Extraktion verbessern: Patterns erweitern")

        anonymization = self.metrics["quality"].get("anonymization_coverage", 0)
        if anonymization < 90:
            recommendations.append("Anonymisierung auf alle Dokumente ausweiten")

        # Compliance
        if not self.metrics["compliance"].get("compliant", False):
            recommendations.append(
                "<strong class='error'>KRITISCH: Compliance-Issues beheben!</strong>"
            )

        # Memory
        memory = self.metrics["performance"].get("memory_used_mb", 0)
        if memory > 500:
            recommendations.append("Memory-Usage reduzieren: Kleinere Batches oder Streaming")

        if not recommendations:
            recommendations.append("System läuft optimal - keine dringenden Empfehlungen")

        return "\n".join(f"<li>{r}</li>" for r in recommendations)


@click.command()
@click.option("--source", type=click.Choice(["openlegaldata", "swiss"]), default="openlegaldata")
@click.option("--count", default=500, help="Anzahl Dokumente zum Testen")
@click.option("--download/--no-download", default=True, help="Sample-Daten herunterladen")
@click.option("--visualize/--no-visualize", default=True, help="Visualisierungen erstellen")
@click.option("--output-dir", type=Path, default=Path("reports"), help="Output-Verzeichnis")
def validate_import(source: str, count: int, download: bool, visualize: bool, output_dir: Path):
    """
    Führt umfassenden Praxis-Test des Import-Systems durch.

    Testet mit echten Daten und erstellt detaillierten Quality-Report.
    """
    click.echo(click.style(f"\n🔬 Import Quality Validation", fg="cyan", bold=True))
    click.echo("=" * 70)

    validator = ImportQualityValidator(output_dir)

    try:
        # 1. Daten vorbereiten
        if download:
            click.echo("\n📥 Lade Sample-Daten...")
            data_file = validator.download_sample_data(source, count)
        else:
            # Verwende existierende Datei
            data_file = output_dir / f"{source}_sample_{count}.json"
            if not data_file.exists():
                click.echo(f"❌ Datei nicht gefunden: {data_file}")
                return

        # 2. Import durchführen
        click.echo(f"\n🚀 Starte Import-Test mit {count} Dokumenten...")
        import_stats = validator.run_import_test(data_file, source)

        # 3. Qualität analysieren
        click.echo("\n🔍 Analysiere Datenqualität...")
        quality_metrics = validator.analyze_data_quality()

        # 4. Compliance prüfen
        click.echo("\n⚖️ Prüfe DSGVO-Compliance...")
        compliance = validator.check_compliance()

        # 5. Visualisierungen
        if visualize:
            click.echo("\n📊 Erstelle Visualisierungen...")
            validator.generate_visualizations()

        # 6. Report generieren
        click.echo("\n📝 Generiere Report...")
        report_path = validator.generate_report()

        # 7. Zusammenfassung ausgeben
        click.echo("\n" + "=" * 70)
        click.echo(click.style("✅ Validation abgeschlossen!", fg="green", bold=True))
        click.echo(f"\n📈 Performance:")
        click.echo(f"  • Durchsatz: {import_stats['throughput']:.2f} docs/s")
        click.echo(
            f"  • Importiert: {import_stats['imported']:,} / {import_stats['total_processed']:,}"
        )
        click.echo(f"  • Memory: {import_stats['memory_used_mb']:.1f} MB")

        click.echo(f"\n📊 Qualität:")
        click.echo(f"  • GDPR-Coverage: {quality_metrics.get('gdpr_coverage', 0):.1f}%")
        click.echo(f"  • Anonymisierung: {quality_metrics.get('anonymization_coverage', 0):.1f}%")

        click.echo(f"\n⚖️ Compliance:")
        if compliance.get("compliant"):
            click.echo(click.style("  • ✅ DSGVO-compliant", fg="green"))
        else:
            click.echo(
                click.style(
                    f"  • ⚠️ {len(compliance.get('issues', []))} Issues gefunden", fg="yellow"
                )
            )

        click.echo(f"\n📄 Report: {report_path}")

        # Optional: Öffne Report im Browser
        if click.confirm("\nReport im Browser öffnen?"):
            import webbrowser

            webbrowser.open(f"file://{report_path.absolute()}")

    except Exception as e:
        click.echo(click.style(f"\n❌ Fehler: {e}", fg="red"))
        logger.error(f"Validation fehlgeschlagen: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    validate_import()
