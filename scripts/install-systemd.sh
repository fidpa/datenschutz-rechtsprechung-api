#!/bin/bash
# Install systemd services

set -e

echo "🔧 Installing Datenschutz-Rechtsprechung API systemd services"

# Copy service files
sudo cp config/systemd/datenschutz-rechtsprechung-api.service /etc/systemd/system/
sudo cp config/systemd/datenschutz-rechtsprechung-api-backup.service /etc/systemd/system/
sudo cp config/systemd/datenschutz-rechtsprechung-api-backup.timer /etc/systemd/system/

# Set permissions
sudo chmod 644 /etc/systemd/system/datenschutz-rechtsprechung-api*.service
sudo chmod 644 /etc/systemd/system/datenschutz-rechtsprechung-api*.timer

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable datenschutz-rechtsprechung-api.service
sudo systemctl enable datenschutz-rechtsprechung-api-backup.timer

# Start timer
sudo systemctl start datenschutz-rechtsprechung-api-backup.timer

echo "✅ systemd services installed and enabled"
echo "📋 Available commands:"
echo "   sudo systemctl start datenschutz-rechtsprechung-api"
echo "   sudo systemctl stop datenschutz-rechtsprechung-api" 
echo "   sudo systemctl status datenschutz-rechtsprechung-api"
echo "   sudo systemctl status datenschutz-rechtsprechung-api-backup.timer"
echo "   sudo journalctl -u datenschutz-rechtsprechung-api -f"