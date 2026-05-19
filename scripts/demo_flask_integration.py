#!/usr/bin/env python3
"""
Demo Flask Integration mit Claude Code Logging System.

Zeigt Zero-Code-Change Integration für bestehende Flask-Anwendung.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify
from src.logging.middleware.flask_middleware import setup_flask_logging
from src.logging.core.config import get_development_config, set_config

# Set development configuration
config = get_development_config()
set_config(config)

# Create Flask app
app = Flask(__name__)

# Setup Claude Logging - ZERO CODE CHANGES NEEDED!
setup_flask_logging(app, component_name="demo_flask")


@app.route("/")
def index():
    """Fast endpoint."""
    return jsonify({"message": "Hello from Flask with Claude Logging!"})


@app.route("/search")
def search():
    """Search endpoint mit performance monitoring."""
    import time

    time.sleep(0.1)  # Simulate search work
    query = request.args.get("q", "default")
    return jsonify({"query": query, "results": [f"Result {i} for {query}" for i in range(1, 6)]})


@app.route("/slow")
def slow_endpoint():
    """Slow endpoint für performance testing."""
    import time

    time.sleep(2.1)  # Trigger slow request detection
    return jsonify({"message": "This was intentionally slow"})


@app.route("/error")
def error_endpoint():
    """Error endpoint für error tracking."""
    raise ValueError("Demo error for testing Claude Logging")


@app.route("/business-action")
def business_action():
    """Business-critical endpoint."""
    import time

    time.sleep(0.05)
    return jsonify(
        {"action": "critical_business_operation", "status": "completed", "user_impact": "high"}
    )


if __name__ == "__main__":
    print("🚀 Starting Flask Demo with Claude Logging Integration")
    print("🔗 Automatic logging is enabled for all requests")
    print("📊 Test endpoints:")
    print("   - GET /          - Fast endpoint")
    print("   - GET /search    - Search with performance monitoring")
    print("   - GET /slow      - Intentionally slow (>2s)")
    print("   - GET /error     - Triggers error logging")
    print("   - GET /business-action - Business-critical endpoint")
    print("\n📁 Logs will be saved to: logs/claude_logging")
    print("📊 Run analysis: python scripts/claude_analysis/daily_analysis.py")
    print("\nStarting server on http://localhost:5002")

    # Run development server
    app.run(host="0.0.0.0", port=5002, debug=True)
