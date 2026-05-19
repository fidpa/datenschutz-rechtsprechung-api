"""
Einfaches HTML-Dashboard für System-Monitoring.
Zeigt Live-Status ohne externe Dependencies.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def monitoring_dashboard(request: Request):
    """
    Einfaches HTML-Dashboard mit Auto-Refresh.
    Zeigt System-Status, Metriken und Health-Informationen.
    """

    dashboard_html = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Datenschutz-Rechtsprechung API - Monitoring Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.15);
        }
        
        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        
        .status-healthy { background-color: #10b981; }
        .status-degraded { background-color: #f59e0b; }
        .status-unhealthy { background-color: #ef4444; }
        .status-unknown { background-color: #6b7280; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .metric:last-child {
            border-bottom: none;
        }
        
        .metric-label {
            color: #6b7280;
            font-size: 0.9rem;
        }
        
        .metric-value {
            font-weight: 600;
            color: #1f2937;
            font-size: 1.1rem;
        }
        
        .metric-value.large {
            font-size: 2rem;
            color: #667eea;
        }
        
        .progress-bar {
            width: 100%;
            height: 20px;
            background-color: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 5px;
        }
        
        .progress-fill {
            height: 100%;
            transition: width 0.3s ease;
        }
        
        .progress-fill.good { background-color: #10b981; }
        .progress-fill.warning { background-color: #f59e0b; }
        .progress-fill.critical { background-color: #ef4444; }
        
        .refresh-info {
            text-align: center;
            color: white;
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .error-message {
            background-color: #fee2e2;
            color: #991b1b;
            padding: 15px;
            border-radius: 5px;
            margin-top: 10px;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #6b7280;
        }
        
        .timestamp {
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 0.85rem;
            opacity: 0.7;
        }
        
        @media (max-width: 768px) {
            h1 { font-size: 1.8rem; }
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Datenschutz-Rechtsprechung API Monitoring</h1>
        
        <div class="dashboard-grid">
            <!-- System Status Card -->
            <div class="card">
                <h2 class="card-title">System Status</h2>
                <div id="system-status" class="loading">Lade Daten...</div>
            </div>
            
            <!-- Database Card -->
            <div class="card">
                <h2 class="card-title">Datenbank</h2>
                <div id="database-status" class="loading">Lade Daten...</div>
            </div>
            
            <!-- Decisions Statistics Card -->
            <div class="card">
                <h2 class="card-title">Entscheidungen</h2>
                <div id="decisions-stats" class="loading">Lade Daten...</div>
            </div>
            
            <!-- System Resources Card -->
            <div class="card">
                <h2 class="card-title">System-Ressourcen</h2>
                <div id="system-resources" class="loading">Lade Daten...</div>
            </div>
            
            <!-- Crawl Statistics Card -->
            <div class="card">
                <h2 class="card-title">Crawler-Statistiken</h2>
                <div id="crawl-stats" class="loading">Lade Daten...</div>
            </div>
            
            <!-- Redis Status Card -->
            <div class="card">
                <h2 class="card-title">Redis Cache</h2>
                <div id="redis-status" class="loading">Lade Daten...</div>
            </div>
        </div>
        
        <div class="refresh-info">
            ⏱️ Auto-Refresh alle 10 Sekunden | Nächstes Update in <span id="countdown">10</span>s
        </div>
        
        <div class="timestamp" id="last-update"></div>
    </div>
    
    <script>
        let countdown = 10;
        const REFRESH_INTERVAL = 10000; // 10 seconds
        
        function formatNumber(num) {
            return new Intl.NumberFormat('de-DE').format(num);
        }
        
        function formatBytes(bytes) {
            if (!bytes) return '0 B';
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(1024));
            return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
        }
        
        function formatUptime(seconds) {
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            
            if (days > 0) return `${days}d ${hours}h ${minutes}m`;
            if (hours > 0) return `${hours}h ${minutes}m`;
            return `${minutes}m`;
        }
        
        function getStatusClass(status) {
            switch(status) {
                case 'healthy': return 'status-healthy';
                case 'degraded': return 'status-degraded';
                case 'unhealthy': return 'status-unhealthy';
                default: return 'status-unknown';
            }
        }
        
        function getProgressClass(percent) {
            if (percent < 70) return 'good';
            if (percent < 90) return 'warning';
            return 'critical';
        }
        
        async function fetchData() {
            try {
                // Fetch health data
                const healthResponse = await fetch('/system/health');
                const healthData = await healthResponse.json();
                
                // Fetch metrics data
                const metricsResponse = await fetch('/system/metrics');
                const metricsData = await metricsResponse.json();
                
                updateDashboard(healthData, metricsData);
                
            } catch (error) {
                console.error('Error fetching data:', error);
                showError('Fehler beim Laden der Daten');
            }
        }
        
        function updateDashboard(health, metrics) {
            // Update System Status
            const systemStatus = document.getElementById('system-status');
            systemStatus.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value">
                        <span class="status-indicator ${getStatusClass(health.status)}"></span>
                        ${health.status}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Umgebung</span>
                    <span class="metric-value">${health.environment || 'development'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Version</span>
                    <span class="metric-value">${health.version}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Uptime</span>
                    <span class="metric-value">${formatUptime(metrics.system?.uptime_seconds || 0)}</span>
                </div>
            `;
            
            // Update Database Status
            const dbStatus = document.getElementById('database-status');
            const dbCheck = health.checks?.database || {};
            dbStatus.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Verbindung</span>
                    <span class="metric-value">
                        <span class="status-indicator ${getStatusClass(dbCheck.status)}"></span>
                        ${dbCheck.connected ? 'Verbunden' : 'Getrennt'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Entscheidungen</span>
                    <span class="metric-value large">${formatNumber(dbCheck.decision_count || 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Letzter Crawl</span>
                    <span class="metric-value">${dbCheck.last_crawl ? new Date(dbCheck.last_crawl).toLocaleString('de-DE') : 'Nie'}</span>
                </div>
            `;
            
            // Update Decisions Statistics
            const decisionsStats = document.getElementById('decisions-stats');
            const decisions = metrics.decisions || {};
            decisionsStats.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Gesamt</span>
                    <span class="metric-value large">${formatNumber(decisions.total || 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Letzte 24h</span>
                    <span class="metric-value">${formatNumber(decisions.last_24h || 0)}</span>
                </div>
                ${Object.entries(decisions.by_source || {}).map(([source, count]) => `
                    <div class="metric">
                        <span class="metric-label">${source}</span>
                        <span class="metric-value">${formatNumber(count)}</span>
                    </div>
                `).join('')}
            `;
            
            // Update System Resources
            const systemResources = document.getElementById('system-resources');
            const cpu = health.checks?.cpu || {};
            const memory = health.checks?.memory || {};
            const disk = health.checks?.disk || {};
            
            systemResources.innerHTML = `
                <div class="metric">
                    <span class="metric-label">CPU (${cpu.cores || 0} Cores)</span>
                    <span class="metric-value">${cpu.usage_percent || 0}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${getProgressClass(cpu.usage_percent || 0)}" style="width: ${cpu.usage_percent || 0}%"></div>
                </div>
                
                <div class="metric" style="margin-top: 15px;">
                    <span class="metric-label">RAM</span>
                    <span class="metric-value">${memory.used_percent || 0}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${getProgressClass(memory.used_percent || 0)}" style="width: ${memory.used_percent || 0}%"></div>
                </div>
                
                <div class="metric" style="margin-top: 15px;">
                    <span class="metric-label">Festplatte</span>
                    <span class="metric-value">${disk.free_gb || 0} GB frei</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${getProgressClass(disk.used_percent || 0)}" style="width: ${disk.used_percent || 0}%"></div>
                </div>
            `;
            
            // Update Crawl Statistics
            const crawlStats = document.getElementById('crawl-stats');
            const crawls = metrics.crawls || {};
            const successRate = crawls.success_rate || 0;
            
            crawlStats.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Gesamt Crawls</span>
                    <span class="metric-value">${formatNumber(crawls.total || 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Erfolgreich</span>
                    <span class="metric-value">${formatNumber(crawls.successful || 0)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Erfolgsrate</span>
                    <span class="metric-value">${successRate.toFixed(1)}%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill ${successRate > 90 ? 'good' : successRate > 70 ? 'warning' : 'critical'}" 
                         style="width: ${successRate}%"></div>
                </div>
            `;
            
            // Update Redis Status
            const redisStatus = document.getElementById('redis-status');
            const redisCheck = health.checks?.redis || {};
            
            redisStatus.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value">
                        <span class="status-indicator ${getStatusClass(redisCheck.status)}"></span>
                        ${redisCheck.connected ? 'Verbunden' : 'Getrennt'}
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Version</span>
                    <span class="metric-value">${redisCheck.version || 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Speicher</span>
                    <span class="metric-value">${redisCheck.used_memory_human || 'N/A'}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Verbindungen</span>
                    <span class="metric-value">${redisCheck.connected_clients || 0}</span>
                </div>
            `;
            
            // Update timestamp
            document.getElementById('last-update').textContent = 
                `Letzte Aktualisierung: ${new Date().toLocaleString('de-DE')}`;
        }
        
        function showError(message) {
            const cards = document.querySelectorAll('.card > div[id]');
            cards.forEach(card => {
                card.innerHTML = `<div class="error-message">${message}</div>`;
            });
        }
        
        // Countdown timer
        setInterval(() => {
            countdown--;
            if (countdown <= 0) {
                countdown = 10;
                fetchData();
            }
            document.getElementById('countdown').textContent = countdown;
        }, 1000);
        
        // Initial load
        fetchData();
        
        // Auto refresh
        setInterval(fetchData, REFRESH_INTERVAL);
    </script>
</body>
</html>
    """

    return dashboard_html
