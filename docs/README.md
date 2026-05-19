# Documentation

Public documentation for the Datenschutz-Rechtsprechung API. The legal-domain documents are kept in
German on purpose — they track DACH statutes verbatim (see the note in the
top-level [README](../README.md)).

## Contents

| Path | Topic |
|------|-------|
| [`quickstart/QUICK_START.md`](quickstart/QUICK_START.md) | Local setup, bootstrap admin login, first run |
| [`architecture/database.md`](architecture/database.md) | PostgreSQL schema and full-text search design |
| [`compliance/GDPR_COMPLIANCE.md`](compliance/GDPR_COMPLIANCE.md) | Legal basis (§60d UrhG), data handling, contact placeholders |
| [`compliance/scope.md`](compliance/scope.md) | Which sources/statutes are in scope (incl. RIS Austria status) |
| [`compliance/ANONYMIZATION_BACKENDS.md`](compliance/ANONYMIZATION_BACKENDS.md) | spaCy NER vs. regex-fallback anonymisation |

This set is intentionally curated for the public release. It is not the full
historical project documentation.
