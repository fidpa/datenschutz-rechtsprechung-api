"""
Intelligente Anonymisierung für deutsche Rechtstexte.
Anonymisiert Personennamen unter Beibehaltung rechtlicher Begriffe.
"""

import re
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass

# Try to import spacy, but provide fallback if not available
try:
    import spacy
    from spacy.language import Language

    SPACY_AVAILABLE = True
except Exception as e:
    # spaCy not available or incompatible (catches all errors including pydantic issues)
    SPACY_AVAILABLE = False
    Language = None
    import warnings

    warnings.warn(f"spaCy could not be imported: {e}. Using regex-based anonymizer.")

from src.utils.logging import get_logger

logger = get_logger("anonymizer")


@dataclass
class AnonymizationResult:
    """Ergebnis der Anonymisierung."""

    anonymized_text: str
    mappings: Dict[str, str]  # Platzhalter -> Original-Hash
    entity_types: Dict[str, str]  # Platzhalter -> Entity-Type
    stats: Dict[str, int]  # Statistiken


class SimpleGermanLegalAnonymizer:
    """Regex-basierter Anonymisierer für deutsche Rechtstexte - spaCy-unabhängig."""

    def __init__(self):
        """
        Initialisiert den Regex-basierten Anonymisierer.
        Funktioniert ohne externe NLP-Bibliotheken.
        """
        self.person_counter = 0
        self.org_counter = 0
        self.location_counter = 0

        # Rechtsbegriffe, die NICHT anonymisiert werden sollen
        self.legal_roles = {
            # Prozessrollen
            "Kläger",
            "Klägerin",
            "Kläger",
            "Klägerinnen",
            "Beklagter",
            "Beklagte",
            "Beklagten",
            "Beklagten",
            "Antragsteller",
            "Antragstellerin",
            "Antragstellerinnen",
            "Antragsgegner",
            "Antragsgegnerin",
            "Antragsgegnerinnen",
            "Beschwerdeführer",
            "Beschwerdeführerin",
            "Beschwerdeführerinnen",
            "Beschwerdegegner",
            "Beschwerdegegnerin",
            "Beschwerdegegnerinnen",
            "Revisionsführer",
            "Revisionsführerin",
            "Revisionsgegner",
            "Revisionsgegnerin",
            "Berufungskläger",
            "Berufungsklägerin",
            "Berufungsbeklagter",
            "Berufungsbeklagte",
            # Prozessbegriffe mit Artikeln
            "Die Berufung",
            "Der Antrag",
            "Die Revision",
            "Die Klage",
            "Das Verfahren",
            "Die Beschwerde",
            "Der Widerspruch",
            "Die Anfechtung",
            "Der Einspruch",
            "Die Vollstreckung",
            # Gerichtsrollen
            "Richter",
            "Richterin",
            "Richterinnen",
            "Vorsitzender",
            "Vorsitzende",
            "Vorsitzenden",
            "Berichterstatter",
            "Berichterstatterin",
            "Beisitzer",
            "Beisitzerin",
            "Beisitzerinnen",
            "Staatsanwalt",
            "Staatsanwältin",
            "Vertreter des öffentlichen Interesses",
            # Weitere rechtliche Rollen
            "Rechtsanwalt",
            "Rechtsanwältin",
            "Rechtsanwälte",
            "Notar",
            "Notarin",
            "Sachverständiger",
            "Sachverständige",
            "Zeuge",
            "Zeugin",
            "Zeugen",
            "Geschädigter",
            "Geschädigte",
            "Schuldner",
            "Schuldnerin",
            "Gläubiger",
            "Gläubigerin",
            "Erbe",
            "Erbin",
            "Erben",
            "Testamentsvollstrecker",
            "Testamentsvollstreckerin",
            "Verfahrensbeistand",
            "Verfahrensbeiständin",
            # Behörden und Institutionen
            "Verantwortlicher",
            "Verantwortliche",
            "Auftragsverarbeiter",
            "Auftragsverarbeiterin",
            "Datenschutzbeauftragter",
            "Datenschutzbeauftragte",
            "Aufsichtsbehörde",
            "Landesbeauftragte",
            "Bundesbeauftragte",
            "Landesbeauftragter",
            "Datenschutzbehörde",
            "Aufsichtsstelle",
            # Weitere Verfahrensbeteiligte
            "Beigeladener",
            "Beigeladene",
            "Nebenintervenient",
            "Streithelfer",
            "Streithelferin",
            "Nebenkläger",
            "Privatkläger",
            "Privatklägerin",
            "Beteiligter",
        }

        # Gerichtsabkürzungen und rechtliche Institutionen
        self.court_abbreviations = {
            "BGH",
            "BVerfG",
            "BVerwG",
            "BSG",
            "BFH",
            "BAG",
            "OLG",
            "LG",
            "AG",
            "VG",
            "OVG",
            "VGH",
            "FG",
            "LSG",
            "LAG",
            "EuGH",
            "EGMR",
            "BPatG",
            "BVA",
            "BKartA",
            "LfDI",
            "BfDI",  # Datenschutzbehörden
            "DSK",  # Datenschutzkonferenz
        }

        # Erweiterte Kontextmuster für Rechtsbegriffe
        self.legal_context_patterns = [
            r"\b(Die|Der|Das)\s+(Berufung|Revision|Klage|Beschwerde)\b",
            r"\b(gemäß|nach|laut)\s+Art\.",
            r"\b(gemäß|nach|laut)\s+§",
            r"\bim\s+Sinne\s+des?\s+Art\.",
            r"\bim\s+Sinne\s+des?\s+§",
            r"\bin\s+Verbindung\s+mit\s+Art\.",
            r"\bin\s+Verbindung\s+mit\s+§",
            r"\bauf\s+Grund\s+von\s+Art\.",
            r"\bauf\s+Grund\s+von\s+§",
        ]

        self.stats = {
            "texts_processed": 0,
            "names_anonymized": 0,
            "organizations_anonymized": 0,
            "locations_anonymized": 0,
        }

        logger.info("simple_anonymizer_initialized", mode="regex-based")

    def anonymize(
        self, text: str, anonymize_orgs: bool = True, anonymize_locations: bool = False
    ) -> AnonymizationResult:
        """Anonymisiert Text mit Regex-Patterns."""
        if not text:
            return AnonymizationResult("", {}, {}, {})

        self.person_counter = 0
        self.org_counter = 0
        self.location_counter = 0
        mappings = {}
        entity_types = {}

        # 1. Email-Adressen
        text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)

        # 2. Telefonnummern
        text = re.sub(r"(?:\+49|0049|0)[\s\-]?(?:\d[\s\-]?){10,}", "[TELEFON]", text)

        # 3. IBAN
        text = re.sub(r"\b[A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){4,5}\b", "[IBAN]", text)

        # 4. Postleitzahlen mit Ort
        text = re.sub(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+[a-zäöüß]+)?\b", "[PLZ ORT]", text)

        # 5. Aktenzeichen (nicht anonymisieren, nur markieren)
        # Diese bleiben erhalten

        # 6. Geburtsdaten
        text = re.sub(
            r"\b(?:0?[1-9]|[12][0-9]|3[01])\.(?:0?[1-9]|1[0-2])\.\d{4}\b", "[GEBURTSDATUM]", text
        )

        # 7. Personennamen (Herr/Frau + Name)
        def replace_person_title(match):
            full_match = match.group(0)
            name_part = match.group(2)

            # Prüfe Rechtsbegriffe und Kontext
            if name_part not in self.legal_roles and not self._is_in_legal_context(
                match.start(), text
            ):
                self.person_counter += 1
                replacement = f"[Person {self.person_counter}]"
                text_hash = hashlib.sha256(full_match.encode()).hexdigest()
                mappings[replacement] = text_hash
                entity_types[replacement] = "PERSON"
                self.stats["names_anonymized"] += 1
                return replacement
            return full_match

        text = re.sub(
            r"\b(Herr|Frau|Dr\.|Prof\.|Dipl\.-Ing\.)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)",
            replace_person_title,
            text,
        )

        # 8. Firmennamen (GmbH, AG, etc.)
        if anonymize_orgs:

            def replace_company(match):
                full_match = match.group(0)
                # Prüfe ob es eine Behörde ist
                if any(
                    keyword in full_match
                    for keyword in ["Gericht", "Amt", "Behörde", "Ministerium"]
                ):
                    return full_match
                self.org_counter += 1
                replacement = f"[Organisation {self.org_counter}]"
                text_hash = hashlib.sha256(full_match.encode()).hexdigest()
                mappings[replacement] = text_hash
                entity_types[replacement] = "ORGANIZATION"
                self.stats["organizations_anonymized"] += 1
                return replacement

            text = re.sub(
                r"\b[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]?[a-zäöüß]+)*\s+(?:GmbH|AG|KG|OHG|e\.V\.|gGmbH|UG|GbR)\b",
                replace_company,
                text,
            )

        # 9. Adressen
        text = re.sub(
            r"\b[A-ZÄÖÜ][a-zäöüß]+(?:straße|weg|platz|allee|ring|damm)\s+\d+[a-z]?\b",
            "[ADRESSE]",
            text,
        )

        self.stats["texts_processed"] += 1

        return AnonymizationResult(
            anonymized_text=text,
            mappings=mappings,
            entity_types=entity_types,
            stats=self.stats.copy(),
        )

    def _is_in_legal_context(self, position: int, text: str) -> bool:
        """Prüft ob Position in rechtlichem Kontext steht."""
        context_start = max(0, position - 100)
        context_end = min(len(text), position + 100)
        context = text[context_start:context_end]

        # Prüfe rechtliche Kontextmuster
        for pattern in self.legal_context_patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return True
        return False

    def bulk_anonymize(self, texts: List[str], **kwargs) -> List[AnonymizationResult]:
        """Anonymisiert mehrere Texte."""
        results = []
        for text in texts:
            results.append(self.anonymize(text, **kwargs))
        return results

    def get_statistics(self) -> Dict[str, int]:
        """Gibt Anonymisierungs-Statistiken zurück."""
        return self.stats.copy()

    def reset_statistics(self):
        """Setzt Statistiken zurück."""
        self.stats = {
            "texts_processed": 0,
            "names_anonymized": 0,
            "organizations_anonymized": 0,
            "locations_anonymized": 0,
        }


