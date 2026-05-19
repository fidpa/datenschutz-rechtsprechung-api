"""
GDPRhub Wiki Collector.
Sammelt DSGVO-Entscheidungen von https://gdprhub.eu
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncIterator
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.base import BaseCollector
from src.database import Decision
from src.analyzers.gdpr_extractor import GDPRArticleExtractor
from src.processors.anonymizer import GermanLegalAnonymizer
from src.utils.logging import get_logger

logger = get_logger("collector.gdprhub")


_FINE_RE = re.compile(
    r"\b(?:Fine|Penalty):?\s+(?:(n/a)|(\d[\d.,]*)\s*(EUR|€|GBP|£|USD|\$)?)",
    re.IGNORECASE,
)


def extract_fine(text: str) -> tuple[Optional[str], Optional[int]]:
    """Parse fine info from page text (current GDPRhub no longer renders infobox).

    Returns ``(fine_amount, fine_eur)`` where ``fine_amount`` is the
    human-readable token (``"200,000 EUR"``, ``"n/a"``) and ``fine_eur``
    is the numeric EUR value (only set when currency is explicitly EUR/€).
    Bare numbers without currency stay non-numeric to avoid false EUR claims.
    """
    match = _FINE_RE.search(text)
    if not match:
        return (None, None)
    na, number, currency = match.groups()
    if na:
        return ("n/a", None)
    if not number:
        return (None, None)
    if currency:
        currency_upper = (
            "EUR"
            if currency in ("€", "EUR")
            else (
                "GBP"
                if currency in ("£", "GBP")
                else ("USD" if currency in ("$", "USD") else currency.upper())
            )
        )
        amount = f"{number.strip()} {currency_upper}"
        if currency_upper == "EUR":
            try:
                return (amount, int(number.replace(",", "").replace(".", "")))
            except ValueError:
                return (amount, None)
        return (amount, None)
    return (number.strip(), None)


class GDPRhubCollector(BaseCollector):
    """
    Collector für GDPRhub Wiki.
    Sammelt Entscheidungen von Datenschutzbehörden und Gerichten.
    """

    BASE_URL = "https://gdprhub.eu"
    SPECIAL_NEWPAGES = "/index.php?title=Special:NewPages"
    SPECIAL_RECENTCHANGES = "/index.php?title=Special:RecentChanges"
    CATEGORY_YEAR = "/index.php?title=Category:{year}"
    DEFAULT_YEARS = (2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018)

    # Mode constants for collect()
    MODE_CATEGORIES = "categories"
    MODE_NEWPAGES = "newpages"

    def __init__(
        self,
        session: AsyncSession,
        max_pages: int = 100,
        mode: str = MODE_CATEGORIES,
        years: Optional[tuple] = None,
    ):
        """
        Initialisiert den GDPRhub Collector.

        Args:
            session: SQLAlchemy Async Session
            max_pages: Maximale Anzahl zu sammelnder Entscheidungen
            mode: Crawl-Strategie — "categories" (Default, deckt mehrere Jahre ab,
                  bis ~200 Decisions pro Kategorie-Seite mit Pagination) oder
                  "newpages" (Special:NewPages, nur die ~85 jüngsten Wiki-Einträge).
            years: Optionale Year-Liste für Modus "categories"
                   (Default: 2026..2018).
        """
        super().__init__(
            source="gdprhub",
            session=session,
            rate_limit=0.5,  # 0.5 req/s = 2 Sekunden Verzögerung
            max_retries=3,
            timeout=30,
        )

        if mode not in (self.MODE_CATEGORIES, self.MODE_NEWPAGES):
            raise ValueError(
                f"Invalid mode {mode!r}; expected one of "
                f"{{{self.MODE_CATEGORIES!r}, {self.MODE_NEWPAGES!r}}}"
            )

        self.max_pages = max_pages
        self.mode = mode
        self.years = tuple(years) if years else self.DEFAULT_YEARS
        self.gdpr_extractor = GDPRArticleExtractor()
        self.anonymizer = None  # Lazy Loading für spaCy

        # Muster für Entscheidungsseiten
        self.decision_patterns = [
            r"^[A-Z]+\s*\([A-Za-z]+\)\s*-\s*",  # "DPA (Country) - Case"
            r"^[A-Z]{2,}\s*-\s*[A-Z]?\d+",  # "CJEU - T-123/45"
            r"^\w+\s+court\s*-\s*",  # "Some court - Case"
        ]

    async def initialize(self):
        """Initialisiert Collector und lädt spaCy-Modell."""
        await super().initialize()

        # Lazy Loading für Anonymisierer (spaCy ist ressourcenintensiv)
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
        Prüft ob GDPRhub erreichbar ist.

        Returns:
            True wenn erreichbar
        """
        try:
            response = await self.fetch_with_retry(self.BASE_URL)
            return response.status_code == 200
        except Exception as e:
            logger.error("access_validation_failed", error=str(e))
            return False

    async def collect(self, full_crawl: bool = False) -> AsyncIterator[Decision]:
        """
        Hauptmethode zum Sammeln von Entscheidungen.

        Args:
            full_crawl: Wenn True, sammle alle Daten (nicht nur neue)

        Yields:
            Decision Objekte
        """
        logger.info(
            "collection_started", source="gdprhub", full_crawl=full_crawl, max_pages=self.max_pages
        )

        # Starte Crawl
        await self.start_crawl("full" if full_crawl else "incremental")

        # Lade gespeicherten State für Resume-Fähigkeit
        state = await self.load_crawl_state() if not full_crawl else None
        start_offset = state.get("last_offset", 0) if state else 0

        pages_processed = 0

        if self.mode == self.MODE_CATEGORIES:
            decision_iter = self._crawl_categories()
        else:
            decision_iter = self._crawl_new_pages(start_offset)

        try:
            # Crawle Entscheidungen
            async for decision in decision_iter:
                if pages_processed >= self.max_pages:
                    logger.info("max_pages_reached", count=self.max_pages)
                    break

                # Prüfe auf Duplikat
                if not await self.check_duplicate(decision.source_id):
                    # Speichere Entscheidung
                    if await self.save_decision(decision):
                        pages_processed += 1
                        yield decision

                        # Speichere State alle 10 Seiten
                        if pages_processed % 10 == 0:
                            await self.save_crawl_state(
                                {
                                    "last_offset": pages_processed + start_offset,
                                    "last_crawled": datetime.now().isoformat(),
                                }
                            )
                else:
                    logger.debug("duplicate_skipped", source_id=decision.source_id)

                self.stats["total_fetched"] += 1

            self.status = self.status.COMPLETED

        except Exception as e:
            logger.error("collection_failed", error=str(e), pages_processed=pages_processed)
            self.status = self.status.FAILED
            self.stats["errors"].append(str(e))
            raise

        finally:
            # Finalisiere Crawl-Log
            await self._finalize_crawl_log()

            logger.info(
                "collection_complete",
                pages_processed=pages_processed,
                stats=self.calculate_progress(),
            )

    async def _crawl_new_pages(self, offset: int = 0) -> AsyncIterator[Decision]:
        """
        Crawlt neue Seiten von Special:NewPages.

        Args:
            offset: Start-Offset für Pagination

        Yields:
            Decision Objekte
        """
        limit = 50  # Seiten pro Request
        current_offset = offset

        while True:
            # Konstruiere URL mit Pagination
            url = f"{self.BASE_URL}{self.SPECIAL_NEWPAGES}"
            if current_offset > 0:
                url += f"&offset={current_offset}&limit={limit}"
            else:
                url += f"&limit={limit}"

            logger.debug("fetching_newpages", url=url, offset=current_offset)

            try:
                # Hole Seite
                response = await self.fetch_with_retry(url)
                soup = BeautifulSoup(response.text, "lxml")

                # Finde alle neuen Seiten
                new_pages = self._extract_new_pages(soup)

                if not new_pages:
                    logger.info("no_more_pages")
                    break

                # Verarbeite jede Seite
                for page_info in new_pages:
                    # Prüfe ob es eine Entscheidungsseite ist
                    if self._is_decision_page(page_info["title"]):
                        # Hole vollständige Entscheidung
                        decision = await self._fetch_decision(page_info)
                        if decision:
                            yield decision

                # Nächste Seite
                current_offset += limit

                # Prüfe ob es weitere Seiten gibt
                if not self._has_next_page(soup):
                    logger.info("reached_end_of_newpages")
                    break

            except Exception as e:
                logger.error("newpages_fetch_failed", error=str(e), offset=current_offset)
                break

    def _extract_new_pages(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extrahiert neue Seiten aus Special:NewPages HTML.

        GDPRhub rendert pro Eintrag eine eigene `<ul class="mw-contributions-list">`
        mit genau einem `<li>`; der erste `<a>` darin verlinkt auf die neue Seite,
        nachfolgende Links sind hist/edit/talk-Metadaten.
        """
        pages: List[Dict[str, Any]] = []
        content = soup.find("div", {"id": "mw-content-text"}) or soup

        for ul in content.find_all("ul", {"class": "mw-contributions-list"}):
            for li in ul.find_all("li"):
                link = li.find("a", href=True)
                if not link:
                    continue
                title = (link.get("title") or link.get_text(strip=True)).strip()
                if not title or title.startswith(("Special:", "User:", "User talk:")):
                    continue
                href = link["href"]
                if "/index.php" not in href:
                    continue

                # Datum aus li.text (Format "HH:MM, D Mon YYYY")
                date_match = re.search(r"(\d{1,2}:\d{2}),\s*(\d{1,2}\s+\w+\s+\d{4})", li.get_text())
                pages.append(
                    {
                        "title": title,
                        "url": self._normalize_page_url(urljoin(self.BASE_URL, href)),
                        "date": date_match.group(0) if date_match else None,
                    }
                )

        if not pages:
            logger.warning(
                "newpages_content_not_found",
                contributions_lists=len(content.find_all("ul", {"class": "mw-contributions-list"})),
            )

        logger.debug("extracted_pages", count=len(pages))
        return pages

    async def _crawl_categories(self) -> AsyncIterator[Decision]:
        """
        Crawlt Category:YYYY-Seiten (Decisions-per-Year-Buckets).

        Vorteil gegenüber Special:NewPages: bis ~200 Decisions pro Kategorie-Seite
        mit `pagefrom`-Pagination, deckt mehrere Jahre ab. Bessere Wahl für
        umfangreiche Crawls (>50 Decisions).

        Yields:
            Decision Objekte
        """
        for year in self.years:
            logger.info("category_started", year=year)
            page_from: Optional[str] = None

            while True:
                url = f"{self.BASE_URL}{self.CATEGORY_YEAR.format(year=year)}"
                if page_from:
                    url += f"&pagefrom={page_from}"

                logger.debug("fetching_category", url=url, year=year)

                try:
                    response = await self.fetch_with_retry(url)
                except Exception as exc:
                    logger.error("category_fetch_failed", year=year, error=str(exc))
                    break

                soup = BeautifulSoup(response.text, "lxml")
                category_pages = self._extract_category_links(soup)

                if not category_pages:
                    logger.info("category_empty", year=year)
                    break

                for page_info in category_pages:
                    if not self._is_decision_page(page_info["title"]):
                        continue
                    decision = await self._fetch_decision(page_info)
                    if decision:
                        yield decision

                next_from = self._extract_next_pagefrom(soup)
                if not next_from:
                    logger.info("category_pagination_end", year=year)
                    break
                page_from = next_from

    def _extract_category_links(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extrahiert Decision-Links aus dem `<div id="mw-pages">`-Block einer Kategorie-Seite."""
        pages: List[Dict[str, Any]] = []
        pages_div = soup.find("div", {"id": "mw-pages"})
        if not pages_div:
            return pages
        for li in pages_div.find_all("li"):
            link = li.find("a", href=True)
            if not link:
                continue
            title = (link.get("title") or link.get_text(strip=True)).strip()
            if not title or title.startswith(("Category:", "Special:", "User:")):
                continue
            pages.append(
                {
                    "title": title,
                    "url": self._normalize_page_url(urljoin(self.BASE_URL, link["href"])),
                    "date": None,
                }
            )
        return pages

    def _extract_next_pagefrom(self, soup: BeautifulSoup) -> Optional[str]:
        """Extrahiert den `pagefrom`-Wert des 'next page'-Links (Kategorie-Pagination)."""
        for link in soup.find_all("a", href=True):
            if "next page" not in link.get_text(strip=True).lower():
                continue
            parsed = urlparse(link["href"])
            value = parse_qs(parsed.query).get("pagefrom", [None])[0]
            if value:
                return value
        return None

    @staticmethod
    def _normalize_page_url(url: str) -> str:
        """
        Entfernt `oldid`/`diff` Query-Parameter, sodass Links auf die aktuelle
        Revision zeigen (Special:NewPages liefert oft Links mit `oldid=…`).
        """
        parsed = urlparse(url)
        title = parse_qs(parsed.query).get("title", [None])[0]
        if title:
            return f"{GDPRhubCollector.BASE_URL}/index.php?title={title}"
        return url

    def _is_decision_page(self, title: str) -> bool:
        """
        Prüft ob Seitentitel eine Entscheidung repräsentiert.

        Args:
            title: Seitentitel

        Returns:
            True wenn Entscheidungsseite
        """
        # Prüfe gegen bekannte Muster
        for pattern in self.decision_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                return True

        # Prüfe auf typische Schlüsselwörter
        decision_keywords = [
            "court",
            "gericht",
            "tribunal",
            "DPA",
            "DSB",
            "CNIL",
            "ICO",
            "AEPD",
            "Garante",
            "authority",
            "behörde",
            "commission",
            # Deutsche/EU-Gerichtskürzel
            "BGH",
            "BVerfG",
            "BAG",
            "BVerwG",
            "OLG",
            "OVG",
            "VG",
            "LG",
            "AG",
            "VwGH",
            "OGH",
            "EuGH",
            "CJEU",
            "ECJ",
            "ECtHR",
        ]

        # Wort-Grenzen-Match (verhindert False-Positives wie "ag" in "page")
        for keyword in decision_keywords:
            if re.search(r"\b" + re.escape(keyword) + r"\b", title, re.IGNORECASE):
                return True

        return False

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Prüft ob es eine nächste Seite gibt."""
        # Suche nach "older X" Link
        next_link = soup.find("a", text=re.compile(r"older \d+"))
        return next_link is not None

    async def _fetch_decision(self, page_info: Dict[str, Any]) -> Optional[Decision]:
        """
        Holt und parst eine einzelne Entscheidung.

        Args:
            page_info: Seiten-Informationen

        Returns:
            Decision Objekt oder None
        """
        try:
            url = page_info["url"]
            logger.debug("fetching_decision", url=url)

            # Hole Seite
            response = await self.fetch_with_retry(url)
            soup = BeautifulSoup(response.text, "lxml")

            # Parse Entscheidung
            decision = await self.parse_decision(
                {"soup": soup, "url": url, "title": page_info["title"]}
            )

            return decision

        except Exception as e:
            logger.error("decision_fetch_failed", url=page_info["url"], error=str(e))
            self.stats["total_errors"] += 1
            return None

    async def parse_decision(self, raw_data: Any) -> Optional[Decision]:
        """
        Parst Rohdaten zu einer Decision.

        Args:
            raw_data: Dictionary mit soup, url, title

        Returns:
            Decision Objekt oder None bei Fehler
        """
        try:
            soup = raw_data["soup"]
            url = raw_data["url"]
            title = raw_data["title"]

            # Generiere source_id aus URL
            source_id = self._extract_source_id(url)

            # Extrahiere Hauptinhalt
            content_div = soup.find("div", {"id": "mw-content-text"})
            if not content_div:
                logger.warning("content_not_found", url=url)
                return None

            # Extrahiere Text
            full_text = self._extract_text_content(content_div)

            # Extrahiere Metadaten
            metadata = self._extract_metadata(soup, title, content_text=full_text)

            # Extrahiere DSGVO-Artikel
            gdpr_articles, bdsg_sections = self.gdpr_extractor.extract_all(full_text)
            keywords = self.gdpr_extractor.extract_keywords(full_text)

            # Anonymisiere Text wenn möglich
            anonymized_text = full_text
            anonymization_result = None
            if self.anonymizer:
                try:
                    anonymization_result = self.anonymizer.anonymize(full_text)
                    anonymized_text = anonymization_result.anonymized_text
                except Exception as e:
                    logger.warning("anonymization_failed", error=str(e))

            # Parse decision_date wenn vorhanden
            decision_date = None
            if "decision_date" in metadata:
                try:
                    # Versuche verschiedene Datumsformate
                    from dateutil import parser

                    decision_date = parser.parse(metadata["decision_date"])
                except:
                    pass

            # Konvertiere alle datetime-Objekte zu ISO-Strings für JSON-Kompatibilität
            metadata_for_json = {}
            for k, v in metadata.items():
                if k == "decision_date":
                    continue  # Bereits als separate Spalte behandelt
                elif isinstance(v, datetime):
                    metadata_for_json[k] = v.isoformat()
                elif hasattr(v, "isoformat"):  # Für date oder andere datetime-ähnliche Objekte
                    metadata_for_json[k] = v.isoformat()
                else:
                    metadata_for_json[k] = v

            # Erstelle Decision Objekt
            decision = Decision(
                source="gdprhub",
                source_id=source_id,
                source_url=url,
                document_type="court_decision" if "court" in title.lower() else "dpa_decision",
                title=title,
                case_number=metadata.get("case_number"),
                court=metadata.get("authority"),
                decision_date=decision_date,
                publication_date=datetime.now(),
                gdpr_articles=gdpr_articles if gdpr_articles else None,
                bdsg_sections=bdsg_sections if bdsg_sections else None,
                keywords=keywords if keywords else None,
                full_text_original=full_text,
                full_text_anonymized=anonymized_text,
                anonymization_applied=bool(self.anonymizer),
                extra_metadata=metadata_for_json,
                language="de"
                if any(word in full_text.lower() for word in ["der", "die", "das"])
                else "en",
            )

            logger.debug(
                "decision_parsed",
                source_id=source_id,
                gdpr_articles=len(gdpr_articles),
                text_length=len(full_text),
            )

            # Füge Anonymisierungs-Mappings als temporäres Attribut hinzu
            if anonymization_result:
                decision._anonymization_result = anonymization_result

            return decision

        except Exception as e:
            logger.error("parse_decision_failed", error=str(e), url=raw_data.get("url"))
            return None

    def _extract_source_id(self, url: str) -> str:
        """Extrahiert eindeutige ID aus URL."""
        # Extrahiere title Parameter aus URL
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        if "title" in params:
            return params["title"][0]

        # Fallback: Verwende letzten Teil der URL
        return url.split("/")[-1].split("?")[0]

    def _extract_text_content(self, content_div) -> str:
        """Extrahiert Textinhalt aus Content-Div."""
        # Entferne Script und Style Tags
        for script in content_div(["script", "style"]):
            script.decompose()

        # Extrahiere Text
        text = content_div.get_text(separator="\n", strip=True)

        # Bereinige Text
        text = re.sub(r"\n{3,}", "\n\n", text)  # Mehrfache Leerzeilen
        text = re.sub(r"^\[\d+\]", "", text, flags=re.MULTILINE)  # Wiki-Referenzen

        return text

    def _extract_metadata(
        self,
        soup: BeautifulSoup,
        title: str,
        content_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extrahiert Metadaten aus der Seite.

        Args:
            soup: Vollständige BeautifulSoup-Repräsentation der Seite.
            title: Seitentitel (für Authority/Country/Case-Number).
            content_text: Optional vorab extrahierter Text aus dem
                ``mw-content-text``-Div. Wenn gesetzt, wird er für die
                Fine-Extraktion bevorzugt, sonst fällt der Code auf
                ``soup.get_text()`` zurück (kann Nav/Footer-Noise enthalten).
        """
        metadata = {}

        # Extrahiere aus Titel
        # Format: "Authority (Country) - Case Number"
        title_match = re.match(r"^([^(]+)\s*\(([^)]+)\)\s*-\s*(.+)$", title)
        if title_match:
            metadata["authority"] = title_match.group(1).strip()
            metadata["country"] = title_match.group(2).strip()
            metadata["case_number"] = title_match.group(3).strip()

        # Suche nach Datum in der Seite
        date_patterns = [
            r"Date of Decision:\s*(\d{1,2}[\s\-\.]\w+[\s\-\.]\d{4})",
            r"Decided on:\s*(\d{1,2}[\s\-\.]\w+[\s\-\.]\d{4})",
            r"(\d{1,2}[\s\-\.]\w+[\s\-\.]\d{4})",  # Generisches Datum
        ]

        text = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Versuche Datum zu parsen
                    date_str = match.group(1)
                    # Vereinfachte Datumskonvertierung - als String für JSON
                    metadata["decision_date"] = date_str
                    break
                except:
                    pass

        # Extrahiere Infobox wenn vorhanden
        infobox = soup.find("table", {"class": "infobox"})
        if infobox:
            for row in infobox.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)

                    # Mappe bekannte Felder
                    if "fine" in key or "penalty" in key:
                        metadata["fine_amount"] = value
                    elif "outcome" in key:
                        metadata["outcome"] = value
                    elif "topic" in key:
                        metadata["topics"] = value

        # Fallback: aktuelle GDPRhub-Seiten rendern keine `<table class="infobox">`
        # mehr; Fine steht im Fließtext (z. B. „Fine: 200,000 EUR Parties: …").
        # Bevorzugt auf dem bereinigten Content-Div-Text suchen, sonst auf
        # `soup.get_text()` (kann Nav/Footer-Rauschen mit spurious „Fine:"-Tokens
        # enthalten).
        if "fine_amount" not in metadata:
            fine_search_text = content_text if content_text is not None else text
            fine_amount, fine_eur = extract_fine(fine_search_text)
            if fine_amount is not None:
                metadata["fine_amount"] = fine_amount
            if fine_eur is not None:
                metadata["fine_eur"] = fine_eur

        return metadata
