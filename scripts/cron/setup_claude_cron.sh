#!/bin/bash
# Setup Cron Job für Claude Code Daily Analysis
# Führt täglich um 07:00 UTC die Claude Analysis aus

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CRON_SCRIPT="$PROJECT_DIR/scripts/cron/claude_daily_analysis.sh"

echo "🚀 Setting up Claude Code Daily Analysis Cron Job..."

# Stelle sicher, dass das Script existiert und ausführbar ist
if [ ! -f "$CRON_SCRIPT" ]; then
    echo "❌ Error: Cron script not found at $CRON_SCRIPT"
    exit 1
fi

chmod +x "$CRON_SCRIPT"

# Erstelle Crontab-Eintrag (02:00 UTC für niedrige Server-Last)
CRON_ENTRY="0 2 * * * $CRON_SCRIPT"

# Prüfe, ob der Eintrag bereits existiert
if crontab -l 2>/dev/null | grep -F "$CRON_SCRIPT" > /dev/null; then
    echo "⚠️  Claude Daily Analysis Cron Job already exists"
    echo "   Current crontab entries for Claude:"
    crontab -l 2>/dev/null | grep -F "$CRON_SCRIPT"
else
    # Füge Cron Job hinzu
    echo "📅 Adding Claude Daily Analysis to crontab..."
    
    # Backup aktuelle crontab
    crontab -l > /tmp/current_crontab 2>/dev/null || touch /tmp/current_crontab
    
    # Füge neuen Eintrag hinzu
    echo "$CRON_ENTRY" >> /tmp/current_crontab
    
    # Installiere neue crontab
    crontab /tmp/current_crontab
    
    # Cleanup
    rm /tmp/current_crontab
    
    echo "✅ Claude Daily Analysis Cron Job added successfully!"
fi

echo ""
echo "📋 Cron Job Details:"
echo "   Schedule: Daily at 02:00 UTC (optimiert für niedrige Server-Last)"
echo "   Script: $CRON_SCRIPT"
echo "   Logs: $PROJECT_DIR/data/logs/cron_claude_analysis.log"
echo ""
echo "📊 Daily Reports werden gespeichert in:"
echo "   $PROJECT_DIR/data/logs/claude_analysis/"
echo ""
echo "🔍 Zum Testen des Scripts manuell ausführen:"
echo "   $CRON_SCRIPT"
echo ""
echo "🚨 Zum Deaktivieren des Cron Jobs:"
echo "   crontab -e  # und die Zeile mit claude_daily_analysis.sh löschen"