class GermanLegalAnonymizer:
    """Anonymisiert Personendaten unter Beibehaltung von Rechtsbegriffen."""

    def __init__(self, nlp: Optional[Language] = None):
        """
        Initialisiert den Anonymisierer.

        Args:
            nlp: Vorgeladenes spaCy-Modell (optional)
        """
        if not SPACY_AVAILABLE:
            logger.warning(
                "spacy_not_available",
                message="spaCy not available, using SimpleGermanLegalAnonymizer as fallback",
            )
            # Delegiere an SimpleGermanLegalAnonymizer
            self._fallback = SimpleGermanLegalAnonymizer()
            self.nlp = None
        elif nlp is None:
            try:
                self.nlp = spacy.load("de_core_news_sm")
                logger.info("spacy_model_loaded", model="de_core_news_sm")
                self._fallback = None
            except OSError:
                logger.warning(
                    "spacy_model_not_found",
                    model="de_core_news_sm",
                    message="Falling back to regex-based anonymizer",
                )
                self._fallback = SimpleGermanLegalAnonymizer()
                self.nlp = None
        else:
            self.nlp = nlp
            self._fallback = None

        # Rechtsbegriffe, die NICHT anonymisiert werden sollen
        self.legal_roles = {
            # Prozessrollen
            "Kläger",
            "Klägerin",
            "Kläger",
            "Klägerinnen",
            "Beklagter",
            "Beklagte",
            "Beklagten",
            "Beklagten",
            "Antragsteller",
            "Antragstellerin",
            "Antragstellerinnen",
            "Antragsgegner",
            "Antragsgegnerin",
            "Antragsgegnerinnen",
            "Beschwerdeführer",
            "Beschwerdeführerin",
            "Beschwerdeführerinnen",
            "Beschwerdegegner",
            "Beschwerdegegnerin",
            "Beschwerdegegnerinnen",
            "Revisionsführer",
            "Revisionsführerin",
            "Revisionsgegner",
            "Revisionsgegnerin",
            "Berufungskläger",
            "Berufungsklägerin",
            "Berufungsbeklagter",
            "Berufungsbeklagte",
            # Prozessbegriffe mit Artikeln
            "Die Berufung",
            "Der Antrag",
            "Die Revision",
            "Die Klage",
            "Das Verfahren",
            "Die Beschwerde",
            "Der Widerspruch",
            "Die Anfechtung",
            "Der Einspruch",
            "Die Vollstreckung",
            # Gerichtsrollen
            "Richter",
            "Richterin",
            "Richterinnen",
            "Vorsitzender",
            "Vorsitzende",
            "Vorsitzenden",
            "Berichterstatter",
            "Berichterstatterin",
            "Beisitzer",
            "Beisitzerin",
            "Beisitzerinnen",
            "Staatsanwalt",
            "Staatsanwältin",
            "Vertreter des öffentlichen Interesses",
            # Weitere rechtliche Rollen
            "Rechtsanwalt",
            "Rechtsanwältin",
            "Rechtsanwälte",
            "Notar",
            "Notarin",
            "Sachverständiger",
            "Sachverständige",
            "Zeuge",
            "Zeugin",
            "Zeugen",
            "Geschädigter",
            "Geschädigte",
            "Schuldner",
            "Schuldnerin",
            "Gläubiger",
            "Gläubigerin",
            "Erbe",
            "Erbin",
            "Erben",
            "Testamentsvollstrecker",
            "Testamentsvollstreckerin",
            "Verfahrensbeistand",
            "Verfahrensbeiständin",
            # Behörden und Institutionen
            "Verantwortlicher",
            "Verantwortliche",
            "Auftragsverarbeiter",
            "Auftragsverarbeiterin",
            "Datenschutzbeauftragter",
            "Datenschutzbeauftragte",
            "Aufsichtsbehörde",
            "Landesbeauftragte",
            "Bundesbeauftragte",
            "Landesbeauftragter",
            "Datenschutzbehörde",
            "Aufsichtsstelle",
            # Weitere Verfahrensbeteiligte
            "Beigeladener",
            "Beigeladene",
            "Nebenintervenient",
            "Streithelfer",
            "Streithelferin",
            "Nebenkläger",
            "Privatkläger",
            "Privatklägerin",
            "Beteiligter",
        }

        # Gerichtsabkürzungen und rechtliche Institutionen
        self.court_abbreviations = {
            "BGH",
            "BVerfG",
            "BVerwG",
            "BSG",
            "BFH",
            "BAG",
            "OLG",
            "LG",
            "AG",
            "VG",
            "OVG",
            "VGH",
            "FG",
            "LSG",
            "LAG",
            "EuGH",
            "EGMR",
            "BPatG",
            "BVA",
            "BKartA",
            "LfDI",
            "BfDI",  # Datenschutzbehörden
            "DSK",  # Datenschutzkonferenz
        }

        # Muster für rechtliche Verweise, die erhalten bleiben müssen
        self.preserve_patterns = [
            r"Art\.\s*\d+",  # Art. 6
            r"§\s*\d+",  # § 26
            r"\b(" + "|".join(self.court_abbreviations) + r")\b",
            r"\b\d+\s*[A-Z]+\s*\d+/\d+\b",  # Aktenzeichen: 1 ZR 140/22
            r"[IVX]+\s*[A-Z]+\s*\d+/\d+",  # Römische Ziffern: VI ZR 140/22
            r"Az\.\s*[A-Za-z0-9\s\-/]+",  # Az. 123/45
            r"Urteil vom\s*\d{1,2}\.\d{1,2}\.\d{4}",  # Urteil vom 01.01.2024
            r"Beschluss vom\s*\d{1,2}\.\d{1,2}\.\d{4}",  # Beschluss vom 01.01.2024
            r"\b(Die|Der|Das)\s+(Berufung|Revision|Klage|Beschwerde)\b",
            r"\b(gemäß|nach|laut)\s+(Art\.|§)",
            r"\bim\s+Sinne\s+des?\s+(Art\.|§)",
            r"\bin\s+Verbindung\s+mit\s+(Art\.|§)",
            r"\bauf\s+Grund\s+von\s+(Art\.|§)",
            r"\bgestützt\s+auf\s+(Art\.|§)",
        ]

        self.stats = {
            "texts_processed": 0,
            "names_anonymized": 0,
            "organizations_anonymized": 0,
            "locations_anonymized": 0,
        }

    def anonymize(
        self, text: str, anonymize_orgs: bool = True, anonymize_locations: bool = False
    ) -> AnonymizationResult:
        """
        Anonymisiert Personennamen unter Beibehaltung der Rechtsstruktur.

        Args:
            text: Zu anonymisierender Text
            anonymize_orgs: Auch Organisationen anonymisieren
            anonymize_locations: Auch Orte anonymisieren

        Returns:
            AnonymizationResult mit anonymisiertem Text und Mappings
        """
        if not text:
            return AnonymizationResult("", {}, {}, {})

        # Use fallback if spaCy is not available
        if self._fallback:
            return self._fallback.anonymize(text, anonymize_orgs, anonymize_locations)

        doc = self.nlp(text)
        anonymized = text
        mappings = {}  # Platzhalter -> Hash
        entity_types = {}  # Platzhalter -> Type

        # Counter für verschiedene Entity-Typen
        person_counter = 1
        org_counter = 1
        location_counter = 1

        # Alle zu anonymisierenden Entitäten sammeln
        entities_to_anonymize = []

        for ent in doc.ents:
            # Prüfen ob Entity anonymisiert werden soll
            should_anonymize = False
            placeholder = None

            if ent.label_ == "PER":
                # Personennamen
                if not self._is_legal_role(ent.text) and not self._is_legal_reference(
                    ent.text, ent.start_char, text
                ):
                    should_anonymize = True
                    placeholder = f"[Person {person_counter}]"
                    person_counter += 1
                    entity_types[placeholder] = "PERSON"
                    self.stats["names_anonymized"] += 1

            elif ent.label_ == "ORG" and anonymize_orgs:
                # Organisationen
                if not self._is_court_or_authority(ent.text) and not self._is_legal_reference(
                    ent.text, ent.start_char, text
                ):
                    should_anonymize = True
                    placeholder = f"[Organisation {org_counter}]"
                    org_counter += 1
                    entity_types[placeholder] = "ORGANIZATION"
                    self.stats["organizations_anonymized"] += 1

            elif ent.label_ == "LOC" and anonymize_locations:
                # Orte
                if not self._is_court_location(ent.text):
                    should_anonymize = True
                    placeholder = f"[Ort {location_counter}]"
                    location_counter += 1
                    entity_types[placeholder] = "LOCATION"
                    self.stats["locations_anonymized"] += 1

            if should_anonymize and placeholder:
                entities_to_anonymize.append(
                    {
                        "text": ent.text,
                        "start": ent.start_char,
                        "end": ent.end_char,
                        "placeholder": placeholder,
                    }
                )

        # Namen konsistent durch gleiche Platzhalter ersetzen
        name_mapping = {}  # Original -> Platzhalter

        # Sortiere nach Position (rückwärts), um Indizes nicht zu verschieben
        for entity in sorted(entities_to_anonymize, key=lambda x: -x["start"]):
            original_text = entity["text"]

            # Verwende existierendes Mapping für gleiche Namen
            if original_text not in name_mapping:
                name_mapping[original_text] = entity["placeholder"]
                # Speichere Hash statt Klartext
                text_hash = hashlib.sha256(original_text.encode()).hexdigest()
                mappings[entity["placeholder"]] = text_hash

            placeholder = name_mapping[original_text]

            # Ersetze im Text
            anonymized = anonymized[: entity["start"]] + placeholder + anonymized[entity["end"] :]

        self.stats["texts_processed"] += 1

        # Logging
        if mappings:
            logger.debug(
                "anonymization_complete",
                entities_count=len(mappings),
                persons=person_counter - 1,
                orgs=org_counter - 1,
                locations=location_counter - 1,
            )

        return AnonymizationResult(
            anonymized_text=anonymized,
            mappings=mappings,
            entity_types=entity_types,
            stats=self.stats.copy(),
        )

    def _is_legal_role(self, text: str) -> bool:
        """Prüft ob Text eine rechtliche Rolle ist."""
        # Prüfe exakte Übereinstimmung und Teilstrings
        for role in self.legal_roles:
            if role in text or text in role:
                return True
        return False

    def _is_court_or_authority(self, text: str) -> bool:
        """Prüft ob Text ein Gericht oder Behörde ist."""
        # Prüfe Gerichtsabkürzungen
        for court in self.court_abbreviations:
            if court in text:
                return True

        # Prüfe typische Behörden-/Gerichtsnamen
        authority_keywords = [
            "Gericht",
            "Landesamt",
            "Bundesamt",
            "Behörde",
            "Ministerium",
            "Datenschutz",
            "Aufsicht",
            "Kammer",
            "Senat",
            "Kommission",
            "Amt für",
        ]

        for keyword in authority_keywords:
            if keyword in text:
                return True

        return False

    def _is_court_location(self, text: str) -> bool:
        """Prüft ob Ort zu einem Gericht gehört."""
        # Deutsche Gerichtsstädte sollten erhalten bleiben wenn mit Gericht verbunden
        court_cities = {
            "Karlsruhe",
            "Leipzig",
            "München",
            "Berlin",
            "Hamburg",
            "Frankfurt",
            "Stuttgart",
            "Köln",
            "Düsseldorf",
            "Dresden",
        }
        return text in court_cities

    def _is_legal_reference(self, text: str, position: int, full_text: str) -> bool:
        """Prüft ob Text an Position Teil einer rechtlichen Referenz ist."""
        # Umgebungskontext betrachten (50 Zeichen vor und nach)
        context_start = max(0, position - 50)
        context_end = min(len(full_text), position + len(text) + 50)
        context = full_text[context_start:context_end]

        # Spezifische Rechtsbegriff-Patterns (ohne Prozessbegriffe mit Personen)
        specific_legal_patterns = [
            r"Art\.\s*\d+",  # Art. 6
            r"§\s*\d+",  # § 26
            r"\b(" + "|".join(self.court_abbreviations) + r")\b",
            r"\b\d+\s*[A-Z]+\s*\d+/\d+\b",  # Aktenzeichen: 1 ZR 140/22
            r"[IVX]+\s*[A-Z]+\s*\d+/\d+",  # Römische Ziffern: VI ZR 140/22
            r"Az\.\s*[A-Za-z0-9\s\-/]+",  # Az. 123/45
            r"Urteil vom\s*\d{1,2}\.\d{1,2}\.\d{4}",  # Urteil vom 01.01.2024
            r"Beschluss vom\s*\d{1,2}\.\d{1,2}\.\d{4}",  # Beschluss vom 01.01.2024
            r"\b(gemäß|nach|laut)\s+(Art\.|§)",
            r"\bim\s+Sinne\s+des?\s+(Art\.|§)",
            r"\bin\s+Verbindung\s+mit\s+(Art\.|§)",
            r"\bauf\s+Grund\s+von\s+(Art\.|§)",
            r"\bgestützt\s+auf\s+(Art\.|§)",
        ]

        # Prüfe spezifische Rechtsbezüge (ohne Prozessbegriffe)
        for pattern in specific_legal_patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return True

        # Prüfe ob Teil eines Aktenzeichens
        if re.search(r"\d+\s*[A-Z]+\s*\d+/\d+", context):
            return True

        return False

    def bulk_anonymize(self, texts: List[str], **kwargs) -> List[AnonymizationResult]:
        """
        Anonymisiert mehrere Texte.

        Args:
            texts: Liste von Texten
            **kwargs: Zusätzliche Argumente für anonymize()

        Returns:
            Liste von AnonymizationResults
        """
        # Use fallback if spaCy is not available
        if self._fallback:
            return self._fallback.bulk_anonymize(texts, **kwargs)

        results = []

        logger.info("bulk_anonymization_started", count=len(texts))

        for i, text in enumerate(texts):
            try:
                result = self.anonymize(text, **kwargs)
                results.append(result)

                if (i + 1) % 10 == 0:
                    logger.debug(f"Processed {i + 1}/{len(texts)} texts")

            except Exception as e:
                logger.error("anonymization_failed", index=i, error=str(e))
                # Füge leeres Ergebnis hinzu bei Fehler
                results.append(AnonymizationResult("", {}, {}, {}))

        logger.info(
            "bulk_anonymization_complete",
            total=len(texts),
            successful=len([r for r in results if r.anonymized_text]),
        )

        return results

    def get_statistics(self) -> Dict[str, int]:
        """Gibt Anonymisierungs-Statistiken zurück."""
        if self._fallback:
            return self._fallback.get_statistics()
        return self.stats.copy()

    def reset_statistics(self):
        """Setzt Statistiken zurück."""
        if self._fallback:
            self._fallback.reset_statistics()
        else:
            self.stats = {
                "texts_processed": 0,
                "names_anonymized": 0,
                "organizations_anonymized": 0,
                "locations_anonymized": 0,
            }


def get_anonymizer():
    """
    Factory-Funktion für Anonymisierer mit automatischer Backend-Auswahl.

    Returns:
        Anonymizer-Instanz (spaCy oder Regex-Fallback)
    """
    try:
        # Versuche spaCy-Anonymisierer zu laden
        anonymizer = GermanLegalAnonymizer()
        logger.info("anonymizer_backend_selected", backend="spacy")
        return anonymizer
    except Exception as e:
        # Fallback zu Regex-Anonymisierer
        logger.warning(f"spaCy unavailable, using regex fallback: {e}")
        logger.info("anonymizer_backend_selected", backend="regex")
        return SimpleGermanLegalAnonymizer()
