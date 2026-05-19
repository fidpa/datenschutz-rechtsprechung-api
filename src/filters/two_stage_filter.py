#!/usr/bin/env python3
"""
Zweistufiges Filter-System für präzise DSGVO-Relevanz-Prüfung.

Dieses Modul implementiert eine zweistufige Filterung:
1. Stage 1 (Grob-Filter): Schnelles Keyword-Matching für breite Erfassung
2. Stage 2 (Fein-Filter): Detaillierte Kontextanalyse für hohe Präzision

Author: Datenschutz-Rechtsprechung API Team
Date: 21.08.2025
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from enum import Enum

from src.utils.logging import get_logger


class FilterStatus(Enum):
    """Status-Enum für Filter-Pipeline."""

    PENDING_STAGE1 = "pending_stage1"
    PENDING_STAGE2 = "pending_stage2"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPORTED = "imported"
    REVIEW_REQUIRED = "review_required"


@dataclass
class Stage1Result:
    """Ergebnis der Stage 1 (Grob-Filter)."""

    passed: bool
    score: int
    keywords_found: List[str]
    processing_time_ms: float


@dataclass
class Stage2Result:
    """Ergebnis der Stage 2 (Fein-Filter)."""

    confidence: float
    context_score: float
    structure_score: float
    metadata_score: float
    patterns_matched: Dict[str, List[str]]
    recommendation: FilterStatus
    rejection_reason: Optional[str]
    processing_time_ms: float


@dataclass
class FilterConfig:
    """Konfiguration für zweistufige Filterung."""

    # Stage 1 Config
    stage1_min_score: int = 2  # Niedriger als vorher für höhere Recall
    stage1_timeout_ms: int = 100

    # Stage 2 Config
    stage2_auto_approve_threshold: float = 80.0
    stage2_review_threshold: float = 50.0
    stage2_timeout_ms: int = 500

    # Feature Flags
    enable_context_analysis: bool = True
    enable_structure_analysis: bool = True
    enable_metadata_analysis: bool = True

    # Context Window
    context_window_size: int = 50  # Wörter vor/nach Keyword


class BaseTwoStageFilter(ABC):
    """
    Abstrakte Basisklasse für zweistufige Filterung.

    Subklassen müssen die abstrakten Methoden für beide Stufen implementieren.
    """

    def __init__(self, config: Optional[FilterConfig] = None):
        """
        Initialisiert den zweistufigen Filter.

        Args:
            config: Filter-Konfiguration (optional)
        """
        self.config = config or FilterConfig()
        self.logger = get_logger(self.__class__.__name__)

        # Statistiken
        self.stats = {
            "stage1_processed": 0,
            "stage1_passed": 0,
            "stage2_processed": 0,
            "stage2_approved": 0,
            "stage2_review": 0,
            "stage2_rejected": 0,
        }

    @abstractmethod
    def stage1_filter(self, document: Dict[str, Any]) -> Stage1Result:
        """
        Stage 1: Grob-Filter mit Keyword-Matching.

        Schnelle Vorfilterung mit breitem Netz für hohe Recall.

        Args:
            document: Dokument-Dictionary mit Rohdaten

        Returns:
            Stage1Result mit Score und gefundenen Keywords
        """

    @abstractmethod
    def stage2_filter(self, document: Dict[str, Any], stage1_result: Stage1Result) -> Stage2Result:
        """
        Stage 2: Fein-Filter mit Kontextanalyse.

        Detaillierte Analyse für hohe Präzision.

        Args:
            document: Dokument-Dictionary mit Rohdaten
            stage1_result: Ergebnis aus Stage 1

        Returns:
            Stage2Result mit Confidence-Score und Empfehlung
        """

    def process_document(self, document: Dict[str, Any]) -> Tuple[FilterStatus, Dict[str, Any]]:
        """
        Verarbeitet ein Dokument durch beide Filter-Stufen.

        Args:
            document: Dokument-Dictionary mit Rohdaten

        Returns:
            Tuple aus (Status, Metadaten-Dictionary)
        """
        import time

        # Stage 1: Grob-Filter
        start_time = time.time()
        stage1_result = self.stage1_filter(document)
        stage1_time = (time.time() - start_time) * 1000

        self.stats["stage1_processed"] += 1

        # Stage 1 nicht bestanden?
        if not stage1_result.passed:
            self.logger.debug(
                f"Dokument {document.get('id', 'unknown')} in Stage 1 abgelehnt "
                f"(Score: {stage1_result.score})"
            )
            return FilterStatus.REJECTED, {
                "stage1_score": stage1_result.score,
                "stage1_keywords": stage1_result.keywords_found,
                "stage1_time_ms": stage1_time,
                "rejection_reason": f"Stage 1 Score zu niedrig: {stage1_result.score}",
            }

        self.stats["stage1_passed"] += 1

        # Stage 2: Fein-Filter
        start_time = time.time()
        stage2_result = self.stage2_filter(document, stage1_result)
        stage2_time = (time.time() - start_time) * 1000

        self.stats["stage2_processed"] += 1

        # Status basierend auf Confidence
        if stage2_result.confidence >= self.config.stage2_auto_approve_threshold:
            status = FilterStatus.APPROVED
            self.stats["stage2_approved"] += 1
        elif stage2_result.confidence >= self.config.stage2_review_threshold:
            status = FilterStatus.REVIEW_REQUIRED
            self.stats["stage2_review"] += 1
        else:
            status = FilterStatus.REJECTED
            self.stats["stage2_rejected"] += 1

        # Metadaten zusammenstellen
        metadata = {
            "stage1_score": stage1_result.score,
            "stage1_keywords": stage1_result.keywords_found,
            "stage1_time_ms": stage1_time,
            "stage2_confidence": stage2_result.confidence,
            "stage2_context_score": stage2_result.context_score,
            "stage2_structure_score": stage2_result.structure_score,
            "stage2_metadata_score": stage2_result.metadata_score,
            "stage2_patterns": stage2_result.patterns_matched,
            "stage2_time_ms": stage2_time,
            "total_time_ms": stage1_time + stage2_time,
        }

        if stage2_result.rejection_reason:
            metadata["rejection_reason"] = stage2_result.rejection_reason

        self.logger.info(
            f"Dokument {document.get('id', 'unknown')}: "
            f"Status={status.value}, Confidence={stage2_result.confidence:.1f}%, "
            f"Zeit={metadata['total_time_ms']:.1f}ms"
        )

        return status, metadata

    def get_statistics(self) -> Dict[str, Any]:
        """
        Gibt Filter-Statistiken zurück.

        Returns:
            Dictionary mit Statistiken
        """
        total = self.stats["stage1_processed"]
        if total == 0:
            return self.stats.copy()

        return {
            **self.stats,
            "stage1_pass_rate": (self.stats["stage1_passed"] / total) * 100,
            "stage2_approval_rate": (
                self.stats["stage2_approved"] / max(1, self.stats["stage2_processed"])
            )
            * 100,
            "overall_approval_rate": (self.stats["stage2_approved"] / total) * 100,
            "review_queue_size": self.stats["stage2_review"],
        }

    def reset_statistics(self):
        """Setzt die Statistiken zurück."""
        self.stats = {
            "stage1_processed": 0,
            "stage1_passed": 0,
            "stage2_processed": 0,
            "stage2_approved": 0,
            "stage2_review": 0,
            "stage2_rejected": 0,
        }


class GDPRTwoStageFilter(BaseTwoStageFilter):
    """
    Konkrete Implementierung des zweistufigen Filters für DSGVO-Relevanz.

    Nutzt Regex-basierte Analyse ohne spaCy-Dependency.
    """

    def __init__(self, config: Optional[FilterConfig] = None):
        """Initialisiert den DSGVO-Filter."""
        super().__init__(config)

        # Erweiterte Keyword-Listen für Stage 1
        self._init_stage1_keywords()

        # Kontext-Patterns für Stage 2
        self._init_stage2_patterns()

    def _init_stage1_keywords(self):
        """Initialisiert erweiterte Keywords für Stage 1."""
        # Breites Netz für hohe Recall
        self.stage1_keywords = {
            "high_priority": [
                r"\bDSGVO\b",
                r"\bGDPR\b",
                r"\bDatenschutz",
                r"EU-?Datenschutz",
                r"Verordnung.*2016/679",
                r"Art\.?\s*\d+\s+DSGVO",
                r"§\s*\d+\s+BDSG",
            ],
            "medium_priority": [
                r"personenbezogen",
                r"Betroffenenrecht",
                r"Datenschutzbehörde",
                r"Aufsichtsbehörde",
                r"Bußgeld.*Daten",
                r"Schadensersatz.*Daten",
            ],
            "low_priority": [
                r"Verarbeitung.*Daten",
                r"Einwilligung",
                r"Lösch",
                r"Auskunft",
                r"Widerspruch",
                r"Datenübertrag",
                r"Transparenz",
            ],
            "entities": [
                r"\bBfDI\b",
                r"\bLfDI\b",
                r"\bDSK\b",
                r"Landesbeauftragt.*Datenschutz",
                r"Datenschutzkonferenz",
            ],
        }

        # Score-Mapping
        self.stage1_scores = {
            "high_priority": 10,
            "medium_priority": 5,
            "low_priority": 2,
            "entities": 7,
        }

    def _init_stage2_patterns(self):
        """Initialisiert Kontext-Patterns für Stage 2."""
        # Patterns die im Kontext vorkommen müssen
        self.context_patterns = {
            "dsgvo_artikel": [
                r"Art(?:ikel)?\.?\s*(\d+)(?:\s*(?:Abs\.?|Absatz)\s*\d+)?\s*(?:DSGVO|GDPR|der Verordnung)",
                r"Artikel\s*(\d+)\s*der\s*(?:DSGVO|Datenschutz-?Grundverordnung)",
            ],
            "rechtsfolgen": [
                r"(?:Bußgeld|Geldbuße|Strafe).*?(?:EUR|Euro|€)\s*[\d.,]+",
                r"Schadensersatz.*?(?:EUR|Euro|€)\s*[\d.,]+",
                r"(?:Unterlassung|Löschung|Sperrung).*?(?:angeordnet|verpflichtet)",
            ],
            "datenschutz_kontext": [
                r"(?:Verarbeitung|Erhebung|Speicherung).*?personenbezogen.*?Daten",
                r"Daten(?:schutz)?.*?(?:Verstoß|Verletzung|Vorfall)",
                r"(?:rechtswidrig|unbefugt|ohne Einwilligung).*?(?:verarbeitet|erhoben|gespeichert)",
            ],
            "betroffenenrechte": [
                r"Recht\s*auf.*?(?:Auskunft|Löschung|Berichtigung|Widerspruch)",
                r"Betroffene.*?(?:informier|benachrichtig|aufgeklärt)",
                r"(?:Einwilligung|Zustimmung).*?(?:fehlt|ungültig|widerrufen)",
            ],
        }

        # Negativ-Patterns (reduzieren Confidence)
        self.negative_patterns = [
            r"Widerspruchsrecht(?!.*?(?:Daten|DSGVO|personenbezogen))",
            r"Informationspflicht(?!.*?(?:Daten|DSGVO|Art\.))",
            r"Transparenz(?!.*?(?:Daten|Verarbeitung))",
        ]

    def stage1_filter(self, document: Dict[str, Any]) -> Stage1Result:
        """
        Stage 1: Schnelles Keyword-Matching.

        Args:
            document: Dokument-Dictionary

        Returns:
            Stage1Result
        """
        import time

        start_time = time.time()

        # Text für Suche vorbereiten
        searchable_text = " ".join(
            [
                str(document.get("name", "")),
                str(document.get("title", "")),
                str(document.get("content", "")),
                str(document.get("court", "")),
            ]
        ).lower()

        total_score = 0
        keywords_found = []

        # Durch alle Kategorien iterieren
        for category, patterns in self.stage1_keywords.items():
            category_score = self.stage1_scores[category]
            category_matched = False

            for pattern in patterns:
                if re.search(pattern, searchable_text, re.IGNORECASE):
                    if not category_matched:  # Nur einmal pro Kategorie zählen
                        total_score += category_score
                        category_matched = True

                    # Keyword für Logging speichern
                    match = re.search(pattern, searchable_text, re.IGNORECASE)
                    if match:
                        keywords_found.append(match.group(0)[:50])  # Max 50 Zeichen

        processing_time = (time.time() - start_time) * 1000

        return Stage1Result(
            passed=total_score >= self.config.stage1_min_score,
            score=min(total_score, 50),  # Cap bei 50
            keywords_found=keywords_found[:10],  # Max 10 Keywords
            processing_time_ms=processing_time,
        )

    def stage2_filter(self, document: Dict[str, Any], stage1_result: Stage1Result) -> Stage2Result:
        """
        Stage 2: Detaillierte Kontextanalyse.

        Args:
            document: Dokument-Dictionary
            stage1_result: Ergebnis aus Stage 1

        Returns:
            Stage2Result
        """
        import time

        start_time = time.time()

        content = str(document.get("content", ""))

        # Scores initialisieren
        context_score = 0.0
        structure_score = 0.0
        metadata_score = 0.0
        patterns_matched = {}

        # 1. Kontext-Analyse
        if self.config.enable_context_analysis:
            context_score, context_patterns = self._analyze_context(
                content, stage1_result.keywords_found
            )
            patterns_matched["context"] = context_patterns

        # 2. Struktur-Analyse
        if self.config.enable_structure_analysis:
            structure_score, structure_patterns = self._analyze_structure(document)
            patterns_matched["structure"] = structure_patterns

        # 3. Metadaten-Analyse
        if self.config.enable_metadata_analysis:
            metadata_score = self._analyze_metadata(document)

        # Gesamt-Confidence berechnen
        confidence = self._calculate_confidence(
            stage1_result.score, context_score, structure_score, metadata_score
        )

        # Empfehlung
        if confidence >= self.config.stage2_auto_approve_threshold:
            recommendation = FilterStatus.APPROVED
            rejection_reason = None
        elif confidence >= self.config.stage2_review_threshold:
            recommendation = FilterStatus.REVIEW_REQUIRED
            rejection_reason = None
        else:
            recommendation = FilterStatus.REJECTED
            rejection_reason = f"Confidence zu niedrig: {confidence:.1f}%"

        processing_time = (time.time() - start_time) * 1000

        return Stage2Result(
            confidence=confidence,
            context_score=context_score,
            structure_score=structure_score,
            metadata_score=metadata_score,
            patterns_matched=patterns_matched,
            recommendation=recommendation,
            rejection_reason=rejection_reason,
            processing_time_ms=processing_time,
        )

    def _analyze_context(self, content: str, keywords: List[str]) -> Tuple[float, List[str]]:
        """
        Analysiert den Kontext um gefundene Keywords.

        Args:
            content: Dokument-Inhalt
            keywords: Gefundene Keywords aus Stage 1

        Returns:
            Tuple aus (Score 0-100, gefundene Patterns)
        """
        score = 0.0
        patterns_found = []

        content_lower = content.lower()

        # Positive Patterns prüfen
        for category, patterns in self.context_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    score += 20  # Jede Kategorie trägt bis zu 20 Punkte bei
                    patterns_found.append(f"{category}: {len(matches)} matches")
                    break  # Nur einmal pro Kategorie

        # Negative Patterns prüfen (reduzieren Score)
        for pattern in self.negative_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                score -= 10
                patterns_found.append(f"NEGATIV: {pattern}")

        # Kontext-Fenster um Keywords analysieren
        for keyword in keywords[:5]:  # Max 5 Keywords prüfen
            # Finde Keyword-Position
            keyword_lower = keyword.lower()
            pos = content_lower.find(keyword_lower)

            if pos >= 0:
                # Extrahiere Kontext-Fenster
                window_start = max(0, pos - 200)
                window_end = min(len(content), pos + len(keyword) + 200)
                context_window = content[window_start:window_end]

                # Prüfe ob Datenschutz-Kontext vorhanden
                if any(
                    term in context_window.lower()
                    for term in ["personenbezogen", "datenschutz", "dsgvo", "verarbeitung"]
                ):
                    score += 5

        return min(score, 100.0), patterns_found

    def _analyze_structure(self, document: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Analysiert die Dokumentstruktur.

        Args:
            document: Dokument-Dictionary

        Returns:
            Tuple aus (Score 0-100, gefundene Strukturelemente)
        """
        score = 0.0
        patterns_found = []

        content = str(document.get("content", ""))

        # Prüfe auf typische Rechtstext-Strukturen
        if re.search(r"<h[1-4]>.*?Tenor.*?</h[1-4]>", content, re.IGNORECASE):
            # Hat Tenor-Sektion
            tenor_match = re.search(
                r"<h[1-4]>.*?Tenor.*?</h[1-4]>(.*?)(?:<h[1-4]>|$)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if tenor_match:
                tenor_text = tenor_match.group(1)
                if any(
                    term in tenor_text.lower()
                    for term in ["datenschutz", "dsgvo", "personenbezogen", "bußgeld"]
                ):
                    score += 40
                    patterns_found.append("DSGVO-Bezug im Tenor")

        # Prüfe auf Leitsatz
        if re.search(r"Leitsatz|Orientierungssatz", content, re.IGNORECASE):
            score += 10
            patterns_found.append("Leitsatz vorhanden")

        # Prüfe auf Gründe/Entscheidungsgründe
        if re.search(
            r"<h[1-4]>.*?(?:Gründe|Entscheidungsgründe).*?</h[1-4]>", content, re.IGNORECASE
        ):
            score += 10
            patterns_found.append("Entscheidungsgründe vorhanden")

        # Prüfe auf Rechtsmittelbelehrung
        if re.search(r"Rechtsmittel|Revision|Berufung|Beschwerde", content, re.IGNORECASE):
            score += 5
            patterns_found.append("Rechtsmittelbelehrung")

        return min(score, 100.0), patterns_found

    def _analyze_metadata(self, document: Dict[str, Any]) -> float:
        """
        Analysiert Dokument-Metadaten.

        Args:
            document: Dokument-Dictionary

        Returns:
            Score 0-100
        """
        score = 0.0

        # Gericht prüfen
        court = str(document.get("court", "")).lower()
        if any(term in court for term in ["datenschutz", "bfdi", "lfdi"]):
            score += 50  # Datenschutzbehörde = hohe Relevanz
        elif any(term in court for term in ["verwaltungsgericht", "vg", "ovg", "vgh"]):
            score += 20  # Verwaltungsgerichte oft für Datenschutz zuständig

        # Aktenzeichen prüfen
        case_number = str(document.get("case_number", ""))
        if re.search(r"DSB|BfDI|LfDI|DSGVO", case_number, re.IGNORECASE):
            score += 30

        # Datum prüfen (DSGVO gilt seit 25.05.2018)
        if document.get("decision_date"):
            try:
                decision_date = document["decision_date"]
                if isinstance(decision_date, str):
                    decision_date = datetime.fromisoformat(decision_date)

                dsgvo_start = datetime(2018, 5, 25)
                if decision_date >= dsgvo_start:
                    score += 10  # Post-DSGVO Entscheidung
            except:
                pass

        # Titel prüfen
        title = str(document.get("title", "")).lower()
        if any(term in title for term in ["datenschutz", "dsgvo", "gdpr", "personenbezogen"]):
            score += 20

        return min(score, 100.0)

    def _calculate_confidence(
        self, stage1_score: int, context_score: float, structure_score: float, metadata_score: float
    ) -> float:
        """
        Berechnet die Gesamt-Confidence.

        Args:
            stage1_score: Score aus Stage 1 (0-50)
            context_score: Kontext-Score (0-100)
            structure_score: Struktur-Score (0-100)
            metadata_score: Metadaten-Score (0-100)

        Returns:
            Confidence 0-100
        """
        # Normalisiere Stage 1 Score auf 0-100
        normalized_stage1 = (stage1_score / 50.0) * 100

        # Gewichtete Summe
        confidence = (
            normalized_stage1 * 0.2
            + context_score * 0.4  # 20% Gewicht für Keywords
            + structure_score * 0.2  # 40% Gewicht für Kontext
            + metadata_score * 0.2  # 20% Gewicht für Struktur  # 20% Gewicht für Metadaten
        )

        return min(confidence, 100.0)
