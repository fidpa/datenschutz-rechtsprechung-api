"""
Unit-Tests für GDPRhubCollector — HTML-Parsing und URL-Normalisierung.

Decken die kritischen, netzwerklosen Pfade ab:
- _extract_new_pages: Selektoren für die `ul.mw-contributions-list`-Struktur
- _extract_category_links: Selektoren für den `<div id="mw-pages">`-Block der
  Category:YYYY-Seiten
- _extract_next_pagefrom: Pagination-Erkennung
- _normalize_page_url: Strippt `oldid`/Revisions-Parameter
- _is_decision_page: Titel-Filter (Behörden- und Gericht-Pattern)

Diese Tests benutzen keine Datenbank, kein Netzwerk und kein spaCy.
"""

from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from src.collectors.gdprhub import GDPRhubCollector, extract_fine


# -----------------------------------------------------------------------------
# Test-Fixtures (HTML-Snippets aus echten GDPRhub-Seiten, gekürzt)
# -----------------------------------------------------------------------------

NEWPAGES_HTML = """
<html><body>
<div id="mw-content-text">
  <ul class="mw-contributions-list">
    <li>
      <a href="/index.php?title=APD/GBA_(Belgium)_-_100/2026&amp;oldid=51662"
         title="APD/GBA (Belgium) - 100/2026">APD/GBA (Belgium) - 100/2026</a>
      (hist | edit) [59,440 bytes]
      <span>10:09, 17 May 2026</span>
    </li>
  </ul>
  <ul class="mw-contributions-list">
    <li>
      <a href="/index.php?title=VwGH_-_Ra_2024/04/0375&amp;oldid=51659"
         title="VwGH - Ra 2024/04/0375">VwGH - Ra 2024/04/0375</a>
      <span>13:31, 16 May 2026</span>
    </li>
  </ul>
  <ul class="mw-contributions-list">
    <li>
      <a href="/index.php?title=User:Some_User&amp;oldid=1"
         title="User:Some User">User:Some User</a>
    </li>
  </ul>
</div>
</body></html>
"""

CATEGORY_HTML = """
<html><body>
<div id="mw-pages">
  <h2>Pages in category "2024"</h2>
  <div class="mw-content-ltr">
    <ul>
      <li><a href="/index.php?title=AEPD_(Spain)_-_EXP202309453"
             title="AEPD (Spain) - EXP202309453">AEPD (Spain) - EXP202309453</a></li>
      <li><a href="/index.php?title=Garante_(Italy)_-_9888206"
             title="Garante (Italy) - 9888206">Garante (Italy) - 9888206</a></li>
      <li><a href="/index.php?title=Category:Subcategory"
             title="Category:Subcategory">Category:Subcategory</a></li>
    </ul>
  </div>
</div>
<a href="/index.php?title=Category:2024&amp;pagefrom=CJEU+-+C%E2%80%91757%2F22">next page</a>
</body></html>
"""

CATEGORY_HTML_NO_NEXT = """
<html><body>
<div id="mw-pages">
  <ul>
    <li><a href="/index.php?title=Foo" title="Foo">Foo</a></li>
  </ul>
</div>
</body></html>
"""

EMPTY_HTML = "<html><body><div id='mw-content-text'></div></body></html>"


# -----------------------------------------------------------------------------
# Collector-Fixture (Session ist Mock; wir testen reine Parsing-Logik)
# -----------------------------------------------------------------------------


@pytest.fixture
def collector() -> GDPRhubCollector:
    """GDPRhubCollector mit Mock-Session — für pure Parsing-Tests."""
    return GDPRhubCollector(session=MagicMock(), max_pages=10)


# -----------------------------------------------------------------------------
# _normalize_page_url
# -----------------------------------------------------------------------------


class TestNormalizePageUrl:
    def test_strips_oldid(self):
        url = "https://gdprhub.eu/index.php?title=AEPD_(Spain)&oldid=51662"
        normalized = GDPRhubCollector._normalize_page_url(url)
        assert normalized == "https://gdprhub.eu/index.php?title=AEPD_(Spain)"

    def test_strips_diff(self):
        url = "https://gdprhub.eu/index.php?title=Foo&diff=42&oldid=41"
        normalized = GDPRhubCollector._normalize_page_url(url)
        assert normalized == "https://gdprhub.eu/index.php?title=Foo"

    def test_preserves_url_without_title(self):
        url = "https://gdprhub.eu/some/path"
        assert GDPRhubCollector._normalize_page_url(url) == url

    def test_clean_url_unchanged(self):
        url = "https://gdprhub.eu/index.php?title=Foo"
        assert GDPRhubCollector._normalize_page_url(url) == url


