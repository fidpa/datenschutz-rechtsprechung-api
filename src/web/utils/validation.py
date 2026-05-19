"""
Form Validation Helper
Pragmatische Validierung ohne WTForms
"""
import re
from markupsafe import escape
from typing import List


def validate_login_form(username: str, password: str) -> List[str]:
    """Validate login form data"""
    errors = []

    if not username or len(username.strip()) < 3:
        errors.append("Benutzername muss mindestens 3 Zeichen lang sein")

    if not password or len(password) < 3:  # Relaxed für Demo
        errors.append("Passwort muss mindestens 3 Zeichen lang sein")

    return errors


def validate_forgot_password_form(email: str) -> List[str]:
    """Validate forgot password form"""
    errors = []

    if not email or not email.strip():
        errors.append("E-Mail-Adresse ist erforderlich")
    elif not validate_email(email):
        errors.append("Bitte geben Sie eine gültige E-Mail-Adresse ein")

    return errors


def validate_reset_password_form(password: str, password_confirm: str) -> List[str]:
    """Validate reset password form"""
    errors = []

    if not password or len(password) < 8:
        errors.append("Passwort muss mindestens 8 Zeichen lang sein")

    if not password_confirm:
        errors.append("Passwort-Bestätigung ist erforderlich")

    if password and password_confirm and password != password_confirm:
        errors.append("Passwörter stimmen nicht überein")

    if password and not validate_password_strength(password):
        errors.extend(
            [
                "Das Passwort erfüllt nicht die Sicherheitsanforderungen:",
                "• Mindestens 8 Zeichen",
                "• Groß- und Kleinbuchstaben",
                "• Mindestens eine Ziffer",
                "• Mindestens ein Sonderzeichen",
            ]
        )

    return errors


def validate_email(email: str) -> bool:
    """Simple email validation"""
    if not email:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_password_strength(password: str) -> bool:
    """Validate password meets security requirements"""
    if len(password) < 8:
        return False

    # At least one uppercase letter
    if not re.search(r"[A-Z]", password):
        return False

    # At least one lowercase letter
    if not re.search(r"[a-z]", password):
        return False

    # At least one digit
    if not re.search(r"\d", password):
        return False

    # At least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=]', password):
        return False

    return True


def sanitize_input(text: str) -> str:
    """Sanitize user input"""
    if not text:
        return ""
    # Remove leading/trailing whitespace
    text = text.strip()
    # Escape HTML
    return escape(text)


def validate_username(username: str) -> List[str]:
    """Validate username for registration"""
    errors = []

    if not username or len(username.strip()) < 3:
        errors.append("Benutzername muss mindestens 3 Zeichen lang sein")

    if len(username) > 50:
        errors.append("Benutzername darf maximal 50 Zeichen lang sein")

    if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
        errors.append(
            "Benutzername darf nur Buchstaben, Zahlen, Punkte, Unterstriche und Bindestriche enthalten"
        )

    return errors


def validate_name(name: str, field_name: str) -> List[str]:
    """Validate first/last name"""
    errors = []

    if name and len(name) > 50:
        errors.append(f"{field_name} darf maximal 50 Zeichen lang sein")

    if name and not re.match(r"^[a-zA-ZäöüÄÖÜß\s\-\'\.]+$", name):
        errors.append(f"{field_name} enthält ungültige Zeichen")

    return errors
