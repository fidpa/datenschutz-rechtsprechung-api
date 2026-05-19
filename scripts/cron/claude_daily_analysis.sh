#!/bin/bash
# Claude Code Daily Analysis Cron Job
# Führt täglich um 07:00 UTC die Claude Analysis aus

# Projekt-Verzeichnis (repo-relativ, device-agnostisch)
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_DIR/data/logs/cron_claude_analysis.log"

# Umgebung vorbereiten
cd "$PROJECT_DIR" || exit 1

# Virtual Environment aktivieren (falls vorhanden)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Timestamp für Logging
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Claude Daily Analysis..." >> "$LOG_FILE"

# Claude Analysis ausführen
python scripts/claude_analysis/daily_analysis.py >> "$LOG_FILE" 2>&1
ANALYSIS_EXIT_CODE=$?

# Resultate loggen
if [ $ANALYSIS_EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Claude Daily Analysis completed successfully" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Claude Daily Analysis failed with exit code $ANALYSIS_EXIT_CODE" >> "$LOG_FILE"
fi

# Optional: Critical Events zu Slack/Email senden
if [ -f "$PROJECT_DIR/data/logs/claude_logging/claude_analysis_queue.jsonl" ]; then
    CRITICAL_COUNT=$(jq 'select(.priority == "critical")' "$PROJECT_DIR/data/logs/claude_logging/"*.jsonl 2>/dev/null | wc -l || echo 0)
    
    if [ "$CRITICAL_COUNT" -gt 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚨 $CRITICAL_COUNT critical events found - consider immediate action" >> "$LOG_FILE"
        
        # Optional: Slack/Email Notification hier hinzufügen
        # curl -X POST "YOUR_SLACK_WEBHOOK" -d "{'text': '$CRITICAL_COUNT critical events in Datenschutz-Rechtsprechung API'}"
    fi
fi

# Log-Rotation (behalte nur letzten 30 Tage)
find "$PROJECT_DIR/data/logs/claude_analysis" -name "daily_*" -mtime +30 -delete 2>/dev/null

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cron job completed" >> "$LOG_FILE"