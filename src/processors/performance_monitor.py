#!/usr/bin/env python3
"""
Performance Monitor für Import-Operationen.

Trackt Memory-Usage, Zeitmetriken und Component-Performance.
"""

import time
import psutil
from typing import Dict
from datetime import timedelta
import click


class PerformanceMonitor:
    """Monitor für Performance-Metriken während des Imports."""

    def __init__(self):
        """Initialisiert den Performance Monitor."""
        self.performance_stats = {
            "total_duration": 0,
            "processing_times": [],
            "memory_usage": [],
            "db_operations": 0,
            "anonymization_time": 0,
            "extraction_time": 0,
            "start_time": None,
            "component_times": {},
        }
        self.process = psutil.Process()

    def start_tracking(self):
        """Startet das Performance-Tracking."""
        self.performance_stats["start_time"] = time.time()

    def stop_tracking(self):
        """Stoppt das Performance-Tracking und berechnet Gesamtdauer."""
        if self.performance_stats["start_time"]:
            self.performance_stats["total_duration"] = (
                time.time() - self.performance_stats["start_time"]
            )

    def track_memory_usage(self):
        """Trackt aktuellen Speicherverbrauch."""
        try:
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            self.performance_stats["memory_usage"].append(memory_mb)
        except Exception:
            pass  # Ignore memory tracking errors

    def track_processing_time(self, duration: float):
        """Trackt Verarbeitungszeit für ein Dokument."""
        self.performance_stats["processing_times"].append(duration)

    def track_component_time(self, component: str, duration: float):
        """Trackt Zeit für eine spezifische Komponente."""
        if component not in self.performance_stats["component_times"]:
            self.performance_stats["component_times"][component] = 0
        self.performance_stats["component_times"][component] += duration

        # Legacy support für spezifische Komponenten
        if component == "anonymization":
            self.performance_stats["anonymization_time"] += duration
        elif component == "extraction":
            self.performance_stats["extraction_time"] += duration

    def increment_db_operations(self, count: int = 1):
        """Erhöht den Zähler für DB-Operationen."""
        self.performance_stats["db_operations"] += count

    def generate_report(self) -> Dict:
        """Generiert einen Performance-Report."""
        report = {
            "total_duration": self.performance_stats["total_duration"],
            "total_duration_str": str(
                timedelta(seconds=int(self.performance_stats["total_duration"]))
            ),
            "db_operations": self.performance_stats["db_operations"],
            "component_times": self.performance_stats["component_times"],
        }

        # Memory-Statistiken
        if self.performance_stats["memory_usage"]:
            report["memory"] = {
                "max_mb": max(self.performance_stats["memory_usage"]),
                "avg_mb": sum(self.performance_stats["memory_usage"])
                / len(self.performance_stats["memory_usage"]),
                "current_mb": self.performance_stats["memory_usage"][-1]
                if self.performance_stats["memory_usage"]
                else 0,
            }

        # Processing-Zeit Statistiken
        if self.performance_stats["processing_times"]:
            report["processing"] = {
                "avg_ms": sum(self.performance_stats["processing_times"])
                * 1000
                / len(self.performance_stats["processing_times"]),
                "total_documents": len(self.performance_stats["processing_times"]),
            }

        # Durchsatz berechnen
        if self.performance_stats["total_duration"] > 0:
            report["throughput"] = {
                "docs_per_sec": len(self.performance_stats["processing_times"])
                / self.performance_stats["total_duration"],
                "db_ops_per_sec": self.performance_stats["db_operations"]
                / self.performance_stats["total_duration"],
            }

        return report

    def print_performance_metrics(self, stats: Dict):
        """Zeigt Performance-Metriken formatiert an."""
        if self.performance_stats["total_duration"] <= 0:
            return

        click.echo("\n" + click.style("⚡ Performance-Metriken:", fg="yellow", bold=True))

        # Zeitmetriken
        duration = self.performance_stats["total_duration"]
        duration_str = str(timedelta(seconds=int(duration)))
        click.echo(f"  • Gesamtdauer: {duration_str} ({duration:.2f}s)")

        # Durchsatz berechnen
        if "total_processed" in stats and stats["total_processed"] > 0:
            docs_per_sec = stats["total_processed"] / duration
            click.echo(f"  • Verarbeitungsrate: {docs_per_sec:.2f} docs/s")

            if "imported" in stats:
                imports_per_sec = stats["imported"] / duration
                click.echo(f"  • Import-Rate: {imports_per_sec:.2f} imports/s")

        # Durchschnittliche Verarbeitungszeit
        if self.performance_stats["processing_times"]:
            avg_time = sum(self.performance_stats["processing_times"]) / len(
                self.performance_stats["processing_times"]
            )
            click.echo(f"  • Ø Verarbeitungszeit: {avg_time*1000:.1f}ms pro Dokument")

        # Memory usage
        if self.performance_stats["memory_usage"]:
            max_memory = max(self.performance_stats["memory_usage"])
            avg_memory = sum(self.performance_stats["memory_usage"]) / len(
                self.performance_stats["memory_usage"]
            )
            click.echo(f"  • Speicherverbrauch: Ø{avg_memory:.1f}MB, Max: {max_memory:.1f}MB")

        # Datenbank-Operationen
        db_ops = self.performance_stats["db_operations"]
        if db_ops > 0 and duration > 0:
            db_ops_per_sec = db_ops / duration
            click.echo(f"  • DB-Operationen: {db_ops:,} ({db_ops_per_sec:.2f} ops/s)")

        # Component-Performance
        if self.performance_stats["component_times"]:
            click.echo("\n" + click.style("🔍 Component-Performance:", fg="blue", bold=True))
            for component, comp_time in self.performance_stats["component_times"].items():
                if comp_time > 0:
                    docs_count = stats.get("total_processed", 1)
                    avg_ms = (comp_time / docs_count) * 1000
                    click.echo(
                        f"  • {component.capitalize()}: {comp_time:.2f}s gesamt, Ø{avg_ms:.1f}ms pro Dokument"
                    )

    def print_recommendations(self, stats: Dict):
        """Zeigt Performance-Empfehlungen basierend auf Metriken an."""
        click.echo("\n" + click.style("💡 Performance-Empfehlungen:", fg="green", bold=True))

        # Speicher-Empfehlungen
        if self.performance_stats["memory_usage"]:
            max_memory = max(self.performance_stats["memory_usage"])
            if max_memory > 1000:  # > 1GB
                click.echo("  ⚠️ Hoher Speicherverbrauch - erwäge kleinere Batch-Sizes")

        # Durchsatz-Empfehlungen
        if self.performance_stats["total_duration"] > 0 and "total_processed" in stats:
            docs_per_sec = stats["total_processed"] / self.performance_stats["total_duration"]
            if docs_per_sec < 1.0:
                click.echo("  ⚠️ Niedrige Verarbeitungsrate - prüfe DB-Performance und Netzwerk")
            elif docs_per_sec > 10.0:
                click.echo("  ✅ Gute Verarbeitungsrate - System läuft optimal")

        # Fehlerrate-Empfehlungen
        if "errors" in stats and "total_processed" in stats and stats["total_processed"] > 0:
            error_rate = (stats.get("errors", 0) / stats["total_processed"]) * 100
            if error_rate > 5.0:
                click.echo(f"  ⚠️ Hohe Fehlerrate ({error_rate:.1f}%) - prüfe Datenqualität")

        # GDPR-Relevanz-Empfehlungen
        if "gdpr_relevant" in stats and "total_processed" in stats and stats["total_processed"] > 0:
            relevance_rate = (stats["gdpr_relevant"] / stats["total_processed"]) * 100
            if relevance_rate < 1.0:
                click.echo(
                    f"  🔍 Niedrige DSGVO-Relevanz ({relevance_rate:.1f}%) - erwäge andere Datenquellen"
                )
            elif relevance_rate > 15.0:
                click.echo(f"  ✅ Hohe DSGVO-Relevanz ({relevance_rate:.1f}%) - gute Datenquelle")

        # Component-Performance Empfehlungen
        if "total_processed" in stats and stats["total_processed"] > 0:
            if "anonymization" in self.performance_stats["component_times"]:
                anon_time = self.performance_stats["component_times"]["anonymization"]
                anon_time_per_doc = anon_time / stats["total_processed"]
                if anon_time_per_doc > 0.5:  # > 500ms pro Dokument
                    click.echo("  ⚠️ Langsame Anonymisierung - erwäge optimierte spaCy-Pipeline")

            if "extraction" in self.performance_stats["component_times"]:
                extract_time = self.performance_stats["component_times"]["extraction"]
                extract_time_per_doc = extract_time / stats["total_processed"]
                if extract_time_per_doc > 0.1:  # > 100ms pro Dokument
                    click.echo("  ⚠️ Langsame GDPR-Extraktion - erwäge kompilierte Regex-Pattern")

        # Batch-Empfehlungen
        if "total_processed" in stats and stats["total_processed"] > 0:
            processing_rate = stats["total_processed"] / max(
                self.performance_stats["total_duration"], 1
            )
            if processing_rate < 5.0 and stats["total_processed"] > 100:
                click.echo("  💡 Erwäge Batch-Processing für bessere Performance")
            elif processing_rate > 50.0:
                click.echo("  🚀 Exzellente Performance - System ist gut optimiert!")
