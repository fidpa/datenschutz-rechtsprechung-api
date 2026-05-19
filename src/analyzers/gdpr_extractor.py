"""
DSGVO-Artikel-Extraktor für deutsche Rechtstexte.
Extrahiert DSGVO/GDPR und BDSG Referenzen aus Texten.
"""

import re
from typing import List, Set, Tuple, Optional
from dataclasses import dataclass
from src.utils.logging import get_logger

logger = get_logger("gdpr_extractor")


@dataclass
class ArticleReference:
    """Strukturierte Artikel-Referenz."""

    article: str
    paragraph: Optional[str] = None
    subparagraph: Optional[str] = None
    law: str = "DSGVO"

    def __str__(self) -> str:
        """Formatierte Ausgabe der Referenz."""
        if self.law == "BDSG":
            base = f"§ {self.article}"
            if self.paragraph:
                base += f" Abs. {self.paragraph}"
            return f"{base} {self.law}"
        else:
            base = f"Art. {self.article}"
            if self.paragraph:
                base += f" Abs. {self.paragraph}"
            if self.subparagraph:
                base += f" lit. {self.subparagraph}"
            return f"{base} {self.law}"

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other) -> bool:
        return str(self) == str(other)


class GDPRArticleExtractor:
    """Extrahiert DSGVO-Artikel-Referenzen aus deutschen Rechtstexten."""

    # Muster für verschiedene DSGVO-Zitierstile
    GDPR_PATTERNS = [
        # Standard-Formate
        # Art. 6 Abs. 1 DSGVO
        (r"Art\.?\s*(\d+)\s*(?:Abs\.?\s*(\d+))?\s*(?:lit\.?\s*([a-z]))?\s*DSGVO", "DSGVO"),
        # Artikel 6 Absatz 1 DSGVO
        (
            r"Artikel\s*(\d+)\s*(?:Absatz\s*(\d+))?\s*(?:Buchstabe\s*([a-z]))?\s*(?:der\s*)?DSGVO",
            "DSGVO",
        ),
        # Art. 6 Abs. 1 DS-GVO
        (r"Art\.?\s*(\d+)\s*(?:Abs\.?\s*(\d+))?\s*(?:lit\.?\s*([a-z]))?\s*DS-?GVO", "DSGVO"),
        # Art. 6(1) DSGVO - Englischer Stil
        (r"Art\.?\s*(\d+)\s*\((\d+)\)\s*(?:\(([a-z])\))?\s*DSGVO", "DSGVO"),
        # Art. 6 GDPR - Englische Referenzen
        (r"Art\.?\s*(\d+)\s*(?:Abs\.?\s*(\d+))?\s*(?:lit\.?\s*([a-z]))?\s*GDPR", "DSGVO"),
        # Article 6 GDPR
        (r"Article\s*(\d+)\s*(?:\((\d+)\))?\s*(?:\(([a-z])\))?\s*GDPR", "DSGVO"),
        # Neue erweiterte Formate - WICHTIG: Bereiche ZUERST prüfen
        # Bereiche: Art. 15-18, Art. 15 bis 18 DSGVO
        (r"Art\.?\s*(\d+)\s*(?:bis|-|–)\s*(\d+)\s*DSGVO", "DSGVO"),
        # Mehrfach-Artikel in Listen: Art. 6, 9 DSGVO
        (r"Art\.?\s*(\d+)(?:\s*,\s*\d+)*\s*DSGVO", "DSGVO"),
        # Verkürzte Formate: Art. 6 I DSGVO
        (r"Art\.?\s*(\d+)\s*([IVX]+)\s*(?:lit\.?\s*([a-z]))?\s*DSGVO", "DSGVO"),
        # EU-Verordnungs-Referenzen: Art. 6 Verordnung (EU) 2016/679
        (
            r"Art\.?\s*(\d+)\s*(?:Abs\.?\s*(\d+))?\s*(?:lit\.?\s*([a-z]))?\s*(?:der\s*)?Verordnung\s*\(EU\)\s*2016/679",
            "DSGVO",
        ),
        # Artikel 6 der Verordnung
        (
            r"Artikel\s*(\d+)\s*(?:Absatz\s*(\d+))?\s*(?:Buchstabe\s*([a-z]))?\s*der\s*Verordnung(?:\s*\(EU\)\s*2016/679)?",
            "DSGVO",
        ),
    ]

    # Muster für BDSG-Referenzen
    BDSG_PATTERNS = [
        # § 26 BDSG
        (r"§\s*(\d+)\s*(?:Abs\.?\s*(\d+))?\s*BDSG", "BDSG"),
        # §§ 26 bis 28 BDSG - Bereich
        (r"§§\s*(\d+)\s*bis\s*(\d+)\s*BDSG", "BDSG_RANGE"),
    ]

    # Muster für kombinierte Referenzen (i.V.m., i.S.d.)
    COMBINED_PATTERNS = [
        r"i\.?V\.?m\.?",  # in Verbindung mit
        r"i\.?S\.?d\.?",  # im Sinne des/der
        r"gem\.?",  # gemäß
        r"nach",  # nach
    ]

    def __init__(self):
        """Initialisiert den Extraktor."""
        self.stats = {"total_processed": 0, "dsr_articles_found": 0, "bdsg_sections_found": 0}

    def extract_all(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Extrahiert alle DSGVO-Artikel und BDSG-Paragraphen.

        Args:
            text: Zu analysierender Text

        Returns:
            Tuple aus (DSGVO-Artikel-Liste, BDSG-Paragraphen-Liste)
        """
        gdpr_articles = self.extract_gdpr_articles(text)
        bdsg_sections = self.extract_bdsg_sections(text)

        self.stats["total_processed"] += 1
        self.stats["dsr_articles_found"] += len(gdpr_articles)
        self.stats["bdsg_sections_found"] += len(bdsg_sections)

        logger.debug(
            "extraction_complete", dsr_count=len(gdpr_articles), bdsg_count=len(bdsg_sections)
        )

        return gdpr_articles, bdsg_sections

    def extract_gdpr_articles(self, text: str) -> List[str]:
        """
        Extrahiert alle DSGVO-Artikel-Referenzen.

        Args:
            text: Zu analysierender Text

        Returns:
            Sortierte Liste eindeutiger DSGVO-Artikel
        """
        articles: Set[ArticleReference] = set()

        for pattern, law_type in self.GDPR_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                article = groups[0] if groups[0] else None

                if not article:
                    continue

                # Spezielle Behandlung für Bereichs-Pattern
                range_pattern = r"Art\.?\s*(\d+)\s*(?:bis|-|–)\s*(\d+)\s*DSGVO"
                if pattern == range_pattern:
                    if len(groups) >= 2 and groups[1]:
                        # Bereich: Art. 15-18 → "Art. 15-18 DSGVO"
                        ref = ArticleReference(
                            article=f"{article}-{groups[1]}",
                            paragraph=None,
                            subparagraph=None,
                            law="DSGVO",
                        )
                        articles.add(ref)
                        continue

                # Normale Artikel-Verarbeitung
                paragraph = groups[1] if len(groups) > 1 and groups[1] else None
                subparagraph = groups[2] if len(groups) > 2 and groups[2] else None

                ref = ArticleReference(
                    article=article, paragraph=paragraph, subparagraph=subparagraph, law="DSGVO"
                )
                articles.add(ref)

        # Sortierte String-Repräsentationen zurückgeben
        result = sorted([str(ref) for ref in articles])

        if result:
            logger.debug(
                "dsr_articles_extracted",
                count=len(result),
                articles=result[:5],  # Erste 5 für Logging
            )

        return result

    def extract_bdsg_sections(self, text: str) -> List[str]:
        """
        Extrahiert BDSG-Paragraphen-Referenzen.

        Args:
            text: Zu analysierender Text

        Returns:
            Sortierte Liste eindeutiger BDSG-Paragraphen
        """
        sections: Set[str] = set()

        for pattern, pattern_type in self.BDSG_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if pattern_type == "BDSG_RANGE":
                    # Bereich: §§ 26 bis 28 BDSG
                    start = int(match.group(1))
                    end = int(match.group(2))
                    for i in range(start, end + 1):
                        sections.add(f"§ {i} BDSG")
                else:
                    # Einzelner Paragraph
                    section = match.group(1)
                    paragraph = (
                        match.group(2) if len(match.groups()) > 1 and match.group(2) else None
                    )

                    if paragraph:
                        sections.add(f"§ {section} Abs. {paragraph} BDSG")
                    else:
                        sections.add(f"§ {section} BDSG")

        result = sorted(list(sections))

        if result:
            logger.debug(
                "bdsg_sections_extracted",
                count=len(result),
                sections=result[:5],  # Erste 5 für Logging
            )

        return result

    def extract_keywords(self, text: str) -> List[str]:
        """
        Extrahiert datenschutzrelevante Schlüsselwörter.

        Args:
            text: Zu analysierender Text

        Returns:
            Liste relevanter Schlüsselwörter
        """
        keywords = []

        # Datenschutz-Schlüsselwörter
        keyword_patterns = [
            r"\b(Einwilligung)\b",
            r"\b(Rechtsgrundlage)\b",
            r"\b(Verarbeitung)\b",
            r"\b(personenbezogene[nr]?\s+Daten)\b",
            r"\b(Verantwortliche[rn]?)\b",
            r"\b(Auftragsverarbeiter)\b",
            r"\b(Betroffene[rn]?)\b",
            r"\b(Datenschutzverstoß)\b",
            r"\b(Bußgeld)\b",
            r"\b(Schadensersatz)\b",
            r"\b(Löschung)\b",
            r"\b(Auskunft)\b",
            r"\b(Widerspruch)\b",
            r"\b(Datenübertragbarkeit)\b",
            r"\b(Profiling)\b",
            r"\b(automatisierte\s+Entscheidung)\b",
        ]

        for pattern in keyword_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # Extrahiere das tatsächliche Match
                match = re.search(pattern, text, re.IGNORECASE)
                keyword = match.group(1)
                if keyword not in keywords:
                    keywords.append(keyword)

        return keywords

    def normalize_article_references(self, articles: List[str]) -> List[str]:
        """
        Normalisiert Artikel-Referenzen für konsistente Speicherung.

        Args:
            articles: Liste von Artikel-Strings

        Returns:
            Normalisierte Liste
        """
        normalized = []

        for article in articles:
            # Bereits im korrekten Format durch ArticleReference
            normalized.append(article)

        return sorted(list(set(normalized)))

    def get_statistics(self) -> dict:
        """Gibt Extraktions-Statistiken zurück."""
        return self.stats.copy()
