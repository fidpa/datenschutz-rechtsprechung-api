"""
System health endpoints für Production Monitoring
"""
from flask import Blueprint, jsonify
import psutil
import time
import os

system_bp = Blueprint("system", __name__, url_prefix="/system")


@system_bp.route("/health")
def health():
    """Health check endpoint for load balancer"""
    try:
        # Basic health checks
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "service": "datenschutz-rechtsprechung-api-web",
            "version": os.environ.get("APP_VERSION", "1.0.0"),
            "checks": {},
        }

        # Database connectivity check
        try:
            from src.web.models.user import WebUser

            WebUser.query.first()
            health_status["checks"]["database"] = "healthy"
        except Exception as e:
            health_status["checks"]["database"] = f"unhealthy: {str(e)}"
            health_status["status"] = "unhealthy"

        # Redis connectivity check
        try:
            import redis

            if "REDIS_URL" in os.environ:
                r = redis.from_url(os.environ["REDIS_URL"])
                r.ping()
                health_status["checks"]["redis"] = "healthy"
        except Exception as e:
            health_status["checks"]["redis"] = f"unhealthy: {str(e)}"

        # API connectivity check
        try:
            from src.web.services.api_client import FastAPIClient

            client = FastAPIClient()
            client.get("/system/health", timeout=5)
            health_status["checks"]["api"] = "healthy"
        except Exception as e:
            health_status["checks"]["api"] = f"unhealthy: {str(e)}"

        # Return appropriate status code
        status_code = 200 if health_status["status"] == "healthy" else 503
        return jsonify(health_status), status_code

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "service": "datenschutz-rechtsprechung-api-web",
                }
            ),
            503,
        )


@system_bp.route("/metrics")
def metrics():
    """Prometheus-compatible metrics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        metrics_data = f"""
# HELP dsr_web_cpu_usage_percent CPU usage percentage
# TYPE dsr_web_cpu_usage_percent gauge
dsr_web_cpu_usage_percent {cpu_percent}

# HELP dsr_web_memory_usage_bytes Memory usage in bytes
# TYPE dsr_web_memory_usage_bytes gauge
dsr_web_memory_usage_bytes {memory.used}

# HELP dsr_web_memory_total_bytes Total memory in bytes
# TYPE dsr_web_memory_total_bytes gauge
dsr_web_memory_total_bytes {memory.total}

# HELP dsr_web_disk_usage_bytes Disk usage in bytes
# TYPE dsr_web_disk_usage_bytes gauge
dsr_web_disk_usage_bytes {disk.used}

# HELP dsr_web_disk_total_bytes Total disk in bytes
# TYPE dsr_web_disk_total_bytes gauge
dsr_web_disk_total_bytes {disk.total}
        """.strip()

        return metrics_data, 200, {"Content-Type": "text/plain; charset=utf-8"}

    except Exception as e:
        return f"# Error generating metrics: {str(e)}", 500
