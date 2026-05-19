#!/usr/bin/env python3
"""
CSV to JSON Converter.

Konvertiert CSV-Dumps zu JSON-Format.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, Iterator

from src.converters.base import BaseConverter
from src.utils.logging import get_logger


class CSVConverter(BaseConverter):
    """Converter für CSV zu JSON."""

    def __init__(self, delimiter: str = ",", encoding: str = "utf-8"):
        """
        Initialisiert den CSV Converter.

        Args:
            delimiter: CSV-Trennzeichen (default: Komma)
            encoding: Datei-Encoding (default: utf-8)
        """
        super().__init__("csv", "json")
        self.delimiter = delimiter
        self.encoding = encoding
        self.logger = get_logger("CSVConverter")

    def convert_file(self, input_path: Path, output_path: Path) -> bool:
        """
        Konvertiert CSV-Datei zu JSON.

        Args:
            input_path: CSV-Eingabedatei
            output_path: JSON-Ausgabedatei

        Returns:
            True bei Erfolg
        """
        try:
            if not self.validate_input(input_path):
                self.logger.error(f"Ungültige Eingabedatei: {input_path}")
                return False

            documents = []

            with open(input_path, "r", encoding=self.encoding) as f:
                # Delimiter automatisch erkennen wenn nötig
                if self.delimiter == "auto":
                    sample = f.read(4096)
                    f.seek(0)
                    sniffer = csv.Sniffer()
                    self.delimiter = sniffer.sniff(sample).delimiter

                reader = csv.DictReader(f, delimiter=self.delimiter)

                for row in reader:
                    # Konvertiere und bereinige
                    doc = self._clean_document(row)
                    if doc:
                        documents.append(doc)

            # Speichere als JSON
            self.save_as_json(documents, output_path)

            self.logger.info(f"CSV konvertiert: {len(documents)} Dokumente")
            return True

        except Exception as e:
            self.logger.error(f"CSV-Konvertierungsfehler: {e}")
            return False

    def convert_document(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Konvertiert CSV-Zeile zu Dictionary.

        Args:
            row: CSV-Zeile als Dictionary

        Returns:
            Bereinigtes Dictionary
        """
        return self._clean_document(row)

    def stream_convert(self, input_path: Path) -> Iterator[Dict[str, Any]]:
        """
        Streaming-Konvertierung für große CSV-Dateien.

        Args:
            input_path: CSV-Eingabedatei

        Yields:
            Konvertierte Dokumente
        """
        with open(input_path, "r", encoding=self.encoding) as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)

            for row in reader:
                doc = self._clean_document(row)
                if doc:
                    yield doc

    def _clean_document(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Bereinigt und normalisiert CSV-Zeile.

        Args:
            row: Rohe CSV-Zeile

        Returns:
            Bereinigtes Dictionary
        """
        doc = {}

        for key, value in row.items():
            if value and value.strip():
                # Entferne führende/trailing Whitespace
                value = value.strip()

                # Konvertiere None-Strings
                if value.lower() in ("null", "none", "n/a"):
                    continue

                # Versuche Typ-Konvertierung
                value = self._convert_type(value)

                # Normalisiere Feldnamen
                clean_key = self._normalize_field_name(key)
                doc[clean_key] = value

        return doc if doc else None

    def _convert_type(self, value: str) -> Any:
        """
        Versucht automatische Typ-Konvertierung.

        Args:
            value: String-Wert

        Returns:
            Konvertierter Wert
        """
        # Boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Integer
        try:
            return int(value)
        except ValueError:
            pass

        # Float
        try:
            return float(value)
        except ValueError:
            pass

        # JSON-Array oder Object
        if value.startswith("[") or value.startswith("{"):
            try:
                return json.loads(value)
            except:
                pass

        # String (default)
        return value

    def _normalize_field_name(self, field: str) -> str:
        """
        Normalisiert Feldnamen.

        Args:
            field: Original-Feldname

        Returns:
            Normalisierter Feldname
        """
        # Entferne Whitespace
        field = field.strip()

        # Ersetze Spaces und Bindestriche mit Underscore
        field = field.replace(" ", "_").replace("-", "_")

        # Lowercase
        field = field.lower()

        # Entferne nicht-alphanumerische Zeichen (außer Underscore)
        import re

        field = re.sub(r"[^\w]", "", field)

        return field

    def convert_swiss_csv(self, input_path: Path, output_path: Path) -> bool:
        """
        Spezialisierte Konvertierung für Schweizer CSV-Dumps.

        Args:
            input_path: Schweizer CSV-Datei
            output_path: JSON-Ausgabedatei

        Returns:
            True bei Erfolg
        """
        try:
            documents = []

            # Mapping für Schweizer Felder
            field_mapping = {
                "urteilsdatum": "date",
                "aktenzeichen": "case_number",
                "gericht": "court",
                "kanton": "canton",
                "rechtsgebiet": "legal_area",
                "urteilstext": "text",
                "zusammenfassung": "summary",
                "sprache": "language",
                "bge_nummer": "bge_id",
            }

            with open(input_path, "r", encoding=self.encoding) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)

                for row in reader:
                    doc = {}

                    # Mappe Felder
                    for swiss_field, standard_field in field_mapping.items():
                        if swiss_field in row and row[swiss_field]:
                            doc[standard_field] = row[swiss_field].strip()

                    # Füge restliche Felder hinzu
                    for key, value in row.items():
                        if key not in field_mapping and value and value.strip():
                            clean_key = self._normalize_field_name(key)
                            doc[clean_key] = self._convert_type(value.strip())

                    if doc:
                        doc["source"] = "swiss_csv"
                        documents.append(doc)

            # Speichere als JSON
            self.save_as_json(documents, output_path)

            self.logger.info(f"Schweizer CSV konvertiert: {len(documents)} Dokumente")
            return True

        except Exception as e:
            self.logger.error(f"Schweizer CSV-Konvertierungsfehler: {e}")
            return False
