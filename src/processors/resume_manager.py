#!/usr/bin/env python3
"""
Resume Manager für unterbrochene Import-Operationen.

Speichert und lädt Import-Zustand für Resume-Funktionalität.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import click


class ResumeManager:
    """Manager für Resume-State bei unterbrochenen Imports."""

    def __init__(self, input_file: Path, resume_file: Optional[Path] = None):
        """
        Initialisiert den Resume Manager.

        Args:
            input_file: Pfad zur Input-Datei
            resume_file: Optionaler Pfad zur Resume-Datei
        """
        self.input_file = input_file
        self.resume_file = resume_file or self._get_default_resume_file()
        self.state = {}
        self.file_hash = self._calculate_file_hash()

    def _get_default_resume_file(self) -> Path:
        """Generiert Standard-Resume-Dateinamen basierend auf Input-Datei."""
        return self.input_file.parent / f".resume_{self.input_file.stem}.json"

    def _calculate_file_hash(self) -> str:
        """Berechnet MD5-Hash der ersten 1MB der Input-Datei."""
        try:
            with open(self.input_file, "rb") as f:
                # Erste 1MB für Hash verwenden (schneller bei großen Dateien)
                data = f.read(1024 * 1024)
                return hashlib.md5(data).hexdigest()
        except Exception as e:
            click.echo(f"⚠️ Warnung: Konnte File-Hash nicht berechnen: {e}", err=True)
            return ""

    def load_state(self) -> Dict[str, Any]:
        """
        Lädt gespeicherten Resume-State.

        Returns:
            Dictionary mit Resume-State oder leeres Dict
        """
        if not self.resume_file.exists():
            return {}

        try:
            with open(self.resume_file, "r") as f:
                state = json.load(f)

            # Validierung
            if self.validate_state(state):
                self.state = state
                return state
            else:
                click.echo("⚠️ Resume-State ungültig oder veraltet, starte neu", err=True)
                return {}

        except Exception as e:
            click.echo(f"⚠️ Fehler beim Laden des Resume-State: {e}", err=True)
            return {}

    def validate_state(self, state: Dict) -> bool:
        """
        Validiert Resume-State.

        Args:
            state: Zu validierender State

        Returns:
            True wenn State gültig, sonst False
        """
        # Prüfe erforderliche Felder
        required_fields = ["position", "timestamp", "file_hash", "stats"]
        if not all(field in state for field in required_fields):
            return False

        # Prüfe File-Hash (Datei hat sich geändert?)
        if state.get("file_hash") != self.file_hash:
            click.echo("⚠️ Input-Datei hat sich geändert seit letztem Resume", err=True)
            return False

        # Prüfe Alter (älter als 7 Tage?)
        try:
            timestamp = datetime.fromisoformat(state["timestamp"])
            age_days = (datetime.now() - timestamp).days
            if age_days > 7:
                click.echo(f"⚠️ Resume-State ist {age_days} Tage alt", err=True)
                return False
        except Exception:
            return False

        return True

    def save_state(self, position: int, stats: Dict, case_id: Optional[str] = None):
        """
        Speichert aktuellen Import-State.

        Args:
            position: Aktuelle Position im Import
            stats: Aktuelle Statistiken
            case_id: Optionale Case-ID für Debugging
        """
        self.state = {
            "position": position,
            "timestamp": datetime.now().isoformat(),
            "file_hash": self.file_hash,
            "input_file": str(self.input_file),
            "stats": stats,
            "last_case_id": case_id,
        }

        try:
            # Atomic write mit temporärer Datei
            temp_file = self.resume_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(self.state, f, indent=2)

            # Atomic rename
            temp_file.replace(self.resume_file)

        except Exception as e:
            click.echo(f"⚠️ Fehler beim Speichern des Resume-State: {e}", err=True)

    def cleanup(self):
        """Löscht Resume-Datei nach erfolgreichem Import."""
        if self.resume_file.exists():
            try:
                self.resume_file.unlink()
                click.echo(f"✅ Resume-Datei gelöscht: {self.resume_file}")
            except Exception as e:
                click.echo(f"⚠️ Konnte Resume-Datei nicht löschen: {e}", err=True)

    def get_resume_position(self) -> int:
        """
        Gibt Resume-Position zurück.

        Returns:
            Position zum Fortsetzen oder 0
        """
        return self.state.get("position", 0)

    def get_resume_stats(self) -> Dict:
        """
        Gibt Resume-Statistiken zurück.

        Returns:
            Gespeicherte Statistiken oder leeres Dict
        """
        return self.state.get("stats", {})

    def is_resuming(self) -> bool:
        """
        Prüft ob ein Resume aktiv ist.

        Returns:
            True wenn Resume-State geladen wurde
        """
        return bool(self.state)

    def print_resume_info(self):
        """Zeigt Resume-Informationen an."""
        if not self.is_resuming():
            return

        click.echo("\n" + click.style("🔄 RESUME-MODUS AKTIVIERT", fg="yellow", bold=True))
        click.echo(f"  • Fortsetzen bei Position: {self.get_resume_position():,}")
        click.echo(f"  • Letzte Case-ID: {self.state.get('last_case_id', 'N/A')}")
        click.echo(f"  • Zeitstempel: {self.state.get('timestamp', 'N/A')}")

        stats = self.get_resume_stats()
        if stats:
            click.echo(f"  • Bisherige Statistiken:")
            click.echo(f"    - Verarbeitet: {stats.get('total_processed', 0):,}")
            click.echo(f"    - Importiert: {stats.get('imported', 0):,}")
            click.echo(f"    - DSGVO-relevant: {stats.get('gdpr_relevant', 0):,}")
        click.echo("")
