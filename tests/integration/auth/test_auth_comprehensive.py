#!/usr/bin/env python3
"""
Comprehensive Authentication System Test
Tests kompletten Login/Logout Flow, Security Features, Admin Access
"""
import requests
import json
import time
from bs4 import BeautifulSoup

BASE_URL = "http://localhost:5001"


def extract_csrf_token(html_content):
    """Extract CSRF token from HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    csrf_input = soup.find("input", {"name": "csrf_token"})
    return csrf_input["value"] if csrf_input else None


def test_phase_2_core_authentication():
    """Phase 2: Core Authentication Tests"""
    print("🧪 Phase 2: Core Authentication Tests\n")
    results = []

    # Create fresh session for each test
    session = requests.Session()

    print("📋 Test 2.1: Login Page Load Test")
    try:
        response = session.get(f"{BASE_URL}/auth/login")
        csrf_token = extract_csrf_token(response.text)

        checks = []
        checks.append(("Page loads", response.status_code == 200))
        checks.append(("CSRF token present", csrf_token is not None))
        checks.append(
            ("German text present", "Anmeldung" in response.text or "Benutzername" in response.text)
        )
        checks.append(("Passwort vergessen link", "Passwort vergessen" in response.text))
        checks.append(("Bootstrap CSS", "bootstrap" in response.text.lower()))

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        results.extend(checks)
        print(f"   📊 CSRF Token: {csrf_token[:10] if csrf_token else 'None'}...")

    except Exception as e:
        print(f"   ❌ Login page test failed: {e}")
        results.append(("Login page accessible", False))

    print("\n📋 Test 2.2: Admin Login Flow Test")
    try:
        # Get fresh login page
        response = session.get(f"{BASE_URL}/auth/login")
        csrf_token = extract_csrf_token(response.text)

        # Submit login form
        login_data = {
            "username": "admin",
            "password": "admin123",
            "remember_me": "on",
            "csrf_token": csrf_token,
        }

        response = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)

        checks = []
        checks.append(("Login request successful", response.status_code == 200))
        checks.append(("Redirected to dashboard", "/admin/dashboard" in response.url))
        checks.append(
            (
                "Welcome message or dashboard",
                "Dashboard" in response.text or "Willkommen" in response.text,
            )
        )

        # Check if user is in navbar
        navbar_user = "admin" in response.text and "dropdown" in response.text.lower()
        checks.append(("User in navbar", navbar_user))

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        results.extend(checks)

        # Store session for later tests
        admin_session = session

    except Exception as e:
        print(f"   ❌ Admin login test failed: {e}")
        results.append(("Admin login successful", False))
        admin_session = None

    print("\n📋 Test 2.3: Failed Login Test")
    try:
        # New session for failed login test
        fail_session = requests.Session()
        response = fail_session.get(f"{BASE_URL}/auth/login")
        csrf_token = extract_csrf_token(response.text)

        # Submit with wrong credentials
        login_data = {"username": "admin", "password": "wrong-password", "csrf_token": csrf_token}

        response = fail_session.post(
            f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True
        )

        checks = []
        checks.append(("Failed login returns 200", response.status_code == 200))
        checks.append(("Still on login page", "/auth/login" in response.url))
        checks.append(
            ("Error message shown", "Ungültige" in response.text or "Fehler" in response.text)
        )

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        results.extend(checks)

    except Exception as e:
        print(f"   ❌ Failed login test error: {e}")
        results.append(("Failed login handled", False))

    print("\n📋 Test 2.4: Viewer Login Flow Test")
    try:
        # New session for viewer
        viewer_session = requests.Session()
        response = viewer_session.get(f"{BASE_URL}/auth/login")
        csrf_token = extract_csrf_token(response.text)

        # Login as viewer
        login_data = {"username": "viewer", "password": "viewer123", "csrf_token": csrf_token}

        response = viewer_session.post(
            f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True
        )

        checks = []
        checks.append(("Viewer login successful", response.status_code == 200))

        # Viewer should not have admin access - test by trying to access admin
        admin_response = viewer_session.get(f"{BASE_URL}/admin/dashboard", allow_redirects=False)
        checks.append(("Viewer blocked from admin", admin_response.status_code in [302, 403]))

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        results.extend(checks)

    except Exception as e:
        print(f"   ❌ Viewer login test failed: {e}")
        results.append(("Viewer login works", False))

    # Calculate success rate
    successful = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (successful / total * 100) if total > 0 else 0

    print(f"\n📊 Phase 2 Results: {successful}/{total} tests passed ({success_rate:.1f}%)")

    return results, admin_session


def test_phase_3_admin_protection():
    """Phase 3: Admin Dashboard Protection Tests"""
    print("\n🧪 Phase 3: Admin Dashboard Protection Tests\n")
    results = []

    print("📋 Test 3.1: Unauthorized Access Tests")
    try:
        # Test with no authentication
        unauth_session = requests.Session()

        endpoints = [
            ("/admin/dashboard", "Dashboard"),
            ("/admin/api/stats", "Stats API"),
            ("/admin/system", "System Info"),
        ]

        for endpoint, name in endpoints:
            response = unauth_session.get(f"{BASE_URL}{endpoint}", allow_redirects=False)
            blocked = response.status_code in [302, 401, 403]
            print(f"   {'✅' if blocked else '❌'} {name} blocked: {response.status_code}")
            results.append((f"{name} protected", blocked))

    except Exception as e:
        print(f"   ❌ Unauthorized access test failed: {e}")
        results.append(("Unauthorized access blocked", False))

    print("\n📋 Test 3.2: Authorized Admin Access")
    try:
        # Get admin session by logging in
        admin_session = requests.Session()
        response = admin_session.get(f"{BASE_URL}/auth/login")
        csrf_token = extract_csrf_token(response.text)

        login_data = {"username": "admin", "password": "admin123", "csrf_token": csrf_token}

        admin_session.post(f"{BASE_URL}/auth/login", data=login_data)

        # Test admin endpoints
        endpoints = [("/admin/dashboard", "Dashboard page"), ("/admin/api/stats", "Stats API")]

        for endpoint, name in endpoints:
            response = admin_session.get(f"{BASE_URL}{endpoint}")
            success = response.status_code == 200
            print(f"   {'✅' if success else '❌'} {name} accessible: {response.status_code}")
            results.append((f"Admin {name} works", success))

    except Exception as e:
        print(f"   ❌ Admin access test failed: {e}")
        results.append(("Admin access works", False))

    # Calculate success rate
    successful = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (successful / total * 100) if total > 0 else 0

    print(f"\n📊 Phase 3 Results: {successful}/{total} tests passed ({success_rate:.1f}%)")

    return results


def test_security_headers():
    """Test Security Headers"""
    print("\n🧪 Security Headers Test")
    results = []

    try:
        response = requests.get(f"{BASE_URL}/")
        headers = response.headers

        security_checks = [
            ("X-Content-Type-Options", "X-Content-Type-Options" in headers),
            ("X-Frame-Options", "X-Frame-Options" in headers),
            ("X-XSS-Protection", "X-XSS-Protection" in headers),
            ("Content-Security-Policy", "Content-Security-Policy" in headers),
        ]

        for header, present in security_checks:
            print(f"   {'✅' if present else '❌'} {header}: {'Present' if present else 'Missing'}")
            results.append((f"Security header {header}", present))

    except Exception as e:
        print(f"   ❌ Security headers test failed: {e}")
        results.append(("Security headers present", False))

    return results


def run_comprehensive_test():
    """Run all authentication tests"""
    print("🚀 Datenschutz-Rechtsprechung API Authentication System - Comprehensive Test\n")

    all_results = []

    # Phase 2: Core Authentication
    phase2_results, admin_session = test_phase_2_core_authentication()
    all_results.extend(phase2_results)

    # Phase 3: Admin Protection
    phase3_results = test_phase_3_admin_protection()
    all_results.extend(phase3_results)

    # Security Headers
    security_results = test_security_headers()
    all_results.extend(security_results)

    # Final Results
    total_successful = sum(1 for _, result in all_results if result)
    total_tests = len(all_results)
    overall_success_rate = (total_successful / total_tests * 100) if total_tests > 0 else 0

    print(f"\n🎯 COMPREHENSIVE TEST RESULTS")
    print(f"📊 Overall: {total_successful}/{total_tests} tests passed ({overall_success_rate:.1f}%)")

    if overall_success_rate >= 90:
        print("🎉 EXCELLENT: Authentication system working very well!")
    elif overall_success_rate >= 75:
        print("✅ GOOD: Authentication system mostly working")
    elif overall_success_rate >= 50:
        print("⚠️ NEEDS WORK: Several issues found")
    else:
        print("❌ CRITICAL: Major authentication issues")

    # List failures
    failures = [test for test, result in all_results if not result]
    if failures:
        print(f"\n❌ Failed tests ({len(failures)}):")
        for i, failure in enumerate(failures, 1):
            print(f"   {i}. {failure}")

    return overall_success_rate >= 75


if __name__ == "__main__":
    success = run_comprehensive_test()
    exit(0 if success else 1)
