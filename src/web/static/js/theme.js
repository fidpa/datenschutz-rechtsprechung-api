// Datenschutz-Rechtsprechung API Theme Manager
(function() {
    'use strict';
    
    // Constants
    const THEME_KEY = 'gdpr-theme';
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';
    
    // Get stored theme or detect system preference
    function getPreferredTheme() {
        const stored = localStorage.getItem(THEME_KEY);
        if (stored) {
            return stored;
        }
        
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return THEME_DARK;
        }
        
        return THEME_LIGHT;
    }
    
    // Apply theme to document
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(THEME_KEY, theme);
        
        // Update toggle button state
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.setAttribute('data-theme', theme);
            const icon = toggle.querySelector('i');
            if (icon) {
                icon.className = theme === THEME_DARK ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
            }
        }
        
        // Update navbar brand icon if exists
        const navIcon = document.querySelector('.navbar-brand i');
        if (navIcon && theme === THEME_DARK) {
            navIcon.style.color = '#e2e8f0';
        } else if (navIcon) {
            navIcon.style.color = '';
        }
        
        // Trigger custom event for other components
        document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
    }
    
    // Toggle between themes
    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || THEME_LIGHT;
        const newTheme = currentTheme === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
        applyTheme(newTheme);
        
        // Show visual feedback
        showThemeToast(newTheme);
    }
    
    // Show theme change toast
    function showThemeToast(theme) {
        const message = theme === THEME_DARK ? 
            '<i class="bi bi-moon-fill me-2"></i>Dark Mode aktiviert' : 
            '<i class="bi bi-sun-fill me-2"></i>Light Mode aktiviert';
            
        // Create toast if Bootstrap is available
        if (typeof bootstrap !== 'undefined') {
            const toastHtml = `
                <div class="toast align-items-center border-0" role="alert" aria-live="assertive" aria-atomic="true" style="position: fixed; top: 20px; right: 20px; z-index: 1055;">
                    <div class="d-flex">
                        <div class="toast-body">${message}</div>
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
        }
    }
    
    // Initialize theme on page load
    function initTheme() {
        const theme = getPreferredTheme();
        applyTheme(theme);
        
        // Add click handler to toggle button
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                toggleTheme();
            });
        }
        
        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                // Only auto-switch if user hasn't manually set a preference
                if (!localStorage.getItem(THEME_KEY)) {
                    applyTheme(e.matches ? THEME_DARK : THEME_LIGHT);
                }
            });
        }
        
        // Add keyboard shortcut (Ctrl/Cmd + Shift + D)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
                e.preventDefault();
                toggleTheme();
            }
        });
    }
    
    // Export functions for external use
    window.GDPRTheme = {
        toggle: toggleTheme,
        apply: applyTheme,
        getCurrent: () => document.documentElement.getAttribute('data-theme') || THEME_LIGHT,
        constants: {
            LIGHT: THEME_LIGHT,
            DARK: THEME_DARK
        }
    };
    
    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
})();