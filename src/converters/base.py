#!/usr/bin/env python3
"""
Base Converter für Format-Konvertierungen.

Abstraktes Interface für verschiedene Datei-Format-Konverter.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Iterator
import json


class BaseConverter(ABC):
    """Abstrakte Basis-Klasse für Format-Konverter."""

    def __init__(self, source_format: str, target_format: str = "json"):
        """
        Initialisiert den Converter.

        Args:
            source_format: Quellformat (z.B. 'xml', 'csv', 'html')
            target_format: Zielformat (default: 'json')
        """
        self.source_format = source_format
        self.target_format = target_format

    @abstractmethod
    def convert_file(self, input_path: Path, output_path: Path) -> bool:
        """
        Konvertiert eine komplette Datei.

        Args:
            input_path: Pfad zur Eingabedatei
            output_path: Pfad zur Ausgabedatei

        Returns:
            True bei Erfolg, False bei Fehler
        """

    @abstractmethod
    def convert_document(self, document: Any) -> Dict[str, Any]:
        """
        Konvertiert ein einzelnes Dokument zu standardisiertem Format.

        Args:
            document: Dokument im Quellformat

        Returns:
            Dokument als Dictionary
        """

    @abstractmethod
    def stream_convert(self, input_path: Path) -> Iterator[Dict[str, Any]]:
        """
        Streaming-Konvertierung für große Dateien.

        Args:
            input_path: Pfad zur Eingabedatei

        Yields:
            Konvertierte Dokumente als Dictionaries
        """

    def validate_input(self, input_path: Path) -> bool:
        """
        Validiert die Eingabedatei.

        Args:
            input_path: Pfad zur Eingabedatei

        Returns:
            True wenn valide, sonst False
        """
        if not input_path.exists():
            return False
        if input_path.stat().st_size == 0:
            return False
        return True

    def save_as_json(self, data: Any, output_path: Path, pretty: bool = True):
        """
        Speichert Daten als JSON.

        Args:
            data: Zu speichernde Daten
            output_path: Ausgabepfad
            pretty: Pretty-Print aktivieren
        """
        with open(output_path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)

    def save_as_jsonl(self, documents: Iterator[Dict], output_path: Path):
        """
        Speichert Dokumente als JSONL (ein JSON pro Zeile).

        Args:
            documents: Iterator über Dokumente
            output_path: Ausgabepfad
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for doc in documents:
                json.dump(doc, f, ensure_ascii=False)
                f.write("\n")
