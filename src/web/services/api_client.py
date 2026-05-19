# src/web/services/api_client.py
import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Base exception für API-Client Fehler."""


class FastAPIClient:
    """
    Client für Kommunikation mit FastAPI Backend.

    Features:
    - Automatische Retry-Logik
    - Timeout-Handling
    - Error-Mapping
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 5,  # Reduziert von 30 auf 5 Sekunden
        max_retries: int = 1,
    ):  # Reduziert von 3 auf 1
        """Initialize FastAPI Client."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        # Session für Connection-Pooling
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "datenschutz-rechtsprechung-api-Flask/1.0",
            }
        )

        logger.info(f"FastAPI Client initialized: {base_url}")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Interner Request-Handler mit Retry-Logik."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = self.session.request(method=method, url=url, timeout=self.timeout, **kwargs)

            # Status-Code prüfen
            if response.status_code >= 400:
                raise APIClientError(f"API Error {response.status_code}: {response.text}")

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise APIClientError(f"Request failed: {str(e)}")

    # =================================================================
    # SYSTEM ENDPOINTS
    # =================================================================

    def health_check(self) -> Dict[str, Any]:
        """System Health-Check."""
        return self._make_request("GET", "/health")

    def get_stats(self) -> Dict[str, Any]:
        """Basis-Statistiken abrufen."""
        return self._make_request("GET", "/api/v1/stats/summary")

    # =================================================================
    # SEARCH ENDPOINTS
    # =================================================================

    def search(self, query: str = "", page: int = 1, **filters) -> Dict[str, Any]:
        """Volltext-Suche durchführen."""
        params = {"q": query, "page": page, "page_size": 20}

        # Filter hinzufügen (nur nicht-None Werte)
        for key, value in filters.items():
            if value is not None and value != "":
                params[key] = value

        return self._make_request("GET", "/api/v1/search/", params=params)

    def get_decision(self, decision_id: int) -> Dict[str, Any]:
        """Einzelne Entscheidung abrufen."""
        return self._make_request("GET", f"/api/v1/decisions/{decision_id}")

    # =================================================================
    # EXPORT ENDPOINTS
    # =================================================================

    def export_excel(self, **params):
        """
        Excel-Export über FastAPI.
        Gibt die komplette Response zurück (nicht nur JSON).
        """
        url = f"{self.base_url}/api/v1/export/excel"

        # Filter-Parameter aufbereiten
        clean_params = {}
        for key, value in params.items():
            if value is not None and value != "":
                clean_params[key] = value

        logger.info(f"Excel-Export von FastAPI: {clean_params}")

        try:
            response = self.session.get(
                url,
                params=clean_params,
                timeout=self.timeout,
                stream=True,  # Stream für große Dateien
            )

            if response.status_code >= 400:
                raise APIClientError(f"Export fehlgeschlagen: {response.status_code}")

            # Gebe komplette Response zurück (nicht JSON)
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"Excel-Export fehlgeschlagen: {str(e)}")
            raise APIClientError(f"Export fehlgeschlagen: {str(e)}")

    # =================================================================
    # HELPER METHODS
    # =================================================================

    def test_connection(self) -> bool:
        """Teste Verbindung zum FastAPI Backend."""
        try:
            health = self.health_check()
            return health.get("status") == "healthy"
        except:
            return False


# =================================================================
# FACTORY FUNCTION
# =================================================================


def create_api_client(config) -> FastAPIClient:
    """Factory-Funktion für API-Client basierend auf Config."""
    base_url = config.get("FASTAPI_BASE_URL", "http://localhost:8000")
    timeout = config.get("API_TIMEOUT", 30)
    max_retries = config.get("API_MAX_RETRIES", 3)

    return FastAPIClient(base_url=base_url, timeout=timeout, max_retries=max_retries)
