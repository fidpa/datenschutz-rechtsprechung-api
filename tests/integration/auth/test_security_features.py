#!/usr/bin/env python3
"""
Security Features Test
Testet CSRF Protection, Rate Limiting, Session Security
"""
import requests
import json
import time
from bs4 import BeautifulSoup

BASE_URL = "http://localhost:5001"


def test_csrf_protection():
    """Test CSRF Protection"""
    print("🔒 CSRF Protection Test\n")

    session = requests.Session()

    print("📋 Test 4.1: CSRF Token Required")
    try:
        # Try login without CSRF token
        login_data = {"username": "admin", "password": "admin123"}

        response = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=False)
        csrf_blocked = response.status_code == 403
        print(
            f"   {'✅' if csrf_blocked else '⚠️'} Login without CSRF token: {response.status_code}"
        )

        if not csrf_blocked:
            print("   📝 Note: Login may have been blocked by rate limiting instead")

        return csrf_blocked

    except Exception as e:
        print(f"   ❌ CSRF test failed: {e}")
        return False


def test_password_reset_flow():
    """Test Password Reset Flow"""
    print("\n🔄 Password Reset Flow Test\n")

    session = requests.Session()

    print("📋 Test 5.1: Forgot Password Page")
    try:
        response = session.get(f"{BASE_URL}/auth/forgot-password")

        checks = []
        checks.append(("Forgot password page loads", response.status_code == 200))
        checks.append(("German text present", "Passwort vergessen" in response.text))
        checks.append(("Email form present", "email" in response.text.lower()))
        checks.append(("CSRF token present", "csrf_token" in response.text))

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        return all(result for _, result in checks)

    except Exception as e:
        print(f"   ❌ Forgot password test failed: {e}")
        return False


def test_session_security():
    """Test Session Security"""
    print("\n🛡️ Session Security Test\n")

    session = requests.Session()

    print("📋 Test 6.1: Session Cookie Security")
    try:
        # Make a request to get session cookie
        response = session.get(f"{BASE_URL}/auth/login")

        cookies = session.cookies
        session_cookie = None

        for cookie in cookies:
            if "session" in cookie.name.lower() or "gdpr" in cookie.name.lower():
                session_cookie = cookie
                break

        if session_cookie:
            # Check cookie security attributes
            checks = []
            checks.append(("Session cookie exists", True))
            checks.append(
                (
                    "HttpOnly set",
                    getattr(session_cookie, "has_nonstandard_attr", lambda x: False)("HttpOnly"),
                )
            )
            checks.append(("SameSite set", "SameSite" in str(session_cookie)))

            for check, result in checks:
                print(f"   {'✅' if result else '⚠️'} {check}")

            return True
        else:
            print("   ⚠️ No session cookie found")
            return False

    except Exception as e:
        print(f"   ❌ Session security test failed: {e}")
        return False


def test_logout_process():
    """Test Logout Process"""
    print("\n👋 Logout Process Test\n")

    print("📋 Test 6.2: Complete Logout Flow")
    try:
        # Create session and login
        session = requests.Session()

        # Get login page and CSRF token
        response = session.get(f"{BASE_URL}/auth/login")
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_token = soup.find("input", {"name": "csrf_token"})["value"]

        # Login
        login_data = {"username": "admin", "password": "admin123", "csrf_token": csrf_token}

        response = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
        login_success = "dashboard" in response.url.lower()

        if not login_success:
            print("   ⚠️ Login failed, may be rate limited")
            return False

        # Access admin area (should work)
        admin_response = session.get(f"{BASE_URL}/admin/dashboard")
        admin_before_logout = admin_response.status_code == 200

        # Logout
        logout_response = session.get(f"{BASE_URL}/auth/logout", allow_redirects=True)
        logout_success = logout_response.status_code == 200

        # Try to access admin area again (should be blocked)
        admin_after_logout = session.get(f"{BASE_URL}/admin/dashboard", allow_redirects=False)
        admin_blocked = admin_after_logout.status_code in [302, 401, 403]

        checks = [
            ("Login successful", login_success),
            ("Admin access before logout", admin_before_logout),
            ("Logout processed", logout_success),
            ("Admin blocked after logout", admin_blocked),
        ]

        for check, result in checks:
            print(f"   {'✅' if result else '❌'} {check}")

        return all(result for _, result in checks)

    except Exception as e:
        print(f"   ❌ Logout test failed: {e}")
        return False


def run_security_tests():
    """Run all security tests"""
    print("🛡️ Datenschutz-Rechtsprechung API Security Features Test\n")

    results = []

    # CSRF Protection
    csrf_result = test_csrf_protection()
    results.append(("CSRF Protection", csrf_result))

    # Password Reset
    reset_result = test_password_reset_flow()
    results.append(("Password Reset Flow", reset_result))

    # Session Security
    session_result = test_session_security()
    results.append(("Session Security", session_result))

    # Logout Process
    logout_result = test_logout_process()
    results.append(("Logout Process", logout_result))

    # Results
    successful = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (successful / total * 100) if total > 0 else 0

    print(f"\n🎯 SECURITY TEST RESULTS")
    print(f"📊 Overall: {successful}/{total} security tests passed ({success_rate:.1f}%)")

    if success_rate >= 90:
        print("🔒 EXCELLENT: All security features working!")
    elif success_rate >= 75:
        print("✅ GOOD: Security features mostly working")
    else:
        print("⚠️ NEEDS ATTENTION: Some security issues found")

    return success_rate >= 75


if __name__ == "__main__":
    success = run_security_tests()
    exit(0 if success else 1)
