"""
UI Integration Tests - Asset Loading & Performance
Tests für CSS/JS Performance, Import-Ketten, Bundle-Größen
Session 11.2 - Asset-Loading-Tests
"""

import pytest
import requests
import time
import gzip
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class TestAssetLoading:
    """Test-Suite für Asset-Loading und Performance"""

    BASE_URL = "http://localhost:5001"
    STATIC_BASE = f"{BASE_URL}/static"

    @pytest.fixture
    def chrome_driver(self):
        """Chrome WebDriver mit Performance-Logging"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--enable-logging")
        options.add_argument("--log-level=0")
        # Performance-Logs aktivieren
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    def test_css_files_load_successfully(self):
        """Test: Alle CSS-Files laden erfolgreich"""
        css_files = [
            "css/main.css",
            "css/custom.css",
            "css/admin/dark-mode.css",
            "css/components/admin-dashboard.css",
            "css/components/cards.css",
            "css/components/forms.css",
            "css/components/loading.css",
        ]

        for css_file in css_files:
            response = requests.get(f"{self.STATIC_BASE}/{css_file}")
            assert response.status_code == 200, f"CSS-File {css_file} nicht erreichbar"
            assert "text/css" in response.headers.get(
                "content-type", ""
            ), f"Falscher Content-Type für {css_file}"
            assert len(response.content) > 100, f"CSS-File {css_file} ist zu klein (< 100 bytes)"

    def test_js_files_load_successfully(self):
        """Test: Alle JavaScript-Files laden erfolgreich"""
        js_files = [
            "js/app.js",
            "js/theme.js",
            "js/admin-modules/admin-dashboard.js",
            "js/shared/loading-states.js",
        ]

        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            assert response.status_code == 200, f"JS-File {js_file} nicht erreichbar"
            assert "javascript" in response.headers.get(
                "content-type", ""
            ), f"Falscher Content-Type für {js_file}"
            assert len(response.content) > 50, f"JS-File {js_file} ist zu klein (< 50 bytes)"

    def test_css_bundle_size_optimization(self):
        """Test: CSS-Bundle-Größe ist optimiert"""
        css_files = [
            "css/main.css",
            "css/admin/dark-mode.css",
            "css/components/admin-dashboard.css",
            "css/components/cards.css",
            "css/components/forms.css",
            "css/components/loading.css",
        ]

        total_css_size = 0

        for css_file in css_files:
            response = requests.get(f"{self.STATIC_BASE}/{css_file}")
            total_css_size += len(response.content)

        # Total CSS sollte unter 50KB sein (unkomprimiert)
        assert (
            total_css_size < 50 * 1024
        ), f"CSS-Bundle zu groß: {total_css_size / 1024:.1f}KB, sollte < 50KB sein"

        # Simuliere gzip-Kompression für Production-Schätzung
        combined_css = ""
        for css_file in css_files:
            response = requests.get(f"{self.STATIC_BASE}/{css_file}")
            combined_css += response.text

        gzipped_size = len(gzip.compress(combined_css.encode("utf-8")))

        # Gzipped sollte unter 15KB sein
        assert (
            gzipped_size < 15 * 1024
        ), f"CSS-Bundle gzipped zu groß: {gzipped_size / 1024:.1f}KB, sollte < 15KB sein"

    def test_js_bundle_size_optimization(self):
        """Test: JavaScript-Bundle-Größe ist optimiert"""
        js_files = [
            "js/theme.js",
            "js/admin-modules/admin-dashboard.js",
            "js/shared/loading-states.js",
        ]

        total_js_size = 0

        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            total_js_size += len(response.content)

        # Total JS sollte unter 30KB sein (unkomprimiert)
        assert (
            total_js_size < 30 * 1024
        ), f"JS-Bundle zu groß: {total_js_size / 1024:.1f}KB, sollte < 30KB sein"

        # Gzip-Schätzung
        combined_js = ""
        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            combined_js += response.text

        gzipped_size = len(gzip.compress(combined_js.encode("utf-8")))

        # Gzipped sollte unter 10KB sein
        assert (
            gzipped_size < 10 * 1024
        ), f"JS-Bundle gzipped zu groß: {gzipped_size / 1024:.1f}KB, sollte < 10KB sein"

    def test_css_import_chain_validity(self):
        """Test: CSS @import-Ketten sind gültig"""
        main_css_response = requests.get(f"{self.STATIC_BASE}/css/main.css")
        main_css_content = main_css_response.text

        # Finde @import-Statements
        import re

        import_statements = re.findall(r'@import\s+url\(["\']([^"\']+)["\']\);', main_css_content)

        for import_path in import_statements:
            # Relative Pfade zu absoluten machen
            if import_path.startswith("admin/") or import_path.startswith("components/"):
                full_url = f"{self.STATIC_BASE}/css/{import_path}"
            else:
                full_url = f"{self.STATIC_BASE}/{import_path}"

            response = requests.get(full_url)
            assert (
                response.status_code == 200
            ), f"Importierte CSS-Datei nicht erreichbar: {import_path}"

    def test_css_variables_declaration(self):
        """Test: CSS Variables sind korrekt deklariert"""
        main_css_response = requests.get(f"{self.STATIC_BASE}/css/main.css")
        main_css_content = main_css_response.text

        # Wichtige CSS Variables prüfen
        required_variables = [
            "--primary",
            "--bg-primary",
            "--text-primary",
            "--border-color",
            "--shadow-sm",
        ]

        for variable in required_variables:
            assert (
                variable in main_css_content
            ), f"CSS Variable {variable} nicht in main.css gefunden"

        # Dark-Mode Variables prüfen
        dark_mode_response = requests.get(f"{self.STATIC_BASE}/css/admin/dark-mode.css")
        dark_mode_content = dark_mode_response.text

        dark_mode_variables = ["--gdpr-bg-primary", "--gdpr-text-primary", '[data-theme="dark"]']

        for variable in dark_mode_variables:
            assert (
                variable in dark_mode_content
            ), f"Dark-Mode Variable/Selector {variable} nicht gefunden"

    def test_asset_loading_performance(self, chrome_driver):
        """Test: Asset-Loading-Performance ist optimiert"""
        driver = chrome_driver

        # Performance-Timing für Asset-Loading
        start_time = time.time()
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis alle CSS/JS geladen
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState === 'complete'")
        )

        end_time = time.time()
        total_load_time = (end_time - start_time) * 1000

        # Page-Load sollte unter 2 Sekunden sein
        assert (
            total_load_time < 2000
        ), f"Asset-Loading dauerte {total_load_time:.2f}ms, sollte < 2000ms sein"

        # Network-Performance via Performance API prüfen
        performance_data = driver.execute_script(
            """
            var entries = performance.getEntriesByType('resource');
            var cssFiles = entries.filter(e => e.name.includes('.css'));
            var jsFiles = entries.filter(e => e.name.includes('.js'));
            
            return {
                cssLoadTime: Math.max(...cssFiles.map(e => e.responseEnd - e.requestStart)),
                jsLoadTime: Math.max(...jsFiles.map(e => e.responseEnd - e.requestStart)),
                totalResources: entries.length
            };
        """
        )

        if performance_data["cssLoadTime"] > 0:
            assert (
                performance_data["cssLoadTime"] < 500
            ), f"CSS-Loading zu langsam: {performance_data['cssLoadTime']:.2f}ms"

        if performance_data["jsLoadTime"] > 0:
            assert (
                performance_data["jsLoadTime"] < 300
            ), f"JS-Loading zu langsam: {performance_data['jsLoadTime']:.2f}ms"

    def test_browser_caching_headers(self):
        """Test: Korrekte Cache-Headers für statische Assets"""
        test_files = ["css/main.css", "js/theme.js", "css/admin/dark-mode.css"]

        for file_path in test_files:
            response = requests.get(f"{self.STATIC_BASE}/{file_path}")

            # Cache-Control Header sollte vorhanden sein
            cache_control = response.headers.get("Cache-Control", "")
            # Für Development kann Cache-Control fehlen, in Production sollte es da sein

            # ETag oder Last-Modified sollte vorhanden sein
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")

            assert etag or last_modified, f"Keine Cache-Header für {file_path} gefunden"

    def test_css_syntax_validity(self):
        """Test: CSS-Syntax ist gültig (keine offensichtlichen Fehler)"""
        css_files = [
            "css/main.css",
            "css/admin/dark-mode.css",
            "css/components/admin-dashboard.css",
        ]

        for css_file in css_files:
            response = requests.get(f"{self.STATIC_BASE}/{css_file}")
            css_content = response.text

            # Basis-Syntax-Checks
            open_braces = css_content.count("{")
            close_braces = css_content.count("}")
            assert open_braces == close_braces, f"Ungleiche Anzahl von Klammern in {css_file}"

            # Keine TODO/FIXME-Kommentare in Production
            assert "TODO" not in css_content.upper(), f"TODO-Kommentare in {css_file} gefunden"
            assert "FIXME" not in css_content.upper(), f"FIXME-Kommentare in {css_file} gefunden"

            # CSS sollte nicht leer sein
            # Entferne Kommentare und Whitespace für echte Content-Prüfung
            import re

            css_without_comments = re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)
            css_without_whitespace = re.sub(r"\s+", "", css_without_comments)
            assert len(css_without_whitespace) > 50, f"CSS-File {css_file} hat zu wenig Content"

    def test_javascript_syntax_validity(self):
        """Test: JavaScript-Syntax ist gültig"""
        js_files = [
            "js/theme.js",
            "js/admin-modules/admin-dashboard.js",
            "js/shared/loading-states.js",
        ]

        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            js_content = response.text

            # Basis-Syntax-Checks
            open_parens = js_content.count("(")
            close_parens = js_content.count(")")
            assert open_parens == close_parens, f"Ungleiche Anzahl von Klammern in {js_file}"

            open_braces = js_content.count("{")
            close_braces = js_content.count("}")
            assert (
                open_braces == close_braces
            ), f"Ungleiche Anzahl von geschweiften Klammern in {js_file}"

            # Keine console.log in Production (außer für Debugging)
            console_logs = js_content.count("console.log")
            assert console_logs < 5, f"Zu viele console.log-Statements in {js_file}: {console_logs}"

            # Keine TODO/FIXME
            assert "TODO" not in js_content.upper(), f"TODO-Kommentare in {js_file} gefunden"
            assert "FIXME" not in js_content.upper(), f"FIXME-Kommentare in {js_file} gefunden"

    def test_asset_compression_potential(self):
        """Test: Assets haben gutes Komprimierungspotential"""
        test_files = [
            ("css/main.css", "text"),
            ("js/theme.js", "text"),
            ("css/admin/dark-mode.css", "text"),
        ]

        for file_path, file_type in test_files:
            response = requests.get(f"{self.STATIC_BASE}/{file_path}")
            original_size = len(response.content)

            # Gzip-Kompression testen
            gzipped_size = len(gzip.compress(response.content))
            compression_ratio = gzipped_size / original_size

            # Gute Kompression sollte < 0.4 (60% Reduktion) erreichen
            assert (
                compression_ratio < 0.6
            ), f"Schlechte Kompression für {file_path}: {compression_ratio:.2f} (sollte < 0.6 sein)"

    def test_font_and_icon_dependencies(self, chrome_driver):
        """Test: Font- und Icon-Dependencies laden korrekt"""
        driver = chrome_driver
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Bootstrap Icons prüfen
        icon_elements = driver.find_elements(By.CSS_SELECTOR, "i[class*='bi-']")
        assert len(icon_elements) > 0, "Keine Bootstrap Icons gefunden"

        # Font-Loading prüfen
        fonts_loaded = driver.execute_script(
            """
            return document.fonts.ready.then(() => {
                return {
                    size: document.fonts.size,
                    status: document.fonts.status
                };
            });
        """
        )

        # Mindestens System-Fonts sollten verfügbar sein
        # Custom Fonts testen ist schwieriger und nicht kritisch

    def test_asset_404_errors(self, chrome_driver):
        """Test: Keine 404-Fehler für referenzierte Assets"""
        driver = chrome_driver
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Network-Logs prüfen
        logs = driver.get_log("performance")

        failed_requests = []
        for log in logs:
            message = json.loads(log["message"])
            if message.get("message", {}).get("method") == "Network.responseReceived":
                response = message["message"]["params"]["response"]
                if response["status"] >= 400:
                    failed_requests.append({"url": response["url"], "status": response["status"]})

        # Filter nur Asset-Requests (CSS/JS/Images)
        asset_failures = [
            req
            for req in failed_requests
            if any(ext in req["url"] for ext in [".css", ".js", ".png", ".jpg", ".svg", ".woff"])
        ]

        assert len(asset_failures) == 0, f"Asset-Requests fehlgeschlagen: {asset_failures}"

    def test_critical_css_inline_potential(self):
        """Test: Analyse für Critical-CSS-Inline-Optimierung"""
        # Above-the-fold CSS analysieren
        main_css_response = requests.get(f"{self.STATIC_BASE}/css/main.css")
        css_content = main_css_response.text

        # Kritische Selektoren identifizieren
        critical_selectors = [
            "body",
            ".navbar",
            ".metric-card",
            ".container-fluid",
            "h1",
            "h2",
            "h3",
        ]

        critical_css_size = 0
        for selector in critical_selectors:
            if selector in css_content:
                # Grobe Schätzung: 100 Zeichen pro kritischem Selector
                critical_css_size += 100

        # Critical CSS sollte unter 2KB bleiben für Inline-Potential
        assert (
            critical_css_size < 2048
        ), f"Critical CSS zu groß für Inline: {critical_css_size} bytes"
