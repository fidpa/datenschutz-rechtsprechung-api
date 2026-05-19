"""
UI Integration Tests - Enhanced Admin Dashboard
Erweiterte Admin-Tests für neue UI-Features und AJAX-Funktionalität
Session 11.2 - Admin-Dashboard-Enhanced-Tests
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
from selenium.webdriver.chrome.options import Options
from unittest.mock import patch


class TestAdminUIEnhanced:
    """Test-Suite für Enhanced Admin-Dashboard-UI"""

    BASE_URL = "http://localhost:5001"

    @pytest.fixture
    def chrome_driver(self):
        """Chrome WebDriver mit Admin-UI-spezifischen Einstellungen"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-web-security")
        options.add_argument("--window-size=1920,1080")
        # Network-Logs für AJAX-Testing
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, chrome_driver):
        """Admin-Session mit Theme-System-Initialierung"""
        driver = chrome_driver

        # Login als Admin
        driver.get(f"{self.BASE_URL}/auth/login")
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys("admin@test.com")
        password_field.send_keys("testpass123")
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()

        # Zum Dashboard navigieren und warten bis vollständig geladen
        WebDriverWait(driver, 10).until(lambda d: "/admin/dashboard" in d.current_url)

        # Warten bis alle neuen JS-Module geladen
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script(
                "return typeof GDPRTheme !== 'undefined' && typeof GDPRDashboard !== 'undefined'"
            )
        )

        return driver

    def test_enhanced_dashboard_header_layout(self, admin_session):
        """Test: Dashboard-Header hat neues Layout mit Theme-Toggle"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Header-Container mit flexbox layout
        header_container = driver.find_element(
            By.CSS_SELECTOR, ".d-flex.justify-content-between.align-items-center"
        )
        assert header_container.is_displayed()

        # Dashboard-Titel
        title = header_container.find_element(By.TAG_NAME, "h1")
        assert "Datenschutz-Rechtsprechung API Dashboard" in title.text

        # Control-Gruppe (Theme-Toggle + Refresh)
        controls_group = header_container.find_element(
            By.CSS_SELECTOR, ".d-flex.align-items-center.gap-3"
        )
        assert controls_group.is_displayed()

        # Theme-Toggle-Button
        theme_toggle = controls_group.find_element(By.ID, "themeToggle")
        assert theme_toggle.is_displayed()
        assert "Theme wechseln" in theme_toggle.get_attribute("title")

        # Refresh-Button
        refresh_button = controls_group.find_element(By.CSS_SELECTOR, "[data-action='refresh']")
        assert refresh_button.is_displayed()
        assert "Dashboard aktualisieren" in refresh_button.get_attribute("title")

        # Last-Refresh-Timestamp
        last_refresh = controls_group.find_element(By.CSS_SELECTOR, "[data-last-refresh]")
        assert last_refresh.is_displayed()
        assert "Letztes Update" in last_refresh.text

    def test_metric_cards_data_attributes(self, admin_session):
        """Test: Metric Cards haben korrekte data-stat Attribute für Live-Updates"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Erwartete data-stat Attribute
        expected_stats = [
            "decisions.total",
            "decisions.this_week",
            "decisions.this_month",
            "quality.anonymization_rate",
        ]

        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        assert len(metric_cards) >= 4, "Mindestens 4 Metric Cards erwartet"

        found_stats = []
        for card in metric_cards:
            data_stat = card.get_attribute("data-stat")
            if data_stat:
                found_stats.append(data_stat)

                # Loading-Spinner vorhanden
                loading_spinner = card.find_element(By.CLASS_NAME, "stat-loading")
                assert (
                    loading_spinner.is_displayed() == False
                ), "Loading-Spinner sollte initial hidden sein"

                # Metric-Value Element vorhanden
                metric_value = card.find_element(By.CLASS_NAME, "metric-value")
                assert metric_value.is_displayed()

                # Metric-Change Element vorhanden
                metric_change = card.find_element(By.CLASS_NAME, "metric-change")
                assert metric_change.is_displayed()

        # Alle erwarteten Stats gefunden
        for expected in expected_stats:
            assert expected in found_stats, f"data-stat '{expected}' nicht gefunden"

    def test_ajax_export_functionality(self, admin_session):
        """Test: Export-Buttons verwenden AJAX mit data-export Attributen"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Excel-Export-Button testen
        excel_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-export='excel']"))
        )

        assert excel_button.get_attribute("data-export") == "excel"
        original_text = excel_button.text
        original_url = driver.current_url

        # Network-Requests vor Klick zählen
        initial_logs_count = len(driver.get_log("performance"))

        # Button klicken
        excel_button.click()

        # Kurz warten für AJAX-Request
        time.sleep(1)

        # URL sollte unverändert sein (kein Page-Reload)
        assert driver.current_url == original_url

        # Network-Logs sollten neuen Request zeigen
        final_logs_count = len(driver.get_log("performance"))
        assert final_logs_count > initial_logs_count, "Kein neuer Network-Request erkannt"

        # JSON-Export-Button testen
        json_button = driver.find_element(By.CSS_SELECTOR, "[data-export='json']")
        assert json_button.get_attribute("data-export") == "json"

        json_button.click()
        time.sleep(1)
        assert driver.current_url == original_url

    def test_ajax_crawler_functionality(self, admin_session):
        """Test: Crawler-Buttons verwenden AJAX mit data-crawl Attributen"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # GDPRhub-Crawler-Button
        gdprhub_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-crawl='gdprhub']"))
        )

        assert gdprhub_button.get_attribute("data-crawl") == "gdprhub"
        original_url = driver.current_url

        gdprhub_button.click()
        time.sleep(1)
        assert driver.current_url == original_url

        # OpenLegalData-Crawler-Button
        openlegaldata_button = driver.find_element(By.CSS_SELECTOR, "[data-crawl='openlegaldata']")
        assert openlegaldata_button.get_attribute("data-crawl") == "openlegaldata"

        openlegaldata_button.click()
        time.sleep(1)
        assert driver.current_url == original_url

    def test_live_updates_functionality(self, admin_session):
        """Test: Live-Updates-System funktioniert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # GDPRDashboard-Utility verfügbar
        dashboard_available = driver.execute_script(
            "return typeof window.GDPRDashboard !== 'undefined'"
        )
        assert dashboard_available, "GDPRDashboard-Utility nicht verfügbar"

        # Auto-Refresh-Funktionen testen
        functions_available = driver.execute_script(
            """
            return {
                refresh: typeof GDPRDashboard.refresh === 'function',
                start: typeof GDPRDashboard.start === 'function',
                stop: typeof GDPRDashboard.stop === 'function'
            };
        """
        )

        assert functions_available["refresh"], "GDPRDashboard.refresh() nicht verfügbar"
        assert functions_available["start"], "GDPRDashboard.start() nicht verfügbar"
        assert functions_available["stop"], "GDPRDashboard.stop() nicht verfügbar"

        # Manual Refresh testen
        refresh_result = driver.execute_script(
            """
            try {
                GDPRDashboard.refresh();
                return {success: true, error: null};
            } catch(e) {
                return {success: false, error: e.message};
            }
        """
        )

        assert refresh_result[
            "success"
        ], f"Manual refresh fehlgeschlagen: {refresh_result['error']}"

    def test_loading_states_integration(self, admin_session):
        """Test: Loading-States sind in Admin-Dashboard integriert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # LoadingStates-Utility verfügbar
        loading_states_available = driver.execute_script(
            "return typeof window.LoadingStates !== 'undefined'"
        )
        assert loading_states_available, "LoadingStates-Utility nicht verfügbar"

        # Test Loading-States mit Export-Button
        excel_button = driver.find_element(By.CSS_SELECTOR, "[data-export='excel']")

        # Simuliere Loading-State setzen
        loading_test = driver.execute_script(
            """
            var button = arguments[0];
            var originalContent = button.innerHTML;
            
            // Loading-State setzen
            LoadingStates.setButtonLoading(button, 'Exportiert...');
            var loadingSet = button.disabled && button.innerHTML.includes('Exportiert...');
            
            // Loading-State zurücksetzen
            LoadingStates.resetButton(button);
            var loadingReset = !button.disabled && button.innerHTML === originalContent;
            
            return {loadingSet: loadingSet, loadingReset: loadingReset};
        """,
            excel_button,
        )

        assert loading_test["loadingSet"], "Loading-State konnte nicht gesetzt werden"
        assert loading_test["loadingReset"], "Loading-State konnte nicht zurückgesetzt werden"

    def test_enhanced_css_integration(self, admin_session):
        """Test: Enhanced CSS ist korrekt integriert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # CSS-Links im Head prüfen
        css_links = driver.find_elements(By.CSS_SELECTOR, "link[rel='stylesheet']")
        css_hrefs = [link.get_attribute("href") for link in css_links]

        expected_css = [
            "css/main.css",
            "css/admin/dark-mode.css",
            "css/components/admin-dashboard.css",
            "css/components/loading.css",
        ]

        for expected in expected_css:
            found = any(expected in href for href in css_hrefs)
            assert found, f"Expected CSS file not loaded: {expected}"

        # CSS-Variables-Verfügbarkeit prüfen
        css_variables_test = driver.execute_script(
            """
            var computedStyle = getComputedStyle(document.documentElement);
            return {
                primary: computedStyle.getPropertyValue('--primary').trim(),
                bgPrimary: computedStyle.getPropertyValue('--bg-primary').trim(),
                textPrimary: computedStyle.getPropertyValue('--text-primary').trim()
            };
        """
        )

        assert css_variables_test["primary"], "CSS Variable --primary nicht gesetzt"
        assert css_variables_test["bgPrimary"], "CSS Variable --bg-primary nicht gesetzt"
        assert css_variables_test["textPrimary"], "CSS Variable --text-primary nicht gesetzt"

    def test_responsive_grid_system(self, admin_session):
        """Test: CSS-Grid-System ist responsive"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Desktop-Layout (1920x1080)
        driver.set_window_size(1920, 1080)
        time.sleep(0.5)

        stats_grid = driver.find_element(By.CLASS_NAME, "stats-grid")
        desktop_display = stats_grid.value_of_css_property("display")
        assert desktop_display == "grid", "Stats-Grid sollte CSS Grid verwenden"

        # Grid-Template prüfen
        grid_template = stats_grid.value_of_css_property("grid-template-columns")
        assert (
            "repeat" in grid_template or "fr" in grid_template
        ), "Grid sollte responsive Template haben"

        # Tablet-Layout (768px)
        driver.set_window_size(768, 1024)
        time.sleep(0.5)

        # Grid sollte weiterhin funktionieren
        tablet_display = stats_grid.value_of_css_property("display")
        assert tablet_display == "grid", "Grid sollte auf Tablet weiterhin funktionieren"

        # Mobile-Layout (375px)
        driver.set_window_size(375, 667)
        time.sleep(0.5)

        # Metric Cards sollten stacken (1 Spalte)
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        for card in metric_cards[:2]:  # Erste 2 Cards testen
            card_rect = card.rect
            assert card_rect["width"] > 0, "Metric Card sollte sichtbare Breite haben"

        # Desktop-Layout wiederherstellen
        driver.set_window_size(1920, 1080)

    def test_dark_mode_dashboard_integration(self, admin_session):
        """Test: Dark-Mode ist vollständig in Dashboard integriert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Zu Dark-Mode wechseln
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()
        time.sleep(0.5)

        # HTML data-theme Attribut prüfen
        html_element = driver.find_element(By.TAG_NAME, "html")
        theme = html_element.get_attribute("data-theme")
        assert theme == "dark", f"Dark-Mode nicht aktiv: {theme}"

        # Metric Cards Dark-Mode styling
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        for card in metric_cards[:2]:
            bg_color = card.value_of_css_property("background-color")
            # Dark-Mode sollte dunklere Farben haben
            import re

            rgb_match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", bg_color)
            if rgb_match:
                r, g, b = map(int, rgb_match.groups())
                brightness = (r + g + b) / 3
                # Cards können Gradients haben, daher weniger strikt
                assert brightness < 200, f"Card im Dark-Mode zu hell: {bg_color}"

        # Body background im Dark-Mode
        body_bg = driver.find_element(By.TAG_NAME, "body").value_of_css_property("background-color")
        rgb_match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", body_bg)
        if rgb_match:
            r, g, b = map(int, rgb_match.groups())
            body_brightness = (r + g + b) / 3
            assert body_brightness < 100, f"Body im Dark-Mode zu hell: {body_bg}"

    def test_enhanced_activity_items(self, admin_session):
        """Test: Activity-Items haben enhanced styling"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Activity-Items finden
        activity_items = driver.find_elements(By.CLASS_NAME, "activity-item")

        if len(activity_items) > 0:
            for item in activity_items[:3]:
                # Border-left styling
                border_left = item.value_of_css_property("border-left-color")
                assert (
                    border_left != "rgba(0, 0, 0, 0)"
                ), "Activity-Item sollte colored border haben"

                # Border-radius für rounded corners
                border_radius = item.value_of_css_property("border-radius")
                assert border_radius != "0px", "Activity-Item sollte border-radius haben"

                # Background-color
                bg_color = item.value_of_css_property("background-color")
                assert bg_color != "rgba(0, 0, 0, 0)", "Activity-Item sollte background haben"
        else:
            # Wenn keine Activity-Items vorhanden, ist das OK (leere Datenbank)
            pass

    def test_cli_commands_enhanced_styling(self, admin_session):
        """Test: CLI-Commands haben enhanced monospace styling"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        cli_commands = driver.find_elements(By.CLASS_NAME, "cli-command")
        assert len(cli_commands) >= 3, "Mindestens 3 CLI-Commands erwartet"

        for cli in cli_commands:
            # Monospace font-family
            font_family = cli.value_of_css_property("font-family")
            monospace_indicators = ["monospace", "Monaco", "Courier", "SF Mono", "Cascadia"]
            has_monospace = any(indicator in font_family for indicator in monospace_indicators)
            assert has_monospace, f"CLI-Command sollte monospace font haben: {font_family}"

            # Dark background für Code-ähnliches Aussehen
            bg_color = cli.value_of_css_property("background-color")
            import re

            rgb_match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", bg_color)
            if rgb_match:
                r, g, b = map(int, rgb_match.groups())
                brightness = (r + g + b) / 3
                assert brightness < 80, f"CLI-Command sollte dunklen Hintergrund haben: {bg_color}"

    def test_performance_no_regressions(self, admin_session):
        """Test: Keine Performance-Regressionen durch UI-Enhancements"""
        driver = admin_session

        # Dashboard-Load-Performance messen
        start_time = time.time()
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis alle Elemente geladen
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState === 'complete'")
        )

        end_time = time.time()
        load_time = (end_time - start_time) * 1000

        # Dashboard sollte weiterhin schnell laden (< 3s)
        assert load_time < 3000, f"Dashboard-Load zu langsam: {load_time:.2f}ms"

        # JavaScript-Performance prüfen
        js_performance = driver.execute_script(
            """
            var start = performance.now();
            
            // Simuliere mehrere Dashboard-Operationen
            if (typeof GDPRTheme !== 'undefined') {
                GDPRTheme.toggle();
                GDPRTheme.toggle();
            }
            
            if (typeof GDPRDashboard !== 'undefined') {
                GDPRDashboard.refresh();
            }
            
            var end = performance.now();
            return end - start;
        """
        )

        assert js_performance < 100, f"JavaScript-Operations zu langsam: {js_performance:.2f}ms"

    def test_no_console_errors_with_enhancements(self, admin_session):
        """Test: Keine Console-Errors durch UI-Enhancements"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis alle Scripts geladen
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script(
                "return typeof GDPRTheme !== 'undefined' && typeof GDPRDashboard !== 'undefined'"
            )
        )

        # Verschiedene UI-Operationen ausführen
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()
        time.sleep(0.5)

        excel_button = driver.find_element(By.CSS_SELECTOR, "[data-export='excel']")
        excel_button.click()
        time.sleep(1)

        # Console-Logs prüfen
        logs = driver.get_log("browser")
        severe_errors = [log for log in logs if log["level"] == "SEVERE"]

        # Filter bekannte harmlose Warnings
        actual_errors = []
        for error in severe_errors:
            message = error["message"]
            # Chart.js, Favicon, etc. ignorieren
            if any(term in message.lower() for term in ["chart", "favicon", "bootstrap"]):
                continue
            actual_errors.append(error)

        assert len(actual_errors) == 0, f"Console-Errors nach UI-Enhancements: {actual_errors}"
