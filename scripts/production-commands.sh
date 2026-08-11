#!/bin/bash
# Quick production management commands

case "$1" in
    status)
        echo "🔍 Datenschutz-Rechtsprechung API Production Status"
        echo "=================================="
        
        # Service status
        systemctl is-active datenschutz-rechtsprechung-api.service
        
        # Container status
        docker-compose -f docker-compose.production.yml ps
        
        # Health check
        curl -s http://localhost/system/health | jq '.status'
        
        # Resource usage
        echo -e "\n📊 Resource Usage:"
        echo "CPU: $(top -bn1 | grep 'Cpu(s)' | cut -d',' -f1 | awk '{print $2}')"
        echo "Memory: $(free -h | grep Mem | awk '{print $3"/"$2}')"
        echo "Disk: $(df -h / | tail -1 | awk '{print $5 " used"}')"
        ;;
        
    logs)
        echo "📜 Recent logs:"
        tail -f /var/log/datenschutz-rechtsprechung-api/health-monitor.log
        ;;
        
    backup)
        echo "💾 Running manual backup..."
        /opt/datenschutz-rechtsprechung-api/scripts/backup-system.sh
        ;;
        
    restart)
        echo "🔄 Restarting Datenschutz-Rechtsprechung API..."
        systemctl restart datenschutz-rechtsprechung-api.service
        ;;
        
    ssl-check)
        echo "🔐 SSL Certificate Status:"
        certbot certificates
        ;;
        
    *)
        echo "Usage: $0 {status|logs|backup|restart|ssl-check}"
        exit 1
        ;;
esac