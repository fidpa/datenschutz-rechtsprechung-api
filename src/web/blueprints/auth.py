"""
Authentication Blueprint für Datenschutz-Rechtsprechung API
Vollständiges Auth-System
"""
from flask import Blueprint, render_template, request, redirect, flash, session, jsonify, url_for
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse  # Updated import for newer werkzeug/flask
import logging

from ..models.user import AuthManager
from ..models.tokens import WebAuthToken
from ..services.email_service import EmailService
from ..utils.csrf import csrf_protect
from ..utils.rate_limit import rate_limit
from ..utils.validation import (
    validate_login_form,
    validate_forgot_password_form,
    validate_reset_password_form,
    sanitize_input,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
@rate_limit(max_requests=5, window_seconds=300, block_seconds=900)  # 5 attempts per 5min
@csrf_protect
def login():
    """Login route mit CSRF und Rate Limiting"""
    # Redirect if already authenticated
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        try:
            username = sanitize_input(request.form.get("username", ""))
            password = request.form.get("password", "")
            remember_me = bool(request.form.get("remember_me"))

            # Validation
            errors = validate_login_form(username, password)
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("auth/login.html")

            # Authenticate user
            user = AuthManager.authenticate(username, password)

            if user:
                # Login successful
                login_user(user, remember=remember_me)

                # Store user info in session (zusätzliche Sicherheit)
                session["user_id"] = str(user.id)
                session["username"] = user.username
                session["is_admin"] = user.is_admin
                session["role"] = user.role
                session.permanent = remember_me

                logger.info(f"User logged in: {username}")

                # Redirect to next page or dashboard
                next_page = request.args.get("next")
                if next_page and urlparse(next_page).netloc == "":
                    return redirect(next_page)
                return redirect(url_for("admin.dashboard"))

            else:
                flash("Ungültige Anmeldedaten. Bitte versuchen Sie es erneut.", "danger")
                logger.warning(f"Failed login attempt: {username}")

        except Exception as e:
            logger.error(f"Login error for {username}: {str(e)}")
            flash("Ein Fehler ist bei der Anmeldung aufgetreten.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout route"""
    try:
        username = current_user.username if current_user.is_authenticated else "Unbekannt"
        current_user.full_name if current_user.is_authenticated else "Unbekannt"

        # Clear session data
        session.clear()

        # Logout user
        logout_user()

        logger.info(f"User logged out: {username}")

    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        flash("Fehler beim Abmelden aufgetreten.", "danger")

    return redirect(url_for("public.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@rate_limit(max_requests=3, window_seconds=600, block_seconds=1800)  # 3 attempts per 10min
@csrf_protect
def forgot_password():
    """Forgot password route - sendet Reset-Email"""
    if request.method == "POST":
        try:
            email = sanitize_input(request.form.get("email", ""))

            # Validation
            errors = validate_forgot_password_form(email)
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("auth/forgot_password.html")

            # Find user by email
            user = AuthManager.get_user_by_email(email)

            if user:
                # Create reset token
                token = WebAuthToken.create_reset_token(str(user.id), expires_hours=1)

                if token:
                    # Generate reset URL
                    reset_url = url_for("auth.reset_password", token=token, _external=True)

                    # Send email
                    email_service = EmailService()
                    success = email_service.send_password_reset(
                        user_email=user.email, user_name=user.full_name, reset_url=reset_url
                    )

                    if success:
                        flash(
                            f"Eine E-Mail mit Anweisungen zum Zurücksetzen wurde an {email} gesendet. "
                            "Prüfen Sie auch Ihren Spam-Ordner.",
                            "success",
                        )
                        logger.info(f"Password reset email sent to: {email}")
                    else:
                        flash(
                            "Fehler beim Senden der E-Mail. Bitte versuchen Sie es später erneut.",
                            "danger",
                        )
                        logger.error(f"Failed to send reset email to: {email}")
                else:
                    flash("Fehler beim Erstellen des Reset-Tokens.", "danger")
                    logger.error(f"Failed to create reset token for user: {user.username}")
            else:
                # Auch bei unbekannter E-Mail Success-Meldung (Security by Obscurity)
                flash(
                    f"Falls ein Konto mit der E-Mail-Adresse {email} existiert, "
                    "wurde eine Anleitung zum Zurücksetzen des Passworts gesendet.",
                    "info",
                )
                logger.warning(f"Password reset requested for unknown email: {email}")

            # Redirect nach POST (PRG pattern)
            return redirect(url_for("auth.login"))

        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}")
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@rate_limit(max_requests=5, window_seconds=300, block_seconds=600)  # 5 attempts per 5min
@csrf_protect
def reset_password(token):
    """Reset password route - mit Token-Validierung"""
    # Validate token and get user
    user = WebAuthToken.validate_reset_token(token)

    if not user:
        flash(
            "Der Reset-Link ist ungültig oder abgelaufen. "
            "Bitte fordern Sie einen neuen Link an.",
            "danger",
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        try:
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")

            # Validation
            errors = validate_reset_password_form(password, password_confirm)
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("auth/reset_password.html", token=token)

            # Update password
            success = user.update_password(password)

            if success:
                # Mark token as used
                WebAuthToken.use_token(
                    token,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get("User-Agent"),
                )

                # Send confirmation email
                email_service = EmailService()
                email_service.send_password_changed_notification(
                    user_email=user.email, user_name=user.full_name
                )

                flash(
                    "Ihr Passwort wurde erfolgreich zurückgesetzt. "
                    "Sie können sich jetzt mit dem neuen Passwort anmelden.",
                    "success",
                )
                logger.info(f"Password reset successful for user: {user.username}")

                return redirect(url_for("auth.login"))
            else:
                flash("Fehler beim Aktualisieren des Passworts.", "danger")
                logger.error(f"Failed to update password for user: {user.username}")

        except Exception as e:
            logger.error(f"Reset password error: {str(e)}")
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
@csrf_protect
def change_password():
    """Change password für angemeldete User"""
    if request.method == "POST":
        try:
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            new_password_confirm = request.form.get("new_password_confirm", "")

            # Validate current password
            if not current_user.check_password(current_password):
                flash("Das aktuelle Passwort ist falsch.", "danger")
                return render_template("auth/change_password.html")

            # Validate new password
            errors = validate_reset_password_form(new_password, new_password_confirm)
            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("auth/change_password.html")

            # Update password
            success = current_user.update_password(new_password)

            if success:
                # Send notification email
                email_service = EmailService()
                email_service.send_password_changed_notification(
                    user_email=current_user.email, user_name=current_user.full_name
                )

                flash("Ihr Passwort wurde erfolgreich geändert.", "success")
                logger.info(f"Password changed for user: {current_user.username}")

                return redirect(url_for("auth.profile"))
            else:
                flash("Fehler beim Aktualisieren des Passworts.", "danger")

        except Exception as e:
            logger.error(f"Change password error: {str(e)}")
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    return render_template("auth/change_password.html")


@auth_bp.route("/profile")
@login_required
def profile():
    """User profile page"""
    return render_template("auth/profile.html", user=current_user)


@auth_bp.route("/status")
def status():
    """Auth status endpoint für AJAX requests"""
    try:
        if current_user.is_authenticated:
            return jsonify({"authenticated": True, "user": current_user.to_dict()})
        else:
            return jsonify({"authenticated": False, "user": None})

    except Exception as e:
        logger.error(f"Auth status error: {str(e)}")
        return jsonify({"error": "Status check failed"}), 500


@auth_bp.route("/test-email", methods=["GET", "POST"])
@login_required
def test_email():
    """Email test endpoint für Admins"""
    if not current_user.is_admin:
        flash("Sie haben keine Berechtigung für diese Funktion.", "danger")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        try:
            test_email_addr = sanitize_input(request.form.get("test_email", ""))

            if not test_email_addr:
                test_email_addr = current_user.email

            if not test_email_addr:
                flash("Keine E-Mail-Adresse verfügbar für den Test.", "danger")
                return render_template("auth/test_email.html")

            # Send test email
            email_service = EmailService()
            success = email_service.send_test_email(
                to_email=test_email_addr, admin_name=current_user.full_name
            )

            if success:
                flash(f"Test-E-Mail erfolgreich an {test_email_addr} gesendet!", "success")
                logger.info(f"Test email sent to: {test_email_addr}")
            else:
                flash("Fehler beim Senden der Test-E-Mail.", "danger")
                logger.error(f"Failed to send test email to: {test_email_addr}")

        except Exception as e:
            logger.error(f"Email test error: {str(e)}")
            flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")

    # Get email config info
    email_service = EmailService()
    config_info = email_service.get_config_info()

    return render_template("auth/test_email.html", email_config=config_info)
