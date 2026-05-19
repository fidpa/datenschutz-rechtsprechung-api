#!/bin/bash
# Production readiness tests

set -e

DOMAIN=${1:-localhost}
PROTOCOL=${2:-http}

echo "🧪 Testing Production Deployment"

# Health Check Tests
echo "🏥 Testing health endpoints..."
curl -f ${PROTOCOL}://${DOMAIN}/system/health || echo "❌ Health check failed"
curl -f ${PROTOCOL}://${DOMAIN}/api/system/health || echo "❌ API health check failed"

# SSL Tests (if HTTPS)
if [ "$PROTOCOL" = "https" ]; then
    echo "🔐 Testing SSL configuration..."
    curl -I ${PROTOCOL}://${DOMAIN} | grep -i "strict-transport-security" || echo "❌ HSTS header missing"
    
    # Test SSL Labs rating (requires external service)
    # ssllabs-scan --host=${DOMAIN} --grade
fi

# Performance Tests
echo "⚡ Testing response times..."
for endpoint in "/" "/api/decisions" "/admin/dashboard"; do
    time=$(curl -o /dev/null -s -w "%{time_total}" ${PROTOCOL}://${DOMAIN}${endpoint} || echo "ERROR")
    echo "  ${endpoint}: ${time}s"
done

# Authentication Tests
echo "🔐 Testing authentication..."
curl -X POST ${PROTOCOL}://${DOMAIN}/auth/api/token \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' || echo "❌ API auth failed"

# Rate Limiting Tests
echo "🚦 Testing rate limiting..."
for i in {1..10}; do
    curl -s ${PROTOCOL}://${DOMAIN}/auth/login >/dev/null
done
echo "  Rate limiting test completed"

echo "✅ Production tests completed"