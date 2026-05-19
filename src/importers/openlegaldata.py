#!/usr/bin/env python3
"""
OpenLegalData Dump Importer.

Spezialisierte Implementierung für OpenLegalData JSON-Dumps.
"""

import re
import time
from typing import Dict, Optional, Any
from datetime import datetime

from src.database import Decision
from src.importers.base import BaseImporter
from src.processors.anonymizer import get_anonymizer
from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.utils.logging import get_logger


class OpenLegalDataImporter(BaseImporter):
    """Importer für OpenLegalData JSON-Dumps."""

    # DSGVO-relevante Suchbegriffe für Filterung mit Scoring
    GDPR_KEYWORDS = {
        # Hochrelevante Begriffe (Score 10)
        "high_relevance": [
            r"\bDSGVO\b",
            r"\bGDPR\b",
            r"Datenschutz-?Grundverordnung",
            r"Art\.?\s*\d+\s+DSGVO",
            r"Artikel\s+\d+\s+DSGVO",
            r"Verordnung\s*\(EU\)\s*2016/679",
            r"EU-?Datenschutz-?grundverordnung",
        ],
        # Mittlere Relevanz (Score 7)
        "medium_relevance": [
            r"personenbezogene(?:n)?\s+Daten",
            r"Betroffenenrechte",
            r"Datenschutzverstoß",
            r"Datenschutzverletzung",
            r"Verarbeitung.*personenbezogener.*Daten",
            r"Auftragsverarbeitung",
            r"Datenschutz-?Folgenabschätzung",
            r"Privacy\s*by\s*Design",
        ],
        # BDSG und nationale Umsetzung (Score 5)
        "bdsg_relevance": [
            r"\bBDSG-?neu\b",
            r"§\s*26\s+BDSG\b",
            r"§\s*\d+\s+BDSG\b",
            r"Bundesdatenschutzgesetz",
            r"\bBDSG\s*n\.?F\.?\b",
        ],
        # Spezifische Rechte (Score 8)
        "rights_relevance": [
            r"Auskunftsrecht.*(?:personenbezogen|Daten)",
            r"Löschungsanspruch.*(?:personenbezogen|Daten)",
            r"Recht auf Vergessenwerden",
            r"Recht auf Berichtigung.*(?:personenbezogen|Daten)",
            r"Recht auf Datenübertragbarkeit",
            r"Datenportabilität",
            r"Widerspruchsrecht.*(?:Datenverarbeitung|personenbezogen)",
            r"Einschränkung der Verarbeitung.*(?:personenbezogen|Daten)",
        ],
        # Rechtsdurchsetzung (Score 6)
        "enforcement_relevance": [
            r"Bußgeld.*Datenschutz",
            r"Datenschutzbehörde",
            r"Aufsichtsbehörde.*Datenschutz",
            r"\bBfDI\b|\bLfDI\b|\bDSK\b",  # Wortgrenzen hinzugefügt!
            r"Datenschutzbeauftragter",
            r"Schadensersatz.*Datenschutz",
        ],
        # Allgemeine Begriffe (Score 3)
        "general_relevance": [
            r"Einwilligung.*Datenverarbeitung",
            r"Datenschutzerklärung",
            r"Informationspflicht.*(?:Daten|DSGVO|BDSG)",
            r"Zweckbindung.*(?:personenbezogen|Daten)",
            r"Datenminimierung",
            r"Transparenz.*Datenverarbeitung",
        ],
    }

    def __init__(self, verbose: bool = False, min_score: int = 3):
        """
        Initialisiert den OpenLegalData Importer.

        Args:
            verbose: Verbose Output
            min_score: Minimaler DSGVO-Relevanz-Score
        """
        super().__init__(verbose)
        self.min_score = min_score
        self.anonymizer = get_anonymizer()
        self.gdpr_extractor = GDPRArticleExtractor()
        self.logger = get_logger("OpenLegalDataImporter")

    def get_document_id(self, raw_data: Dict[str, Any]) -> str:
        """
        Extrahiert eindeutige ID aus OpenLegalData-Dokument.

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            Eindeutige Dokument-ID
        """
        return str(raw_data.get("id", "unknown"))

    def is_relevant(self, raw_data: Dict[str, Any]) -> bool:
        """
        Prüft ob ein Dokument DSGVO-relevant ist.

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            True wenn DSGVO-relevant
        """
        score = self.calculate_relevance_score(raw_data)
        return score >= self.min_score

    def calculate_relevance_score(self, case_data: Dict) -> int:
        """
        Berechnet DSGVO-Relevanz-Score für eine Entscheidung.

        Args:
            case_data: Rohdaten aus dem Dump

        Returns:
            Relevanz-Score (0-50)
        """
        # Kombiniere alle Textfelder für die Suche
        searchable_text = " ".join(
            [
                str(case_data.get("name", "")),
                str(case_data.get("content", "")),
                str(case_data.get("slug", "")),
                " ".join(case_data.get("ecli", []))
                if isinstance(case_data.get("ecli"), list)
                else "",
            ]
        ).lower()

        total_score = 0

        # Score-Mapping für verschiedene Relevanz-Kategorien
        score_mapping = {
            "high_relevance": 10,
            "medium_relevance": 7,
            "bdsg_relevance": 5,
            "rights_relevance": 8,
            "enforcement_relevance": 6,
            "general_relevance": 3,
        }

        # Durchsuche alle Kategorien
        for category, patterns in self.GDPR_KEYWORDS.items():
            category_score = score_mapping.get(category, 0)
            for pattern in patterns:
                if re.search(pattern, searchable_text, re.IGNORECASE):
                    total_score += category_score
                    # Maximal einmal pro Kategorie zählen
                    break

        return min(total_score, 50)  # Cap bei 50 Punkten

    def parse_document(self, raw_data: Dict[str, Any]) -> Optional[Decision]:
        """
        Parst ein OpenLegalData-Dokument zu einer Decision.

        Args:
            raw_data: Rohdaten aus dem Dump

        Returns:
            Decision-Objekt oder None bei Fehler
        """
        try:
            # Basis-Felder extrahieren
            title = raw_data.get("name", "Unbekannte Entscheidung")
            content = raw_data.get("content", "")

            # Datum parsen
            date_str = raw_data.get("date")
            decision_date = None
            if date_str:
                try:
                    decision_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass

            # Gericht extrahieren
            court_data = raw_data.get("court", {})
            court_name = court_data.get("name") if isinstance(court_data, dict) else str(court_data)

            # Aktenzeichen
            file_number = raw_data.get("file_number", "")

            # ECLI
            ecli = raw_data.get("ecli", "")
            if isinstance(ecli, list):
                ecli = ecli[0] if ecli else ""

            # Anonymisierung mit Performance-Tracking
            anonymization_start = time.time()
            anonymized_content = content
            if content and self.anonymizer:
                try:
                    result = self.anonymizer.anonymize(content)
                    anonymized_content = result.anonymized_text
                except Exception as e:
                    self.logger.warning(f"Anonymisierung fehlgeschlagen: {e}")

            # Track anonymization time
            if hasattr(self.performance_monitor, "track_component_time"):
                anon_duration = time.time() - anonymization_start
                self.performance_monitor.track_component_time("anonymization", anon_duration)

            # DSGVO-Artikel extrahieren mit Performance-Tracking
            extraction_start = time.time()
            gdpr_articles = []
            if self.gdpr_extractor and content:
                gdpr_articles, _ = self.gdpr_extractor.extract_all(content)

            # Track extraction time
            if hasattr(self.performance_monitor, "track_component_time"):
                extract_duration = time.time() - extraction_start
                self.performance_monitor.track_component_time("extraction", extract_duration)

            # Decision-Objekt erstellen
            decision = Decision(
                source="openlegaldata_dump",
                source_id=str(raw_data.get("id", "")),
                source_url=raw_data.get("url", ""),
                title=title[:500],  # Begrenzen auf DB-Limit
                court=court_name,
                decision_date=decision_date,
                case_number=file_number,
                full_text_anonymized=anonymized_content,
                gdpr_articles=gdpr_articles if gdpr_articles else None,
            )

            # Zusätzliche Metadaten wenn vorhanden
            metadata = {}
            if "ecli" in raw_data and ecli:
                metadata["ecli"] = ecli

            if "jurisdiction" in raw_data:
                metadata["jurisdiction"] = raw_data["jurisdiction"]

            if "legal_area" in raw_data:
                metadata["legal_area"] = raw_data["legal_area"]

            if metadata:
                decision.metadata = metadata

            return decision

        except Exception as e:
            self.logger.error(
                f"Fehler beim Parsen von Dokument {self.get_document_id(raw_data)}: {e}"
            )
            return None

    def import_with_scoring(self, file_path, min_score: int = 3, **kwargs) -> Dict[str, Any]:
        """
        Importiert mit spezifischem Mindest-Score.

        Args:
            file_path: Pfad zur Dump-Datei
            min_score: Minimaler DSGVO-Relevanz-Score
            **kwargs: Weitere Argumente für import_from_file

        Returns:
            Import-Statistiken
        """
        self.min_score = min_score
        return self.import_from_file(file_path, **kwargs)

    def get_score_distribution(self, file_path, sample_size: int = 1000) -> Dict[int, int]:
        """
        Analysiert Score-Verteilung in einer Dump-Datei.

        Args:
            file_path: Pfad zur Dump-Datei
            sample_size: Anzahl zu analysierender Dokumente

        Returns:
            Dictionary mit Score -> Anzahl Mapping
        """
        score_distribution = {}

        for idx, raw_document in enumerate(self.file_handler.open_file(file_path)):
            if idx >= sample_size:
                break

            score = self.calculate_relevance_score(raw_document)
            score_distribution[score] = score_distribution.get(score, 0) + 1

        return dict(sorted(score_distribution.items(), reverse=True))
