/**
 * Chart Loader Module - Dynamic Chart.js Loading für Code Splitting
 * 
 * Phase 12.3 Performance Optimization:
 * - Dynamic imports für Chart.js
 * - Bundle size reduction
 * - Lazy loading integration
 */

class ChartLoader {
    constructor() {
        this.chartJsLoaded = false;
        this.loadingPromise = null;
        this.chartInstances = new Map();
        
        // Performance tracking
        this.loadStartTime = 0;
        this.metrics = {
            loadTime: 0,
            bundleSize: 0,
            chartsCreated: 0
        };
    }
    
    /**
     * Dynamically load Chart.js only when needed
     */
    async loadChartJS() {
        if (this.chartJsLoaded) {
            return window.Chart;
        }
        
        // Prevent multiple simultaneous loads
        if (this.loadingPromise) {
            return this.loadingPromise;
        }
        
        this.loadStartTime = performance.now();
        
        this.loadingPromise = this._loadChartJSScript();
        
        try {
            await this.loadingPromise;
            this.chartJsLoaded = true;
            
            // Performance metrics
            this.metrics.loadTime = performance.now() - this.loadStartTime;
            console.log(`📊 Chart.js loaded dynamically in ${Math.round(this.metrics.loadTime)}ms`);
            
            return window.Chart;
        } catch (error) {
            console.error('Failed to load Chart.js:', error);
            this.loadingPromise = null;
            throw error;
        }
    }
    
    async _loadChartJSScript() {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (window.Chart) {
                resolve(window.Chart);
                return;
            }
            
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js';
            script.async = true;
            
            script.onload = () => {
                if (window.Chart) {
                    resolve(window.Chart);
                } else {
                    reject(new Error('Chart.js loaded but not available'));
                }
            };
            
            script.onerror = () => {
                reject(new Error('Failed to load Chart.js script'));
            };
            
            // Add to head for faster loading
            document.head.appendChild(script);
        });
    }
    
    /**
     * Create chart with automatic Chart.js loading
     */
    async createChart(canvasId, config, options = {}) {
        try {
            // Load Chart.js if needed
            const Chart = await this.loadChartJS();
            
            const canvas = document.getElementById(canvasId);
            if (!canvas) {
                throw new Error(`Canvas element '${canvasId}' not found`);
            }
            
            const ctx = canvas.getContext('2d');
            
            // Apply performance optimizations based on network
            const optimizedConfig = this._optimizeChartConfig(config, options);
            
            // Create chart instance
            const chartInstance = new Chart(ctx, optimizedConfig);
            
            // Cache for future reference
            this.chartInstances.set(canvasId, chartInstance);
            this.metrics.chartsCreated++;
            
            console.log(`📈 Chart '${canvasId}' created successfully`);
            return chartInstance;
            
        } catch (error) {
            console.error(`Failed to create chart '${canvasId}':`, error);
            throw error;
        }
    }
    
    /**
     * Optimize chart config based on network conditions
     */
    _optimizeChartConfig(config, options) {
        const optimized = JSON.parse(JSON.stringify(config)); // Deep clone
        
        // Network-aware optimizations
        const connection = navigator.connection;
        const isSlowConnection = connection && 
            ['slow-2g', '2g', '3g'].includes(connection.effectiveType);
        
        if (isSlowConnection || options.reducedPerformance) {
            // Disable animations on slow connections
            if (optimized.options) {
                optimized.options.animation = false;
                optimized.options.hover = optimized.options.hover || {};
                optimized.options.hover.animationDuration = 0;
                
                // Reduce responsiveness checks
                optimized.options.responsive = true;
                optimized.options.maintainAspectRatio = false;
                
                console.log('🐌 Applied low-performance optimizations for slow connection');
            }
        }
        
        // Mobile optimizations
        if (window.innerWidth < 768) {
            if (optimized.options && optimized.options.plugins && optimized.options.plugins.legend) {
                optimized.options.plugins.legend.labels = optimized.options.plugins.legend.labels || {};
                optimized.options.plugins.legend.labels.padding = 10; // Reduced padding
                optimized.options.plugins.legend.labels.usePointStyle = true; // Smaller legend items
            }
            
            // Reduce tooltip complexity on mobile
            if (optimized.options && optimized.options.plugins) {
                optimized.options.plugins.tooltip = optimized.options.plugins.tooltip || {};
                optimized.options.plugins.tooltip.mode = 'nearest';
                optimized.options.plugins.tooltip.intersect = true;
            }
        }
        
        return optimized;
    }
    
    /**
     * Destroy chart and clean up
     */
    destroyChart(canvasId) {
        const chart = this.chartInstances.get(canvasId);
        if (chart) {
            chart.destroy();
            this.chartInstances.delete(canvasId);
            console.log(`🗑️ Chart '${canvasId}' destroyed`);
        }
    }
    
    /**
     * Update existing chart data
     */
    updateChart(canvasId, newData, updateMode = 'none') {
        const chart = this.chartInstances.get(canvasId);
        if (!chart) {
            console.warn(`Chart '${canvasId}' not found for update`);
            return false;
        }
        
        try {
            // Update data
            if (newData.labels) {
                chart.data.labels = newData.labels;
            }
            
            if (newData.datasets) {
                chart.data.datasets = newData.datasets;
            }
            
            // Update with performance consideration
            chart.update(updateMode);
            
            console.log(`📊 Chart '${canvasId}' updated`);
            return true;
            
        } catch (error) {
            console.error(`Failed to update chart '${canvasId}':`, error);
            return false;
        }
    }
    
    /**
     * Get all performance metrics
     */
    getMetrics() {
        return {
            ...this.metrics,
            chartsActive: this.chartInstances.size,
            memoryUsage: this._estimateMemoryUsage()
        };
    }
    
    _estimateMemoryUsage() {
        // Rough estimation basierend auf chart count
        const baseMemoryPerChart = 500; // KB estimate
        return this.chartInstances.size * baseMemoryPerChart;
    }
    
    /**
     * Batch create multiple charts efficiently
     */
    async createCharts(chartConfigs) {
        const Chart = await this.loadChartJS(); // Load once for all charts
        
        const results = [];
        
        for (const config of chartConfigs) {
            try {
                const chart = await this.createChart(config.canvasId, config.config, config.options);
                results.push({ canvasId: config.canvasId, chart, success: true });
            } catch (error) {
                console.error(`Failed to create chart ${config.canvasId}:`, error);
                results.push({ canvasId: config.canvasId, error, success: false });
            }
        }
        
        console.log(`📊 Batch created ${results.filter(r => r.success).length}/${results.length} charts`);
        return results;
    }
}

// Global instance
window.chartLoader = new ChartLoader();

// Legacy compatibility
window.loadChartJS = () => window.chartLoader.loadChartJS();

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChartLoader;
}