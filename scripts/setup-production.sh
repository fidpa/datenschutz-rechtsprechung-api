#!/bin/bash
# Production setup script

set -e

echo "🚀 Setting up Datenschutz-Rechtsprechung API Production Environment"

# Create required directories
mkdir -p config/nginx/sites-enabled
mkdir -p ssl/certbot/{conf,www}
mkdir -p ssl/dhparam
mkdir -p logs/{nginx,app}
mkdir -p data/{uploads,sessions,temp}
mkdir -p backups

# Generate DH parameters (takes several minutes)
if [ ! -f ssl/dhparam/dhparam.pem ]; then
    echo "📜 Generating DH parameters (this may take several minutes)..."
    openssl dhparam -out ssl/dhparam/dhparam.pem 2048
fi

# Copy environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your actual configuration!"
fi

# Set permissions
chmod 600 .env
chmod -R 755 ssl/
chmod -R 755 config/
chmod -R 777 logs/
chmod -R 777 data/

echo "✅ Production setup complete!"
echo "📝 Next steps:"
echo "  1. Edit .env with your configuration"
echo "  2. Update config/nginx/sites-enabled/datenschutz-rechtsprechung-api.conf with your domain"
echo "  3. Run: docker-compose -f docker-compose.production.yml up -d"
echo "  4. For production: Run: docker-compose exec certbot certbot certonly --webroot --webroot-path=/var/www/certbot -d your-domain.com"