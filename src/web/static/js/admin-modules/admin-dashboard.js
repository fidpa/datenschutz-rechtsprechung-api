/**
 * Datenschutz-Rechtsprechung API Admin Dashboard JavaScript Module
 * Admin-Dashboard-Funktionalität
 * Handles dashboard interactions and live updates
 */

(function() {
    'use strict';

    // Configuration
    const config = {
        refreshInterval: 30000, // 30 seconds
        statsEndpoint: '/admin/api/stats',
        animationDuration: 800,
        maxRetries: 3
    };

    // State
    let refreshTimer = null;
    let isRefreshing = false;
    let retryCount = 0;

    /**
     * Initialize dashboard functionality
     */
    function init() {
        // Setup event listeners
        setupEventListeners();
        
        // Start auto-refresh
        startAutoRefresh();
        
        // Initial animation for stats
        animateStats();
        
        // Setup theme change listener
        document.addEventListener('themeChanged', handleThemeChange);
    }

    /**
     * Setup event listeners
     */
    function setupEventListeners() {
        // Manual refresh button
        const refreshBtn = document.querySelector('[data-action="refresh"]');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshStats);
        }

        // Page visibility change
        document.addEventListener('visibilitychange', handleVisibilityChange);
        
        // Export buttons
        document.querySelectorAll('[data-export]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const format = e.target.dataset.export;
                handleExport(format, e.target);
            });
        });
        
        // Crawl buttons
        document.querySelectorAll('[data-crawl]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const source = e.target.dataset.crawl;
                handleCrawl(source, e.target);
            });
        });
    }

    /**
     * Start automatic stats refresh
     */
    function startAutoRefresh() {
        refreshTimer = setInterval(refreshStats, config.refreshInterval);
    }

    /**
     * Stop automatic refresh
     */
    function stopAutoRefresh() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
    }

    /**
     * Refresh dashboard statistics
     */
    async function refreshStats() {
        if (isRefreshing) return;
        
        isRefreshing = true;
        showLoadingState();
        
        try {
            const response = await fetch(config.statsEndpoint);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const stats = await response.json();
            updateStats(stats);
            retryCount = 0; // Reset retry count on success
            
        } catch (error) {
            console.error('Error refreshing stats:', error);
            retryCount++;
            
            if (retryCount < config.maxRetries) {
                showNotification('Verbindungsfehler - Wiederhole...', 'warning');
                setTimeout(refreshStats, 5000); // Retry after 5 seconds
            } else {
                showNotification('Fehler beim Aktualisieren der Statistiken', 'error');
                retryCount = 0;
            }
        } finally {
            isRefreshing = false;
            hideLoadingState();
        }
    }

    /**
     * Show loading state
     */
    function showLoadingState() {
        document.querySelectorAll('[data-stat]').forEach(element => {
            const loadingSpan = element.querySelector('.stat-loading');
            if (loadingSpan) {
                loadingSpan.style.display = 'inline-block';
            }
        });
    }

    /**
     * Hide loading state
     */
    function hideLoadingState() {
        document.querySelectorAll('[data-stat]').forEach(element => {
            const loadingSpan = element.querySelector('.stat-loading');
            if (loadingSpan) {
                loadingSpan.style.display = 'none';
            }
        });
    }

    /**
     * Update stats in the UI
     */
    function updateStats(stats) {
        // Update each stat element
        document.querySelectorAll('[data-stat]').forEach(element => {
            const statPath = element.dataset.stat.split('.');
            let value = stats;
            
            // Navigate through nested object
            for (const key of statPath) {
                value = value?.[key];
            }
            
            if (value !== undefined) {
                // Find the value span within the element
                const valueSpan = element.querySelector('.metric-value') || element;
                const currentValue = parseInt(valueSpan.textContent) || 0;
                
                animateValue(valueSpan, currentValue, value);
            }
        });
        
        // Update timestamp
        updateLastRefreshTime();
        
        // Update charts if they exist
        updateCharts(stats);
    }

    /**
     * Animate number changes with easing
     */
    function animateValue(element, start, end) {
        const duration = config.animationDuration;
        const range = end - start;
        
        // Skip animation if difference is minimal
        if (Math.abs(range) < 2) {
            element.textContent = end;
            return;
        }
        
        const startTime = performance.now();
        
        function updateValue(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Easing function for smooth animation
            const easeOutQuart = 1 - Math.pow(1 - progress, 4);
            const current = start + (range * easeOutQuart);
            
            element.textContent = Math.round(current);
            
            if (progress < 1) {
                requestAnimationFrame(updateValue);
            }
        }
        
        requestAnimationFrame(updateValue);
    }
    
    /**
     * Update last refresh timestamp
     */
    function updateLastRefreshTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('de-DE', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
        
        const timestampEl = document.querySelector('[data-last-refresh]');
        if (timestampEl) {
            timestampEl.textContent = timeString;
        }
    }

    /**
     * Initial stats animation
     */
    function animateStats() {
        document.querySelectorAll('.metric-value').forEach((element, index) => {
            const value = parseInt(element.textContent) || 0;
            element.textContent = '0';
            
            // Staggered animation
            setTimeout(() => {
                animateValue(element, 0, value);
            }, index * 200);
        });
    }

    /**
     * Handle export requests
     */
    async function handleExport(format, button) {
        const originalContent = button.innerHTML;
        const loadingContent = '<span class="spinner-border spinner-border-sm me-2"></span>Exportiere...';
        
        try {
            button.disabled = true;
            button.innerHTML = loadingContent;
            
            const response = await fetch('/admin/trigger_export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ type: format })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showNotification(`${format.toUpperCase()}-Export erfolgreich gestartet`, 'success');
                if (data.download_url) {
                    // Download file
                    window.open(data.download_url, '_blank');
                }
            } else {
                showNotification(data.error || 'Export fehlgeschlagen', 'error');
            }
            
        } catch (error) {
            console.error('Export error:', error);
            showNotification('Export-Fehler: ' + error.message, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    }

    /**
     * Handle crawl requests
     */
    async function handleCrawl(source, button) {
        const originalContent = button.innerHTML;
        const loadingContent = '<span class="spinner-border spinner-border-sm me-2"></span>Startet...';
        
        try {
            button.disabled = true;
            button.innerHTML = loadingContent;
            
            const response = await fetch('/admin/trigger_crawl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ source: source })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showNotification(`${source} Crawler erfolgreich gestartet`, 'info');
            } else {
                showNotification(data.error || 'Crawler-Start fehlgeschlagen', 'error');
            }
            
        } catch (error) {
            console.error('Crawl error:', error);
            showNotification('Crawler-Fehler: ' + error.message, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    }

    /**
     * Handle page visibility changes
     */
    function handleVisibilityChange() {
        if (document.hidden) {
            stopAutoRefresh();
        } else {
            startAutoRefresh();
            refreshStats();
        }
    }

    /**
     * Handle theme changes
     */
    function handleThemeChange(event) {
        const theme = event.detail.theme;
        
        // Update chart colors if charts exist
        if (window.Chart) {
            updateChartTheme(theme);
        }
    }

    /**
     * Update chart colors for theme
     */
    function updateChartTheme(theme) {
        // This would update Chart.js instances with new colors
        // Implementation depends on chart instances available
        console.log('Theme changed to:', theme);
    }

    /**
     * Update charts with new data
     */
    function updateCharts(stats) {
        // Implementation for updating Chart.js instances
        // This would be called when stats are refreshed
    }

    /**
     * Get CSRF token from page
     */
    function getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }

    /**
     * Show notification toast
     */
    function showNotification(message, type = 'info') {
        const alertClass = {
            'success': 'alert-success',
            'error': 'alert-danger', 
            'warning': 'alert-warning',
            'info': 'alert-info'
        }[type] || 'alert-info';
        
        const iconClass = {
            'success': 'bi-check-circle',
            'error': 'bi-exclamation-triangle',
            'warning': 'bi-exclamation-triangle',
            'info': 'bi-info-circle'
        }[type] || 'bi-info-circle';
        
        // Create toast if Bootstrap is available
        if (typeof bootstrap !== 'undefined') {
            const toastHtml = `
                <div class="toast align-items-center border-0 ${alertClass}" role="alert" aria-live="assertive" aria-atomic="true" style="position: fixed; top: 20px; right: 20px; z-index: 1055;">
                    <div class="d-flex">
                        <div class="toast-body">
                            <i class="bi ${iconClass} me-2"></i>${message}
                        </div>
                        <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', toastHtml);
            const toast = new bootstrap.Toast(document.querySelector('.toast:last-child'));
            toast.show();
            
            // Remove toast element after it's hidden
            setTimeout(() => {
                const toastEl = document.querySelector('.toast:last-child');
                if (toastEl) toastEl.remove();
            }, 4000);
        } else {
            // Fallback alert
            alert(message);
        }
    }

    // Export functions for external use
    window.GDPRDashboard = {
        refresh: refreshStats,
        start: startAutoRefresh,
        stop: stopAutoRefresh,
        export: handleExport,
        crawl: handleCrawl
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();