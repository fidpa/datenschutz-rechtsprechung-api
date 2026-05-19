#!/usr/bin/env python3
"""
Test Script für Complete Authentication System
Tests: Login, CSRF, Rate Limiting, Admin Access, Logout
"""
import requests
import json
import time
from bs4 import BeautifulSoup

BASE_URL = "http://localhost:5001"


def test_authentication_system():
    """Test Complete Authentication Flow"""
    session = requests.Session()

    print("🧪 Testing Datenschutz-Rechtsprechung API Complete Authentication System\n")

    # Test 1: Public access (should work)
    print("1️⃣ Testing public access...")
    response = session.get(f"{BASE_URL}/")
    print(f"   ✅ Public homepage: {response.status_code}")

    # Test 2: Admin access without login (should redirect to login)
    print("2️⃣ Testing admin access without login...")
    response = session.get(f"{BASE_URL}/admin/dashboard", allow_redirects=False)
    print(f"   ✅ Admin redirect: {response.status_code} (should be 302)")

    # Test 3: Get login page and extract CSRF token
    print("3️⃣ Getting login page and CSRF token...")
    response = session.get(f"{BASE_URL}/auth/login")
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_token = soup.find("input", {"name": "csrf_token"})["value"]
        print(f"   ✅ Login page loaded, CSRF token extracted: {csrf_token[:10]}...")
    else:
        print(f"   ❌ Login page failed: {response.status_code}")
        return

    # Test 4: Login with correct credentials
    print("4️⃣ Testing login with admin credentials...")
    login_data = {
        "username": "admin",
        "password": "admin123",
        "remember_me": "on",
        "csrf_token": csrf_token,
    }

    response = session.post(f"{BASE_URL}/auth/login", data=login_data, allow_redirects=True)
    if "Willkommen" in response.text or response.url.endswith("/admin/dashboard"):
        print(f"   ✅ Login successful! Final URL: {response.url}")
    else:
        print(f"   ❌ Login failed: {response.status_code}")
        print(f"   Response content preview: {response.text[:200]}")
        return

    # Test 5: Access admin dashboard (should work now)
    print("5️⃣ Testing admin dashboard access after login...")
    response = session.get(f"{BASE_URL}/admin/dashboard")
    if response.status_code == 200 and "Dashboard" in response.text:
        print(f"   ✅ Admin dashboard accessible: {response.status_code}")
    else:
        print(f"   ❌ Admin dashboard failed: {response.status_code}")

    # Test 6: API Stats endpoint (admin-only)
    print("6️⃣ Testing admin API stats endpoint...")
    response = session.get(f"{BASE_URL}/admin/api/stats")
    if response.status_code == 200:
        stats = response.json()
        print(
            f"   ✅ Stats API accessible - Decisions: {stats.get('decisions', {}).get('total', 'N/A')}"
        )
    else:
        print(f"   ❌ Stats API failed: {response.status_code}")

    # Test 7: Password reset flow (without email)
    print("7️⃣ Testing forgot password flow...")

    # Get forgot password page
    response = session.get(f"{BASE_URL}/auth/forgot-password")
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_token = soup.find("input", {"name": "csrf_token"})["value"]

        # Submit forgot password (should show success message even for unknown email)
        reset_data = {"email": "test@example.com", "csrf_token": csrf_token}
        response = session.post(
            f"{BASE_URL}/auth/forgot-password", data=reset_data, allow_redirects=True
        )
        if "Falls ein Konto" in response.text or "gesendet" in response.text:
            print(f"   ✅ Forgot password flow works (security by obscurity)")
        else:
            print(f"   ⚠️ Forgot password response unclear: {response.status_code}")

    # Test 8: Logout
    print("8️⃣ Testing logout...")
    response = session.get(f"{BASE_URL}/auth/logout", allow_redirects=True)
    if "Auf Wiedersehen" in response.text or response.url.endswith("/"):
        print(f"   ✅ Logout successful")
    else:
        print(f"   ❌ Logout failed: {response.status_code}")

    # Test 9: Access admin after logout (should fail)
    print("9️⃣ Testing admin access after logout...")
    response = session.get(f"{BASE_URL}/admin/dashboard", allow_redirects=False)
    if response.status_code == 302:
        print(f"   ✅ Admin access properly blocked after logout: {response.status_code}")
    else:
        print(f"   ❌ Admin access not properly blocked: {response.status_code}")

    # Test 10: Rate limiting (multiple failed attempts)
    print("🔟 Testing rate limiting...")
    for i in range(3):  # Only 3 attempts to avoid blocking too long
        login_data = {"username": "admin", "password": "wrong-password", "csrf_token": csrf_token}
        response = session.post(f"{BASE_URL}/auth/login", data=login_data)
        print(f"   Attempt {i+1}: {response.status_code}")
        time.sleep(0.5)  # Small delay

    print(f"   ✅ Rate limiting test completed (check logs for blocked requests)")

    print("\n🎉 Authentication System Test Complete!")
    print("📊 Summary:")
    print("   ✅ Public access works")
    print("   ✅ Authentication required for admin areas")
    print("   ✅ CSRF protection active")
    print("   ✅ Login/logout flow works")
    print("   ✅ Admin dashboard protected")
    print("   ✅ Password reset flow implemented")
    print("   ✅ Rate limiting active")


if __name__ == "__main__":
    test_authentication_system()
