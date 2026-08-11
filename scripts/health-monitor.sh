#!/bin/bash
# Health monitoring with alerting

set -e

HEALTH_URL="http://localhost/system/health"
ALERT_EMAIL=${ALERT_EMAIL:-"admin@your-domain.com"}
STATUS_FILE="/tmp/datenschutz-rechtsprechung-api-status"
LOG_FILE="/var/log/datenschutz-rechtsprechung-api/health-monitor.log"

# Function: Log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# Function: Send alert email
send_alert() {
    local subject="$1"
    local message="$2"
    
    if [ -n "$ALERT_EMAIL" ]; then
        cat <<EOF | mail -s "$subject" $ALERT_EMAIL
Datenschutz-Rechtsprechung API Health Alert

Time: $(date)
Status: $subject

Details:
$message

System Information:
- Server: $(hostname)
- Load: $(uptime | cut -d',' -f3-5)
- Memory: $(free -h | grep Mem)
- Disk: $(df -h / | tail -1)

Please check the system immediately.

Health URL: $HEALTH_URL
Logs: tail -f $LOG_FILE
EOF
        
        log "Alert sent: $subject"
    fi
}

# Function: Check health
check_health() {
    local response=$(curl -s -w "%{http_code}" -o /tmp/health_response $HEALTH_URL 2>/dev/null || echo "000")
    local health_data=$(cat /tmp/health_response 2>/dev/null || echo "{}")
    
    if [ "$response" = "200" ]; then
        # Parse health status
        local status=$(echo $health_data | jq -r '.status // "unknown"')
        local checks=$(echo $health_data | jq -r '.checks // {}' | jq -r 'to_entries[] | "\(.key): \(.value)"' | tr '\n' ', ')
        
        if [ "$status" = "healthy" ]; then
            log "✅ System healthy - Checks: $checks"
            
            # Clear any previous failure status
            if [ -f $STATUS_FILE ] && [ "$(cat $STATUS_FILE)" != "healthy" ]; then
                send_alert "Datenschutz-Rechtsprechung API - System Recovered" "System is now healthy again.\n\nChecks: $checks"
                echo "healthy" > $STATUS_FILE
            elif [ ! -f $STATUS_FILE ]; then
                echo "healthy" > $STATUS_FILE
            fi
        else
            log "⚠️ System unhealthy - Status: $status, Checks: $checks"
            
            # Send alert if status changed
            if [ ! -f $STATUS_FILE ] || [ "$(cat $STATUS_FILE)" = "healthy" ]; then
                send_alert "Datenschutz-Rechtsprechung API - System Unhealthy" "System health check failed.\n\nStatus: $status\nChecks: $checks\nResponse: $health_data"
                echo "unhealthy" > $STATUS_FILE
            fi
        fi
    else
        log "❌ Health check failed - HTTP $response"
        
        # Send alert if status changed  
        if [ ! -f $STATUS_FILE ] || [ "$(cat $STATUS_FILE)" != "failed" ]; then
            send_alert "Datenschutz-Rechtsprechung API - Health Check Failed" "Cannot reach health endpoint.\n\nHTTP Status: $response\nURL: $HEALTH_URL\n\nSystem may be down!"
            echo "failed" > $STATUS_FILE
        fi
    fi
    
    # Cleanup
    rm -f /tmp/health_response
}

# Function: Check SSL certificate expiry
check_ssl() {
    if [ -n "$DOMAIN" ]; then
        local expiry_date=$(openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2)
        local expiry_timestamp=$(date -d "$expiry_date" +%s)
        local current_timestamp=$(date +%s)
        local days_until_expiry=$(( ($expiry_timestamp - $current_timestamp) / 86400 ))
        
        if [ $days_until_expiry -lt 7 ]; then
            send_alert "Datenschutz-Rechtsprechung API - SSL Certificate Expiring" "SSL certificate expires in $days_until_expiry days.\n\nDomain: $DOMAIN\nExpiry: $expiry_date"
            log "⚠️ SSL certificate expires in $days_until_expiry days"
        elif [ $days_until_expiry -lt 30 ]; then
            log "⚠️ SSL certificate expires in $days_until_expiry days"
        fi
    fi
}

# Main execution
log "Starting health check"
check_health
check_ssl
log "Health check completed"