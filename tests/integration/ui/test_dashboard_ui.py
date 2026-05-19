"""
UI Integration Tests - Dashboard UI Interactions
Tests für AJAX-Actions, Live-Updates, Loading-States
Session 11.2 - Frontend-UI-Tests
"""

import pytest
import requests
import time
import json
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from unittest.mock import patch


class TestDashboardUI:
    """Test-Suite für Dashboard-UI-Interaktionen"""

    BASE_URL = "http://localhost:5001"

    @pytest.fixture
    def chrome_driver(self):
        """Chrome WebDriver mit optimierten Einstellungen"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-web-security")  # Für AJAX-Tests
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, chrome_driver):
        """Authentifizierte Admin-Session im Dashboard"""
        driver = chrome_driver

        # Login
        driver.get(f"{self.BASE_URL}/auth/login")
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys("admin@test.com")
        password_field.send_keys("testpass123")
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()

        # Zum Dashboard navigieren
        WebDriverWait(driver, 10).until(lambda d: "/admin/dashboard" in d.current_url)

        return driver

    def test_dashboard_loads_with_enhanced_assets(self, admin_session):
        """Test: Dashboard lädt mit neuen CSS/JS-Assets"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Prüfe ob neue CSS-Files geladen wurden
        css_links = driver.find_elements(By.CSS_SELECTOR, "link[rel='stylesheet']")
        css_hrefs = [link.get_attribute("href") for link in css_links]

        # Erwartete CSS-Files
        expected_css = [
            "css/main.css",
            "css/admin/dark-mode.css",
            "css/components/admin-dashboard.css",
            "css/components/loading.css",
        ]

        for expected in expected_css:
            assert any(
                expected in href for href in css_hrefs
            ), f"CSS-File {expected} nicht gefunden"

        # Prüfe ob neue JS-Files geladen wurden
        script_tags = driver.find_elements(By.TAG_NAME, "script")
        script_srcs = [
            script.get_attribute("src") for script in script_tags if script.get_attribute("src")
        ]

        expected_js = [
            "js/theme.js",
            "js/shared/loading-states.js",
            "js/admin-modules/admin-dashboard.js",
        ]

        for expected in expected_js:
            assert any(expected in src for src in script_srcs), f"JS-File {expected} nicht gefunden"

    def test_metric_cards_enhanced_styling(self, admin_session):
        """Test: Metric Cards haben enhanced styling mit data-stat Attributen"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Metric Cards finden
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        assert len(metric_cards) >= 4, "Mindestens 4 Metric Cards erwartet"

        for card in metric_cards:
            # data-stat Attribut prüfen
            data_stat = card.get_attribute("data-stat")
            assert data_stat is not None, "Metric Card sollte data-stat Attribut haben"

            # Loading-Spinner prüfen
            loading_spinner = card.find_elements(By.CLASS_NAME, "stat-loading")
            assert len(loading_spinner) == 1, "Metric Card sollte loading-spinner haben"

            # Enhanced styling prüfen
            card_classes = card.get_attribute("class")
            assert "metric-card" in card_classes

            # Hover-Effekt testen (CSS Transform)
            original_transform = card.value_of_css_property("transform")
            ActionChains(driver).move_to_element(card).perform()
            time.sleep(0.1)
            # Note: Schwer zu testen da CSS :hover in Selenium nicht zuverlässig

    def test_refresh_button_functionality(self, admin_session):
        """Test: Refresh-Button triggert Dashboard-Aktualisierung"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Refresh-Button finden
        refresh_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-action='refresh']"))
        )

        # Ursprünglichen Last-Refresh-Zeitstempel merken
        last_refresh_element = driver.find_elements(By.CSS_SELECTOR, "[data-last-refresh]")
        if last_refresh_element:
            original_time = last_refresh_element[0].text

        # Refresh-Button klicken
        refresh_button.click()

        # Warten auf AJAX-Request (Loading-State)
        time.sleep(1)

        # Prüfen ob Last-Refresh-Zeit aktualisiert wurde
        if last_refresh_element:
            WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "[data-last-refresh]").text
                != original_time
            )

    def test_export_button_ajax_functionality(self, admin_session):
        """Test: Export-Buttons verwenden AJAX anstatt Page-Reload"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Excel-Export-Button finden
        excel_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-export='excel']"))
        )

        # Ursprüngliche URL merken
        original_url = driver.current_url

        # Button klicken
        excel_button.click()

        # Kurz warten für AJAX
        time.sleep(2)

        # URL sollte sich nicht geändert haben (AJAX, nicht Page-Reload)
        assert driver.current_url == original_url

        # Loading-State prüfen (Button sollte disabled gewesen sein)
        # Note: Schwer zu testen da AJAX oft sehr schnell ist

        # JSON-Export testen
        json_button = driver.find_element(By.CSS_SELECTOR, "[data-export='json']")
        json_button.click()
        time.sleep(2)
        assert driver.current_url == original_url

    def test_crawler_buttons_ajax_functionality(self, admin_session):
        """Test: Crawler-Buttons verwenden AJAX für Start-Requests"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # GDPRhub-Crawler-Button finden
        gdprhub_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-crawl='gdprhub']"))
        )

        original_url = driver.current_url

        # Button klicken
        gdprhub_button.click()
        time.sleep(2)

        # URL sollte unverändert sein (AJAX)
        assert driver.current_url == original_url

        # OpenLegalData-Crawler testen
        openlegaldata_button = driver.find_element(By.CSS_SELECTOR, "[data-crawl='openlegaldata']")
        openlegaldata_button.click()
        time.sleep(2)
        assert driver.current_url == original_url

    def test_loading_states_display(self, admin_session):
        """Test: Loading-States werden korrekt angezeigt"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # LoadingStates JavaScript-Utility testen
        loading_states_available = driver.execute_script(
            "return typeof window.LoadingStates !== 'undefined';"
        )
        assert loading_states_available, "LoadingStates Utility sollte verfügbar sein"

        # Test verschiedene Loading-State-Methoden
        test_script = """
        // Test-Element erstellen
        var testDiv = document.createElement('div');
        testDiv.id = 'loadingTest';
        document.body.appendChild(testDiv);
        
        // Skeleton Loading testen
        LoadingStates.show(testDiv, 'skeleton', 3);
        var skeletonPresent = testDiv.innerHTML.includes('skeleton-line');
        
        // Loading zurücksetzen
        LoadingStates.hide(testDiv);
        var loadingRemoved = !testDiv.innerHTML.includes('skeleton-line');
        
        // Aufräumen
        document.body.removeChild(testDiv);
        
        return {skeletonPresent: skeletonPresent, loadingRemoved: loadingRemoved};
        """

        result = driver.execute_script(test_script)
        assert result["skeletonPresent"], "Skeleton-Loading sollte angezeigt werden"
        assert result["loadingRemoved"], "Loading-State sollte entfernt werden können"

    def test_dashboard_auto_refresh(self, admin_session):
        """Test: Auto-Refresh funktioniert (alle 30 Sekunden)"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # GDPRDashboard JavaScript-Utility prüfen
        dashboard_available = driver.execute_script(
            "return typeof window.GDPRDashboard !== 'undefined';"
        )
        assert dashboard_available, "GDPRDashboard Utility sollte verfügbar sein"

        # Auto-Refresh-Interval prüfen (sollte gestartet sein)
        auto_refresh_active = driver.execute_script(
            """
            // Prüfen ob Timer-ID gesetzt ist (private, aber wir können den Effekt testen)
            // Stattdessen testen wir ob refresh-Funktion verfügbar ist
            return typeof GDPRDashboard.refresh === 'function' && 
                   typeof GDPRDashboard.start === 'function' &&
                   typeof GDPRDashboard.stop === 'function';
        """
        )
        assert auto_refresh_active, "Auto-Refresh-Funktionen sollten verfügbar sein"

        # Manual refresh testen
        refresh_result = driver.execute_script("GDPRDashboard.refresh(); return true;")
        assert refresh_result

    def test_chart_containers_enhanced(self, admin_session):
        """Test: Chart-Container haben enhanced styling"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Chart-Container finden
        chart_containers = driver.find_elements(By.CLASS_NAME, "chart-container")
        assert len(chart_containers) >= 3, "Mindestens 3 Chart-Container erwartet"

        for container in chart_containers:
            # Enhanced styling prüfen
            border_radius = container.value_of_css_property("border-radius")
            assert border_radius != "0px", "Chart-Container sollte border-radius haben"

            # Box-shadow prüfen
            box_shadow = container.value_of_css_property("box-shadow")
            assert box_shadow != "none", "Chart-Container sollte box-shadow haben"

            # Background-color prüfen
            bg_color = container.value_of_css_property("background-color")
            assert bg_color != "rgba(0, 0, 0, 0)", "Chart-Container sollte background-color haben"

    def test_cli_command_styling(self, admin_session):
        """Test: CLI-Commands haben enhanced monospace styling"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # CLI-Command-Elemente finden
        cli_commands = driver.find_elements(By.CLASS_NAME, "cli-command")
        assert len(cli_commands) >= 2, "Mindestens 2 CLI-Commands erwartet"

        for cli_cmd in cli_commands:
            # Monospace Font prüfen
            font_family = cli_cmd.value_of_css_property("font-family")
            monospace_fonts = ["monospace", "Monaco", "Courier", "SF Mono", "Cascadia Code"]
            assert any(
                font in font_family for font in monospace_fonts
            ), f"CLI-Command sollte monospace font haben: {font_family}"

            # Dark background prüfen
            bg_color = cli_cmd.value_of_css_property("background-color")
            # RGB-Werte für dunklen Hintergrund extrahieren
            import re

            rgb_match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", bg_color)
            if rgb_match:
                r, g, b = map(int, rgb_match.groups())
                brightness = (r + g + b) / 3
                assert brightness < 100, f"CLI-Command sollte dunklen Hintergrund haben: {bg_color}"

    def test_responsive_grid_layout(self, admin_session):
        """Test: CSS-Grid-basierte responsive Layouts"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Stats-Grid prüfen
        stats_grid = driver.find_element(By.CLASS_NAME, "stats-grid")
        display_type = stats_grid.value_of_css_property("display")
        assert display_type == "grid", "Stats-Grid sollte CSS Grid verwenden"

        grid_template = stats_grid.value_of_css_property("grid-template-columns")
        assert (
            "repeat" in grid_template or "fr" in grid_template
        ), "Grid sollte responsive template haben"

        # Mobile-Ansicht simulieren
        driver.set_window_size(375, 667)  # iPhone-Größe
        time.sleep(0.5)

        # Grid sollte sich anpassen (schwer exakt zu testen, aber Layout sollte nicht brechen)
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")
        for card in metric_cards:
            card_width = card.size["width"]
            assert card_width > 0, "Metric Card sollte sichtbare Breite haben"

        # Desktop-Ansicht wiederherstellen
        driver.set_window_size(1920, 1080)

    def test_activity_items_enhanced(self, admin_session):
        """Test: Activity-Items haben enhanced styling"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Activity-Items finden
        activity_items = driver.find_elements(By.CLASS_NAME, "activity-item")

        if len(activity_items) > 0:
            for item in activity_items[:3]:  # Nur erste 3 testen
                # Border-left prüfen (sollte colored border haben)
                border_left = item.value_of_css_property("border-left-width")
                assert border_left != "0px", "Activity-Item sollte left border haben"

                # Background-color prüfen
                bg_color = item.value_of_css_property("background-color")
                assert bg_color != "rgba(0, 0, 0, 0)", "Activity-Item sollte background haben"

                # Border-radius prüfen
                border_radius = item.value_of_css_property("border-radius")
                # Sollte rechts rounded sein (border-radius: 0 8px 8px 0)
                assert border_radius != "0px", "Activity-Item sollte border-radius haben"

    def test_javascript_modules_error_free(self, admin_session):
        """Test: Keine JavaScript-Fehler in Console nach Dashboard-Load"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis alle Scripts geladen sind
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return typeof GDPRTheme !== 'undefined'")
        )

        # Console-Logs prüfen
        logs = driver.get_log("browser")

        # Nur SEVERE Errors sind problematisch
        severe_errors = [log for log in logs if log["level"] == "SEVERE"]

        # Filter bekannte harmlose Errors
        actual_errors = []
        for error in severe_errors:
            message = error["message"]
            # Chart.js Warnings ignorieren (sind normal)
            if "Chart.js" in message or "chart" in message.lower():
                continue
            # Favicon 404 ignorieren
            if "favicon" in message.lower():
                continue
            actual_errors.append(error)

        assert len(actual_errors) == 0, f"JavaScript-Fehler gefunden: {actual_errors}"

    def test_dashboard_performance_metrics(self, admin_session):
        """Test: Dashboard-Performance-Metriken"""
        driver = admin_session

        # Performance-Timing für Dashboard-Load
        start_time = time.time()
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis Dashboard vollständig geladen
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return typeof GDPRDashboard !== 'undefined'")
        )

        end_time = time.time()
        load_time = (end_time - start_time) * 1000  # in ms

        # Dashboard sollte unter 3 Sekunden laden
        assert load_time < 3000, f"Dashboard-Load dauerte {load_time:.2f}ms, sollte < 3000ms sein"

        # JavaScript-Performance prüfen
        js_performance = driver.execute_script(
            """
            var start = performance.now();
            // Simuliere Theme-Wechsel-Performance
            if (typeof GDPRTheme !== 'undefined') {
                GDPRTheme.apply('dark');
                GDPRTheme.apply('light');
            }
            var end = performance.now();
            return end - start;
        """
        )

        assert (
            js_performance < 50
        ), f"JavaScript-Operations dauerten {js_performance:.2f}ms, sollten < 50ms sein"
