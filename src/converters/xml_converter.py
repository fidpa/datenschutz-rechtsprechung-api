#!/usr/bin/env python3
"""
XML to JSON Converter.

Konvertiert XML-Dumps (z.B. EUR-Lex) zu JSON.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Iterator, Optional

from src.converters.base import BaseConverter
from src.utils.logging import get_logger


class XMLConverter(BaseConverter):
    """Converter für XML zu JSON."""

    def __init__(self, namespace_map: Optional[Dict[str, str]] = None):
        """
        Initialisiert den XML Converter.

        Args:
            namespace_map: Mapping von Namespace-Präfixen zu URIs
        """
        super().__init__("xml", "json")
        self.logger = get_logger("XMLConverter")
        self.namespace_map = namespace_map or {}

        # Standard-Namespaces für rechtliche Dokumente
        self.default_namespaces = {
            "eurlex": "http://eur-lex.europa.eu/",
            "celex": "http://publications.europa.eu/celex/",
            "xhtml": "http://www.w3.org/1999/xhtml",
        }
        self.namespace_map.update(self.default_namespaces)

    def convert_file(self, input_path: Path, output_path: Path) -> bool:
        """
        Konvertiert XML-Datei zu JSON.

        Args:
            input_path: XML-Eingabedatei
            output_path: JSON-Ausgabedatei

        Returns:
            True bei Erfolg
        """
        try:
            if not self.validate_input(input_path):
                self.logger.error(f"Ungültige Eingabedatei: {input_path}")
                return False

            # Parse XML
            tree = ET.parse(input_path)
            root = tree.getroot()

            # Konvertiere zu Dictionary
            data = self._element_to_dict(root)

            # Speichere als JSON
            self.save_as_json(data, output_path)

            self.logger.info(f"Erfolgreich konvertiert: {input_path} -> {output_path}")
            return True

        except ET.ParseError as e:
            self.logger.error(f"XML-Parse-Fehler: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Konvertierungsfehler: {e}")
            return False

    def convert_document(self, element: ET.Element) -> Dict[str, Any]:
        """
        Konvertiert XML-Element zu Dictionary.

        Args:
            element: XML-Element

        Returns:
            Dictionary-Repräsentation
        """
        return self._element_to_dict(element)

    def stream_convert(self, input_path: Path) -> Iterator[Dict[str, Any]]:
        """
        Streaming-Konvertierung für große XML-Dateien.

        Args:
            input_path: XML-Eingabedatei

        Yields:
            Konvertierte Dokumente
        """
        # Nutze iterparse für memory-effizientes Parsing
        for event, elem in ET.iterparse(input_path, events=("end",)):
            # Suche nach Dokument-Elementen (anpassbar)
            if (
                elem.tag.endswith("decision")
                or elem.tag.endswith("case")
                or elem.tag.endswith("judgment")
            ):
                yield self._element_to_dict(elem)
                # Speicher freigeben
                elem.clear()

    def _element_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """
        Rekursive Konvertierung von XML-Element zu Dictionary.

        Args:
            element: XML-Element

        Returns:
            Dictionary-Repräsentation
        """
        result = {}

        # Tag-Name (ohne Namespace)
        element.tag.split("}")[-1] if "}" in element.tag else element.tag

        # Attribute
        if element.attrib:
            result["@attributes"] = dict(element.attrib)

        # Text-Inhalt
        if element.text and element.text.strip():
            text = element.text.strip()
            if len(element) == 0:  # Keine Kinder
                return text if not result else {**result, "text": text}
            else:
                result["text"] = text

        # Kinder-Elemente
        children = {}
        for child in element:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            child_data = self._element_to_dict(child)

            if child_tag in children:
                # Mehrere Elemente mit gleichem Tag -> Liste
                if not isinstance(children[child_tag], list):
                    children[child_tag] = [children[child_tag]]
                children[child_tag].append(child_data)
            else:
                children[child_tag] = child_data

        if children:
            result.update(children)

        return result if result else None

    def convert_eurlex_xml(self, input_path: Path, output_path: Path) -> bool:
        """
        Spezialisierte Konvertierung für EUR-Lex XML.

        Args:
            input_path: EUR-Lex XML-Datei
            output_path: JSON-Ausgabedatei

        Returns:
            True bei Erfolg
        """
        try:
            documents = []

            for event, elem in ET.iterparse(input_path, events=("end",)):
                # EUR-Lex spezifische Dokument-Tags
                if elem.tag.endswith("NOTICE") or elem.tag.endswith("JUDGMENT"):
                    doc = self._extract_eurlex_document(elem)
                    if doc:
                        documents.append(doc)
                    elem.clear()

            # Speichere als JSON-Array
            self.save_as_json(documents, output_path)

            self.logger.info(f"EUR-Lex konvertiert: {len(documents)} Dokumente")
            return True

        except Exception as e:
            self.logger.error(f"EUR-Lex Konvertierungsfehler: {e}")
            return False

    def _extract_eurlex_document(self, element: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Extrahiert strukturierte Daten aus EUR-Lex XML-Element.

        Args:
            element: EUR-Lex XML-Element

        Returns:
            Strukturiertes Dokument oder None
        """
        try:
            doc = {"source": "eurlex", "type": "legal_document"}

            # CELEX-Nummer
            celex = element.find(".//CELEX_NUMBER", self.namespace_map)
            if celex is not None and celex.text:
                doc["celex_number"] = celex.text
                doc["id"] = celex.text

            # Titel
            title = element.find(".//TITLE", self.namespace_map)
            if title is not None and title.text:
                doc["title"] = title.text

            # Datum
            date = element.find(".//DATE_DOCUMENT", self.namespace_map)
            if date is not None and date.text:
                doc["date"] = date.text

            # Gericht/Institution
            court = element.find(".//AUTHOR", self.namespace_map)
            if court is not None and court.text:
                doc["court"] = court.text

            # Volltext
            text_elements = element.findall(".//TEXT", self.namespace_map)
            if text_elements:
                doc["text"] = " ".join([t.text for t in text_elements if t.text])

            # Rechtsgebiet
            subject = element.find(".//SUBJECT_MATTER", self.namespace_map)
            if subject is not None and subject.text:
                doc["legal_area"] = subject.text

            # Verfahrensart
            procedure = element.find(".//PROCEDURE_TYPE", self.namespace_map)
            if procedure is not None and procedure.text:
                doc["procedure_type"] = procedure.text

            return doc if "id" in doc else None

        except Exception as e:
            self.logger.warning(f"Fehler beim Extrahieren von EUR-Lex Dokument: {e}")
            return None
