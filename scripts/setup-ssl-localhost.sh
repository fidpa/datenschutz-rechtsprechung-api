#!/bin/bash
# SSL Certificate setup für localhost-Testing (Self-signed)

set -e

echo "🔐 Setting up SSL for localhost testing"

# Create SSL directory structure
mkdir -p ssl/dhparam
mkdir -p ssl/certbot/{conf,www}

# Generate self-signed certificate for localhost
if [ ! -f ssl/dhparam/localhost.crt ]; then
    echo "📜 Generating self-signed certificate for localhost..."
    
    # Create SSL config for localhost
    cat > ssl/localhost.conf << EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C = DE
ST = Germany
L = Berlin
O = Datenschutz-Rechtsprechung API
OU = Development
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    # Generate private key
    openssl genrsa -out ssl/dhparam/localhost.key 2048
    
    # Generate certificate
    openssl req -new -x509 -key ssl/dhparam/localhost.key \
        -out ssl/dhparam/localhost.crt \
        -days 365 \
        -config ssl/localhost.conf \
        -extensions v3_req
    
    echo "✅ Self-signed certificate generated for localhost"
fi

# Generate DH parameters if not exists
if [ ! -f ssl/dhparam/dhparam.pem ]; then
    echo "📜 Generating DH parameters (this takes 1-2 minutes)..."
    openssl dhparam -out ssl/dhparam/dhparam.pem 2048
    echo "✅ DH parameters generated"
fi

# Set proper permissions
chmod 600 ssl/dhparam/localhost.key
chmod 644 ssl/dhparam/localhost.crt
chmod 644 ssl/dhparam/dhparam.pem

echo "🌟 SSL setup for localhost complete!"
echo "📍 Certificate files:"
echo "  - Certificate: ssl/dhparam/localhost.crt"
echo "  - Private Key: ssl/dhparam/localhost.key"
echo "  - DH Params: ssl/dhparam/dhparam.pem"
echo ""
echo "⚠️  Browser Warning: You'll need to accept the self-signed certificate"
echo "🌐 Access via: https://localhost"