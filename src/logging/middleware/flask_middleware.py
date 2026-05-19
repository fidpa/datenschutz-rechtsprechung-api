"""
Flask Middleware für automatisches Request/Response Logging.

Zero-Code-Change Integration für Flask-Anwendungen mit
intelligenter Business-Impact-Assessment und UX-Monitoring.
"""

import time
import uuid
from typing import Optional, Dict, Any
from flask import Flask, request, g
from flask.wrappers import Response
import asyncio

from ..core.logger import get_logger
from ..core.config import get_config


class FlaskLoggingMiddleware:
    """
    Flask Middleware für Enterprise Logging.

    Features:
    - Automatic Request/Response Logging
    - Performance Monitoring
    - Error Tracking
    - Business Event Classification
    - User Experience Monitoring
    - Security Event Detection
    """

    def __init__(self, app: Optional[Flask] = None, component_name: str = "flask"):
        self.component_name = component_name
        self.config = get_config()
        self.logger = get_logger(component_name)

        # Business-critical endpoints
        self.critical_endpoints = {
            "/login",
            "/auth",
            "/signup",
            "/register",
            "/payment",
            "/checkout",
            "/billing",
            "/admin",
            "/dashboard",
        }

        # Performance thresholds für verschiedene endpoint types
        self.endpoint_thresholds = {
            "api": 500,  # API endpoints should be fast
            "auth": 1000,  # Auth can be slower
            "admin": 2000,  # Admin pages can be slower
            "default": 1000,  # Default threshold
        }

        if app:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Initialize Flask app with logging middleware."""
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.teardown_request(self._teardown_request)

        # Error handler für uncaught exceptions
        @app.errorhandler(Exception)
        def handle_exception(error):
            self._log_error_async(error)
            # Re-raise to let Flask handle it normally
            raise error

    def _before_request(self) -> None:
        """Called before each request."""
        # Store request start time and ID
        g.request_start_time = time.perf_counter()
        g.request_id = str(uuid.uuid4())

        # Log request start für critical endpoints
        if self._is_critical_endpoint(request.endpoint or request.path):
            self._log_request_start_async()

    def _after_request(self, response) -> Response:
        """Called after each request."""
        # Calculate request duration
        start_time = getattr(g, "request_start_time", time.perf_counter())
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log request completion
        self._log_request_completion_async(response, duration_ms)

        return response

    def _teardown_request(self, exception=None) -> None:
        """Called when request context is torn down."""
        if exception:
            self._log_error_async(exception)

    def _is_critical_endpoint(self, endpoint: str) -> bool:
        """Check if endpoint is business-critical."""
        if not endpoint:
            return False

        endpoint = endpoint.lower()
        return any(critical in endpoint for critical in self.critical_endpoints)

    def _get_endpoint_type(self, endpoint: str) -> str:
        """Determine endpoint type for performance thresholds."""
        if not endpoint:
            return "default"

        endpoint = endpoint.lower()

        if any(api_indicator in endpoint for api_indicator in ["/api/", "api."]):
            return "api"
        elif any(auth_indicator in endpoint for auth_indicator in ["auth", "login", "signup"]):
            return "auth"
        elif "admin" in endpoint:
            return "admin"
        else:
            return "default"

    def _assess_business_impact(self, response_code: int, endpoint: str) -> str:
        """Assess business impact of request."""
        # Error responses have higher impact
        if response_code >= 500:
            return "high"
        elif response_code >= 400:
            return "medium"

        # Critical endpoints have higher impact
        if self._is_critical_endpoint(endpoint):
            return "high"

        # API endpoints have medium impact
        if self._get_endpoint_type(endpoint) == "api":
            return "medium"

        return "low"

    def _get_user_id(self) -> Optional[str]:
        """Extract user ID from request context."""
        # Try to get user from Flask-Login
        try:
            from flask_login import current_user

            if current_user and current_user.is_authenticated:
                return str(current_user.id) if hasattr(current_user, "id") else str(current_user)
        except ImportError:
            pass

        # Try to get from session
        try:
            from flask import session

            return session.get("user_id")
        except:
            pass

        # Try to get from custom headers
        return request.headers.get("X-User-ID")

    def _extract_request_context(self) -> Dict[str, Any]:
        """Extract relevant context from Flask request."""
        context = {
            "method": request.method,
            "endpoint": request.endpoint or request.path,
            "path": request.path,
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", ""),
            "referrer": request.headers.get("Referer", ""),
        }

        # Add query parameters (without sensitive data)
        if request.args:
            safe_args = {
                k: v
                for k, v in request.args.items()
                if k.lower() not in ["password", "token", "secret", "key"]
            }
            context["query_params"] = safe_args

        # Add form data size (not content for security)
        if request.form:
            context["form_data_size"] = len(request.form)

        # Add JSON data size (not content for security)
        if request.is_json and request.content_length:
            context["json_data_size"] = request.content_length

        return context

    def _log_request_start_async(self) -> None:
        """Log request start asynchronously."""
        context = self._extract_request_context()
        user_id = self._get_user_id()

        # Create task to log asynchronously
        asyncio.create_task(
            self.logger.business_event(
                action="request_started",
                feature=context["endpoint"],
                user_id=user_id,
                impact=self._assess_business_impact(200, context["endpoint"]),
                request_id=g.request_id,
                context=context,
            )
        )

    def _log_request_completion_async(self, response, duration_ms: float) -> None:
        """Log request completion asynchronously."""
        context = self._extract_request_context()
        user_id = self._get_user_id()
        endpoint = context["endpoint"]

        # Determine if this is a performance issue
        endpoint_type = self._get_endpoint_type(endpoint)
        threshold = self.endpoint_thresholds.get(endpoint_type, self.endpoint_thresholds["default"])

        is_slow = duration_ms > threshold
        is_critical_slow = duration_ms > self.config.critical_response_time_ms

        # Assess business impact
        business_impact = self._assess_business_impact(response.status_code, endpoint)

        # Add response context
        context.update(
            {
                "status_code": response.status_code,
                "response_size": len(response.data) if response.data else 0,
                "content_type": response.content_type,
            }
        )

        # Performance logging
        if is_critical_slow or (is_slow and business_impact in ["high", "critical"]):
            asyncio.create_task(
                self.logger.performance(
                    operation=f"HTTP {context['method']} {endpoint}",
                    duration_ms=duration_ms,
                    request_id=g.request_id,
                    user_id=user_id,
                    endpoint=endpoint,
                    method=context["method"],
                    status_code=response.status_code,
                    user_impact=business_impact,
                    context=context,
                )
            )

        # Business event logging
        if business_impact in ["high", "medium"] or response.status_code >= 400:
            action = "request_completed"
            if response.status_code >= 500:
                action = "request_failed_server_error"
            elif response.status_code >= 400:
                action = "request_failed_client_error"

            asyncio.create_task(
                self.logger.business_event(
                    action=action,
                    feature=endpoint,
                    user_id=user_id,
                    impact=business_impact,
                    request_id=g.request_id,
                    duration_ms=duration_ms,
                    status_code=response.status_code,
                    context=context,
                )
            )

        # Security event logging für suspicious requests
        if self._is_suspicious_request(context, response.status_code):
            asyncio.create_task(
                self.logger.security_event(
                    event_type="suspicious_request",
                    description=f"Suspicious {context['method']} to {endpoint}",
                    severity="medium",
                    user_id=user_id,
                    request_id=g.request_id,
                    context=context,
                )
            )

    def _is_suspicious_request(self, context: Dict[str, Any], status_code: int) -> bool:
        """Detect potentially suspicious requests."""
        # Multiple 401/403 responses
        if status_code in [401, 403]:
            return True

        # SQL injection patterns in path
        path = context.get("path", "").lower()
        sql_patterns = ["union select", "drop table", "1=1", "or 1=1", "--", ";--"]
        if any(pattern in path for pattern in sql_patterns):
            return True

        # XSS patterns
        xss_patterns = ["<script", "javascript:", "onerror=", "onload="]
        if any(pattern in path for pattern in xss_patterns):
            return True

        # Path traversal
        if "../" in path or "..\\" in path:
            return True

        return False

    def _log_error_async(self, error: Exception) -> None:
        """Log error asynchronously."""
        context = self._extract_request_context() if request else {}
        user_id = self._get_user_id() if request else None

        # Determine error severity
        if isinstance(error, (ValueError, TypeError)):
            pass
        elif isinstance(error, KeyError):
            pass

        asyncio.create_task(
            self.logger.error(
                f"Flask request error: {str(error)}",
                error=error,
                request_id=getattr(g, "request_id", None),
                user_id=user_id,
                user_impact=self._assess_business_impact(500, context.get("endpoint", "")),
                context=context,
            )
        )


def setup_flask_logging(app: Flask, component_name: str = "flask") -> FlaskLoggingMiddleware:
    """
    Setup Flask logging middleware.

    Usage:
        from src.logging.middleware import setup_flask_logging

        app = Flask(__name__)
        setup_flask_logging(app)
    """
    middleware = FlaskLoggingMiddleware(component_name=component_name)
    middleware.init_app(app)
    return middleware


# Convenience decorator für einzelne routes
def log_route_performance(feature_name: Optional[str] = None, impact: str = "medium"):
    """
    Decorator für detailed route logging.

    Usage:
        @app.route('/critical-feature')
        @log_route_performance("critical_feature", impact="high")
        def critical_feature():
            return "data"
    """

    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            logger = get_logger("flask_route")

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log success
                asyncio.create_task(
                    logger.business_event(
                        action="route_executed",
                        feature=feature_name or func.__name__,
                        impact=impact,
                        duration_ms=duration_ms,
                        context={"function": func.__name__},
                    )
                )

                return result

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Log error
                asyncio.create_task(
                    logger.error(
                        f"Route error in {func.__name__}: {str(e)}",
                        error=e,
                        duration_ms=duration_ms,
                        feature_affected=feature_name or func.__name__,
                        user_impact=impact,
                        context={"function": func.__name__},
                    )
                )
                raise

        return wrapper

    return decorator
