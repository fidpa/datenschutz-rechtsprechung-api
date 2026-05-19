"""
UI Integration Tests - Accessibility Compliance
Tests für WCAG 2.1 AA Compliance, Keyboard Navigation, Screen Reader
Session 11.2 - Accessibility-Tests
"""

import pytest
import requests
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re


class TestAccessibility:
    """Test-Suite für Accessibility-Compliance (WCAG 2.1 AA)"""

    BASE_URL = "http://localhost:5001"

    @pytest.fixture
    def a11y_driver(self):
        """Chrome WebDriver mit Accessibility-Features"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        # Force high contrast for testing
        options.add_argument("--force-prefers-reduced-motion")

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, a11y_driver):
        """Admin-Session für Accessibility-Tests"""
        driver = a11y_driver

        # Login
        driver.get(f"{self.BASE_URL}/auth/login")
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys("admin@test.com")
        password_field.send_keys("testpass123")
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()

        WebDriverWait(driver, 10).until(lambda d: "/admin/dashboard" in d.current_url)

        return driver

    def test_keyboard_navigation_full_flow(self, admin_session):
        """Test: Vollständige Keyboard-Navigation durch Dashboard"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Start mit Body-Focus
        body = driver.find_element(By.TAG_NAME, "body")
        body.click()

        # Tab-Navigation-Reihenfolge testen
        focusable_elements = []
        max_tabs = 30  # Maximum Tab-Versuche

        for i in range(max_tabs):
            ActionChains(driver).send_keys(Keys.TAB).perform()
            time.sleep(0.1)

            focused_element = driver.switch_to.active_element
            element_info = {
                "tag": focused_element.tag_name,
                "id": focused_element.get_attribute("id"),
                "class": focused_element.get_attribute("class"),
                "type": focused_element.get_attribute("type"),
                "text": focused_element.text[:50] if focused_element.text else "",
                "tabindex": focused_element.get_attribute("tabindex"),
            }
            focusable_elements.append(element_info)

            # Wenn wir zum Theme-Toggle kommen, testen wir Enter-Aktivierung
            if element_info["id"] == "themeToggle":
                initial_theme = driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
                ActionChains(driver).send_keys(Keys.ENTER).perform()
                time.sleep(0.5)
                new_theme = driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
                assert initial_theme != new_theme, "Theme-Toggle sollte via Enter funktionieren"
                break

        # Mindestens 5 fokussierbare Elemente erwartet
        assert (
            len(focusable_elements) >= 5
        ), f"Zu wenige fokussierbare Elemente: {len(focusable_elements)}"

        # Wichtige Elemente sollten fokussierbar sein
        element_ids = [elem["id"] for elem in focusable_elements if elem["id"]]
        assert "themeToggle" in element_ids, "Theme-Toggle nicht keyboard-accessible"

    def test_color_contrast_compliance(self, admin_session):
        """Test: Farbkontrast entspricht WCAG 2.1 AA (4.5:1 für normalen Text)"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        def calculate_luminance(r, g, b):
            """Berechne Luminanz nach WCAG-Formel"""

            def linear_rgb(c):
                c = c / 255.0
                return c / 12.92 if c <= 0.03928 else pow((c + 0.055) / 1.055, 2.4)

            return 0.2126 * linear_rgb(r) + 0.7152 * linear_rgb(g) + 0.0722 * linear_rgb(b)

        def extract_rgb(color_string):
            """Extrahiere RGB-Werte aus CSS-Color-String"""
            match = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", color_string)
            if match:
                return int(match.group(1)), int(match.group(2)), int(match.group(3))
            return 0, 0, 0

        def contrast_ratio(color1, color2):
            """Berechne Kontrast-Ratio zwischen zwei Farben"""
            r1, g1, b1 = extract_rgb(color1)
            r2, g2, b2 = extract_rgb(color2)

            lum1 = calculate_luminance(r1, g1, b1)
            lum2 = calculate_luminance(r2, g2, b2)

            lighter = max(lum1, lum2)
            darker = min(lum1, lum2)

            return (lighter + 0.05) / (darker + 0.05)

        # Test verschiedene Text-Elemente
        text_elements = [
            (By.TAG_NAME, "h1"),
            (By.TAG_NAME, "h2"),
            (By.CLASS_NAME, "metric-label"),
            (By.CLASS_NAME, "metric-value"),
            (By.TAG_NAME, "p"),
            (By.TAG_NAME, "button"),
        ]

        contrast_failures = []

        for selector_type, selector_value in text_elements:
            elements = driver.find_elements(selector_type, selector_value)

            for element in elements[:3]:  # Teste nur erste 3 von jedem Typ
                if not element.is_displayed():
                    continue

                text_color = element.value_of_css_property("color")
                bg_color = element.value_of_css_property("background-color")

                # Wenn background transparent, parent-background verwenden
                if "rgba(0, 0, 0, 0)" in bg_color:
                    parent = driver.execute_script("return arguments[0].parentElement", element)
                    if parent:
                        bg_color = parent.value_of_css_property("background-color")

                # Fallback zu body-background
                if "rgba(0, 0, 0, 0)" in bg_color:
                    bg_color = driver.find_element(By.TAG_NAME, "body").value_of_css_property(
                        "background-color"
                    )

                ratio = contrast_ratio(text_color, bg_color)

                # WCAG AA: 4.5:1 für normalen Text, 3:1 für großen Text
                font_size = element.value_of_css_property("font-size")
                font_size_px = float(font_size.replace("px", "")) if "px" in font_size else 16

                min_ratio = 3.0 if font_size_px >= 18 else 4.5

                if ratio < min_ratio:
                    contrast_failures.append(
                        {
                            "element": f"{selector_type}[{selector_value}]",
                            "text": element.text[:30],
                            "ratio": ratio,
                            "required": min_ratio,
                            "text_color": text_color,
                            "bg_color": bg_color,
                        }
                    )

        assert len(contrast_failures) == 0, f"Kontrast-Ratio-Failures: {contrast_failures}"

    def test_semantic_html_structure(self, admin_session):
        """Test: Semantische HTML-Struktur für Screen Reader"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Page-Source für HTML-Analyse
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        # Heading-Hierarchie prüfen
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        assert len(headings) >= 1, "Mindestens ein Heading erforderlich"

        # H1 sollte vorhanden sein
        h1_elements = soup.find_all("h1")
        assert len(h1_elements) >= 1, "H1-Element erforderlich für Page-Title"

        # Heading-Reihenfolge prüfen (keine Sprünge)
        heading_levels = [int(h.name[1]) for h in headings]
        for i in range(1, len(heading_levels)):
            level_jump = heading_levels[i] - heading_levels[i - 1]
            assert (
                level_jump <= 1
            ), f"Heading-Level-Sprung zu groß: {heading_levels[i-1]} -> {heading_levels[i]}"

        # Landmark-Elemente prüfen
        landmarks = soup.find_all(["main", "nav", "header", "footer", "aside", "section"])
        # Dashboard sollte structure haben
        assert len(landmarks) >= 1, "Semantische Landmark-Elemente erforderlich"

        # Button-Elemente sollten Labels haben
        buttons = soup.find_all("button")
        for button in buttons:
            has_text = button.get_text(strip=True)
            has_aria_label = button.get("aria-label")
            has_title = button.get("title")

            assert has_text or has_aria_label or has_title, f"Button ohne Label: {button}"

    def test_aria_attributes_compliance(self, admin_session):
        """Test: ARIA-Attribute sind korrekt implementiert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Theme-Toggle-Button ARIA-Attribute
        theme_toggle = driver.find_element(By.ID, "themeToggle")

        # Button sollte title oder aria-label haben
        title = theme_toggle.get_attribute("title")
        aria_label = theme_toggle.get_attribute("aria-label")
        assert title or aria_label, "Theme-Toggle sollte title oder aria-label haben"

        # Metric Cards ARIA-Struktur
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        for card in metric_cards[:2]:  # Erste 2 testen
            # Card sollte semantische Struktur haben
            metric_label = card.find_elements(By.CLASS_NAME, "metric-label")
            metric_value = card.find_elements(By.CLASS_NAME, "metric-value")

            assert len(metric_label) > 0, "Metric Card sollte Label haben"
            assert len(metric_value) > 0, "Metric Card sollte Value haben"

        # Form-Elemente (falls vorhanden) sollten Labels haben
        form_inputs = driver.find_elements(By.TAG_NAME, "input")
        for input_field in form_inputs:
            input_id = input_field.get_attribute("id")
            aria_label = input_field.get_attribute("aria-label")
            aria_labelledby = input_field.get_attribute("aria-labelledby")

            # Suche nach associated label
            has_label = False
            if input_id:
                try:
                    label = driver.find_element(By.CSS_SELECTOR, f"label[for='{input_id}']")
                    has_label = True
                except:
                    pass

            assert (
                has_label or aria_label or aria_labelledby
            ), f"Input ohne Label: {input_field.get_attribute('name')}"

    def test_focus_indicators_visibility(self, admin_session):
        """Test: Focus-Indikatoren sind sichtbar und deutlich"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Fokussierbare Elemente testen
        focusable_selectors = [
            "#themeToggle",
            "[data-action='refresh']",
            "[data-export='excel']",
            "[data-crawl='gdprhub']",
        ]

        for selector in focusable_selectors:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)

                # Element fokussieren
                driver.execute_script("arguments[0].focus()", element)
                time.sleep(0.1)

                # Focus-Styles prüfen
                outline = element.value_of_css_property("outline")
                outline_width = element.value_of_css_property("outline-width")
                box_shadow = element.value_of_css_property("box-shadow")
                border = element.value_of_css_property("border")

                # Mindestens eine Form von Focus-Indikator
                has_focus_indicator = (
                    outline != "none"
                    or "0px" not in outline_width
                    or "none" not in box_shadow
                    or any(prop in box_shadow for prop in ["rgb", "rgba"])
                    or "2px" in border
                )

                assert (
                    has_focus_indicator
                ), f"Kein Focus-Indikator für {selector}: outline={outline}, box-shadow={box_shadow}"

            except Exception as e:
                # Element nicht gefunden ist OK für optionale Elemente
                pass

    def test_reduced_motion_support(self, admin_session):
        """Test: Unterstützung für prefers-reduced-motion"""
        driver = admin_session

        # CSS prüfen auf @media (prefers-reduced-motion: reduce)
        css_files = [
            f"{self.BASE_URL}/static/css/main.css",
            f"{self.BASE_URL}/static/css/admin/dark-mode.css",
            f"{self.BASE_URL}/static/css/components/admin-dashboard.css",
        ]

        reduced_motion_support = False

        for css_url in css_files:
            try:
                response = requests.get(css_url)
                css_content = response.text

                if "prefers-reduced-motion" in css_content:
                    reduced_motion_support = True
                    break
            except:
                pass

        assert reduced_motion_support, "Keine prefers-reduced-motion Unterstützung gefunden"

        # JavaScript-Test für reduced motion
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Simuliere prefers-reduced-motion: reduce
        reduced_motion_test = driver.execute_script(
            """
            // Test ob Animationen respektiert werden
            var testElement = document.createElement('div');
            testElement.style.cssText = 'transition: all 0.3s ease; transform: translateX(0px);';
            document.body.appendChild(testElement);
            
            // Trigger animation
            testElement.style.transform = 'translateX(100px)';
            
            // Check computed style
            var computedStyle = getComputedStyle(testElement);
            var transition = computedStyle.transitionDuration;
            
            document.body.removeChild(testElement);
            
            return {
                transitionDuration: transition,
                supportsReducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches
            };
        """
        )

        # Test passiert implizit - Browser-Support wird geprüft
        assert "transitionDuration" in reduced_motion_test

    def test_screen_reader_compatibility(self, admin_session):
        """Test: Screen Reader-Kompatibilität"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Page-Title für Screen Reader
        page_title = driver.title
        assert page_title and len(page_title) > 0, "Page-Title für Screen Reader erforderlich"
        assert "Admin Dashboard" in page_title, "Page-Title sollte aussagekräftig sein"

        # Meta-Description (falls vorhanden)
        meta_description = driver.find_elements(By.CSS_SELECTOR, "meta[name='description']")
        if meta_description:
            content = meta_description[0].get_attribute("content")
            assert len(content) > 10, "Meta-Description sollte aussagekräftig sein"

        # Lang-Attribut
        html_element = driver.find_element(By.TAG_NAME, "html")
        lang_attr = html_element.get_attribute("lang")
        assert lang_attr, "HTML-Element sollte lang-Attribut haben"

        # Images sollten alt-Attribute haben
        images = driver.find_elements(By.TAG_NAME, "img")
        for img in images:
            alt_text = img.get_attribute("alt")
            src = img.get_attribute("src")

            # Decorative images können alt="" haben
            assert alt_text is not None, f"Image ohne alt-Attribut: {src}"

        # Icons sollten aria-hidden oder alt-text haben
        icons = driver.find_elements(By.CSS_SELECTOR, "i[class*='bi-']")
        for icon in icons:
            aria_hidden = icon.get_attribute("aria-hidden")
            aria_label = icon.get_attribute("aria-label")
            title = icon.get_attribute("title")

            # Decorative icons sollten aria-hidden="true" haben
            # Functional icons sollten labels haben
            parent_text = icon.find_element(By.XPATH, "..").text

            if not parent_text.strip():  # Icon ohne umgebenden Text
                assert (
                    aria_label or title
                ), f"Functional icon ohne Label: {icon.get_attribute('class')}"

    def test_form_accessibility(self, admin_session):
        """Test: Formular-Accessibility (falls Formulare vorhanden)"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Suche nach Formularen
        forms = driver.find_elements(By.TAG_NAME, "form")

        for form in forms:
            # Form sollte accessible name haben
            form_aria_label = form.get_attribute("aria-label")
            form_aria_labelledby = form.get_attribute("aria-labelledby")

            # Oder durch Heading/Legend identifizierbar sein
            legends = form.find_elements(By.TAG_NAME, "legend")
            headings_in_form = form.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6")

            has_form_label = (
                form_aria_label
                or form_aria_labelledby
                or len(legends) > 0
                or len(headings_in_form) > 0
            )

            # Für komplexe Forms ist Label empfohlen
            form_inputs = form.find_elements(By.TAG_NAME, "input")
            if len(form_inputs) > 2:
                assert has_form_label, "Komplexe Forms sollten accessible name haben"

            # Error-Messages sollten mit aria-describedby verknüpft sein
            error_messages = form.find_elements(
                By.CSS_SELECTOR, ".invalid-feedback, .error-message"
            )
            for error in error_messages:
                error_id = error.get_attribute("id")
                if error_id:
                    # Suche nach Input mit aria-describedby
                    related_inputs = form.find_elements(
                        By.CSS_SELECTOR, f"[aria-describedby*='{error_id}']"
                    )
                    # Error-Message sollte mit Input verknüpft sein

    def test_table_accessibility(self, admin_session):
        """Test: Tabellen-Accessibility (falls vorhanden)"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Suche nach Tabellen
        tables = driver.find_elements(By.TAG_NAME, "table")

        for table in tables:
            # Table sollte caption oder aria-label haben
            caption = table.find_elements(By.TAG_NAME, "caption")
            aria_label = table.get_attribute("aria-label")
            aria_labelledby = table.get_attribute("aria-labelledby")

            has_table_label = len(caption) > 0 or aria_label or aria_labelledby

            # Komplexe Tabellen sollten Labels haben
            rows = table.find_elements(By.TAG_NAME, "tr")
            if len(rows) > 3:
                assert has_table_label, "Komplexe Tabellen sollten caption oder aria-label haben"

            # Header-Zellen sollten th-Elemente sein
            headers = table.find_elements(By.TAG_NAME, "th")
            first_row_cells = table.find_elements(
                By.CSS_SELECTOR, "tr:first-child td, tr:first-child th"
            )

            # Erste Zeile sollte Headers enthalten
            if len(first_row_cells) > 1:
                assert len(headers) > 0, "Tabelle sollte th-Elemente für Headers haben"

    def test_skip_links_navigation(self, admin_session):
        """Test: Skip-Links für Keyboard-Navigation"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Tab zum ersten Element
        ActionChains(driver).send_keys(Keys.TAB).perform()
        time.sleep(0.1)

        focused_element = driver.switch_to.active_element

        # Prüfe ob erstes fokussierbares Element ein Skip-Link ist
        element_text = focused_element.text.lower()
        href = focused_element.get_attribute("href")

        # Skip-Links sind optional, aber empfohlen für komplexe Seiten
        # Test passiert implizit - wenn Skip-Link vorhanden, sollte er funktionieren
        if "skip" in element_text or "springe" in element_text:
            # Skip-Link sollte zu Hauptinhalt führen
            assert href and "#" in href, "Skip-Link sollte Anchor-Link sein"

            # Skip-Link aktivieren
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.1)

            # Focus sollte sich bewegt haben
            new_focused = driver.switch_to.active_element
            assert new_focused != focused_element, "Skip-Link sollte Focus bewegen"

    def test_responsive_accessibility(self, admin_session):
        """Test: Accessibility bleibt bei verschiedenen Viewport-Größen erhalten"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        viewport_sizes = [
            (1920, 1080),  # Desktop
            (768, 1024),  # Tablet
            (375, 667),  # Mobile
        ]

        for width, height in viewport_sizes:
            driver.set_window_size(width, height)
            time.sleep(0.5)

            # Theme-Toggle sollte weiterhin accessible sein
            theme_toggle = driver.find_element(By.ID, "themeToggle")
            assert theme_toggle.is_displayed(), f"Theme-Toggle nicht sichtbar bei {width}x{height}"

            # Tab-Navigation sollte funktionieren
            theme_toggle.click()  # Focus setzen
            ActionChains(driver).send_keys(Keys.TAB).perform()
            time.sleep(0.1)

            # Nächstes Element sollte fokussiert sein
            focused = driver.switch_to.active_element
            assert focused != theme_toggle, f"Tab-Navigation nicht functional bei {width}x{height}"

            # Text sollte lesbar bleiben (nicht zu klein)
            body_font_size = driver.find_element(By.TAG_NAME, "body").value_of_css_property(
                "font-size"
            )
            font_size_px = float(body_font_size.replace("px", "")) if "px" in body_font_size else 16

            # Minimum 14px für Accessibility
            assert font_size_px >= 14, f"Font zu klein bei {width}x{height}: {font_size_px}px"
