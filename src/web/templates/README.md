# Flask Templates

> **Status**: Bereit für Session 2 Implementation

## 📁 Geplante Struktur

```
templates/
├── base.html              # Base Template mit Navigation (Session 2)
├── index.html            # Startseite (Session 2)
├── public/
│   ├── search.html       # Such-Interface (Session 2)
│   ├── results.html      # Ergebnis-Liste (Session 2)
│   └── decision.html     # Detail-Ansicht (Session 2)
├── admin/
│   ├── dashboard.html    # Admin Dashboard (Session 4)
│   └── crawler.html      # Crawler Control (Session 4)
├── auth/
│   ├── login.html        # Login-Formular (Session 4)
│   └── logout.html       # Logout-Seite (Session 4)
└── partials/
    ├── pagination.html   # Pagination Component (Session 2)
    ├── filters.html      # Filter-Sidebar (Session 2)
    └── stats.html        # Statistik-Widget (Session 3)
```

## 🎨 Template-Engine

- **Jinja2** (bereits installiert mit Flask)
- **Bootstrap 5** via CDN (Session 2)
- **Keine Build-Tools** nötig (kein npm/webpack)

## 📝 Nächste Schritte

Siehe `docs/phases/ui/sessions/SESSION_2_TEMPLATES.md` für die vollständige Implementation.