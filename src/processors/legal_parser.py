"""
Parser für deutsche Rechtsstruktur in Gerichtsentscheidungen.

Extrahiert strukturierte Abschnitte wie Leitsatz, Tenor, Tatbestand
und Entscheidungsgründe aus deutschsprachigen Gerichtsdokumenten.
"""

import re
from typing import Dict, Optional, Tuple
import structlog

logger = structlog.get_logger()


class LegalStructureParser:
    """Parser für deutsche Rechtsstruktur in Gerichtsentscheidungen."""

    def __init__(self):
        # Muster für Abschnittserkennung (case-insensitive)
        self.section_patterns = {
            "leitsatz": [
                r"(?:^|\n)\s*Leitsatz(?:\s*:|$)",
                r"(?:^|\n)\s*Leitsätze(?:\s*:|$)",
                r"(?:^|\n)\s*Orientierungssatz(?:\s*:|$)",
                r"(?:^|\n)\s*Orientierungssätze(?:\s*:|$)",
            ],
            "tenor": [
                r"(?:^|\n)\s*Tenor(?:\s*:|$)",
                r"(?:^|\n)\s*Urteilsformel(?:\s*:|$)",
                r"(?:^|\n)\s*Beschluss(?:\s*:|$)",
                r"(?:^|\n)\s*Entscheidungsformel(?:\s*:|$)",
            ],
            "tatbestand": [
                r"(?:^|\n)\s*Tatbestand(?:\s*:|$)",
                r"(?:^|\n)\s*Sachverhalt(?:\s*:|$)",
                r"(?:^|\n)\s*Sachverhalt und Verfahren(?:\s*:|$)",
                r"(?:^|\n)\s*I+\.\s*(?:Tatbestand|Sachverhalt)",
            ],
            "entscheidungsgruende": [
                r"(?:^|\n)\s*(?:Entscheidungs)?[Gg]ründe(?:\s*:|$)",
                r"(?:^|\n)\s*Begründung(?:\s*:|$)",
                r"(?:^|\n)\s*Urteilsgründe(?:\s*:|$)",
                r"(?:^|\n)\s*I+\.\s*(?:Gründe|Begründung)",
                r"(?:^|\n)\s*B\.\s*(?:Gründe|Begründung)",
            ],
        }

        # Endmarker für Abschnitte
        self.section_end_patterns = {
            "leitsatz": ["Tenor", "Tatbestand", "Sachverhalt", "Gründe"],
            "tenor": ["Tatbestand", "Sachverhalt", "Gründe", "Begründung"],
            "tatbestand": ["Gründe", "Begründung", "Entscheidungsgründe"],
            "entscheidungsgruende": [
                "Kostenentscheidung",
                "Rechtsmittelbelehrung",
                "Unterschriften",
            ],
        }

        # Muster für Rechtskraft-Status
        self.rechtskraft_patterns = {
            "rechtskraeftig": [
                r"rechtskräftig",
                r"ist\s+rechtskräftig",
                r"Rechtskraft\s+eingetreten",
                r"bestandskräftig",
            ],
            "berufung_moeglich": [
                r"Berufung\s+(?:ist\s+)?zulässig",
                r"kann\s+Berufung\s+eingelegt\s+werden",
                r"Rechtsmittel(?:belehrung)?",
            ],
            "berufung_eingelegt": [
                r"Berufung\s+(?:wurde\s+)?eingelegt",
                r"hat\s+Berufung\s+eingelegt",
                r"Berufungsverfahren\s+anhängig",
            ],
            "aufgehoben": [r"(?:wurde\s+)?aufgehoben", r"Aufhebung\s+(?:der|des)", r"hebt\s+auf"],
            "vergleich": [
                r"Vergleich\s+geschlossen",
                r"haben\s+sich\s+verglichen",
                r"Prozessvergleich",
            ],
        }

    def parse(self, text: str) -> Dict[str, Optional[str]]:
        """
        Parst den Text und extrahiert strukturierte Abschnitte.

        Args:
            text: Volltext der Entscheidung

        Returns:
            Dict mit extrahierten Abschnitten:
                - leitsatz: Leitsatz/Orientierungssatz
                - tenor: Tenor/Urteilsformel
                - tatbestand: Tatbestand/Sachverhalt
                - entscheidungsgruende: Entscheidungsgründe
                - rechtskraft_status: Erkannter Rechtskraft-Status
        """
        if not text:
            return {
                "leitsatz": None,
                "tenor": None,
                "tatbestand": None,
                "entscheidungsgruende": None,
                "rechtskraft_status": None,
            }

        result = {}

        # Hauptabschnitte extrahieren
        for section_name in ["leitsatz", "tenor", "tatbestand", "entscheidungsgruende"]:
            result[section_name] = self._extract_section(text, section_name)

        # Rechtskraft-Status ermitteln
        result["rechtskraft_status"] = self._detect_rechtskraft_status(text)

        # Statistiken loggen
        extracted_count = sum(1 for v in result.values() if v and v != "unbekannt")
        logger.info(
            "legal_structure_parsed",
            sections_found=extracted_count,
            rechtskraft=result["rechtskraft_status"],
        )

        return result

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Extrahiert einen spezifischen Abschnitt aus dem Text."""

        # Finde Startposition des Abschnitts
        start_pos, start_pattern = self._find_section_start(text, section_name)

        if start_pos == -1:
            return None

        # Finde Endposition (Beginn des nächsten Abschnitts)
        end_pos = self._find_section_end(text, section_name, start_pos)

        # Extrahiere Text zwischen Start und Ende
        if end_pos == -1:
            section_text = text[start_pos:]
        else:
            section_text = text[start_pos:end_pos]

        # Bereinige extrahierten Text
        section_text = self._clean_section_text(section_text, start_pattern)

        # Mindestlänge prüfen (zu kurze Abschnitte sind wahrscheinlich Fehlerkennungen)
        if len(section_text) < 20:
            return None

        # Maximal 5000 Zeichen pro Abschnitt (für DB-Speicherung)
        if len(section_text) > 5000:
            section_text = section_text[:4997] + "..."

        return section_text

    def _find_section_start(self, text: str, section_name: str) -> Tuple[int, str]:
        """Findet die Startposition eines Abschnitts."""

        patterns = self.section_patterns.get(section_name, [])

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.start(), match.group()

        return -1, ""

    def _find_section_end(self, text: str, section_name: str, start_pos: int) -> int:
        """Findet die Endposition eines Abschnitts."""

        # Suche nach Beginn des nächsten Abschnitts
        end_markers = self.section_end_patterns.get(section_name, [])

        min_end_pos = -1
        search_text = text[start_pos + 1 :]  # Nicht den eigenen Start matchen

        for marker in end_markers:
            # Erstelle Pattern für Marker
            pattern = r"(?:^|\n)\s*" + re.escape(marker) + r"(?:\s*:|$)"
            match = re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE)

            if match:
                actual_pos = start_pos + 1 + match.start()
                if min_end_pos == -1 or actual_pos < min_end_pos:
                    min_end_pos = actual_pos

        # Alternative: Suche nach typischen Endmarkern
        if min_end_pos == -1:
            # Römische Ziffern als Abschnittsbeginn
            roman_pattern = r"(?:^|\n)\s*(?:I{1,3}|IV|V|VI{0,3}|IX|X)\.\s*[A-Z]"
            match = re.search(roman_pattern, search_text, re.MULTILINE)
            if match:
                min_end_pos = start_pos + 1 + match.start()

        return min_end_pos

    def _clean_section_text(self, text: str, start_pattern: str) -> str:
        """Bereinigt den extrahierten Abschnittstext."""

        # Entferne das Start-Pattern selbst
        if start_pattern:
            text = text[len(start_pattern) :].lstrip(": \n")

        # Entferne führende/abschließende Whitespaces
        text = text.strip()

        # Entferne übermäßige Leerzeilen
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Entferne Seitenzahlen (z.B. "- 12 -")
        text = re.sub(r"\n\s*-\s*\d+\s*-\s*\n", "\n", text)

        return text

    def _detect_rechtskraft_status(self, text: str) -> str:
        """
        Ermittelt den Rechtskraft-Status aus dem Text.

        Returns:
            Status als String: rechtskraeftig, berufung_moeglich,
            berufung_eingelegt, aufgehoben, vergleich, unbekannt
        """

        # Prüfe Muster in Prioritätsreihenfolge
        for status, patterns in self.rechtskraft_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return status

        return "unbekannt"

    def extract_metadata(self, text: str) -> Dict[str, Optional[str]]:
        """
        Extrahiert zusätzliche Metadaten aus dem Text.

        Returns:
            Dict mit:
                - aktenzeichen: Gefundene Aktenzeichen
                - datum: Entscheidungsdatum
                - gericht: Gerichtsbezeichnung
        """
        metadata = {}

        # Aktenzeichen (verschiedene Formate)
        az_patterns = [
            r"\b\d+\s*[A-Z]+\s*\d+/\d+\b",  # z.B. "3 StR 123/20"
            r"\b[IVX]+\s*[A-Z]+\s*\d+/\d+\b",  # z.B. "VI ZR 456/19"
            r"\b\d+\s*[A-Z]\s*\d+/\d+\b",  # z.B. "1 C 789/21"
        ]

        for pattern in az_patterns:
            match = re.search(pattern, text)
            if match:
                metadata["aktenzeichen"] = match.group()
                break
        else:
            metadata["aktenzeichen"] = None

        # Datum (verschiedene Formate)
        datum_patterns = [
            r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b",  # z.B. "15.03.2024"
            r"\b\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*\d{4}\b",
        ]

        for pattern in datum_patterns:
            match = re.search(pattern, text[:1000])  # Nur am Anfang suchen
            if match:
                metadata["datum"] = match.group()
                break
        else:
            metadata["datum"] = None

        # Gericht
        gericht_patterns = [
            r"Bundesgerichtshof|BGH",
            r"Bundesverwaltungsgericht|BVerwG",
            r"Bundesarbeitsgericht|BAG",
            r"Oberlandesgericht|OLG\s+\w+",
            r"Landgericht|LG\s+\w+",
            r"Amtsgericht|AG\s+\w+",
            r"Verwaltungsgericht|VG\s+\w+",
        ]

        for pattern in gericht_patterns:
            match = re.search(pattern, text[:500], re.IGNORECASE)
            if match:
                metadata["gericht"] = match.group()
                break
        else:
            metadata["gericht"] = None

        return metadata


# Convenience-Funktionen
def parse_legal_structure(text: str) -> Dict[str, Optional[str]]:
    """Wrapper-Funktion für einfache Nutzung."""
    parser = LegalStructureParser()
    return parser.parse(text)


def extract_legal_metadata(text: str) -> Dict[str, Optional[str]]:
    """Extrahiert sowohl Struktur als auch Metadaten."""
    parser = LegalStructureParser()
    structure = parser.parse(text)
    metadata = parser.extract_metadata(text)
    return {**structure, **metadata}
