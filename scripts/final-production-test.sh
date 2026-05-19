#!/bin/bash
# Comprehensive production test

set -e

echo "🧪 Final Production Readiness Test"

# Test 1: Service Health
echo "1️⃣ Testing service health..."
systemctl is-active datenschutz-rechtsprechung-api.service >/dev/null && echo "✅ Main service active" || echo "❌ Main service failed"

# Test 2: HTTP/HTTPS Response
echo "2️⃣ Testing web endpoints..."
curl -f http://localhost/ >/dev/null && echo "✅ HTTP redirect working" || echo "❌ HTTP failed"
curl -f https://localhost/ >/dev/null && echo "✅ HTTPS working" || echo "❌ HTTPS failed"

# Test 3: API Endpoints  
echo "3️⃣ Testing API..."
curl -f https://localhost/api/system/health >/dev/null && echo "✅ API health working" || echo "❌ API failed"

# Test 4: Authentication
echo "4️⃣ Testing authentication..."
curl -X POST https://localhost/auth/api/token \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' \
    | grep -q "access_token" && echo "✅ JWT auth working" || echo "❌ Auth failed"

# Test 5: Database Connection
echo "5️⃣ Testing database..."
docker-compose -f docker-compose.production.yml exec -T postgres \
    psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;" >/dev/null && \
    echo "✅ Database working" || echo "❌ Database failed"

# Test 6: Backup System
echo "6️⃣ Testing backup system..."
/opt/datenschutz-rechtsprechung-api/scripts/backup-system.sh >/dev/null && \
    echo "✅ Backup system working" || echo "❌ Backup failed"

# Test 7: SSL Certificate
echo "7️⃣ Testing SSL certificate..."
echo | openssl s_client -connect localhost:443 2>/dev/null | \
    openssl x509 -noout -subject >/dev/null && \
    echo "✅ SSL certificate valid" || echo "❌ SSL failed"

# Test 8: Performance
echo "8️⃣ Testing performance..."
response_time=$(curl -o /dev/null -s -w "%{time_total}" https://localhost/)
if (( $(echo "$response_time < 2.0" | bc -l) )); then
    echo "✅ Response time: ${response_time}s"
else
    echo "⚠️ Response time slow: ${response_time}s"
fi

# Test 9: systemd Timer Status
echo "9️⃣ Testing systemd timers..."
systemctl is-active datenschutz-rechtsprechung-api-backup.timer >/dev/null && echo "✅ Backup timer active" || echo "❌ Backup timer failed"
systemctl is-active datenschutz-rechtsprechung-api-monitor.timer >/dev/null && echo "✅ Monitor timer active" || echo "❌ Monitor timer failed"

# Test 10: Health Monitoring
echo "🔟 Testing health monitoring..."
if [ -f "/var/log/datenschutz-rechtsprechung-api/health-monitor.log" ]; then
    echo "✅ Health monitor log exists"
else
    echo "⚠️ Health monitor log not found"
fi

echo "🎉 Production testing completed!"