"""
Simple Rate Limiting für Login-Endpunkte
Rate-Limiting-Utility für Datenschutz-Rechtsprechung API
"""
from functools import wraps
from flask import request, jsonify, flash, redirect, url_for
import time
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# In-memory rate limiting (in production use Redis)
rate_limit_storage = defaultdict(list)


def rate_limit(max_requests: int = 5, window_seconds: int = 300, block_seconds: int = 900):
    """Rate limiting decorator"""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get client identifier
            client_id = request.remote_addr
            now = time.time()

            # Clean old entries
            rate_limit_storage[client_id] = [
                timestamp
                for timestamp in rate_limit_storage[client_id]
                if timestamp > now - window_seconds
            ]

            # Check if blocked
            if len(rate_limit_storage[client_id]) >= max_requests:
                logger.warning(f"Rate limit exceeded for {client_id} on {request.endpoint}")

                if request.is_json:
                    return (
                        jsonify(
                            {
                                "error": "Zu viele Anfragen. Versuchen Sie es später erneut.",
                                "retry_after": block_seconds,
                            }
                        ),
                        429,
                    )
                else:
                    flash(
                        "Zu viele Anmeldeversuche. Versuchen Sie es in 15 Minuten erneut.", "danger"
                    )
                    return redirect(url_for("auth.login"))

            # Add current request
            rate_limit_storage[client_id].append(now)

            return f(*args, **kwargs)

        return wrapped

    return decorator


def get_rate_limit_status(client_id: str = None) -> dict:
    """Get current rate limit status (für Debugging)"""
    if client_id is None:
        client_id = request.remote_addr

    now = time.time()
    recent_requests = [
        timestamp
        for timestamp in rate_limit_storage[client_id]
        if timestamp > now - 300  # 5 minutes
    ]

    return {
        "client_id": client_id,
        "requests_in_window": len(recent_requests),
        "max_requests": 5,
        "window_seconds": 300,
        "remaining": max(0, 5 - len(recent_requests)),
        "reset_time": int(min(recent_requests) + 300) if recent_requests else int(now),
    }


def clear_rate_limit(client_id: str = None):
    """Clear rate limit für specific client (für Admin-Tools)"""
    if client_id is None:
        client_id = request.remote_addr

    if client_id in rate_limit_storage:
        del rate_limit_storage[client_id]
        logger.info(f"Rate limit cleared for client: {client_id}")
        return True
    return False
