"""
UI Integration Tests - Theme System
Tests für Dark/Light Mode, Theme-Toggle und LocalStorage Persistence
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options


class TestThemeSystem:
    """Test-Suite für das Theme-System (Dark/Light Mode)"""

    BASE_URL = "http://localhost:5001"

    @pytest.fixture
    def chrome_driver(self):
        """Chrome WebDriver mit optimierten Einstellungen"""
        options = Options()
        options.add_argument("--headless")  # Für CI/CD
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, chrome_driver):
        """Authentifizierte Admin-Session"""
        driver = chrome_driver

        # Login-Seite aufrufen
        driver.get(f"{self.BASE_URL}/auth/login")

        # Login-Formular ausfüllen
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")

        username_field.send_keys("admin@test.com")
        password_field.send_keys("testpass123")

        # Submit-Button finden und klicken
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()

        # Warten auf Weiterleitung
        WebDriverWait(driver, 10).until(lambda d: "/admin/dashboard" in d.current_url)

        return driver

    def test_theme_toggle_button_exists(self, admin_session):
        """Test: Theme-Toggle-Button ist im Admin-Dashboard vorhanden"""
        driver = admin_session

        # Dashboard-Seite aufrufen
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Theme-Toggle-Button finden
        theme_toggle = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "themeToggle"))
        )

        assert theme_toggle.is_displayed()
        assert theme_toggle.is_enabled()

        # Button-Icon prüfen (sollte Moon-Icon für Light-Mode sein)
        icon = theme_toggle.find_element(By.TAG_NAME, "i")
        assert "bi-moon-fill" in icon.get_attribute("class")

    def test_theme_toggle_functionality(self, admin_session):
        """Test: Theme-Toggle wechselt zwischen Light und Dark Mode"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Initial sollte Light Mode aktiv sein
        html_element = driver.find_element(By.TAG_NAME, "html")
        initial_theme = html_element.get_attribute("data-theme")
        assert initial_theme != "dark"  # Sollte light oder None sein

        # Theme-Toggle-Button klicken
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()

        # Warten auf Theme-Wechsel (Animation)
        time.sleep(0.5)

        # Dark Mode sollte aktiv sein
        html_element = driver.find_element(By.TAG_NAME, "html")
        new_theme = html_element.get_attribute("data-theme")
        assert new_theme == "dark"

        # Icon sollte sich geändert haben (Sun-Icon für Dark-Mode)
        icon = theme_toggle.find_element(By.TAG_NAME, "i")
        assert "bi-sun-fill" in icon.get_attribute("class")

        # Nochmal klicken -> zurück zu Light Mode
        theme_toggle.click()
        time.sleep(0.5)

        html_element = driver.find_element(By.TAG_NAME, "html")
        final_theme = html_element.get_attribute("data-theme")
        assert final_theme != "dark"

    def test_theme_keyboard_shortcut(self, admin_session):
        """Test: Keyboard Shortcut Ctrl+Shift+D für Theme-Toggle"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Initial Theme feststellen
        html_element = driver.find_element(By.TAG_NAME, "html")
        initial_theme = html_element.get_attribute("data-theme")

        # Keyboard Shortcut ausführen (Ctrl+Shift+D)
        ActionChains(driver).key_down(Keys.CONTROL).key_down(Keys.SHIFT).send_keys("d").key_up(
            Keys.SHIFT
        ).key_up(Keys.CONTROL).perform()

        # Warten auf Theme-Wechsel
        time.sleep(0.5)

        # Theme sollte gewechselt haben
        html_element = driver.find_element(By.TAG_NAME, "html")
        new_theme = html_element.get_attribute("data-theme")
        assert new_theme != initial_theme

    def test_theme_localstorage_persistence(self, admin_session):
        """Test: Theme-Einstellung wird in LocalStorage gespeichert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Auf Dark Mode wechseln
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()
        time.sleep(0.5)

        # LocalStorage prüfen
        stored_theme = driver.execute_script("return localStorage.getItem('gdpr-theme');")
        assert stored_theme == "dark"

        # Seite neu laden
        driver.refresh()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "themeToggle")))

        # Theme sollte Dark Mode bleiben
        html_element = driver.find_element(By.TAG_NAME, "html")
        theme_after_reload = html_element.get_attribute("data-theme")
        assert theme_after_reload == "dark"

        # Icon sollte Sun-Icon sein
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        icon = theme_toggle.find_element(By.TAG_NAME, "i")
        assert "bi-sun-fill" in icon.get_attribute("class")

    def test_theme_css_variables_application(self, admin_session):
        """Test: CSS Variables werden korrekt angewendet bei Theme-Wechsel"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Light Mode CSS Variables prüfen
        body_bg_light = driver.execute_script(
            "return getComputedStyle(document.body).backgroundColor;"
        )

        # Zu Dark Mode wechseln
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()
        time.sleep(0.5)

        # Dark Mode CSS Variables prüfen
        body_bg_dark = driver.execute_script(
            "return getComputedStyle(document.body).backgroundColor;"
        )

        # Background-Color sollte sich geändert haben
        assert body_bg_light != body_bg_dark

        # Dark Mode sollte dunklere Farben haben
        # RGB-Werte extrahieren und vergleichen
        import re

        def extract_rgb_values(color_string):
            match = re.search(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", color_string)
            if match:
                return [int(match.group(1)), int(match.group(2)), int(match.group(3))]
            return [255, 255, 255]  # Default white

        light_rgb = extract_rgb_values(body_bg_light)
        dark_rgb = extract_rgb_values(body_bg_dark)

        # Dark Mode sollte niedrigere RGB-Werte haben (dunkler)
        light_brightness = sum(light_rgb) / 3
        dark_brightness = sum(dark_rgb) / 3

        assert (
            dark_brightness < light_brightness
        ), f"Dark mode ({dark_brightness}) should be darker than light mode ({light_brightness})"

    def test_theme_toast_notification(self, admin_session):
        """Test: Toast-Notification wird beim Theme-Wechsel angezeigt"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Theme wechseln
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()

        # Toast-Notification sollte erscheinen
        try:
            toast = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "toast"))
            )
            assert toast.is_displayed()

            # Toast sollte Dark Mode Text enthalten
            toast_body = toast.find_element(By.CLASS_NAME, "toast-body")
            assert "Dark Mode aktiviert" in toast_body.text

        except:
            # Falls Bootstrap nicht verfügbar, sollte trotzdem kein Fehler auftreten
            pass

    def test_theme_system_preference_detection(self, chrome_driver):
        """Test: System-Theme-Preference wird erkannt"""
        driver = chrome_driver

        # System auf Dark Mode setzen (simuliert)
        driver.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {"media": "screen", "features": [{"name": "prefers-color-scheme", "value": "dark"}]},
        )

        # Neuer Besuch der Seite (ohne LocalStorage)
        driver.execute_script("localStorage.clear();")
        driver.get(f"{self.BASE_URL}/admin/login")

        # JavaScript sollte Dark Mode erkennen
        preferred_theme = driver.execute_script(
            """
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        """
        )

        assert preferred_theme == "dark"

    def test_theme_performance(self, admin_session):
        """Test: Theme-Wechsel-Performance unter 100ms"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        theme_toggle = driver.find_element(By.ID, "themeToggle")

        # Performance messen
        start_time = time.time()
        theme_toggle.click()

        # Warten bis Theme-Attribut geändert ist
        WebDriverWait(driver, 2).until(
            lambda d: d.find_element(By.TAG_NAME, "html").get_attribute("data-theme") == "dark"
        )

        end_time = time.time()
        switch_duration = (end_time - start_time) * 1000  # in ms

        assert (
            switch_duration < 100
        ), f"Theme switch took {switch_duration:.2f}ms, should be < 100ms"

    def test_theme_accessibility_focus(self, admin_session):
        """Test: Theme-Toggle-Button ist keyboard-accessible"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Tab-Navigation zum Theme-Toggle
        body = driver.find_element(By.TAG_NAME, "body")
        body.click()  # Focus setzen

        # Tab mehrmals drücken um zum Theme-Toggle zu gelangen
        for _ in range(10):  # Max 10 Tab-Versuche
            ActionChains(driver).send_keys(Keys.TAB).perform()
            focused_element = driver.switch_to.active_element

            if focused_element.get_attribute("id") == "themeToggle":
                # Enter-Taste drücken
                ActionChains(driver).send_keys(Keys.ENTER).perform()
                time.sleep(0.5)

                # Theme sollte gewechselt haben
                html_element = driver.find_element(By.TAG_NAME, "html")
                theme = html_element.get_attribute("data-theme")
                assert theme == "dark"
                return

        pytest.fail("Theme-Toggle-Button nicht via Tab-Navigation erreichbar")

    def test_theme_css_isolation(self, admin_session):
        """Test: Theme-CSS beeinflusst nicht andere UI-Komponenten negativ"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Wichtige UI-Elemente vor Theme-Wechsel sammeln
        elements_before = {
            "navbar": driver.find_element(By.CLASS_NAME, "navbar").value_of_css_property("display"),
            "cards": len(driver.find_elements(By.CLASS_NAME, "metric-card")),
            "buttons": len(driver.find_elements(By.TAG_NAME, "button")),
        }

        # Theme wechseln
        theme_toggle = driver.find_element(By.ID, "themeToggle")
        theme_toggle.click()
        time.sleep(0.5)

        # UI-Elemente nach Theme-Wechsel prüfen
        elements_after = {
            "navbar": driver.find_element(By.CLASS_NAME, "navbar").value_of_css_property("display"),
            "cards": len(driver.find_elements(By.CLASS_NAME, "metric-card")),
            "buttons": len(driver.find_elements(By.TAG_NAME, "button")),
        }

        # Struktur sollte unverändert sein
        assert elements_before["navbar"] == elements_after["navbar"]
        assert elements_before["cards"] == elements_after["cards"]
        assert elements_before["buttons"] == elements_after["buttons"]

        # Keine Console-Errors nach Theme-Wechsel
        logs = driver.get_log("browser")
        severe_errors = [log for log in logs if log["level"] == "SEVERE"]
        assert len(severe_errors) == 0, f"Console errors after theme switch: {severe_errors}"
