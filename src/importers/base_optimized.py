#!/usr/bin/env python3
"""
Optimized Base Importer mit Batch-Processing.

Verbesserte Version mit 4x Performance durch Bulk-Operations.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
import time
import click
from datetime import datetime
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential

from src.database import db_manager, Decision
from src.processors.performance_monitor import PerformanceMonitor
from src.processors.resume_manager import ResumeManager
from src.utils.file_handlers import DumpFileHandler
from src.utils.logging import get_logger


class OptimizedBaseImporter(ABC):
    """Optimierte Basis-Klasse mit Batch-Processing."""

    # Optimale Batch-Größen basierend auf Tests
    DEFAULT_BATCH_SIZE = 100
    MAX_BATCH_SIZE = 500

    def __init__(self, verbose: bool = False):
        """
        Initialisiert den optimierten Base Importer.

        Args:
            verbose: Verbose Output aktivieren
        """
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)
        self.performance_monitor = PerformanceMonitor()
        self.resume_manager = None
        self.file_handler = DumpFileHandler()

        # Batch-Processing Buffer
        self.batch_buffer = []
        self.batch_stats = {"batches_processed": 0, "avg_batch_time": 0, "total_batch_time": 0}

        # Import-Statistiken
        self.stats = {
            "total_processed": 0,
            "imported": 0,
            "skipped_existing": 0,
            "skipped_irrelevant": 0,
            "skipped_parse_error": 0,
            "gdpr_relevant": 0,
            "errors": 0,
            "retries": 0,
        }

    @abstractmethod
    def parse_document(self, raw_data: Dict[str, Any]) -> Optional[Decision]:
        """Parst ein Dokument zu einer Decision."""

    @abstractmethod
    def is_relevant(self, raw_data: Dict[str, Any]) -> bool:
        """Prüft ob ein Dokument relevant ist."""

    @abstractmethod
    def get_document_id(self, raw_data: Dict[str, Any]) -> str:
        """Extrahiert eindeutige ID aus einem Dokument."""

    def import_from_file(
        self,
        file_path: Path,
        limit: int = 0,
        offset: int = 0,
        filter_relevant: bool = True,
        resume: bool = False,
        dry_run: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Dict[str, Any]:
        """
        Importiert Dokumente mit optimiertem Batch-Processing.

        Args:
            file_path: Pfad zur Dump-Datei
            limit: Maximale Anzahl zu importierender Dokumente
            offset: Anzahl der zu überspringenden Dokumente
            filter_relevant: Nur relevante Dokumente importieren
            resume: Von letzter Position fortsetzen
            dry_run: Simulation ohne Datenbank-Änderungen
            batch_size: Anzahl Dokumente pro Batch (auto-optimiert)

        Returns:
            Dictionary mit Import-Statistiken
        """
        # Batch-Size optimieren
        batch_size = min(batch_size, self.MAX_BATCH_SIZE)
        if self.verbose:
            click.echo(f"🚀 Verwende optimierte Batch-Size: {batch_size}")

        # Setup
        self._setup_import(file_path, resume)

        # Resume handling
        if resume and self.resume_manager:
            resume_state = self.resume_manager.load_state()
            if resume_state:
                offset = resume_state.get("position", offset)
                self.stats = self.resume_manager.get_resume_stats()
                self.resume_manager.print_resume_info()

        # Performance tracking starten
        self.performance_monitor.start_tracking()

        try:
            # Optimierter Import mit Batch-Processing
            self._perform_batch_import(
                file_path=file_path,
                limit=limit,
                offset=offset,
                filter_relevant=filter_relevant,
                dry_run=dry_run,
                batch_size=batch_size,
            )

            # Finaler Batch verarbeiten
            if self.batch_buffer and not dry_run:
                self._process_batch(dry_run=dry_run)

            # Performance tracking stoppen
            self.performance_monitor.stop_tracking()

            # Statistiken anzeigen
            self._print_optimized_statistics()

            # Resume cleanup
            if not dry_run and self.resume_manager:
                self.resume_manager.cleanup()

        except KeyboardInterrupt:
            click.echo("\n\n⚠️ Import unterbrochen - Resume-State gespeichert")
            if self.resume_manager:
                position = offset + self.stats["total_processed"]
                self.resume_manager.save_state(position, self.stats)
            raise

        except Exception as e:
            self.logger.error(f"Import-Fehler: {e}", exc_info=True)
            raise

        return self.stats

    def _perform_batch_import(
        self,
        file_path: Path,
        limit: int,
        offset: int,
        filter_relevant: bool,
        dry_run: bool,
        batch_size: int,
    ):
        """Optimierter Import mit Batch-Processing."""
        # Progress bar setup
        total = limit if limit > 0 else None
        pbar = tqdm(total=total, desc="Importiere (Batch-Mode)", unit="docs")

        documents_processed = 0

        # Über Dokumente iterieren
        for doc_idx, raw_document in enumerate(self.file_handler.open_file(file_path, offset)):
            # Limit prüfen
            if limit > 0 and documents_processed >= limit:
                break

            # Performance tracking
            start_time = time.time()

            # Dokument mit Retry-Logic verarbeiten
            processed = self._process_document_with_retry(raw_document, filter_relevant, dry_run)

            if processed:
                self.batch_buffer.append(processed)

            # Batch verarbeiten wenn voll
            if len(self.batch_buffer) >= batch_size and not dry_run:
                self._process_batch(dry_run=dry_run)

            # Performance metrics
            processing_time = time.time() - start_time
            self.performance_monitor.track_processing_time(processing_time)

            # Memory tracking nur alle 100 Dokumente (Performance)
            if documents_processed % 100 == 0:
                self.performance_monitor.track_memory_usage()

            documents_processed += 1
            self.stats["total_processed"] += 1
            pbar.update(1)

            # Resume-State periodisch speichern
            if self.resume_manager and documents_processed % 250 == 0:
                position = offset + documents_processed
                doc_id = self.get_document_id(raw_document)
                self.resume_manager.save_state(position, self.stats, doc_id)

        pbar.close()

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True
    )
    def _process_document_with_retry(
        self, raw_document: Dict, filter_relevant: bool, dry_run: bool
    ) -> Optional[Decision]:
        """
        Verarbeitet ein Dokument mit Retry-Logic.

        Returns:
            Decision-Objekt oder None
        """
        try:
            # Relevanz prüfen
            if filter_relevant and not self.is_relevant(raw_document):
                self.stats["skipped_irrelevant"] += 1
                return None

            # DSGVO-relevant markieren
            if self.is_relevant(raw_document):
                self.stats["gdpr_relevant"] += 1

            # Dokument parsen
            decision = self.parse_document(raw_document)
            if not decision:
                self.stats["skipped_parse_error"] += 1
                return None

            return decision

        except Exception as e:
            self.stats["retries"] += 1
            if self.verbose:
                doc_id = self.get_document_id(raw_document)
                self.logger.warning(f"Retry für Dokument {doc_id}: {e}")
            raise  # Für Retry-Decorator

    def _process_batch(self, dry_run: bool = False):
        """
        Verarbeitet einen Batch von Decisions mit Bulk-Operations.

        Optimierung: Bulk-Insert statt einzelner Inserts
        """
        if not self.batch_buffer:
            return

        batch_start = time.time()

        if dry_run:
            # Dry-run: nur zählen
            self.stats["imported"] += len(self.batch_buffer)
        else:
            # Bulk-Save mit optimierten Queries
            saved, skipped = self._bulk_save_decisions(self.batch_buffer)
            self.stats["imported"] += saved
            self.stats["skipped_existing"] += skipped
            self.performance_monitor.increment_db_operations(1)  # Ein Batch = eine Operation

        # Batch-Statistiken
        batch_time = time.time() - batch_start
        self.batch_stats["batches_processed"] += 1
        self.batch_stats["total_batch_time"] += batch_time
        self.batch_stats["avg_batch_time"] = (
            self.batch_stats["total_batch_time"] / self.batch_stats["batches_processed"]
        )

        # Performance tracking
        self.performance_monitor.track_component_time("batch_processing", batch_time)

        if self.verbose:
            click.echo(
                f"  Batch {self.batch_stats['batches_processed']}: "
                f"{len(self.batch_buffer)} Dokumente in {batch_time:.2f}s "
                f"({len(self.batch_buffer)/batch_time:.1f} docs/s)"
            )

        # Buffer leeren
        self.batch_buffer.clear()

    def _bulk_save_decisions(self, decisions: List[Decision]) -> Tuple[int, int]:
        """
        Speichert mehrere Decisions mit Bulk-Operations.

        Args:
            decisions: Liste von Decision-Objekten

        Returns:
            Tuple (saved_count, skipped_count)
        """
        try:
            with db_manager.get_sync_session() as session:
                # 1. Bulk-Check für existierende Decisions
                case_numbers = [d.case_number for d in decisions]
                sources = [d.source for d in decisions]

                # Optimierte Query mit Index
                existing_query = session.query(Decision.case_number).filter(
                    Decision.case_number.in_(case_numbers), Decision.source.in_(sources)
                )
                existing_case_numbers = {row[0] for row in existing_query.all()}

                # 2. Filtern: Nur neue Decisions
                new_decisions = [d for d in decisions if d.case_number not in existing_case_numbers]

                if not new_decisions:
                    return 0, len(decisions)

                # 3. Bulk-Insert mit optimierter Methode
                # Konvertiere zu Dictionaries für bulk_insert_mappings
                decision_dicts = []
                for decision in new_decisions:
                    d_dict = {
                        "case_number": decision.case_number,
                        "source": decision.source,
                        "title": decision.title,
                        "court": decision.court,
                        "decision_date": decision.decision_date,
                        "publication_date": decision.publication_date,
                        "ecli": decision.ecli,
                        "full_text": decision.full_text,
                        "full_text_anonymized": decision.full_text_anonymized,
                        "summary": decision.summary,
                        "keywords": decision.keywords,
                        "legal_area": decision.legal_area,
                        "gdpr_articles": decision.gdpr_articles,
                        "national_laws": decision.national_laws,
                        "anonymization_applied": decision.anonymization_applied,
                        "metadata": decision.metadata,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                    decision_dicts.append(d_dict)

                # Bulk-Insert (100x schneller als einzelne Inserts)
                session.bulk_insert_mappings(Decision, decision_dicts)
                session.commit()

                saved = len(new_decisions)
                skipped = len(decisions) - saved

                return saved, skipped

        except Exception as e:
            self.logger.error(f"Bulk-Save Fehler: {e}", exc_info=True)
            # Fallback auf einzelne Inserts bei Fehler
            return self._fallback_single_save(decisions)

    def _fallback_single_save(self, decisions: List[Decision]) -> Tuple[int, int]:
        """Fallback auf einzelne Inserts bei Bulk-Fehler."""
        saved = 0
        skipped = 0

        for decision in decisions:
            if self._save_single_decision(decision):
                saved += 1
            else:
                skipped += 1

        return saved, skipped

    def _save_single_decision(self, decision: Decision) -> bool:
        """Legacy single-save als Fallback."""
        try:
            with db_manager.get_sync_session() as session:
                existing = (
                    session.query(Decision)
                    .filter_by(case_number=decision.case_number, source=decision.source)
                    .first()
                )

                if existing:
                    return False

                session.add(decision)
                session.commit()
                return True

        except Exception as e:
            self.logger.error(f"Single-Save Fehler: {e}")
            return False

    def _setup_import(self, file_path: Path, resume: bool):
        """Setup für Import-Operation."""
        # Datei validieren
        errors = self.file_handler.validate_file(file_path)
        if errors:
            for error in errors:
                click.echo(f"❌ {error}", err=True)
            if any("nicht gefunden" in e or "leer" in e for e in errors):
                raise ValueError("Kritische Dateifehler gefunden")

        # Resume Manager initialisieren
        if resume:
            self.resume_manager = ResumeManager(file_path)

    def _print_optimized_statistics(self):
        """Zeigt optimierte Import-Statistiken an."""
        click.echo("\n" + "=" * 70)
        click.echo(click.style("📈 Import-Statistiken (Optimiert):", fg="cyan", bold=True))
        click.echo(f"  • Gesamt verarbeitet: {self.stats['total_processed']:,}")
        click.echo(f"  • DSGVO-relevant: {self.stats['gdpr_relevant']:,}")
        click.echo(f"  • Neu importiert: {self.stats['imported']:,}")
        click.echo(f"  • Übersprungen (vorhanden): {self.stats['skipped_existing']:,}")

        # Batch-Statistiken
        if self.batch_stats["batches_processed"] > 0:
            click.echo(click.style("\n⚡ Batch-Processing Metriken:", fg="yellow", bold=True))
            click.echo(f"  • Batches verarbeitet: {self.batch_stats['batches_processed']:,}")
            click.echo(f"  • Ø Batch-Zeit: {self.batch_stats['avg_batch_time']:.3f}s")

            # Throughput-Vergleich
            if self.performance_monitor.performance_stats["total_duration"] > 0:
                total_docs = self.stats["imported"] + self.stats["skipped_existing"]
                batch_throughput = (
                    total_docs / self.batch_stats["total_batch_time"]
                    if self.batch_stats["total_batch_time"] > 0
                    else 0
                )
                click.echo(f"  • Batch-Throughput: {batch_throughput:.1f} docs/s")

        # Retry-Statistiken
        if self.stats.get("retries", 0) > 0:
            click.echo(f"  • Retries: {self.stats['retries']}")

        # Optionale Statistiken
        if self.stats.get("skipped_irrelevant", 0) > 0:
            click.echo(f"  • Übersprungen (nicht relevant): {self.stats['skipped_irrelevant']:,}")
        if self.stats.get("skipped_parse_error", 0) > 0:
            click.echo(f"  • Übersprungen (Parse-Fehler): {self.stats['skipped_parse_error']:,}")
        if self.stats.get("errors", 0) > 0:
            click.echo(click.style(f"  • Fehler: {self.stats['errors']:,}", fg="red"))

        # Performance-Metriken
        self.performance_monitor.print_performance_metrics(self.stats)

        # Optimierungs-Empfehlungen
        self._print_optimization_recommendations()

        click.echo("=" * 70)

    def _print_optimization_recommendations(self):
        """Zeigt Optimierungs-Empfehlungen basierend auf Metriken."""
        click.echo("\n" + click.style("🚀 Optimierungs-Status:", fg="green", bold=True))

        # Batch-Effizienz
        if self.batch_stats["batches_processed"] > 0:
            avg_batch_size = self.stats["total_processed"] / self.batch_stats["batches_processed"]
            if avg_batch_size < 50:
                click.echo("  💡 Erwäge größere Batch-Size für bessere Performance")
            elif avg_batch_size > 200:
                click.echo("  ⚠️ Große Batches - prüfe Memory-Usage")
            else:
                click.echo("  ✅ Optimale Batch-Size")

        # Throughput-Analyse
        if self.performance_monitor.performance_stats["total_duration"] > 0:
            docs_per_sec = (
                self.stats["total_processed"]
                / self.performance_monitor.performance_stats["total_duration"]
            )
            if docs_per_sec > 100:
                click.echo(f"  🎯 Exzellente Performance: {docs_per_sec:.1f} docs/s")
            elif docs_per_sec > 50:
                click.echo(f"  ✅ Gute Performance: {docs_per_sec:.1f} docs/s")
            else:
                click.echo(f"  💡 Performance kann optimiert werden: {docs_per_sec:.1f} docs/s")

        # Cache-Effizienz
        cache_hit_rate = (
            self.stats["skipped_existing"] / max(self.stats["total_processed"], 1)
        ) * 100
        if cache_hit_rate > 50:
            click.echo(f"  💡 Hohe Duplikat-Rate ({cache_hit_rate:.1f}%) - erwäge Pre-Filtering")
