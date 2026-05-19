# src/web/config.py
import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env aus Projekt-Root laden
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


class Config:
    """Basis-Konfiguration für Flask-App."""

    # Flask Basics
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"
    DEBUG = False
    TESTING = False

    # FastAPI Integration
    FASTAPI_BASE_URL = os.environ.get("FASTAPI_BASE_URL", "http://localhost:8000")
    API_TIMEOUT = int(os.environ.get("API_TIMEOUT", 30))
    API_MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", 3))

    # Session Configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)

    # Pagination
    ITEMS_PER_PAGE = 20
    MAX_ITEMS_PER_PAGE = 100


class DevelopmentConfig(Config):
    """Development-spezifische Konfiguration."""

    DEBUG = True
    SESSION_COOKIE_SECURE = False  # HTTP für Development


class ProductionConfig(Config):
    """Production-spezifische Konfiguration."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True  # HTTPS required
    SESSION_COOKIE_NAME = "__Host-session"


class TestingConfig(Config):
    """Test-spezifische Konfiguration."""

    TESTING = True
    DEBUG = True
    FASTAPI_BASE_URL = "http://localhost:8001"  # Test-API


# Config-Mapping
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
