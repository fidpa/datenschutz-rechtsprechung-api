#!/usr/bin/env python3
"""
File Handler für verschiedene Dump-Formate.

Unterstützt JSON, JSONL und GZ-komprimierte Dateien.
"""

import json
import gzip
from pathlib import Path
from typing import Iterator, Dict, Any, List
import click


class DumpFileHandler:
    """Handler für verschiedene Dump-Datei-Formate."""

    SUPPORTED_FORMATS = {".json", ".jsonl", ".gz"}
    MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB

    @staticmethod
    def detect_format(file_path: Path) -> str:
        """
        Erkennt das Format der Dump-Datei.

        Args:
            file_path: Pfad zur Datei

        Returns:
            Format-String: 'json', 'jsonl', 'json.gz', 'jsonl.gz'
        """
        name = file_path.name.lower()

        if name.endswith(".json.gz"):
            return "json.gz"
        elif name.endswith(".jsonl.gz"):
            return "jsonl.gz"
        elif name.endswith(".json"):
            return "json"
        elif name.endswith(".jsonl"):
            return "jsonl"
        elif name.endswith(".gz"):
            # Versuche zu erraten basierend auf Inhalt
            return DumpFileHandler._detect_gz_content_format(file_path)
        else:
            raise ValueError(f"Nicht unterstütztes Dateiformat: {file_path.suffix}")

    @staticmethod
    def _detect_gz_content_format(file_path: Path) -> str:
        """Erkennt Format einer GZ-Datei durch Inhalt."""
        try:
            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("["):
                    return "json.gz"
                elif first_line.startswith("{"):
                    # Könnte JSON oder JSONL sein
                    second_line = f.readline().strip()
                    if second_line and second_line.startswith("{"):
                        return "jsonl.gz"
                    else:
                        return "json.gz"
        except Exception:
            return "json.gz"  # Default

    @staticmethod
    def validate_file(file_path: Path) -> List[str]:
        """
        Validiert eine Dump-Datei.

        Args:
            file_path: Pfad zur Datei

        Returns:
            Liste von Fehlermeldungen (leer wenn valide)
        """
        errors = []

        # Existenz prüfen
        if not file_path.exists():
            errors.append(f"Datei nicht gefunden: {file_path}")
            return errors

        # Größe prüfen
        file_size = file_path.stat().st_size
        if file_size == 0:
            errors.append(f"Datei ist leer: {file_path}")
        elif file_size > DumpFileHandler.MAX_FILE_SIZE:
            size_gb = file_size / 1024 / 1024 / 1024
            errors.append(f"Datei sehr groß ({size_gb:.1f}GB) - Überprüfung empfohlen")

        # Format prüfen
        try:
            format_type = DumpFileHandler.detect_format(file_path)
            if not format_type:
                errors.append(f"Unbekanntes Dateiformat: {file_path.suffix}")
        except ValueError as e:
            errors.append(str(e))

        # Inhalt spot-check
        try:
            count = 0
            for _ in DumpFileHandler.open_file(file_path):
                count += 1
                if count >= 3:  # Nur erste 3 Einträge prüfen
                    break
            if count == 0:
                errors.append("Datei enthält keine gültigen JSON-Objekte")
        except Exception as e:
            errors.append(f"Fehler beim Lesen der Datei: {e}")

        return errors

    @staticmethod
    def open_file(file_path: Path, offset: int = 0) -> Iterator[Dict[str, Any]]:
        """
        Öffnet eine Dump-Datei und iteriert über Dokumente.

        Args:
            file_path: Pfad zur Datei
            offset: Anzahl der zu überspringenden Dokumente

        Yields:
            Einzelne Dokumente als Dictionaries
        """
        format_type = DumpFileHandler.detect_format(file_path)

        if format_type == "json":
            yield from DumpFileHandler._read_json(file_path, offset)
        elif format_type == "jsonl":
            yield from DumpFileHandler._read_jsonl(file_path, offset)
        elif format_type == "json.gz":
            yield from DumpFileHandler._read_json_gz(file_path, offset)
        elif format_type == "jsonl.gz":
            yield from DumpFileHandler._read_jsonl_gz(file_path, offset)
        else:
            raise ValueError(f"Nicht unterstütztes Format: {format_type}")

    @staticmethod
    def _read_json(file_path: Path, offset: int = 0) -> Iterator[Dict]:
        """Liest normale JSON-Datei (Array von Objekten)."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if i >= offset:
                        yield item
            elif isinstance(data, dict):
                # Einzelnes Objekt
                if offset == 0:
                    yield data

    @staticmethod
    def _read_jsonl(file_path: Path, offset: int = 0) -> Iterator[Dict]:
        """Liest JSONL-Datei (ein JSON-Objekt pro Zeile)."""
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= offset:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as e:
                            click.echo(f"⚠️ JSON-Fehler in Zeile {i+1}: {e}", err=True)
                            continue

    @staticmethod
    def _read_json_gz(file_path: Path, offset: int = 0) -> Iterator[Dict]:
        """Liest GZ-komprimierte JSON-Datei."""
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if i >= offset:
                        yield item
            elif isinstance(data, dict):
                if offset == 0:
                    yield data

    @staticmethod
    def _read_jsonl_gz(file_path: Path, offset: int = 0) -> Iterator[Dict]:
        """Liest GZ-komprimierte JSONL-Datei."""
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= offset:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as e:
                            click.echo(f"⚠️ JSON-Fehler in Zeile {i+1}: {e}", err=True)
                            continue

    @staticmethod
    def count_documents(file_path: Path) -> int:
        """
        Zählt Dokumente in einer Dump-Datei (schnell).

        Args:
            file_path: Pfad zur Datei

        Returns:
            Anzahl der Dokumente
        """
        count = 0
        format_type = DumpFileHandler.detect_format(file_path)

        # Für JSON-Arrays müssen wir alles laden
        if format_type in ["json", "json.gz"]:
            try:
                if format_type == "json":
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    with gzip.open(file_path, "rt", encoding="utf-8") as f:
                        data = json.load(f)

                if isinstance(data, list):
                    return len(data)
                else:
                    return 1
            except Exception:
                return 0

        # Für JSONL können wir Zeilen zählen (schneller)
        elif format_type == "jsonl":
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1

        elif format_type == "jsonl.gz":
            with gzip.open(file_path, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1

        return count

    @staticmethod
    def get_file_info(file_path: Path) -> Dict[str, Any]:
        """
        Sammelt Informationen über eine Dump-Datei.

        Args:
            file_path: Pfad zur Datei

        Returns:
            Dictionary mit Datei-Informationen
        """
        info = {
            "path": str(file_path),
            "name": file_path.name,
            "size_bytes": file_path.stat().st_size,
            "size_mb": file_path.stat().st_size / 1024 / 1024,
            "format": DumpFileHandler.detect_format(file_path),
        }

        # Document count (kann bei großen Dateien lange dauern)
        if info["size_mb"] < 100:  # Nur bei Dateien < 100MB
            try:
                info["document_count"] = DumpFileHandler.count_documents(file_path)
            except Exception:
                info["document_count"] = "unknown"
        else:
            info["document_count"] = "too_large_to_count"

        return info
