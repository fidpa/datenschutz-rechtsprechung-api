"""
Email Service für Datenschutz-Rechtsprechung API
E-Mail-Service mit professionellen HTML-Templates
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import render_template_string
import os

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for password resets and notifications"""

    def __init__(self):
        self.smtp_server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("MAIL_PORT", "587"))
        self.smtp_username = os.environ.get("MAIL_USERNAME", "")
        self.smtp_password = os.environ.get("MAIL_PASSWORD", "")
        self.use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
        self.sender_email = os.environ.get("MAIL_FROM", self.smtp_username)
        self.sender_name = os.environ.get("MAIL_FROM_NAME", "Datenschutz-Rechtsprechung API")

    def send_password_reset(self, user_email: str, user_name: str, reset_url: str) -> bool:
        """Send password reset email to user"""
        try:
            subject = "Datenschutz-Rechtsprechung API - Passwort zurücksetzen"

            # HTML email template
            html_template = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #2563eb; color: white; padding: 20px; text-align: center; }
        .content { background-color: #f8fafc; padding: 30px; margin-top: 20px; }
        .button { display: inline-block; padding: 12px 24px; background-color: #2563eb; 
                  color: white; text-decoration: none; border-radius: 6px; margin: 20px 0; }
        .footer { text-align: center; margin-top: 20px; font-size: 0.8em; color: #666; }
        .warning { background-color: #fef3c7; border: 1px solid #f59e0b; 
                   padding: 15px; border-radius: 6px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Datenschutz-Rechtsprechung API</h1>
            <p>Datenschutz-Rechtsprechung API</p>
        </div>
        <div class="content">
            <h2>Passwort zurücksetzen</h2>
            <p>Hallo {{ user_name }},</p>
            <p>Sie haben eine Anfrage zum Zurücksetzen Ihres Passworts gestellt. 
               Klicken Sie auf den folgenden Button, um ein neues Passwort zu wählen:</p>
            
            <p style="text-align: center;">
                <a href="{{ reset_url }}" class="button">Passwort jetzt zurücksetzen</a>
            </p>
            
            <p>Oder kopieren Sie diesen Link in Ihren Browser:</p>
            <p style="word-break: break-all; background-color: #fff; padding: 15px; 
                      border: 1px solid #e5e7eb; border-radius: 6px; font-family: monospace;">
                {{ reset_url }}
            </p>
            
            <div class="warning">
                <p><strong>⚠️ Wichtige Sicherheitshinweise:</strong></p>
                <ul>
                    <li>Dieser Link ist nur <strong>1 Stunde</strong> gültig</li>
                    <li>Der Link kann nur <strong>einmal</strong> verwendet werden</li>
                    <li>Falls Sie diese Anfrage nicht gestellt haben, ignorieren Sie diese E-Mail</li>
                </ul>
            </div>
        </div>
        <div class="footer">
            <p>Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht darauf.</p>
            <p>&copy; {{ current_year }} Datenschutz-Rechtsprechung API - Datenschutz-konformes System</p>
        </div>
    </div>
</body>
</html>
            """

            # Plain text version
            text_template = """
Datenschutz-Rechtsprechung API - Passwort zurücksetzen

Hallo {{ user_name }},

Sie haben eine Anfrage zum Zurücksetzen Ihres Passworts gestellt.

Bitte öffnen Sie den folgenden Link in Ihrem Browser:
{{ reset_url }}

Wichtiger Hinweis: Dieser Link ist nur 1 Stunde gültig.

Falls Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail ignorieren.

--
Datenschutz-Rechtsprechung API Team
Diese E-Mail wurde automatisch generiert.
            """

            # Render templates
            from datetime import datetime

            context = {
                "user_name": user_name,
                "reset_url": reset_url,
                "current_year": datetime.now().year,
            }

            html_body = render_template_string(html_template, **context)
            text_body = render_template_string(text_template, **context)

            return self._send_email(user_email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Error sending password reset email to {user_email}: {e}")
            return False

    def send_password_changed_notification(self, user_email: str, user_name: str) -> bool:
        """Send password changed notification"""
        try:
            subject = "Datenschutz-Rechtsprechung API - Passwort wurde geändert"

            html_template = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #16a34a; color: white; padding: 20px; text-align: center; }
        .content { background-color: #f0fdf4; padding: 30px; margin-top: 20px; }
        .success { background-color: #dcfce7; border: 1px solid #16a34a; 
                   padding: 15px; border-radius: 6px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✅ Datenschutz-Rechtsprechung API</h1>
        </div>
        <div class="content">
            <h2>Passwort erfolgreich geändert</h2>
            <p>Hallo {{ user_name }},</p>
            
            <div class="success">
                <p><strong>✅ Ihr Passwort wurde erfolgreich geändert.</strong></p>
                <p>Zeitpunkt: {{ timestamp }}</p>
            </div>
            
            <p>Falls Sie diese Änderung nicht vorgenommen haben, wenden Sie sich sofort 
               an Ihren Administrator.</p>
        </div>
    </div>
</body>
</html>
            """

            text_template = """
Datenschutz-Rechtsprechung API - Passwort wurde geändert

Hallo {{ user_name }},

Ihr Passwort wurde erfolgreich geändert.
Zeitpunkt: {{ timestamp }}

Falls Sie diese Änderung nicht vorgenommen haben, 
wenden Sie sich sofort an Ihren Administrator.

--
Datenschutz-Rechtsprechung API Team
            """

            from datetime import datetime

            context = {
                "user_name": user_name,
                "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

            html_body = render_template_string(html_template, **context)
            text_body = render_template_string(text_template, **context)

            return self._send_email(user_email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Error sending password changed notification: {e}")
            return False

    def send_test_email(self, to_email: str, admin_name: str = "Administrator") -> bool:
        """Send test email for configuration verification"""
        try:
            subject = "Datenschutz-Rechtsprechung API - E-Mail Test erfolgreich"

            html_template = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #059669; color: white; padding: 20px; text-align: center; }
        .content { background-color: #ecfdf5; padding: 30px; margin-top: 20px; }
        .success { background-color: #d1fae5; border: 1px solid #059669; 
                   padding: 15px; border-radius: 6px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 Datenschutz-Rechtsprechung API</h1>
            <p>E-Mail-System funktioniert!</p>
        </div>
        <div class="content">
            <h2>Test E-Mail erfolgreich</h2>
            <p>Hallo {{ admin_name }},</p>
            
            <div class="success">
                <p><strong>✅ Die E-Mail-Konfiguration funktioniert korrekt!</strong></p>
                <ul>
                    <li>SMTP-Server: {{ smtp_server }}:{{ smtp_port }}</li>
                    <li>TLS/SSL: {{ use_tls }}</li>
                    <li>Absender: {{ sender_email }}</li>
                    <li>Test-Zeit: {{ timestamp }}</li>
                </ul>
            </div>
            
            <p>Das Password-Reset System ist jetzt einsatzbereit.</p>
        </div>
    </div>
</body>
</html>
            """

            text_template = """
Datenschutz-Rechtsprechung API - E-Mail Test erfolgreich

Hallo {{ admin_name }},

Die E-Mail-Konfiguration funktioniert korrekt!

SMTP-Server: {{ smtp_server }}:{{ smtp_port }}
TLS/SSL: {{ use_tls }}
Absender: {{ sender_email }}
Test-Zeit: {{ timestamp }}

Das Password-Reset System ist jetzt einsatzbereit.

--
Datenschutz-Rechtsprechung API System
            """

            from datetime import datetime

            context = {
                "admin_name": admin_name,
                "smtp_server": self.smtp_server,
                "smtp_port": self.smtp_port,
                "use_tls": "Aktiviert" if self.use_tls else "Deaktiviert",
                "sender_email": self.sender_email,
                "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

            html_body = render_template_string(html_template, **context)
            text_body = render_template_string(text_template, **context)

            return self._send_email(to_email, subject, text_body, html_body)

        except Exception as e:
            logger.error(f"Error sending test email: {e}")
            return False

    def _send_email(
        self, to_email: str, subject: str, text_body: str, html_body: str = None
    ) -> bool:
        """Send email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = to_email

            # Add text part
            msg.attach(MIMEText(text_body, "plain", "utf-8"))

            # Add HTML part if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.set_debuglevel(0)

                if self.use_tls:
                    server.starttls()

                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)

                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def test_configuration(self) -> tuple[bool, str]:
        """Test email configuration"""
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.set_debuglevel(0)

                if self.use_tls:
                    server.starttls()

                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)

            return True, "E-Mail-Konfiguration erfolgreich getestet"

        except Exception as e:
            return False, f"E-Mail-Konfigurationsfehler: {str(e)}"

    def get_config_info(self) -> dict:
        """Get current email configuration (ohne Passwort)"""
        return {
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "use_tls": self.use_tls,
            "sender_email": self.sender_email,
            "sender_name": self.sender_name,
            "username_configured": bool(self.smtp_username),
            "password_configured": bool(self.smtp_password),
        }
