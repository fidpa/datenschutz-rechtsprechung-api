#!/bin/bash
# Production startup script

set -e

echo "🚀 Starting Datenschutz-Rechtsprechung API Production"

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Run setup-production.sh first."
    exit 1
fi

# Source environment
set -a
source .env
set +a

# Validate required environment variables
required_vars=("POSTGRES_PASSWORD" "REDIS_PASSWORD" "FLASK_SECRET_KEY" "API_SECRET_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

echo "🔍 Checking Docker Compose configuration..."
docker-compose -f docker-compose.production.yml config -q

echo "🏗️  Building containers..."
docker-compose -f docker-compose.production.yml build --parallel

echo "🚀 Starting services..."
docker-compose -f docker-compose.production.yml up -d

echo "⏳ Waiting for services to be healthy..."
sleep 30

# Health checks
echo "🏥 Running health checks..."
services=("postgres" "redis" "api" "web" "nginx")
for service in "${services[@]}"; do
    if docker-compose -f docker-compose.production.yml ps $service | grep -q "Up (healthy)"; then
        echo "✅ $service: healthy"
    else
        echo "❌ $service: unhealthy"
        docker-compose -f docker-compose.production.yml logs --tail=10 $service
    fi
done

echo "📊 System Status:"
docker-compose -f docker-compose.production.yml ps

echo "🌐 Service URLs:"
echo "  - Web UI: https://${DOMAIN:-localhost}"
echo "  - API: https://${DOMAIN:-localhost}/api"
echo "  - Admin: https://${DOMAIN:-localhost}/admin"
echo "  - Health: https://${DOMAIN:-localhost}/system/health"

echo "✅ Datenschutz-Rechtsprechung API Production is running!"