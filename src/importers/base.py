#!/usr/bin/env python3
"""
Base Importer für alle Dump-Import-Operationen.

Abstraktes Interface für verschiedene Datenquellen.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any
import time
import click
from tqdm import tqdm

from src.database import db_manager, Decision
from src.processors.performance_monitor import PerformanceMonitor
from src.processors.resume_manager import ResumeManager
from src.utils.file_handlers import DumpFileHandler
from src.utils.logging import get_logger


class BaseImporter(ABC):
    """Abstrakte Basis-Klasse für alle Dump-Importer."""

    def __init__(self, verbose: bool = False):
        """
        Initialisiert den Base Importer.

        Args:
            verbose: Verbose Output aktivieren
        """
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)
        self.performance_monitor = PerformanceMonitor()
        self.resume_manager = None
        self.file_handler = DumpFileHandler()

        # Import-Statistiken
        self.stats = {
            "total_processed": 0,
            "imported": 0,
            "skipped_existing": 0,
            "skipped_irrelevant": 0,
            "skipped_parse_error": 0,
            "gdpr_relevant": 0,
            "errors": 0,
        }

    @abstractmethod
    def parse_document(self, raw_data: Dict[str, Any]) -> Optional[Decision]:
        """
        Parst ein Dokument aus dem Dump zu einer Decision.

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            Decision-Objekt oder None bei Fehler
        """

    @abstractmethod
    def is_relevant(self, raw_data: Dict[str, Any]) -> bool:
        """
        Prüft ob ein Dokument relevant ist (z.B. DSGVO-Bezug).

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            True wenn relevant, sonst False
        """

    @abstractmethod
    def get_document_id(self, raw_data: Dict[str, Any]) -> str:
        """
        Extrahiert eindeutige ID aus einem Dokument.

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            Eindeutige Dokument-ID
        """

    def import_from_file(
        self,
        file_path: Path,
        limit: int = 0,
        offset: int = 0,
        filter_relevant: bool = True,
        resume: bool = False,
        dry_run: bool = False,
        batch_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Importiert Dokumente aus einer Dump-Datei.

        Args:
            file_path: Pfad zur Dump-Datei
            limit: Maximale Anzahl zu importierender Dokumente (0 = unbegrenzt)
            offset: Anzahl der zu überspringenden Dokumente
            filter_relevant: Nur relevante Dokumente importieren
            resume: Von letzter Position fortsetzen
            dry_run: Simulation ohne Datenbank-Änderungen
            batch_size: Anzahl Dokumente pro Batch

        Returns:
            Dictionary mit Import-Statistiken
        """
        # Setup
        self._setup_import(file_path, resume)

        # Resume handling
        if resume and self.resume_manager:
            resume_state = self.resume_manager.load_state()
            if resume_state:
                offset = resume_state.get("position", offset)
                self.stats = self.resume_manager.get_resume_stats()
                self.resume_manager.print_resume_info()

                # WICHTIG: Log Resume-Parameter
                if self.verbose:
                    self.logger.info(
                        f"Resume aktiviert: Position={offset}, Filter={filter_relevant}"
                    )
                    self.logger.info(f"Bisherige Statistiken: {self.stats}")

        # Performance tracking starten
        self.performance_monitor.start_tracking()

        try:
            # Import durchführen
            self._perform_import(
                file_path=file_path,
                limit=limit,
                offset=offset,
                filter_relevant=filter_relevant,
                dry_run=dry_run,
                batch_size=batch_size,
            )

            # Performance tracking stoppen
            self.performance_monitor.stop_tracking()

            # Statistiken anzeigen
            self._print_statistics()

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

    def _perform_import(
        self,
        file_path: Path,
        limit: int,
        offset: int,
        filter_relevant: bool,
        dry_run: bool,
        batch_size: int,
    ):
        """Führt den eigentlichen Import durch."""
        # Progress bar setup - bei unbegrenztem Import Schätzung verwenden
        if limit > 0:
            total = limit
        else:
            # Schätzung basierend auf typischer Dateigröße (~22.000 Dokumente)
            total = 22000 - offset if offset < 22000 else None

        pbar = tqdm(
            total=total,
            desc="Importiere",
            unit="docs",
            initial=self.stats.get("total_processed", 0),
            ncols=100,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        )

        # Batch-Verarbeitung
        documents_processed = 0

        # Über Dokumente iterieren
        for doc_idx, raw_document in enumerate(self.file_handler.open_file(file_path, offset)):
            # Limit prüfen
            if limit > 0 and documents_processed >= limit:
                break

            # Performance tracking
            start_time = time.time()

            # Debug: Erste paar Dokumente loggen
            if self.verbose and documents_processed < 3:
                doc_id = self.get_document_id(raw_document)
                self.logger.debug(
                    f"Verarbeite Dokument {documents_processed+1}: ID={doc_id}, filter_relevant={filter_relevant}"
                )

            # Dokument verarbeiten
            self._process_document(raw_document, filter_relevant, dry_run)

            # Performance metrics
            processing_time = time.time() - start_time
            self.performance_monitor.track_processing_time(processing_time)
            self.performance_monitor.track_memory_usage()

            documents_processed += 1
            self.stats["total_processed"] += 1
            pbar.update(1)

            # Statistiken in Progress-Bar anzeigen
            pbar.set_postfix(
                {
                    "DSGVO": self.stats.get("gdpr_relevant", 0),
                    "Import": self.stats.get("imported", 0),
                    "Skip": self.stats.get("skipped_irrelevant", 0),
                }
            )

            # Resume-State periodisch speichern
            if self.resume_manager and documents_processed % 100 == 0:
                position = offset + documents_processed
                doc_id = self.get_document_id(raw_document)
                self.resume_manager.save_state(position, self.stats, doc_id)

        pbar.close()

    def _process_document(self, raw_document: Dict, filter_relevant: bool, dry_run: bool):
        """Verarbeitet ein einzelnes Dokument."""
        try:
            # Relevanz prüfen
            is_doc_relevant = self.is_relevant(raw_document)

            # Debug-Logging für Filter-Entscheidung
            if self.verbose:
                doc_id = self.get_document_id(raw_document)
                self.logger.debug(
                    f"Dokument {doc_id}: relevant={is_doc_relevant}, filter_active={filter_relevant}"
                )

            # Filter anwenden
            if filter_relevant and not is_doc_relevant:
                self.stats["skipped_irrelevant"] += 1
                if self.verbose:
                    self.logger.debug(f"Dokument {doc_id} übersprungen (irrelevant)")
                return

            # DSGVO-relevant markieren (nur wenn Dokument verarbeitet wird)
            if is_doc_relevant:
                self.stats["gdpr_relevant"] += 1

            # Dokument parsen
            decision = self.parse_document(raw_document)
            if not decision:
                self.stats["skipped_parse_error"] += 1
                if self.verbose:
                    doc_id = self.get_document_id(raw_document)
                    self.logger.warning(f"Dokument {doc_id}: Parse-Fehler")
                return

            # In Datenbank speichern (wenn nicht dry-run)
            if not dry_run:
                if self._save_decision(decision):
                    self.stats["imported"] += 1
                    self.performance_monitor.increment_db_operations()
                    if self.verbose:
                        self.logger.info(f"Dokument {decision.case_number} importiert")
                else:
                    self.stats["skipped_existing"] += 1
                    if self.verbose:
                        self.logger.debug(f"Dokument {decision.case_number} bereits vorhanden")
            else:
                # Dry-run: nur zählen
                self.stats["imported"] += 1
                if self.verbose:
                    self.logger.info(f"Dry-Run: Dokument {decision.case_number} würde importiert")

        except Exception as e:
            self.stats["errors"] += 1
            if self.verbose:
                doc_id = self.get_document_id(raw_document)
                self.logger.error(f"Fehler bei Dokument {doc_id}: {e}")

    def _save_decision(self, decision: Decision) -> bool:
        """
        Speichert eine Decision in der Datenbank.

        Args:
            decision: Zu speichernde Decision

        Returns:
            True wenn gespeichert, False wenn bereits vorhanden
        """
        try:
            with db_manager.get_sync_session() as session:
                # Prüfe ob bereits vorhanden (via case_number)
                existing = (
                    session.query(Decision)
                    .filter_by(case_number=decision.case_number, source=decision.source)
                    .first()
                )

                if existing:
                    return False

                # Speichern
                session.add(decision)
                session.commit()
                return True

        except Exception as e:
            self.logger.error(f"DB-Fehler beim Speichern: {e}")
            return False

    def _print_statistics(self):
        """Zeigt Import-Statistiken an."""
        click.echo("\n" + "=" * 70)
        click.echo(click.style("📈 Import-Statistiken:", fg="cyan", bold=True))
        click.echo(f"  • Gesamt verarbeitet: {self.stats['total_processed']:,}")
        click.echo(f"  • DSGVO-relevant: {self.stats['gdpr_relevant']:,}")
        click.echo(f"  • Neu importiert: {self.stats['imported']:,}")
        click.echo(f"  • Übersprungen (vorhanden): {self.stats['skipped_existing']:,}")

        # Optionale Statistiken
        if self.stats.get("skipped_irrelevant", 0) > 0:
            click.echo(f"  • Übersprungen (nicht relevant): {self.stats['skipped_irrelevant']:,}")
        if self.stats.get("skipped_parse_error", 0) > 0:
            click.echo(f"  • Übersprungen (Parse-Fehler): {self.stats['skipped_parse_error']:,}")
        if self.stats.get("errors", 0) > 0:
            click.echo(click.style(f"  • Fehler: {self.stats['errors']:,}", fg="red"))

        # Performance-Metriken
        self.performance_monitor.print_performance_metrics(self.stats)
        self.performance_monitor.print_recommendations(self.stats)

        click.echo("=" * 70)
