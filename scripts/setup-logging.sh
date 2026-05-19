#!/bin/bash
# Setup centralized logging

set -e

LOG_DIR="/var/log/datenschutz-rechtsprechung-api"
APP_DIR="/opt/datenschutz-rechtsprechung-api"

echo "📊 Setting up Datenschutz-Rechtsprechung API logging"

# Create log directories
sudo mkdir -p $LOG_DIR/{nginx,app,system}
sudo mkdir -p $APP_DIR/logs

# Set permissions
sudo chown -R dsr:dsr $LOG_DIR
sudo chown -R dsr:dsr $APP_DIR/logs

# Symlink application logs to system log directory
if [ ! -L $LOG_DIR/app ]; then
    sudo ln -sf $APP_DIR/logs $LOG_DIR/app
fi

# Install logrotate configuration
sudo cp config/logrotate/datenschutz-rechtsprechung-api /etc/logrotate.d/
sudo chmod 644 /etc/logrotate.d/datenschutz-rechtsprechung-api

# Test logrotate
sudo logrotate -d /etc/logrotate.d/datenschutz-rechtsprechung-api

echo "✅ Logging setup complete"
echo "📍 Logs location: $LOG_DIR"
echo "🔄 Logrotate configured for 30-60 day retention"