# -----------------------------------------------------------------------------
# _extract_new_pages (Special:NewPages)
# -----------------------------------------------------------------------------


class TestExtractNewPages:
    def test_finds_contributions_list_entries(self, collector):
        soup = BeautifulSoup(NEWPAGES_HTML, "lxml")
        pages = collector._extract_new_pages(soup)
        titles = [p["title"] for p in pages]
        assert "APD/GBA (Belgium) - 100/2026" in titles
        assert "VwGH - Ra 2024/04/0375" in titles

    def test_filters_user_pages(self, collector):
        soup = BeautifulSoup(NEWPAGES_HTML, "lxml")
        pages = collector._extract_new_pages(soup)
        titles = [p["title"] for p in pages]
        assert "User:Some User" not in titles

    def test_normalizes_oldid_in_url(self, collector):
        soup = BeautifulSoup(NEWPAGES_HTML, "lxml")
        pages = collector._extract_new_pages(soup)
        for page in pages:
            assert "oldid=" not in page["url"]

    def test_empty_html(self, collector):
        soup = BeautifulSoup(EMPTY_HTML, "lxml")
        assert collector._extract_new_pages(soup) == []


# -----------------------------------------------------------------------------
# _extract_category_links + _extract_next_pagefrom (Category:YYYY)
# -----------------------------------------------------------------------------


class TestExtractCategoryLinks:
    def test_finds_decision_entries(self, collector):
        soup = BeautifulSoup(CATEGORY_HTML, "lxml")
        pages = collector._extract_category_links(soup)
        titles = [p["title"] for p in pages]
        assert "AEPD (Spain) - EXP202309453" in titles
        assert "Garante (Italy) - 9888206" in titles

    def test_filters_subcategory_links(self, collector):
        soup = BeautifulSoup(CATEGORY_HTML, "lxml")
        pages = collector._extract_category_links(soup)
        titles = [p["title"] for p in pages]
        assert not any(t.startswith("Category:") for t in titles)

    def test_no_mw_pages_div(self, collector):
        soup = BeautifulSoup(EMPTY_HTML, "lxml")
        assert collector._extract_category_links(soup) == []


class TestExtractNextPagefrom:
    def test_extracts_pagefrom_value(self, collector):
        soup = BeautifulSoup(CATEGORY_HTML, "lxml")
        next_from = collector._extract_next_pagefrom(soup)
        assert next_from is not None
        assert "CJEU" in next_from

    def test_no_next_link_returns_none(self, collector):
        soup = BeautifulSoup(CATEGORY_HTML_NO_NEXT, "lxml")
        assert collector._extract_next_pagefrom(soup) is None


# -----------------------------------------------------------------------------
# _is_decision_page (titel-basierter Filter)
# -----------------------------------------------------------------------------


class TestIsDecisionPage:
    @pytest.mark.parametrize(
        "title",
        [
            "AEPD (Spain) - EXP202309453",
            "Garante (Italy) - 9888206",
            "CJEU - C-757/22",
            "Higher Regional Court - 6 U 5042/19",
            "BGH - I ZR 7/20",
        ],
    )
    def test_matches_decision_patterns(self, collector, title):
        assert collector._is_decision_page(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "Some random wiki page",
            "About GDPRhub",
            "Help:Editing",
        ],
    )
    def test_rejects_non_decisions(self, collector, title):
        assert collector._is_decision_page(title) is False


# -----------------------------------------------------------------------------
# extract_fine — Fließtext-Fallback nach defektem `<table class="infobox">`
# -----------------------------------------------------------------------------


