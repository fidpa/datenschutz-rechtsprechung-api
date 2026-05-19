/**
 * Datenschutz-Rechtsprechung API Loading States Utility
 * Konsistente Loading-Indikatoren
 */

class LoadingStates {
    /**
     * Inline loading spinner for small elements
     */
    static inline() {
        return '<span class="loading-spinner"><i class="bi bi-arrow-clockwise fa-spin"></i></span>';
    }
    
    /**
     * Skeleton loader for content placeholders
     */
    static skeleton(lines = 2) {
        let skeletons = '';
        for (let i = 0; i < lines; i++) {
            const isShort = i % 2 === 1;
            skeletons += `<div class="skeleton-line ${isShort ? 'short' : ''}"></div>`;
        }
        return `<div class="skeleton-loader">${skeletons}</div>`;
    }
    
    /**
     * Button loading state with Bootstrap spinner
     */
    static button(text = 'Wird geladen...') {
        return `<span><span class="spinner-border spinner-border-sm me-2"></span>${text}</span>`;
    }
    
    /**
     * Replace button content with loading state
     */
    static setButtonLoading(button, loadingText = 'Wird geladen...') {
        button.disabled = true;
        button.dataset.originalContent = button.innerHTML;
        button.innerHTML = this.button(loadingText);
        button.classList.add('loading');
    }
    
    /**
     * Restore button to original state
     */
    static resetButton(button) {
        button.disabled = false;
        button.classList.remove('loading');
        if (button.dataset.originalContent) {
            button.innerHTML = button.dataset.originalContent;
            delete button.dataset.originalContent;
        }
    }
    
    /**
     * Full page loading overlay
     */
    static overlay(message = 'Lade Daten...') {
        return `
            <div class="loading-overlay">
                <div class="loading-content">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;"></div>
                    <p class="mt-3">${message}</p>
                </div>
            </div>
        `;
    }
    
    /**
     * Card loading state for dashboard cards
     */
    static card(title = 'Lädt...') {
        return `
            <div class="card-loading">
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm me-2"></div>
                    <span>${title}</span>
                </div>
                <div class="skeleton-loader mt-2">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                </div>
            </div>
        `;
    }
    
    /**
     * Table loading state
     */
    static table(rows = 3, cols = 4) {
        let tableHtml = '<div class="table-loading"><table class="table"><tbody>';
        
        for (let i = 0; i < rows; i++) {
            tableHtml += '<tr>';
            for (let j = 0; j < cols; j++) {
                const isShort = j % 2 === 1;
                tableHtml += `<td><div class="skeleton-line ${isShort ? 'short' : ''}"></div></td>`;
            }
            tableHtml += '</tr>';
        }
        
        tableHtml += '</tbody></table></div>';
        return tableHtml;
    }
    
    /**
     * Chart loading state
     */
    static chart(height = '200px') {
        return `
            <div class="chart-loading" style="height: ${height}; display: flex; align-items: center; justify-content: center;">
                <div class="text-center">
                    <div class="spinner-border text-primary mb-2"></div>
                    <div>Lade Chart-Daten...</div>
                </div>
            </div>
        `;
    }
    
    /**
     * Progress bar loading
     */
    static progress(percent = 0, text = '') {
        return `
            <div class="progress-loading">
                <div class="progress mb-2">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         style="width: ${percent}%"></div>
                </div>
                ${text ? `<small class="text-muted">${text}</small>` : ''}
            </div>
        `;
    }
    
    /**
     * Stats loading for metric cards
     */
    static stats() {
        return `
            <div class="stats-loading">
                <div class="skeleton-line short mb-2"></div>
                <div class="skeleton-line"></div>
            </div>
        `;
    }
    
    /**
     * List loading state
     */
    static list(items = 3) {
        let listHtml = '<div class="list-loading">';
        
        for (let i = 0; i < items; i++) {
            listHtml += `
                <div class="list-item-loading mb-2 p-2 border rounded">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short mt-1"></div>
                </div>
            `;
        }
        
        listHtml += '</div>';
        return listHtml;
    }
    
    /**
     * Show loading state for element
     */
    static show(element, type = 'inline', ...args) {
        if (!element) return;
        
        element.dataset.originalContent = element.innerHTML;
        element.classList.add('loading');
        
        switch (type) {
            case 'skeleton':
                element.innerHTML = this.skeleton(...args);
                break;
            case 'card':
                element.innerHTML = this.card(...args);
                break;
            case 'table':
                element.innerHTML = this.table(...args);
                break;
            case 'chart':
                element.innerHTML = this.chart(...args);
                break;
            case 'stats':
                element.innerHTML = this.stats();
                break;
            case 'list':
                element.innerHTML = this.list(...args);
                break;
            default:
                element.innerHTML = this.inline();
        }
    }
    
    /**
     * Hide loading state for element
     */
    static hide(element) {
        if (!element) return;
        
        element.classList.remove('loading');
        if (element.dataset.originalContent) {
            element.innerHTML = element.dataset.originalContent;
            delete element.dataset.originalContent;
        }
    }
    
    /**
     * Auto-timeout loading states
     */
    static autoTimeout(element, type = 'inline', timeout = 10000, ...args) {
        this.show(element, type, ...args);
        
        setTimeout(() => {
            if (element.classList.contains('loading')) {
                this.hide(element);
                element.innerHTML = '<div class="text-muted">Timeout beim Laden</div>';
            }
        }, timeout);
    }
}

// Export for use in other modules
window.LoadingStates = LoadingStates;