# Legacy Test Scripts Archive

**Datum**: 16.08.2025  
**Grund**: Post Phase 12.3 Konsolidierung

## Archivierte Scripts

### Phase-spezifische Test-Scripts (veraltet)
- `test_phase4.py` - Phase 4 PDF-Extraktion Tests (ersetzt durch reguläre Tests)
- `phase6_demo.py` - Phase 6 Demo-Script (Funktionalität in regulären Tools)
- `test_new_features.py` - Ad-hoc Feature-Tests (in Test-Suite integriert)
- `test_openlegaldata.py` - OpenLegalData Tests (in Test-Suite verfügbar)

## Warum archiviert?

1. **Redundanz**: Funktionalität in regulären Test-Suites verfügbar
2. **Verwirrung**: Phase-spezifische Scripts verwirren nach Projekt-Abschluss
3. **Wartung**: Reduziert Script-Proliferation
4. **Klarheit**: Fokus auf aktive, wartbare Scripts

## Aktive Test-Scripts (behalten)

- `test_api.py` - API-Integration Tests
- `test_web_ui.py` - Web-UI Tests
- `admin.py` - Admin CLI-Tool mit integrierten Tests

## Wiederherstellung

Falls benötigt können Scripts mit git history wiederhergestellt werden:
```bash
git log --follow scripts/archive/legacy-tests/
```

**Status**: Archiviert, nicht gelöscht - verfügbar bei Bedarf.