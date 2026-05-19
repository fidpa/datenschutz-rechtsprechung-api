"""
OpenLegalData.io Collector.
Sammelt deutsche Gerichtsentscheidungen mit DSGVO-Bezug von https://de.openlegaldata.io
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.base import BaseCollector
from src.database import Decision, DocumentType
from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.processors.anonymizer import GermanLegalAnonymizer
from src.utils.logging import get_logger

logger = get_logger("collector.openlegaldata")


class OpenLegalDataCollector(BaseCollector):
    """
    Collector für OpenLegalData API.

    Features:
    - REST API mit JSON-Responses
    - Pagination-Support für große Datenmengen
    - DSGVO-Filter für relevante Entscheidungen
    - Incremental Sync via updated_date
    """

    BASE_URL = "https://de.openlegaldata.io"
    API_BASE = f"{BASE_URL}/api"
    CASES_ENDPOINT = f"{API_BASE}/cases/"
    SEARCH_ENDPOINT = f"{API_BASE}/cases/search/"

    # DSGVO-relevante Suchbegriffe
    GDPR_SEARCH_TERMS = [
        "DSGVO",
        "Datenschutz-Grundverordnung",
        "GDPR",
        "Datenschutz",
        "Art. 6 DSGVO",
        "Art. 7 DSGVO",
        "Art. 15 DSGVO",
        "Art. 17 DSGVO",
        "personenbezogene Daten",
        "Verarbeitung personenbezogener",
        "Datenschutzverletzung",
        "Datenschutzbeauftragter",
        "BDSG",  # Bundesdatenschutzgesetz
        "DSB",  # Datenschutzbehörde
    ]

    def __init__(
        self,
        session: AsyncSession,
        max_pages: int = 100,
        page_size: int = 100,
        api_key: Optional[str] = None,
    ):
        """
        Initialisiert den OpenLegalData Collector.

        Args:
            session: SQLAlchemy Async Session
            max_pages: Maximale Anzahl zu crawlender Seiten
            page_size: Anzahl Ergebnisse pro API-Seite (max 100)
            api_key: Optional API-Key für höhere Rate-Limits
        """
        super().__init__(
            source="openlegaldata",
            session=session,
            rate_limit=3.0,  # 3 req/s (konservativ)
            max_retries=3,
            timeout=30,
        )

        self.max_pages = max_pages
        self.page_size = min(page_size, 100)  # API-Maximum ist 100
        self.api_key = api_key
        self.gdpr_extractor = GDPRArticleExtractor()
        self.anonymizer = None  # Lazy Loading für spaCy

        # Statistiken
        self.total_cases_found = 0
        self.gdpr_relevant_cases = 0

    async def initialize(self):
        """Initialisiert Collector und lädt spaCy-Modell."""
        await super().initialize()

        # API-Key Header hinzufügen falls vorhanden
        if self.api_key:
            self.http_client.headers["Authorization"] = f"Token {self.api_key}"

        # Lazy Loading für Anonymisierer
        try:
            self.anonymizer = GermanLegalAnonymizer()
            logger.info("anonymizer_initialized")
        except Exception as e:
            logger.warning(
                "anonymizer_init_failed", error=str(e), message="Continuing without anonymization"
            )
            self.anonymizer = None

    async def validate_access(self) -> bool:
        """
        Prüft ob OpenLegalData API erreichbar ist.

        Returns:
            True wenn erreichbar
        """
        try:
            # Teste mit minimalem Request
            test_url = f"{self.CASES_ENDPOINT}?page_size=1"
            response = await self.fetch_with_retry(test_url)

            # Prüfe ob Response valides JSON ist
            data = response.json()

            if "results" in data:
                logger.info("api_access_validated", total_cases=data.get("count", "unknown"))
                return True

            return False

        except Exception as e:
            logger.error("access_validation_failed", error=str(e))
            return False

    async def collect(self, full_crawl: bool = False) -> AsyncIterator[Decision]:
        """
        Hauptmethode zum Sammeln von Entscheidungen.

        Args:
            full_crawl: Wenn True, sammle alle DSGVO-relevanten Daten

        Yields:
            Decision Objekte
        """
        # Starte Crawl
        await self.start_crawl("full" if full_crawl else "incremental")

        # Lade gespeicherten State für Resume
        state = await self.load_crawl_state() if not full_crawl else None
        start_page = 1
        last_updated = None

        if state:
            start_page = state.get("last_page", 1)
            last_updated = state.get("last_updated")
            logger.info("resuming_crawl", from_page=start_page, last_updated=last_updated)

        # Iteriere über DSGVO-Suchbegriffe
        for search_term in self.GDPR_SEARCH_TERMS[:3]:  # Erstmal nur erste 3 für MVP
            logger.info("searching_term", term=search_term)

            # Crawle Seiten für diesen Suchbegriff
            async for decision in self._crawl_search_term(
                search_term,
                start_page=start_page if search_term == self.GDPR_SEARCH_TERMS[0] else 1,
                last_updated=last_updated,
            ):
                yield decision

                # Speichere State alle 100 Entscheidungen
                if self.stats["total_processed"] % 100 == 0:
                    await self.save_crawl_state(
                        {
                            "last_page": self.stats.get("current_page", 1),
                            "last_updated": datetime.now().isoformat(),
                            "current_search_term": search_term,
                        }
                    )

        # Finalisiere Crawl
        self.status = self.status.COMPLETED
        logger.info(
            "crawl_completed",
            total_found=self.total_cases_found,
            gdpr_relevant=self.gdpr_relevant_cases,
            processed=self.stats["total_processed"],
        )

    async def _crawl_search_term(
        self, search_term: str, start_page: int = 1, last_updated: Optional[str] = None
    ) -> AsyncIterator[Decision]:
        """
        Crawlt alle Seiten für einen bestimmten Suchbegriff.

        Args:
            search_term: DSGVO-relevanter Suchbegriff
            start_page: Startseite für Pagination
            last_updated: Letztes Update-Datum für incremental sync

        Yields:
            Decision Objekte
        """
        current_page = start_page
        pages_crawled = 0

        while pages_crawled < self.max_pages:
            # Baue URL mit Suchparametern
            params = {
                "q": search_term,
                "page": current_page,
                "page_size": self.page_size,
                "ordering": "-updated_date",  # Neueste zuerst
            }

            # Füge Datum-Filter für incremental sync hinzu
            if last_updated and not pages_crawled:  # Nur erste Seite
                params["updated_after"] = last_updated

            url = f"{self.CASES_ENDPOINT}"

            try:
                # API-Request
                response = await self.fetch_with_retry(url, params=params)
                data = response.json()

                self.stats["total_fetched"] += 1
                self.stats["current_page"] = current_page

                # Verarbeite Ergebnisse
                results = data.get("results", [])

                if not results:
                    logger.info("no_more_results", search_term=search_term, page=current_page)
                    break

                self.total_cases_found += len(results)

                # Parse jede Entscheidung
                for case_data in results:
                    # Prüfe Duplikat
                    source_id = str(case_data.get("id", ""))
                    if await self.check_duplicate(source_id):
                        logger.debug("duplicate_skipped", source_id=source_id)
                        continue

                    # Parse zu Decision
                    decision = await self.parse_decision(case_data)

                    if decision:
                        # Prüfe DSGVO-Relevanz
                        if self._is_gdpr_relevant(decision):
                            self.gdpr_relevant_cases += 1

                            # Speichere in DB
                            if await self.save_decision(decision):
                                yield decision

                # Nächste Seite
                if data.get("next"):
                    current_page += 1
                    pages_crawled += 1
                else:
                    break

            except Exception as e:
                logger.error(
                    "page_crawl_failed", error=str(e), page=current_page, search_term=search_term
                )
                self.stats["total_errors"] += 1

                # Bei zu vielen Fehlern abbrechen
                if self.stats["total_errors"] > 10:
                    logger.error("too_many_errors_aborting")
                    break

    async def parse_decision(self, raw_data: Dict[str, Any]) -> Optional[Decision]:
        """
        Parst OpenLegalData JSON zu einer Decision.

        Args:
            raw_data: JSON-Daten von der API

        Returns:
            Decision Objekt oder None bei Fehler
        """
        try:
            # Extrahiere Basis-Felder
            source_id = str(raw_data.get("id", ""))

            # Extrahiere Gericht-Informationen
            court_data = raw_data.get("court", {})
            court_name = court_data.get("name", "")
            court_jurisdiction = court_data.get("jurisdiction", "")

            # Datum-Parsing
            decision_date = self._parse_date(raw_data.get("date"))
            publication_date = self._parse_date(raw_data.get("created_date"))

            # Volltext
            content = raw_data.get("content", "")

            # Erstelle Decision-Objekt
            decision = Decision(
                source="openlegaldata",
                source_id=source_id,
                source_url=f"{self.BASE_URL}/case/{raw_data.get('slug', '')}",
                # Dokumenttyp basierend auf Gericht
                document_type=(
                    DocumentType.DPA_DECISION.value
                    if "datenschutz" in court_name.lower()
                    else DocumentType.COURT_DECISION.value
                ),
                # Metadaten
                title=self._generate_title(raw_data),
                case_number=raw_data.get("file_number", ""),
                court=court_name,
                decision_date=decision_date,
                publication_date=publication_date,
                # Volltext
                full_text_original=content,
                # Extra Metadaten
                extra_metadata={
                    "ecli": raw_data.get("ecli"),
                    "type": raw_data.get("type"),  # Urteil, Beschluss, etc.
                    "court_jurisdiction": court_jurisdiction,
                    "court_level": court_data.get("level_of_appeal"),
                    "court_state": court_data.get("state"),
                    "court_city": court_data.get("city"),
                    "openlegaldata_slug": raw_data.get("slug"),
                    "openlegaldata_updated": raw_data.get("updated_date"),
                },
            )

            # Extrahiere DSGVO-Artikel
            if content:
                decision.gdpr_articles = self.gdpr_extractor.extract_gdpr_articles(content)

                # Anonymisiere Text wenn möglich
                if self.anonymizer:
                    result = self.anonymizer.anonymize(content)
                    decision.full_text_anonymized = result.anonymized_text
                    decision.anonymization_applied = True

            # Extrahiere Keywords aus Titel und Content
            decision.keywords = self._extract_keywords(decision)

            return decision

        except Exception as e:
            logger.error("parse_decision_failed", error=str(e), source_id=raw_data.get("id"))
            self.stats["total_errors"] += 1
            return None

    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """
        Parst verschiedene Datumsformate.

        Args:
            date_string: Datum als String

        Returns:
            datetime Objekt oder None
        """
        if not date_string:
            return None

        # Versuche verschiedene Formate
        formats = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"]

        for fmt in formats:
            try:
                return datetime.strptime(date_string.split("+")[0], fmt)
            except ValueError:
                continue

        logger.warning("date_parse_failed", date_string=date_string)
        return None

    def _generate_title(self, case_data: Dict[str, Any]) -> str:
        """
        Generiert einen aussagekräftigen Titel.

        Args:
            case_data: Rohdaten der Entscheidung

        Returns:
            Generierter Titel
        """
        parts = []

        # Gericht
        if case_data.get("court", {}).get("name"):
            parts.append(case_data["court"]["name"])

        # Entscheidungstyp
        if case_data.get("type"):
            parts.append(case_data["type"])

        # Aktenzeichen
        if case_data.get("file_number"):
            parts.append(f"({case_data['file_number']})")

        # Datum
        if case_data.get("date"):
            parts.append(f"vom {case_data['date']}")

        return " ".join(parts) if parts else "Unbenannte Entscheidung"

    def _is_gdpr_relevant(self, decision: Decision) -> bool:
        """
        Prüft ob eine Entscheidung DSGVO-relevant ist.

        Args:
            decision: Decision Objekt

        Returns:
            True wenn DSGVO-relevant
        """
        # Hat DSGVO-Artikel?
        if decision.gdpr_articles and len(decision.gdpr_articles) > 0:
            return True

        # Enthält DSGVO-Keywords?
        text = (decision.full_text_original or "").lower()
        dsr_keywords = [
            "dsgvo",
            "gdpr",
            "datenschutz-grundverordnung",
            "art. 6 dsgvo",
            "art. 7 dsgvo",
            "personenbezogene daten",
        ]

        return any(keyword in text for keyword in dsr_keywords)

    def _extract_keywords(self, decision: Decision) -> List[str]:
        """
        Extrahiert relevante Keywords aus der Entscheidung.

        Args:
            decision: Decision Objekt

        Returns:
            Liste von Keywords
        """
        keywords = []

        # Extrahiere aus Titel
        if decision.title:
            # Entferne häufige Wörter
            title_words = decision.title.split()
            stop_words = {"der", "die", "das", "und", "oder", "vom", "am", "im"}
            keywords.extend(
                [word for word in title_words if len(word) > 3 and word.lower() not in stop_words][
                    :5
                ]
            )

        # Füge Gerichtstyp hinzu
        if decision.court:
            if "BGH" in decision.court:
                keywords.append("Bundesgerichtshof")
            elif "OLG" in decision.court:
                keywords.append("Oberlandesgericht")
            elif "LG" in decision.court:
                keywords.append("Landgericht")
            elif "AG" in decision.court:
                keywords.append("Amtsgericht")

        # Füge DSGVO-spezifische Keywords hinzu
        if decision.gdpr_articles:
            keywords.append("DSGVO")
            for article in decision.gdpr_articles[:3]:  # Erste 3 Artikel
                keywords.append(f"Art. {article} DSGVO")

        # Dedupliziere und limitiere
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw and kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:10]  # Max 10 Keywords
