/**
 * SVG Icon System für Phase 12.3 Mobile Performance Optimization
 * 
 * Ersetzt Bootstrap Icons mit optimierten SVG Sprites für bessere Performance
 */

class SvgIconSystem {
    constructor() {
        this.spriteLoaded = false;
        this.iconCache = new Map();
        this.spriteUrl = '/static/icons/sprite.svg';
        
        // Icon mapping Bootstrap → SVG sprite
        this.iconMap = {
            'bi-speedometer2': 'icon-speedometer',
            'bi-heart-pulse': 'icon-heart-pulse', 
            'bi-cpu': 'icon-cpu',
            'bi-bar-chart': 'icon-bar-chart',
            'bi-graph-up': 'icon-graph-up',
            'bi-activity': 'icon-activity',
            'bi-terminal': 'icon-terminal',
            'bi-clock-history': 'icon-clock-history',
            'bi-arrow-clockwise': 'icon-arrow-clockwise',
            'bi-moon-fill': 'icon-moon',
            'bi-exclamation-triangle': 'icon-exclamation-triangle'
        };
        
        this.init();
    }
    
    async init() {
        try {
            // Preload sprite für kritische Icons
            await this.loadSprite();
            
            // Replace critical Bootstrap icons sofort
            this.replaceCriticalIcons();
            
            // Progressive enhancement - replace andere icons nach load
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    this.replaceAllIcons();
                });
            } else {
                // Delayed replacement für non-critical icons
                setTimeout(() => this.replaceAllIcons(), 100);
            }
            
        } catch (error) {
            console.warn('SVG Icon System failed to initialize:', error);
            // Fallback: Keep Bootstrap icons
        }
    }
    
    async loadSprite() {
        if (this.spriteLoaded) return;
        
        try {
            // Inject sprite SVG into DOM für internal referencing
            const response = await fetch(this.spriteUrl);
            const svgText = await response.text();
            
            // Create hidden container
            const container = document.createElement('div');
            container.style.display = 'none';
            container.innerHTML = svgText;
            document.body.insertBefore(container, document.body.firstChild);
            
            this.spriteLoaded = true;
            console.log('SVG sprite loaded successfully');
            
        } catch (error) {
            console.error('Failed to load SVG sprite:', error);
            throw error;
        }
    }
    
    createSvgIcon(iconId, className = '', size = 16) {
        if (!this.spriteLoaded) {
            console.warn('SVG sprite not loaded yet');
            return null;
        }
        
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', size);
        svg.setAttribute('height', size);
        svg.setAttribute('fill', 'currentColor');
        svg.setAttribute('class', className);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-hidden', 'true');
        
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', `#${iconId}`);
        
        svg.appendChild(use);
        return svg;
    }
    
    replaceCriticalIcons() {
        // Nur kritische Icons für initial load performance
        const criticalSelectors = [
            'h1 .bi-speedometer2', // Dashboard title
            '.health-score-display .bi-heart-pulse', // Health widget
            '.metric-card .bi', // Metric cards
            'button .bi-arrow-clockwise' // Refresh buttons
        ];
        
        criticalSelectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => this.replaceBootstrapIcon(el));
        });
        
        console.log('Critical icons replaced with SVG');
    }
    
    replaceAllIcons() {
        // Progressive replacement aller anderen Icons
        Object.keys(this.iconMap).forEach(bootstrapClass => {
            const elements = document.querySelectorAll(`.${bootstrapClass}`);
            elements.forEach(el => this.replaceBootstrapIcon(el));
        });
        
        console.log('All Bootstrap icons replaced with SVG sprites');
    }
    
    replaceBootstrapIcon(element) {
        if (!element || !this.spriteLoaded) return;
        
        // Find matching icon mapping
        let svgIconId = null;
        
        for (const [bootstrapClass, spriteId] of Object.entries(this.iconMap)) {
            if (element.classList.contains(bootstrapClass)) {
                svgIconId = spriteId;
                break;
            }
        }
        
        if (!svgIconId) return;
        
        // Preserve original classes (except Bootstrap icon classes)
        const preservedClasses = Array.from(element.classList)
            .filter(cls => !cls.startsWith('bi-') && cls !== 'bi')
            .join(' ');
        
        // Create SVG replacement
        const svgIcon = this.createSvgIcon(svgIconId, preservedClasses, 16);
        
        if (svgIcon) {
            // Replace element
            element.parentNode.replaceChild(svgIcon, element);
        }
    }
    
    // Utility für dynamisches Icon-Loading
    getIcon(iconName, className = '', size = 16) {
        const spriteId = this.iconMap[iconName] || iconName;
        return this.createSvgIcon(spriteId, className, size);
    }
    
    // Performance monitoring
    measureIconLoadPerformance() {
        if (!window.performance) return;
        
        const timing = performance.timing;
        const spriteLoadTime = timing.loadEventEnd - timing.domContentLoaded;
        
        console.log(`SVG Icon System performance: ${spriteLoadTime}ms`);
        
        // Count replaced icons
        const svgIcons = document.querySelectorAll('svg[role="img"]').length;
        console.log(`${svgIcons} icons replaced with SVG sprites`);
        
        return {
            loadTime: spriteLoadTime,
            iconCount: svgIcons
        };
    }
}

// Global instance
window.svgIconSystem = new SvgIconSystem();

// Export für module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SvgIconSystem;
}