class TestExtractFine:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Fine: 200,000 EUR Parties: AXA", ("200,000 EUR", 200_000)),
            ("Fine: 400000 EUR Parties: UNICAJA", ("400000 EUR", 400_000)),
            ("Fine: 27,000,000 EUR Parties: FREE", ("27,000,000 EUR", 27_000_000)),
            ("Fine: 1,250,000 EUR Parties:", ("1,250,000 EUR", 1_250_000)),
            ("Fine: 1500 EUR Parties:", ("1500 EUR", 1500)),
            ("Penalty: 500 EUR Parties:", ("500 EUR", 500)),
            ("Fine: 100 € Parties:", ("100 EUR", 100)),
        ],
    )
    def test_eur_with_numeric(self, text, expected):
        assert extract_fine(text) == expected

    def test_na(self):
        assert extract_fine("Fine: n/a Parties: Microsoft") == ("n/a", None)

    def test_gbp_keeps_amount_no_eur(self):
        assert extract_fine("Fine: 120,000 GBP Parties: Allay") == ("120,000 GBP", None)

    def test_bare_number_no_eur(self):
        """Bare number without currency: amount captured, fine_eur stays None."""
        assert extract_fine("Fine: 5,000 Parties: Bakeca") == ("5,000", None)

    def test_no_match(self):
        assert extract_fine("No fine in this text") == (None, None)

    def test_truncated_number_only(self):
        """Summary cutoff leaves digits without currency — must not invent EUR."""
        assert extract_fine("Fine: 6,636") == ("6,636", None)


# -----------------------------------------------------------------------------
# _extract_metadata — Fallback-Pfad ohne Infobox
# -----------------------------------------------------------------------------

METADATA_NO_INFOBOX_HTML = """
<html><body>
<div id="mw-content-text">
  <p>Authority: AEPD (Spain) Decided on: 15 April 2026
  Fine: 200,000 EUR Parties: AXA SEGUROS</p>
</div>
</body></html>
"""


class TestExtractMetadataFallback:
    def test_fine_extracted_from_text_when_no_infobox(self, collector):
        soup = BeautifulSoup(METADATA_NO_INFOBOX_HTML, "lxml")
        metadata = collector._extract_metadata(soup, "AEPD (Spain) - EXP202309453")
        assert metadata["fine_amount"] == "200,000 EUR"
        assert metadata["fine_eur"] == 200_000

    def test_content_text_preferred_over_full_soup(self, collector):
        """When `content_text` is provided, the fine fallback must search only
        the cleaned content (no nav/footer/sidebar noise)."""
        noisy_html = """
        <html><body>
          <nav>Fine: 999,999 EUR (sidebar advertisement)</nav>
          <div id="mw-content-text">
            <p>Authority: AEPD (Spain). Fine: 5,000 EUR Parties: Foo.</p>
          </div>
          <footer>Fine: 1,000 EUR (footer template)</footer>
        </body></html>
        """
        soup = BeautifulSoup(noisy_html, "lxml")
        content_text = "Authority: AEPD (Spain). Fine: 5,000 EUR Parties: Foo."
        metadata = collector._extract_metadata(
            soup, "AEPD (Spain) - TEST", content_text=content_text
        )
        # Must pick 5,000 (content), not 999,999 (nav — first in soup.get_text()).
        assert metadata["fine_amount"] == "5,000 EUR"
        assert metadata["fine_eur"] == 5_000

    def test_falls_back_to_soup_when_no_content_text(self, collector):
        """Backwards-compat: legacy callers passing only (soup, title) still work."""
        soup = BeautifulSoup(METADATA_NO_INFOBOX_HTML, "lxml")
        metadata = collector._extract_metadata(soup, "AEPD (Spain) - EXP202309453")
        assert metadata["fine_amount"] == "200,000 EUR"
        assert metadata["fine_eur"] == 200_000


# -----------------------------------------------------------------------------
# __init__ validation
# -----------------------------------------------------------------------------


class TestInit:
    def test_default_mode_is_categories(self):
        c = GDPRhubCollector(session=MagicMock())
        assert c.mode == GDPRhubCollector.MODE_CATEGORIES

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            GDPRhubCollector(session=MagicMock(), mode="invalid")

    def test_custom_years(self):
        c = GDPRhubCollector(session=MagicMock(), years=(2024, 2023))
        assert c.years == (2024, 2023)

    def test_default_years(self):
        c = GDPRhubCollector(session=MagicMock())
        assert 2026 in c.years
        assert 2018 in c.years
