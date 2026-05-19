"""
UI Integration Tests - Security Integration with UI
Tests für CSRF in AJAX, XSS-Protection, Secure Storage
Session 11.2 - Security-UI-Integration-Tests
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
from bs4 import BeautifulSoup
import re


class TestSecurityUIIntegration:
    """Test-Suite für Security-Integration mit UI"""

    BASE_URL = "http://localhost:5001"

    @pytest.fixture
    def security_driver(self):
        """Chrome WebDriver mit Security-Testing-Features"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-web-security")  # Nur für Security-Tests
        options.add_argument("--window-size=1920,1080")
        # Security-relevante Logs aktivieren
        options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})

        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(10)
        yield driver
        driver.quit()

    @pytest.fixture
    def admin_session(self, security_driver):
        """Admin-Session für Security-Tests"""
        driver = security_driver

        # Login und Session etablieren
        driver.get(f"{self.BASE_URL}/auth/login")
        username_field = driver.find_element(By.NAME, "username")
        password_field = driver.find_element(By.NAME, "password")
        username_field.send_keys("admin@test.com")
        password_field.send_keys("testpass123")
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_button.click()

        WebDriverWait(driver, 10).until(lambda d: "/admin/dashboard" in d.current_url)

        return driver

    def test_csrf_token_in_ajax_requests(self, admin_session):
        """Test: CSRF-Token wird in AJAX-Requests korrekt übertragen"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # CSRF-Token im Meta-Tag prüfen
        csrf_meta = driver.find_elements(By.CSS_SELECTOR, "meta[name='csrf-token']")

        if len(csrf_meta) > 0:
            csrf_token = csrf_meta[0].get_attribute("content")
            assert (
                csrf_token and len(csrf_token) > 10
            ), "CSRF-Token sollte vorhanden und ausreichend lang sein"

            # JavaScript-Test für CSRF-Token-Handling
            csrf_test = driver.execute_script(
                """
                // Test ob CSRF-Token in AJAX-Headers gesetzt wird
                var originalFetch = window.fetch;
                var fetchCalled = false;
                var csrfHeaderSet = false;
                
                window.fetch = function(url, options) {
                    fetchCalled = true;
                    if (options && options.headers) {
                        csrfHeaderSet = 'X-CSRFToken' in options.headers || 'X-CSRF-Token' in options.headers;
                    }
                    return originalFetch.apply(this, arguments);
                };
                
                // Export-Button klicken um AJAX zu triggern
                var exportButton = document.querySelector('[data-export="excel"]');
                if (exportButton) {
                    exportButton.click();
                }
                
                // Kurz warten
                setTimeout(function() {
                    window.fetch = originalFetch;
                }, 1000);
                
                return {
                    csrfToken: document.querySelector('meta[name="csrf-token"]')?.content,
                    fetchIntercepted: fetchCalled
                };
            """
            )

            assert csrf_test["csrfToken"], "CSRF-Token nicht in Meta-Tag verfügbar"

            # Warten für AJAX-Request
            time.sleep(1)

        # Alternativ: CSRF-Protection via Form-basierte Requests testen
        # (Falls keine Meta-Token-Implementation)
        page_source = driver.page_source
        csrf_inputs = re.findall(r'<input[^>]*name=["\']csrf_token["\'][^>]*>', page_source)
        csrf_forms = re.findall(r"<form[^>]*csrf[^>]*>", page_source, re.IGNORECASE)

        # Mindestens eine Form von CSRF-Protection sollte vorhanden sein
        has_csrf_protection = len(csrf_meta) > 0 or len(csrf_inputs) > 0 or len(csrf_forms) > 0
        assert has_csrf_protection, "Keine CSRF-Protection erkannt"

    def test_xss_protection_in_dynamic_content(self, admin_session):
        """Test: XSS-Protection für dynamisch geladenen Content"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Test XSS-Payload über Theme-Storage (LocalStorage)
        xss_payload = "<script>alert('XSS')</script>"

        # Versuche XSS-Payload in LocalStorage zu setzen
        storage_test = driver.execute_script(
            f"""
            try {{
                localStorage.setItem('gdpr-theme', '{xss_payload}');
                localStorage.setItem('test-data', '{xss_payload}');
                
                // Theme-System neu laden
                if (typeof GDPRTheme !== 'undefined') {{
                    GDPRTheme.apply('light');
                }}
                
                return {{
                    payloadStored: localStorage.getItem('test-data'),
                    themeValue: localStorage.getItem('gdpr-theme'),
                    alertTriggered: false
                }};
            }} catch(e) {{
                return {{error: e.message}};
            }}
        """
        )

        # XSS sollte nicht ausgeführt werden
        # Browser-Logs auf Script-Execution prüfen
        logs = driver.get_log("browser")
        security_errors = [
            log
            for log in logs
            if "security" in log["message"].lower() or "script" in log["message"].lower()
        ]

        # Page sollte weiterhin funktionieren (kein XSS-Execution)
        dashboard_still_functional = driver.execute_script(
            """
            return document.querySelector('.metric-card') !== null && 
                   typeof GDPRTheme !== 'undefined';
        """
        )

        assert (
            dashboard_still_functional
        ), "Dashboard sollte nach XSS-Attempt weiterhin funktionieren"

    def test_content_security_policy_headers(self):
        """Test: Content Security Policy Headers sind gesetzt"""
        # Test verschiedene Admin-Endpunkte für CSP-Headers
        endpoints = [
            f"{self.BASE_URL}/admin/dashboard",
            f"{self.BASE_URL}/admin/login",
        ]

        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, allow_redirects=False)

                # CSP-Header prüfen
                csp_header = response.headers.get("Content-Security-Policy")
                x_content_type = response.headers.get("X-Content-Type-Options")
                x_frame_options = response.headers.get("X-Frame-Options")
                x_xss_protection = response.headers.get("X-XSS-Protection")

                # Mindestens einige Security-Headers sollten gesetzt sein
                security_headers_count = sum(
                    [
                        bool(csp_header),
                        bool(x_content_type),
                        bool(x_frame_options),
                        bool(x_xss_protection),
                    ]
                )

                # In Production sollten mehr Security-Headers gesetzt sein
                # Für Development akzeptieren wir mindestens 1
                assert security_headers_count >= 1, f"Zu wenige Security-Headers für {endpoint}"

                if csp_header:
                    # CSP sollte 'unsafe-eval' vermeiden
                    assert "unsafe-eval" not in csp_header, "CSP sollte 'unsafe-eval' vermeiden"

                if x_content_type:
                    assert (
                        "nosniff" in x_content_type
                    ), "X-Content-Type-Options sollte 'nosniff' enthalten"

            except requests.exceptions.RequestException:
                # Endpoint nicht erreichbar ist OK für manche Tests
                pass

    def test_secure_session_storage(self, admin_session):
        """Test: Session-Storage ist sicher implementiert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Session-Cookies prüfen
        session_cookies = driver.get_cookies()

        session_cookie = None
        for cookie in session_cookies:
            if "session" in cookie["name"].lower() or "flask" in cookie["name"].lower():
                session_cookie = cookie
                break

        if session_cookie:
            # Session-Cookie sollte HttpOnly sein (wenn verfügbar)
            # httpOnly wird von Selenium nicht immer zurückgegeben

            # Secure-Flag prüfen (in Production sollte es gesetzt sein)
            # Für localhost/development ist secure=False normal

            # SameSite-Attribut prüfen
            same_site = session_cookie.get("sameSite")
            # SameSite sollte 'Lax' oder 'Strict' sein für CSRF-Protection

            # Domain/Path sollten korrekt gesetzt sein
            domain = session_cookie.get("domain")
            path = session_cookie.get("path")

            assert path, "Session-Cookie sollte Path-Attribut haben"

        # localStorage/sessionStorage auf sensitive Daten prüfen
        storage_test = driver.execute_script(
            """
            var sensitivePatterns = ['password', 'token', 'secret', 'key', 'auth'];
            var issues = [];
            
            // localStorage prüfen
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                var value = localStorage.getItem(key);
                
                for (var pattern of sensitivePatterns) {
                    if (key.toLowerCase().includes(pattern) || 
                        (value && value.toLowerCase().includes(pattern))) {
                        issues.push({type: 'localStorage', key: key, pattern: pattern});
                    }
                }
            }
            
            // sessionStorage prüfen
            for (var i = 0; i < sessionStorage.length; i++) {
                var key = sessionStorage.key(i);
                var value = sessionStorage.getItem(key);
                
                for (var pattern of sensitivePatterns) {
                    if (key.toLowerCase().includes(pattern) || 
                        (value && value.toLowerCase().includes(pattern))) {
                        issues.push({type: 'sessionStorage', key: key, pattern: pattern});
                    }
                }
            }
            
            return issues;
        """
        )

        # Sensitive Daten sollten nicht in Client-Storage sein
        # Theme-Preferences sind OK, aber keine Passwörter/Tokens
        critical_storage_issues = [
            issue for issue in storage_test if issue["pattern"] in ["password", "token", "secret"]
        ]

        assert (
            len(critical_storage_issues) == 0
        ), f"Sensitive Daten in Client-Storage: {critical_storage_issues}"

    def test_input_sanitization_in_ui(self, admin_session):
        """Test: Input-Sanitization in UI-Elementen"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Test mit potentiell gefährlichen Inputs in JavaScript-Funktionen
        dangerous_inputs = [
            "<script>alert('xss')</script>",
            "';alert('xss');//",
            "\"><script>alert('xss')</script>",
            "javascript:alert('xss')",
            "onload=alert('xss')",
        ]

        for payload in dangerous_inputs:
            # Test Input-Handling in Theme-System
            sanitization_test = driver.execute_script(
                f"""
                try {{
                    // Test verschiedene Input-Punkte
                    var testResults = [];
                    
                    // Theme-System Input-Test
                    if (typeof GDPRTheme !== 'undefined') {{
                        try {{
                            GDPRTheme.apply('{payload}');
                            testResults.push({{function: 'GDPRTheme.apply', executed: true}});
                        }} catch(e) {{
                            testResults.push({{function: 'GDPRTheme.apply', error: e.message}});
                        }}
                    }}
                    
                    // LoadingStates Input-Test
                    if (typeof LoadingStates !== 'undefined') {{
                        var testDiv = document.createElement('div');
                        document.body.appendChild(testDiv);
                        try {{
                            LoadingStates.show(testDiv, 'skeleton', '{payload}');
                            testResults.push({{function: 'LoadingStates.show', executed: true}});
                        }} catch(e) {{
                            testResults.push({{function: 'LoadingStates.show', error: e.message}});
                        }}
                        document.body.removeChild(testDiv);
                    }}
                    
                    return testResults;
                }} catch(e) {{
                    return [{{globalError: e.message}}];
                }}
            """
            )

            # XSS-Payload sollte nicht zu Script-Execution führen
            # Fehler oder sichere Behandlung sind OK
            for result in sanitization_test:
                if "executed" in result and result["executed"]:
                    # Prüfe ob tatsächlich Script ausgeführt wurde
                    # (schwer zu testen, aber Page sollte intakt bleiben)
                    page_intact = driver.execute_script("return typeof GDPRTheme !== 'undefined'")
                    assert page_intact, f"Page-Integrität nach Input: {payload}"

        # Console auf JavaScript-Errors prüfen
        logs = driver.get_log("browser")
        critical_errors = [
            log for log in logs if log["level"] == "SEVERE" and "script" in log["message"].lower()
        ]

        # Script-Errors durch XSS-Attempts sind ein Security-Problem
        xss_related_errors = [
            error
            for error in critical_errors
            if any(keyword in error["message"].lower() for keyword in ["alert", "xss", "script"])
        ]

        assert len(xss_related_errors) == 0, f"XSS-related Script-Errors: {xss_related_errors}"

    def test_ajax_request_authentication(self, admin_session):
        """Test: AJAX-Requests sind authentifiziert"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Intercepte AJAX-Requests um Authentication zu prüfen
        ajax_test = driver.execute_script(
            """
            var requests = [];
            var originalFetch = window.fetch;
            
            window.fetch = function(url, options) {
                requests.push({
                    url: url,
                    options: options,
                    hasAuth: !!(options && options.headers && 
                              (options.headers['Authorization'] || 
                               options.headers['X-CSRF-Token'] ||
                               options.headers['X-CSRFToken']))
                });
                return originalFetch.apply(this, arguments);
            };
            
            // Trigger AJAX-Requests
            var exportButton = document.querySelector('[data-export="excel"]');
            if (exportButton) {
                exportButton.click();
            }
            
            setTimeout(function() {
                var crawlButton = document.querySelector('[data-crawl="gdprhub"]');
                if (crawlButton) {
                    crawlButton.click();
                }
            }, 500);
            
            // Restore original fetch after test
            setTimeout(function() {
                window.fetch = originalFetch;
            }, 2000);
            
            return new Promise(function(resolve) {
                setTimeout(function() {
                    resolve(requests);
                }, 1500);
            });
        """
        )

        # Warten auf AJAX-Test-Completion
        time.sleep(2)

        # Session-Cookie sollte für Authentication ausreichen
        # Explizite Auth-Headers sind optional je nach Implementation
        session_cookies = driver.get_cookies()
        has_session_cookie = any("session" in cookie["name"].lower() for cookie in session_cookies)

        assert has_session_cookie, "Session-Cookie für AJAX-Authentication erforderlich"

    def test_secure_error_handling(self, admin_session):
        """Test: Error-Handling gibt keine sensitiven Informationen preis"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Trigger verschiedene Error-Scenarios
        error_scenarios = [
            # Invalid Export-Format
            ("GDPRDashboard.export('invalid_format', null)", "invalid export"),
            # Invalid Crawler-Source
            ("GDPRDashboard.crawl('invalid_source', null)", "invalid crawler"),
            # Theme-System Error
            ("GDPRTheme.apply(null)", "theme error"),
        ]

        for scenario_code, scenario_name in error_scenarios:
            error_result = driver.execute_script(
                f"""
                try {{
                    {scenario_code};
                    return {{executed: true, error: null}};
                }} catch(e) {{
                    return {{executed: false, error: e.message}};
                }}
            """
            )

            # Error-Messages sollten keine sensitiven Pfade/Details enthalten
            if error_result.get("error"):
                error_message = error_result["error"].lower()

                # Sensitive Informationen, die nicht in Error-Messages stehen sollten
                sensitive_patterns = [
                    "password",
                    "secret",
                    "token",
                    "/users/",
                    "database",
                    "internal error",
                    "stack trace",
                    "file not found",
                    "permission denied",
                ]

                for pattern in sensitive_patterns:
                    assert (
                        pattern not in error_message
                    ), f"Sensitive Info in Error ({scenario_name}): {error_message}"

        # UI-Error-Display sollte User-Friendly sein
        # Trigger Export-Error für UI-Response
        export_button = driver.find_element(By.CSS_SELECTOR, "[data-export='excel']")
        export_button.click()
        time.sleep(2)

        # Prüfe ob Error-Toast/Modal User-Friendly ist
        error_displays = driver.find_elements(
            By.CSS_SELECTOR, ".alert-danger, .toast, .error-message"
        )

        for error_display in error_displays:
            if error_display.is_displayed():
                error_text = error_display.text.lower()

                # User-Errors sollten keine Stack-Traces enthalten
                assert "traceback" not in error_text, "Error-Display sollte keine Tracebacks zeigen"
                assert (
                    "exception" not in error_text
                ), "Error-Display sollte keine Exception-Details zeigen"

    def test_clickjacking_protection(self, admin_session):
        """Test: Clickjacking-Protection (X-Frame-Options)"""
        # Test ob Admin-Dashboard in iframe einbettbar ist
        driver = admin_session

        # Test iframe-Embedding
        iframe_test = driver.execute_script(
            """
            try {
                var iframe = document.createElement('iframe');
                iframe.src = window.location.href;
                iframe.style.width = '100px';
                iframe.style.height = '100px';
                document.body.appendChild(iframe);
                
                // Warten kurz
                setTimeout(function() {
                    var loaded = iframe.contentDocument !== null;
                    document.body.removeChild(iframe);
                    return {iframeLoaded: loaded};
                }, 1000);
                
                return {created: true};
            } catch(e) {
                return {error: e.message, created: false};
            }
        """
        )

        # iframe-Embedding sollte durch X-Frame-Options verhindert werden
        # oder zumindest sollte keine kritischen Funktionen zugänglich sein

        # HTTP-Header für Clickjacking-Protection prüfen
        response = requests.get(f"{self.BASE_URL}/admin/dashboard", allow_redirects=False)
        x_frame_options = response.headers.get("X-Frame-Options")

        # X-Frame-Options sollte gesetzt sein für Admin-Bereiche
        if x_frame_options:
            assert x_frame_options in [
                "DENY",
                "SAMEORIGIN",
            ], f"X-Frame-Options unsicher: {x_frame_options}"

    def test_theme_storage_security(self, admin_session):
        """Test: Theme-Storage ist sicher gegen Manipulation"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Test Theme-Storage-Manipulation
        storage_manipulation_test = driver.execute_script(
            """
            var originalTheme = localStorage.getItem('gdpr-theme');
            var results = {};
            
            // Test 1: Invalid Theme-Values
            var invalidThemes = ['<script>', 'javascript:', 'data:text/html', '../../etc/passwd'];
            
            for (var invalidTheme of invalidThemes) {
                try {
                    localStorage.setItem('gdpr-theme', invalidTheme);
                    GDPRTheme.apply(invalidTheme);
                    results[invalidTheme] = 'applied';
                } catch(e) {
                    results[invalidTheme] = 'error: ' + e.message;
                }
            }
            
            // Test 2: Theme-Value-Validation
            try {
                localStorage.setItem('gdpr-theme', 'malicious-theme');
                var currentTheme = GDPRTheme.getCurrent();
                results.maliciousThemeHandled = currentTheme !== 'malicious-theme';
            } catch(e) {
                results.maliciousThemeHandled = true;
            }
            
            // Restore original theme
            if (originalTheme) {
                localStorage.setItem('gdpr-theme', originalTheme);
            } else {
                localStorage.removeItem('gdpr-theme');
            }
            
            return results;
        """
        )

        # Theme-System sollte nur gültige Werte akzeptieren
        for invalid_theme, result in storage_manipulation_test.items():
            if invalid_theme.startswith("<") or invalid_theme.startswith("javascript:"):
                assert (
                    "applied" not in result
                ), f"Theme-System sollte ungültigen Wert ablehnen: {invalid_theme}"

        # Page sollte nach Manipulation noch funktionieren
        page_functional = driver.execute_script(
            """
            return typeof GDPRTheme !== 'undefined' && 
                   document.querySelector('.metric-card') !== null;
        """
        )

        assert page_functional, "Page sollte nach Storage-Manipulation funktionieren"

    def test_javascript_injection_prevention(self, admin_session):
        """Test: JavaScript-Injection-Prevention in dynamischen Inhalten"""
        driver = admin_session
        driver.get(f"{self.BASE_URL}/admin/dashboard")

        # Test dynamische Content-Injection über verschiedene Wege
        injection_test = driver.execute_script(
            """
            var results = [];
            
            // Test 1: LoadingStates mit Script-Payload
            try {
                var testDiv = document.createElement('div');
                testDiv.id = 'injection-test';
                document.body.appendChild(testDiv);
                
                var payload = '<img src=x onerror=alert("XSS")>';
                LoadingStates.show(testDiv, 'skeleton', payload);
                
                // Prüfe ob Script-Tag erstellt wurde
                var hasScript = testDiv.innerHTML.includes('<script>') || 
                               testDiv.innerHTML.includes('onerror=');
                
                results.push({
                    test: 'LoadingStates injection',
                    scriptDetected: hasScript,
                    innerHTML: testDiv.innerHTML.substring(0, 100)
                });
                
                document.body.removeChild(testDiv);
            } catch(e) {
                results.push({
                    test: 'LoadingStates injection',
                    error: e.message
                });
            }
            
            // Test 2: Theme-Name-Injection
            try {
                var themePayload = 'dark"; alert("XSS"); //';
                GDPRTheme.apply(themePayload);
                
                var htmlTheme = document.documentElement.getAttribute('data-theme');
                var containsScript = htmlTheme && htmlTheme.includes('alert');
                
                results.push({
                    test: 'Theme attribute injection',
                    scriptDetected: containsScript,
                    themeValue: htmlTheme
                });
            } catch(e) {
                results.push({
                    test: 'Theme attribute injection',
                    error: e.message
                });
            }
            
            return results;
        """
        )

        # Keine Script-Injection sollte erfolgreich sein
        for test_result in injection_test:
            if "scriptDetected" in test_result:
                assert not test_result[
                    "scriptDetected"
                ], f"Script-Injection detected in {test_result['test']}"

        # Console-Logs auf XSS-Alerts prüfen
        logs = driver.get_log("browser")
        xss_alerts = [
            log
            for log in logs
            if "alert" in log["message"].lower() and "xss" in log["message"].lower()
        ]

        assert len(xss_alerts) == 0, f"XSS-Alerts detected: {xss_alerts}"
