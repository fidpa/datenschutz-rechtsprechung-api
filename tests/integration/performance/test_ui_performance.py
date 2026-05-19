"""
Performance Tests - UI Performance & Optimization
Tests für Frontend-Performance, Bundle-Größen, Load-Times
Session 11.2 - Performance-Tests
"""

import pytest
import requests
import time
import json
import gzip
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains


class TestUIPerformance:
    """Test-Suite für UI-Performance und Optimierung"""

    BASE_URL = "http://localhost:5001"
    STATIC_BASE = f"{BASE_URL}/static"

    @pytest.fixture
    def performance_driver(self):
        """Chrome WebDriver mit Performance-Monitoring"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--enable-logging")
        options.add_argument("--log-level=0")

        # Performance-Logging aktivieren
        options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})

        # Performance-Features aktivieren
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, performance_driver):
        """Admin-Session für Performance-Tests"""
        driver = performance_driver

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

    def test_dashboard_initial_load_performance(self, admin_session):
        """Test: Dashboard Initial-Load-Performance"""
        driver = admin_session

        # Performance-Timing messen
        start_time = time.time()
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis kritische Elemente geladen
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState === 'complete'")
        )

        end_time = time.time()
        total_load_time = (end_time - start_time) * 1000

        # Performance-Ziel: < 2 Sekunden für Dashboard-Load
        assert (
            total_load_time < 2000
        ), f"Dashboard-Load zu langsam: {total_load_time:.2f}ms (Ziel: < 2000ms)"

        # Performance-API für detaillierte Metriken
        performance_metrics = driver.execute_script(
            """
            return {
                domContentLoaded: performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart,
                loadComplete: performance.timing.loadEventEnd - performance.timing.navigationStart,
                firstPaint: performance.getEntriesByType('paint')[0]?.startTime,
                resourceCount: performance.getEntriesByType('resource').length
            };
        """
        )

        assert (
            performance_metrics["domContentLoaded"] < 1500
        ), f"DOM-Load zu langsam: {performance_metrics['domContentLoaded']}ms"
        assert (
            performance_metrics["resourceCount"] < 50
        ), f"Zu viele Resources: {performance_metrics['resourceCount']}"

    def test_theme_switch_performance(self, admin_session):
        """Test: Theme-Switch-Performance unter 100ms"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis Theme-System geladen
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return typeof GDPRTheme !== 'undefined'")
        )

        theme_toggle = driver.find_element(By.ID, "themeToggle")

        # Theme-Switch-Performance messen
        switch_times = []

        for i in range(5):  # 5 Messungen für Durchschnitt
            start_time = time.time()
            theme_toggle.click()

            # Warten bis Theme-Attribut geändert
            if i % 2 == 0:  # Dark Mode
                WebDriverWait(driver, 2).until(
                    lambda d: d.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
                    == "dark"
                )
            else:  # Light Mode
                WebDriverWait(driver, 2).until(
                    lambda d: d.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
                    != "dark"
                )

            end_time = time.time()
            switch_duration = (end_time - start_time) * 1000
            switch_times.append(switch_duration)

            time.sleep(0.1)  # Kurze Pause zwischen Tests

        avg_switch_time = sum(switch_times) / len(switch_times)
        max_switch_time = max(switch_times)

        assert (
            avg_switch_time < 100
        ), f"Durchschnittliche Theme-Switch-Zeit zu langsam: {avg_switch_time:.2f}ms"
        assert (
            max_switch_time < 150
        ), f"Langsamster Theme-Switch zu langsam: {max_switch_time:.2f}ms"

    def test_css_load_performance(self, performance_driver):
        """Test: CSS-Load-Performance und Render-Blocking"""
        driver = performance_driver

        # Dashboard laden mit Performance-Monitoring
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )

        # CSS-Resource-Timings analysieren
        css_performance = driver.execute_script(
            """
            var cssResources = performance.getEntriesByType('resource')
                .filter(r => r.name.includes('.css'));
            
            var totalCssLoadTime = 0;
            var slowestCss = 0;
            var cssCount = 0;
            
            cssResources.forEach(resource => {
                var loadTime = resource.responseEnd - resource.requestStart;
                totalCssLoadTime += loadTime;
                slowestCss = Math.max(slowestCss, loadTime);
                cssCount++;
            });
            
            return {
                totalLoadTime: totalCssLoadTime,
                slowestCss: slowestCss,
                cssCount: cssCount,
                avgLoadTime: cssCount > 0 ? totalCssLoadTime / cssCount : 0
            };
        """
        )

        assert (
            css_performance["slowestCss"] < 500
        ), f"Langsamstes CSS-File: {css_performance['slowestCss']:.2f}ms (Ziel: < 500ms)"
        assert (
            css_performance["avgLoadTime"] < 200
        ), f"Durchschnittliche CSS-Load-Zeit: {css_performance['avgLoadTime']:.2f}ms (Ziel: < 200ms)"
        assert (
            css_performance["cssCount"] < 10
        ), f"Zu viele CSS-Requests: {css_performance['cssCount']} (Ziel: < 10)"

    def test_javascript_execution_performance(self, admin_session):
        """Test: JavaScript-Execution-Performance"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Warten bis alle JS-Module geladen
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script(
                "return typeof GDPRTheme !== 'undefined' && typeof GDPRDashboard !== 'undefined'"
            )
        )

        # JavaScript-Performance-Tests
        js_performance = driver.execute_script(
            """
            var results = {};
            
            // Theme-Switch-Performance
            var start = performance.now();
            for (var i = 0; i < 10; i++) {
                GDPRTheme.apply(i % 2 === 0 ? 'dark' : 'light');
            }
            results.themeSwitchTime = performance.now() - start;
            
            // Dashboard-Refresh-Performance
            start = performance.now();
            for (var i = 0; i < 5; i++) {
                GDPRDashboard.refresh();
            }
            results.dashboardRefreshTime = performance.now() - start;
            
            // LoadingStates-Performance
            start = performance.now();
            var testDiv = document.createElement('div');
            document.body.appendChild(testDiv);
            for (var i = 0; i < 20; i++) {
                LoadingStates.show(testDiv, 'skeleton');
                LoadingStates.hide(testDiv);
            }
            document.body.removeChild(testDiv);
            results.loadingStatesTime = performance.now() - start;
            
            return results;
        """
        )

        # Performance-Ziele
        assert (
            js_performance["themeSwitchTime"] < 50
        ), f"Theme-Switch zu langsam: {js_performance['themeSwitchTime']:.2f}ms"
        assert (
            js_performance["dashboardRefreshTime"] < 100
        ), f"Dashboard-Refresh zu langsam: {js_performance['dashboardRefreshTime']:.2f}ms"
        assert (
            js_performance["loadingStatesTime"] < 200
        ), f"LoadingStates zu langsam: {js_performance['loadingStatesTime']:.2f}ms"

    def test_ajax_request_performance(self, admin_session):
        """Test: AJAX-Request-Performance für Dashboard-Actions"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Excel-Export AJAX-Performance
        excel_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-export='excel']"))
        )

        start_time = time.time()
        excel_button.click()

        # Warten auf AJAX-Response (durch Network-Logs)
        max_wait = 5  # 5 Sekunden max
        elapsed = 0
        ajax_completed = False

        while elapsed < max_wait and not ajax_completed:
            time.sleep(0.1)
            elapsed = time.time() - start_time

            # Check ob Button wieder enabled ist (sign of completion)
            if not excel_button.get_attribute("disabled"):
                ajax_completed = True

        ajax_time = elapsed * 1000

        # AJAX sollte unter 3 Sekunden sein
        assert ajax_time < 3000, f"Excel-Export AJAX zu langsam: {ajax_time:.2f}ms"

        # Crawler-Start AJAX testen
        gdprhub_button = driver.find_element(By.CSS_SELECTOR, "[data-crawl='gdprhub']")

        start_time = time.time()
        gdprhub_button.click()
        time.sleep(1)  # Pause für AJAX
        crawler_ajax_time = (time.time() - start_time) * 1000

        assert crawler_ajax_time < 2000, f"Crawler-Start AJAX zu langsam: {crawler_ajax_time:.2f}ms"

    def test_memory_usage_optimization(self, admin_session):
        """Test: Memory-Usage bleibt optimiert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Initial Memory-Usage
        initial_memory = driver.execute_script(
            """
            if (performance.memory) {
                return {
                    used: performance.memory.usedJSHeapSize,
                    total: performance.memory.totalJSHeapSize,
                    limit: performance.memory.jsHeapSizeLimit
                };
            }
            return null;
        """
        )

        if initial_memory:
            # Mehrere Theme-Switches und Dashboard-Refreshes
            for i in range(10):
                theme_toggle = driver.find_element(By.ID, "themeToggle")
                theme_toggle.click()
                time.sleep(0.1)

                if i % 3 == 0:  # Alle 3 Iterationen Dashboard refresh
                    driver.execute_script("GDPRDashboard.refresh()")
                    time.sleep(0.2)

            # Memory nach Operationen
            final_memory = driver.execute_script(
                """
                if (performance.memory) {
                    return {
                        used: performance.memory.usedJSHeapSize,
                        total: performance.memory.totalJSHeapSize,
                        limit: performance.memory.jsHeapSizeLimit
                    };
                }
                return null;
            """
            )

            if final_memory:
                memory_increase = final_memory["used"] - initial_memory["used"]
                memory_increase_mb = memory_increase / (1024 * 1024)

                # Memory-Increase sollte unter 10MB bleiben
                assert memory_increase_mb < 10, f"Memory-Usage zu hoch: +{memory_increase_mb:.2f}MB"

                # Total Memory sollte unter 50MB bleiben
                total_memory_mb = final_memory["used"] / (1024 * 1024)
                assert total_memory_mb < 50, f"Total Memory-Usage zu hoch: {total_memory_mb:.2f}MB"

    def test_bundle_size_performance(self):
        """Test: Asset-Bundle-Größen sind performant"""
        # CSS-Bundle-Größe testen
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

        css_size_kb = total_css_size / 1024
        assert css_size_kb < 50, f"CSS-Bundle zu groß: {css_size_kb:.1f}KB (Ziel: < 50KB)"

        # JavaScript-Bundle-Größe testen
        js_files = [
            "js/theme.js",
            "js/admin-modules/admin-dashboard.js",
            "js/shared/loading-states.js",
        ]

        total_js_size = 0
        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            total_js_size += len(response.content)

        js_size_kb = total_js_size / 1024
        assert js_size_kb < 30, f"JS-Bundle zu groß: {js_size_kb:.1f}KB (Ziel: < 30KB)"

        # Gzip-Compression-Ratio testen
        combined_content = ""
        for css_file in css_files:
            response = requests.get(f"{self.STATIC_BASE}/{css_file}")
            combined_content += response.text

        for js_file in js_files:
            response = requests.get(f"{self.STATIC_BASE}/{js_file}")
            combined_content += response.text

        original_size = len(combined_content.encode("utf-8"))
        gzipped_size = len(gzip.compress(combined_content.encode("utf-8")))
        compression_ratio = gzipped_size / original_size

        assert (
            compression_ratio < 0.4
        ), f"Schlechte Compression-Ratio: {compression_ratio:.2f} (Ziel: < 0.4)"

    def test_render_performance_metrics(self, admin_session):
        """Test: Render-Performance-Metriken"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "metric-card"))
        )

        # Paint-Timing-Metriken
        paint_metrics = driver.execute_script(
            """
            var paintEntries = performance.getEntriesByType('paint');
            var result = {};
            
            paintEntries.forEach(function(entry) {
                result[entry.name] = entry.startTime;
            });
            
            // Layout-Shift-Score (wenn verfügbar)
            var layoutShiftEntries = performance.getEntriesByType('layout-shift');
            var totalScore = 0;
            layoutShiftEntries.forEach(function(entry) {
                totalScore += entry.value;
            });
            result.cumulativeLayoutShift = totalScore;
            
            return result;
        """
        )

        if "first-paint" in paint_metrics:
            assert (
                paint_metrics["first-paint"] < 1000
            ), f"First Paint zu langsam: {paint_metrics['first-paint']:.2f}ms"

        if "first-contentful-paint" in paint_metrics:
            assert (
                paint_metrics["first-contentful-paint"] < 1500
            ), f"FCP zu langsam: {paint_metrics['first-contentful-paint']:.2f}ms"

        # Cumulative Layout Shift sollte minimal sein
        if "cumulativeLayoutShift" in paint_metrics:
            assert (
                paint_metrics["cumulativeLayoutShift"] < 0.1
            ), f"CLS zu hoch: {paint_metrics['cumulativeLayoutShift']}"

    def test_responsive_performance(self, admin_session):
        """Test: Responsive-Layout-Performance"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Verschiedene Viewport-Größen testen
        viewport_sizes = [
            (1920, 1080),  # Desktop
            (1024, 768),  # Tablet
            (375, 667),  # Mobile
        ]

        resize_times = []

        for width, height in viewport_sizes:
            start_time = time.time()
            driver.set_window_size(width, height)

            # Warten bis Layout stabil
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return document.readyState === 'complete'")
            )
            time.sleep(0.2)  # Additional settling time

            end_time = time.time()
            resize_time = (end_time - start_time) * 1000
            resize_times.append(resize_time)

        avg_resize_time = sum(resize_times) / len(resize_times)
        max_resize_time = max(resize_times)

        assert (
            avg_resize_time < 500
        ), f"Durchschnittliche Resize-Zeit zu langsam: {avg_resize_time:.2f}ms"
        assert max_resize_time < 1000, f"Langsamste Resize-Zeit zu langsam: {max_resize_time:.2f}ms"

    def test_animation_performance(self, admin_session):
        """Test: CSS-Animation-Performance"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Hover-Animations auf Metric Cards testen
        metric_cards = driver.find_elements(By.CLASS_NAME, "metric-card")

        if len(metric_cards) > 0:
            card = metric_cards[0]

            # Hover-Animation triggern und Performance messen
            animation_performance = driver.execute_script(
                """
                var card = arguments[0];
                var start = performance.now();
                
                // Hover-Event simulieren
                var event = new MouseEvent('mouseenter', {bubbles: true});
                card.dispatchEvent(event);
                
                // Kurz warten für Animation
                setTimeout(function() {
                    var event2 = new MouseEvent('mouseleave', {bubbles: true});
                    card.dispatchEvent(event2);
                }, 100);
                
                var end = performance.now();
                return end - start;
            """,
                card,
            )

            assert (
                animation_performance < 50
            ), f"Animation-Performance zu langsam: {animation_performance:.2f}ms"

    def test_concurrent_users_simulation(self, admin_session):
        """Test: Performance bei simulierter Multi-User-Last"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Simuliere schnelle aufeinanderfolgende Aktionen (wie bei mehreren Usern)
        start_time = time.time()

        for i in range(20):  # 20 schnelle Aktionen
            if i % 4 == 0:
                # Theme toggle
                theme_toggle = driver.find_element(By.ID, "themeToggle")
                theme_toggle.click()
            elif i % 4 == 1:
                # Dashboard refresh
                driver.execute_script("GDPRDashboard.refresh()")
            elif i % 4 == 2:
                # Export-Button klick
                excel_button = driver.find_element(By.CSS_SELECTOR, "[data-export='excel']")
                excel_button.click()
            else:
                # Crawler-Button klick
                gdprhub_button = driver.find_element(By.CSS_SELECTOR, "[data-crawl='gdprhub']")
                gdprhub_button.click()

            time.sleep(0.05)  # 50ms zwischen Aktionen

        end_time = time.time()
        total_time = (end_time - start_time) * 1000

        # Alle 20 Aktionen sollten unter 5 Sekunden abgeschlossen sein
        assert total_time < 5000, f"Multi-User-Simulation zu langsam: {total_time:.2f}ms"

        # UI sollte weiterhin responsive sein
        dashboard_responsive = driver.execute_script(
            """
            return document.readyState === 'complete' && 
                   typeof GDPRTheme !== 'undefined' && 
                   typeof GDPRDashboard !== 'undefined';
        """
        )

        assert dashboard_responsive, "Dashboard nicht mehr responsive nach Multi-User-Simulation"
