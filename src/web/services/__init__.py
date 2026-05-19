"""
Service-Layer für Flask Web-UI.

Enthält Business-Logik und Integrationen:
- api_client: FastAPI Integration (✅ implementiert)
- excel_export: Excel-Export Service (Session 3)
- auth_service: Authentication (Session 4)
"""

from .api_client import FastAPIClient, create_api_client

__all__ = ["FastAPIClient", "create_api_client"]
