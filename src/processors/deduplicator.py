"""
Deduplizierungs-System für Gerichtsentscheidungen.
Erkennt und merged Duplikate über verschiedene Datenquellen.
"""

import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from difflib import SequenceMatcher
import re

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Decision
from src.utils.logging import get_logger

logger = get_logger("processor.deduplicator")


class DecisionDeduplicator:
    """
    Erkennt und merged Duplikate über Datenquellen.

    Matching-Strategien:
    1. Exakte Matches (case_number + court + date)
    2. Fuzzy Title Match (>90% Ähnlichkeit)
    3. Content-basierte Matches (MinHash/Text-Similarity)
    """

    # Schwellwerte für Duplikaterkennung
    TITLE_SIMILARITY_THRESHOLD = 0.85  # 85% Ähnlichkeit
    CONTENT_SIMILARITY_THRESHOLD = 0.90  # 90% für Volltext

    # Priorität der Datenquellen (höher = bevorzugt)
    SOURCE_PRIORITY = {
        "gdprhub": 3,
        "openlegaldata": 2,
        "ris_austria": 1,
        "manual": 4,  # Manuelle Einträge höchste Priorität
    }

    def __init__(self, session: AsyncSession):
        """
        Initialisiert den Deduplicator.

        Args:
            session: SQLAlchemy Async Session
        """
        self.session = session
        self.stats = {
            "total_checked": 0,
            "exact_matches": 0,
            "fuzzy_matches": 0,
            "content_matches": 0,
            "merged": 0,
        }

    async def find_duplicates(
        self, decision: Decision, check_content: bool = True
    ) -> List[Decision]:
        """
        Findet potenzielle Duplikate für eine Entscheidung.

        Args:
            decision: Zu prüfende Entscheidung
            check_content: Ob auch Content-Similarity geprüft werden soll

        Returns:
            Liste von potenziellen Duplikaten
        """
        self.stats["total_checked"] += 1
        duplicates = []

        # 1. Exakte Matches
        exact_matches = await self._find_exact_matches(decision)
        if exact_matches:
            self.stats["exact_matches"] += len(exact_matches)
            duplicates.extend(exact_matches)

        # 2. Fuzzy Title Matches
        fuzzy_matches = await self._find_fuzzy_matches(decision)
        if fuzzy_matches:
            self.stats["fuzzy_matches"] += len(fuzzy_matches)
            duplicates.extend(fuzzy_matches)

        # 3. Content-basierte Matches (optional, da ressourcenintensiv)
        if check_content and decision.full_text_original:
            content_matches = await self._find_content_matches(decision)
            if content_matches:
                self.stats["content_matches"] += len(content_matches)
                duplicates.extend(content_matches)

        # Dedupliziere Ergebnisse
        seen_ids = set()
        unique_duplicates = []
        for dup in duplicates:
            if dup.id not in seen_ids and dup.id != decision.id:
                seen_ids.add(dup.id)
                unique_duplicates.append(dup)

        logger.info(
            "duplicates_found",
            decision_id=decision.id,
            total_duplicates=len(unique_duplicates),
            exact=len(exact_matches),
            fuzzy=len(fuzzy_matches),
        )

        return unique_duplicates

    async def _find_exact_matches(self, decision: Decision) -> List[Decision]:
        """
        Findet exakte Duplikate basierend auf case_number + court + date.

        Args:
            decision: Zu prüfende Entscheidung

        Returns:
            Liste von exakten Duplikaten
        """
        if not decision.case_number or not decision.court:
            return []

        # Query für exakte Matches
        stmt = select(Decision).where(
            and_(
                Decision.case_number == decision.case_number,
                Decision.court == decision.court,
                Decision.id != decision.id,  # Nicht sich selbst
            )
        )

        # Optional: Datum prüfen wenn vorhanden
        if decision.decision_date:
            # Erlaube kleine Abweichungen (±7 Tage)
            date_min = decision.decision_date.replace(day=max(1, decision.decision_date.day - 7))
            date_max = decision.decision_date.replace(day=min(31, decision.decision_date.day + 7))
            stmt = stmt.where(
                and_(Decision.decision_date >= date_min, Decision.decision_date <= date_max)
            )

        result = await self.session.execute(stmt)
        matches = result.scalars().all()

        return list(matches)

    async def _find_fuzzy_matches(self, decision: Decision) -> List[Decision]:
        """
        Findet Duplikate basierend auf Titel-Ähnlichkeit.

        Args:
            decision: Zu prüfende Entscheidung

        Returns:
            Liste von fuzzy Duplikaten
        """
        if not decision.title:
            return []

        # Normalisiere Titel für Vergleich
        normalized_title = self._normalize_text(decision.title)

        # Query für potenzielle Kandidaten (gleiches Gericht oder ähnliches Datum)
        stmt = select(Decision).where(Decision.id != decision.id)

        # Filtere nach Gericht wenn vorhanden
        if decision.court:
            # Extrahiere Gerichtstyp (BGH, OLG, LG, AG)
            court_type = self._extract_court_type(decision.court)
            if court_type:
                stmt = stmt.where(Decision.court.contains(court_type))

        # Limitiere auf 100 Kandidaten
        stmt = stmt.limit(100)

        result = await self.session.execute(stmt)
        candidates = result.scalars().all()

        # Berechne Ähnlichkeit
        matches = []
        for candidate in candidates:
            if not candidate.title:
                continue

            candidate_title = self._normalize_text(candidate.title)
            similarity = self._calculate_similarity(normalized_title, candidate_title)

            if similarity >= self.TITLE_SIMILARITY_THRESHOLD:
                matches.append(candidate)
                logger.debug(
                    "fuzzy_match_found",
                    similarity=similarity,
                    title1=decision.title[:50],
                    title2=candidate.title[:50],
                )

        return matches

    async def _find_content_matches(self, decision: Decision) -> List[Decision]:
        """
        Findet Duplikate basierend auf Content-Ähnlichkeit.

        Args:
            decision: Zu prüfende Entscheidung

        Returns:
            Liste von Content-Duplikaten
        """
        if not decision.full_text_original:
            return []

        # Generiere Content-Hash für schnellen Vergleich
        content_hash = self._generate_content_hash(decision.full_text_original)

        # Query für exakte Content-Matches (gleicher Hash)
        stmt = select(Decision).where(
            and_(Decision.id != decision.id, Decision.full_text_original.isnot(None))
        )

        # Limitiere auf Entscheidungen aus ähnlichem Zeitraum
        if decision.decision_date:
            year = decision.decision_date.year
            stmt = stmt.where(
                func.extract("year", Decision.decision_date).between(year - 1, year + 1)
            )

        stmt = stmt.limit(50)  # Limitiere für Performance

        result = await self.session.execute(stmt)
        candidates = result.scalars().all()

        # Prüfe Content-Ähnlichkeit
        matches = []
        for candidate in candidates:
            if not candidate.full_text_original:
                continue

            # Schnell-Check mit Hash
            candidate_hash = self._generate_content_hash(candidate.full_text_original)
            if content_hash == candidate_hash:
                matches.append(candidate)
                continue

            # Detaillierter Similarity-Check für ähnliche Texte
            similarity = self._calculate_content_similarity(
                decision.full_text_original, candidate.full_text_original
            )

            if similarity >= self.CONTENT_SIMILARITY_THRESHOLD:
                matches.append(candidate)
                logger.debug(
                    "content_match_found",
                    similarity=similarity,
                    decision_id=decision.id,
                    candidate_id=candidate.id,
                )

        return matches

    async def merge_duplicates(
        self, duplicates: List[Decision], keep_strategy: str = "priority"
    ) -> Decision:
        """
        Merged mehrere Duplikate zu einer Entscheidung.

        Args:
            duplicates: Liste von Duplikaten
            keep_strategy: "priority" (nach Quelle) oder "complete" (vollständigste)

        Returns:
            Gemergete Entscheidung
        """
        if not duplicates:
            return None

        if len(duplicates) == 1:
            return duplicates[0]

        # Sortiere nach Strategie
        if keep_strategy == "priority":
            # Sortiere nach Quellen-Priorität
            sorted_dups = sorted(
                duplicates, key=lambda d: self.SOURCE_PRIORITY.get(d.source, 0), reverse=True
            )
        else:  # complete
            # Sortiere nach Vollständigkeit
            sorted_dups = sorted(
                duplicates, key=lambda d: self._calculate_completeness(d), reverse=True
            )

        # Basis ist die beste Entscheidung
        master = sorted_dups[0]

        # Merge Metadaten von anderen
        for dup in sorted_dups[1:]:
            # Merge GDPR Artikel (Union)
            if dup.gdpr_articles:
                master.gdpr_articles = list(set((master.gdpr_articles or []) + dup.gdpr_articles))

            # Merge Keywords (Union)
            if dup.keywords:
                master.keywords = list(set((master.keywords or []) + dup.keywords))

            # Fülle fehlende Felder
            if not master.leitsatz and dup.leitsatz:
                master.leitsatz = dup.leitsatz

            if not master.tenor and dup.tenor:
                master.tenor = dup.tenor

            if not master.tatbestand and dup.tatbestand:
                master.tatbestand = dup.tatbestand

            if not master.entscheidungsgruende and dup.entscheidungsgruende:
                master.entscheidungsgruende = dup.entscheidungsgruende

            # Tracke alle Quellen
            if not master.extra_metadata:
                master.extra_metadata = {}

            if "merged_sources" not in master.extra_metadata:
                master.extra_metadata["merged_sources"] = []

            master.extra_metadata["merged_sources"].append(
                {
                    "source": dup.source,
                    "source_id": dup.source_id,
                    "merged_at": datetime.now().isoformat(),
                }
            )

        # Update Zeitstempel
        master.updated_at = datetime.now()

        # Markiere andere als merged (soft delete)
        for dup in sorted_dups[1:]:
            dup.extra_metadata = dup.extra_metadata or {}
            dup.extra_metadata["merged_into"] = str(master.id)
            dup.extra_metadata["merged_at"] = datetime.now().isoformat()

        await self.session.commit()

        self.stats["merged"] += len(duplicates) - 1

        logger.info(
            "duplicates_merged",
            master_id=master.id,
            merged_count=len(duplicates) - 1,
            strategy=keep_strategy,
        )

        return master

    def _normalize_text(self, text: str) -> str:
        """
        Normalisiert Text für Vergleiche.

        Args:
            text: Zu normalisierender Text

        Returns:
            Normalisierter Text
        """
        # Konvertiere zu Kleinbuchstaben
        text = text.lower()

        # Entferne Sonderzeichen und extra Whitespace
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)

        # Entferne führende/nachfolgende Whitespaces
        text = text.strip()

        return text

    def _extract_court_type(self, court: str) -> Optional[str]:
        """
        Extrahiert Gerichtstyp aus Gerichtsnamen.

        Args:
            court: Gerichtsname

        Returns:
            Gerichtstyp (BGH, OLG, etc.) oder None
        """
        court_types = [
            "BGH",
            "BVerfG",
            "BVerwG",
            "BSG",
            "BAG",
            "BFH",
            "OLG",
            "OVG",
            "LSG",
            "LAG",
            "FG",
            "LG",
            "VG",
            "SG",
            "ArbG",
            "AG",
        ]

        court_upper = court.upper()
        for ct in court_types:
            if ct in court_upper:
                return ct

        return None

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Berechnet Ähnlichkeit zwischen zwei Texten.

        Args:
            text1: Erster Text
            text2: Zweiter Text

        Returns:
            Ähnlichkeitswert zwischen 0 und 1
        """
        return SequenceMatcher(None, text1, text2).ratio()

    def _calculate_content_similarity(self, text1: str, text2: str) -> float:
        """
        Berechnet Content-Ähnlichkeit für lange Texte.

        Args:
            text1: Erster Text
            text2: Zweiter Text

        Returns:
            Ähnlichkeitswert zwischen 0 und 1
        """
        # Normalisiere Texte
        norm1 = self._normalize_text(text1[:5000])  # Erste 5000 Zeichen
        norm2 = self._normalize_text(text2[:5000])

        # Verwende SequenceMatcher für Ähnlichkeit
        return SequenceMatcher(None, norm1, norm2).ratio()

    def _generate_content_hash(self, text: str) -> str:
        """
        Generiert Hash für Content-Vergleiche.

        Args:
            text: Text zum Hashen

        Returns:
            MD5 Hash des normalisierten Texts
        """
        # Normalisiere Text
        normalized = self._normalize_text(text[:5000])  # Erste 5000 Zeichen

        # Generiere Hash
        return hashlib.md5(normalized.encode()).hexdigest()

    def _calculate_completeness(self, decision: Decision) -> int:
        """
        Berechnet Vollständigkeits-Score einer Entscheidung.

        Args:
            decision: Zu bewertende Entscheidung

        Returns:
            Score (höher = vollständiger)
        """
        score = 0

        # Basis-Felder
        if decision.title:
            score += 1
        if decision.case_number:
            score += 2
        if decision.court:
            score += 2
        if decision.decision_date:
            score += 1

        # Volltext
        if decision.full_text_original:
            score += 3
            score += len(decision.full_text_original) // 1000  # Bonus für Länge

        if decision.full_text_anonymized:
            score += 2

        # Strukturierte Felder
        if decision.leitsatz:
            score += 3
        if decision.tenor:
            score += 3
        if decision.tatbestand:
            score += 2
        if decision.entscheidungsgruende:
            score += 2

        # Metadaten
        if decision.gdpr_articles:
            score += 2
        if decision.keywords:
            score += 1

        return score

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über Deduplizierung zurück.

        Returns:
            Dictionary mit Statistiken
        """
        # Query für Duplikat-Statistiken
        stmt = select(
            func.count(Decision.id).label("total_decisions"),
            func.count(func.distinct(Decision.case_number)).label("unique_case_numbers"),
        )

        result = await self.session.execute(stmt)
        db_stats = result.first()

        return {
            "session_stats": self.stats,
            "database_stats": {
                "total_decisions": db_stats.total_decisions,
                "unique_case_numbers": db_stats.unique_case_numbers,
                "potential_duplicates": db_stats.total_decisions - db_stats.unique_case_numbers,
            },
        }

    def reset_stats(self):
        """Setzt Session-Statistiken zurück."""
        self.stats = {
            "total_checked": 0,
            "exact_matches": 0,
            "fuzzy_matches": 0,
            "content_matches": 0,
            "merged": 0,
        }
