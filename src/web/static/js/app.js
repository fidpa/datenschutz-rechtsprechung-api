// Basic JavaScript für Datenschutz-Rechtsprechung API

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts mit unterschiedlichen Zeiten
    
    // Success-Alerts: 3 Sekunden
    const successAlerts = document.querySelectorAll('.alert-success');
    successAlerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 3000);
    });
    
    // Warning/Info-Alerts: 5 Sekunden  
    const warningAlerts = document.querySelectorAll('.alert-warning, .alert-info');
    warningAlerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // Error/Danger-Alerts: Bleiben bis manuell geschlossen
    
    // Loading-State für Formulare
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                const originalContent = submitBtn.innerHTML;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Lädt...';
                
                // Fallback: Button nach 10 Sekunden wieder aktivieren
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalContent;
                }, 10000);
            }
        });
    });
});