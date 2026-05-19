#!/usr/bin/env python3
"""
Swiss Court Ruling Corpus Importer.

Spezialisierte Implementierung für Schweizer Gerichtsentscheidungen.
Unterstützt Hugging Face Datasets und andere akademische Quellen.
"""

import re
from typing import Dict, Optional, Any, List
from datetime import datetime

from src.database import Decision
from src.importers.base import BaseImporter
from src.processors.anonymizer import get_anonymizer
from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.utils.logging import get_logger


class SwissDatasetImporter(BaseImporter):
    """Importer für Schweizer Gerichtsentscheidungs-Datasets."""

    # Schweizer Datenschutz-relevante Suchbegriffe (FADP/DSG)
    PRIVACY_KEYWORDS = {
        # Bundesgesetz über den Datenschutz (DSG/FADP)
        "fadp_high": [
            r"\bDSG\b",
            r"\bFADP\b",
            r"Datenschutzgesetz",
            r"Bundesgesetz über den Datenschutz",
            r"Art\.?\s*\d+\s+DSG",
            r"Artikel\s+\d+\s+DSG",
            r"LPD",  # Loi sur la protection des données
            r"LFPD",  # Loi fédérale sur la protection des données
        ],
        # DSGVO-Bezüge (EU-Schweiz)
        "dsr_relevance": [
            r"\bDSGVO\b",
            r"\bGDPR\b",
            r"\bRGPD\b",  # Französisch
            r"EU-?Datenschutz",
            r"Privacy Shield",
            r"Angemessenheitsbeschluss",
        ],
        # Datenschutzbehörden
        "authorities": [
            r"EDÖB",  # Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter
            r"PFPDT",  # Préposé fédéral à la protection des données
            r"Datenschutzbeauftragter",
            r"Öffentlichkeitsbeauftragter",
        ],
        # Spezifische Rechte
        "rights": [
            r"Auskunftsrecht",
            r"Löschung.*Daten",
            r"Berichtigung.*Daten",
            r"Datenportabilität",
            r"Widerspruchsrecht",
            r"Informationspflicht",
            r"droit d\'accès",  # Französisch
            r"droit de rectification",
        ],
        # Datenschutz-Begriffe
        "privacy_terms": [
            r"Personendaten",
            r"données personnelles",
            r"besonders schützenswerte",
            r"Persönlichkeitsverletzung",
            r"Datensicherheit",
            r"Datenbearbeitung",
            r"traitement de données",
        ],
    }

    def __init__(self, verbose: bool = False, min_score: int = 3):
        """
        Initialisiert den Swiss Dataset Importer.

        Args:
            verbose: Verbose Output
            min_score: Minimaler Datenschutz-Relevanz-Score
        """
        super().__init__(verbose)
        self.min_score = min_score
        self.anonymizer = get_anonymizer()
        self.gdpr_extractor = GDPRArticleExtractor()
        self.logger = get_logger("SwissDatasetImporter")

    def get_document_id(self, raw_data: Dict[str, Any]) -> str:
        """
        Extrahiert eindeutige ID aus Schweizer Dokument.

        Args:
            raw_data: Rohdaten aus dem Dataset

        Returns:
            Eindeutige Dokument-ID
        """
        # Verschiedene ID-Felder je nach Dataset-Format
        if "id" in raw_data:
            return str(raw_data["id"])
        elif "bge_id" in raw_data:  # Bundesgerichtsentscheid
            return raw_data["bge_id"]
        elif "file_number" in raw_data:
            return raw_data["file_number"]
        else:
            # Fallback: Hash aus verfügbaren Feldern
            import hashlib

            content = str(raw_data.get("text", ""))[:1000]
            return hashlib.md5(content.encode()).hexdigest()[:16]

    def is_relevant(self, raw_data: Dict[str, Any]) -> bool:
        """
        Prüft ob ein Dokument datenschutzrechtlich relevant ist.

        Args:
            raw_data: Rohdaten aus dem Dataset

        Returns:
            True wenn datenschutzrelevant
        """
        score = self.calculate_relevance_score(raw_data)
        return score >= self.min_score

    def calculate_relevance_score(self, doc_data: Dict) -> int:
        """
        Berechnet Datenschutz-Relevanz-Score für Schweizer Entscheidung.

        Args:
            doc_data: Rohdaten aus dem Dataset

        Returns:
            Relevanz-Score (0-50)
        """
        # Kombiniere alle Textfelder
        searchable_text = " ".join(
            [
                str(doc_data.get("text", "")),
                str(doc_data.get("title", "")),
                str(doc_data.get("summary", "")),
                str(doc_data.get("canton", "")),
                str(doc_data.get("legal_area", "")),
            ]
        ).lower()

        total_score = 0

        # Score-Mapping
        score_mapping = {
            "fadp_high": 10,  # DSG/FADP direkte Referenzen
            "dsr_relevance": 8,  # DSGVO-Bezüge
            "authorities": 7,  # Behördenbezug
            "rights": 6,  # Spezifische Rechte
            "privacy_terms": 4,  # Allgemeine Datenschutzbegriffe
        }

        # Durchsuche alle Kategorien
        for category, patterns in self.PRIVACY_KEYWORDS.items():
            category_score = score_mapping.get(category, 0)
            for pattern in patterns:
                if re.search(pattern, searchable_text, re.IGNORECASE):
                    total_score += category_score
                    break  # Nur einmal pro Kategorie

        # Bonus für Bundesgericht
        if "court" in doc_data:
            court = str(doc_data["court"]).lower()
            if "bundesgericht" in court or "tribunal fédéral" in court:
                total_score += 3

        # Bonus für bestimmte Rechtsgebiete
        if "legal_area" in doc_data:
            area = str(doc_data["legal_area"]).lower()
            if any(term in area for term in ["datenschutz", "persönlichkeit", "privacy"]):
                total_score += 5

        return min(total_score, 50)  # Cap bei 50

    def parse_document(self, raw_data: Dict[str, Any]) -> Optional[Decision]:
        """
        Parst ein Schweizer Gerichts-Dokument zu einer Decision.

        Args:
            raw_data: Rohdaten aus dem Dataset

        Returns:
            Decision-Objekt oder None bei Fehler
        """
        try:
            # Extrahiere Basis-Felder (verschiedene Formate unterstützen)
            title = raw_data.get("title") or raw_data.get("name", "Unbekannte Entscheidung")
            text = raw_data.get("text") or raw_data.get("content", "")

            # Datum parsen (verschiedene Formate)
            decision_date = self._parse_date(raw_data)

            # Gericht extrahieren
            court = self._extract_court(raw_data)

            # Aktenzeichen
            case_number = raw_data.get("file_number") or raw_data.get("case_number", "")

            # Kanton extrahieren
            canton = raw_data.get("canton", "")

            # Anonymisierung
            anonymized_text = text
            if text and self.anonymizer:
                try:
                    result = self.anonymizer.anonymize(text)
                    anonymized_text = result.anonymized_text
                except Exception as e:
                    self.logger.warning(f"Anonymisierung fehlgeschlagen: {e}")

            # DSGVO/DSG-Artikel extrahieren
            legal_references = self._extract_legal_references(text)

            # Decision erstellen
            decision = Decision(
                source="swiss_court_corpus",
                source_id=self.get_document_id(raw_data),
                source_url=raw_data.get("url", ""),
                title=title[:500],
                court=court,
                decision_date=decision_date,
                case_number=case_number,
                full_text_anonymized=anonymized_text,
                gdpr_articles=legal_references if legal_references else None,
            )

            # Metadaten hinzufügen
            metadata = {}
            if canton:
                metadata["canton"] = canton
            if "language" in raw_data:
                metadata["language"] = raw_data["language"]
            if "legal_area" in raw_data:
                metadata["legal_area"] = raw_data["legal_area"]
            if "bge_id" in raw_data:  # Bundesgerichtsentscheid-ID
                metadata["bge_id"] = raw_data["bge_id"]

            if metadata:
                decision.metadata = metadata

            return decision

        except Exception as e:
            self.logger.error(
                f"Fehler beim Parsen von Dokument {self.get_document_id(raw_data)}: {e}"
            )
            return None

    def _parse_date(self, raw_data: Dict) -> Optional[datetime]:
        """Parst Datum aus verschiedenen Formaten."""
        date_fields = ["date", "decision_date", "date_decided", "datum"]

        for field in date_fields:
            if field in raw_data and raw_data[field]:
                try:
                    date_str = str(raw_data[field])
                    # ISO-Format
                    if "T" in date_str:
                        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    # Deutsches Format (DD.MM.YYYY)
                    elif "." in date_str:
                        return datetime.strptime(date_str, "%d.%m.%Y")
                    # Standard Format (YYYY-MM-DD)
                    else:
                        return datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    continue
        return None

    def _extract_court(self, raw_data: Dict) -> str:
        """Extrahiert Gerichtsbezeichnung."""
        if "court" in raw_data:
            return str(raw_data["court"])

        # Aus Text extrahieren
        text = str(raw_data.get("text", ""))[:500]

        # Bekannte Schweizer Gerichte
        courts = {
            "Bundesgericht": ["Bundesgericht", "Tribunal fédéral", "Tribunale federale"],
            "Bundesverwaltungsgericht": [
                "Bundesverwaltungsgericht",
                "Tribunal administratif fédéral",
            ],
            "Bundesstrafgericht": ["Bundesstrafgericht", "Tribunal pénal fédéral"],
        }

        for court_name, patterns in courts.items():
            for pattern in patterns:
                if pattern in text:
                    return court_name

        # Kantonsgericht aus Kanton ableiten
        if "canton" in raw_data:
            return f"Kantonsgericht {raw_data['canton']}"

        return "Schweizer Gericht"

    def _extract_legal_references(self, text: str) -> List[str]:
        """Extrahiert DSG/FADP/DSGVO-Artikel-Referenzen."""
        references = []

        if not text:
            return references

        # DSG/FADP-Artikel
        dsg_pattern = r"Art\.?\s*(\d+)\s+(?:DSG|FADP|LPD)"
        for match in re.finditer(dsg_pattern, text, re.IGNORECASE):
            references.append(f"DSG Art. {match.group(1)}")

        # DSGVO-Artikel (falls EU-Bezug)
        if self.gdpr_extractor:
            gdpr_articles, _ = self.gdpr_extractor.extract_all(text)
            references.extend(gdpr_articles)

        # Deduplizieren und sortieren
        references = sorted(list(set(references)))

        return references[:10]  # Maximal 10 Referenzen

    def import_from_huggingface(self, dataset_name: str = "rcds/swiss_court_rulings", **kwargs):
        """
        Importiert direkt von Hugging Face Datasets.

        Args:
            dataset_name: Name des Hugging Face Datasets
            **kwargs: Weitere Parameter für import_from_file
        """
        try:
            from datasets import load_dataset

            self.logger.info(f"Lade Dataset von Hugging Face: {dataset_name}")
            dataset = load_dataset(dataset_name, split="train")

            # Konvertiere zu temporärer JSON-Datei
            import tempfile
            import json

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                # Dataset zu JSON konvertieren
                data = [dict(row) for row in dataset]
                json.dump(data, f)
                temp_path = f.name

            # Mit Standard-Import verarbeiten
            from pathlib import Path

            result = self.import_from_file(Path(temp_path), **kwargs)

            # Temp-Datei löschen
            Path(temp_path).unlink()

            return result

        except ImportError:
            self.logger.error(
                "Hugging Face datasets library nicht installiert. Installiere mit: pip install datasets"
            )
            raise
        except Exception as e:
            self.logger.error(f"Fehler beim Laden von Hugging Face Dataset: {e}")
            raise
