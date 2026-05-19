# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-18

### Added
- Initial public release as an engineering showcase.
- Multi-source collectors (`src/collectors/`): GDPRhub (HTML scraping) and OpenLegalData (API), with rate limiting (`RateLimiter`) in `src/collectors/base.py`. (robots.txt enforcement is designed but not yet implemented — see README Known Issues.)
- PDF-to-text conversion and German legal-document structure analysis (`src/converters/`, `src/processors/`).
- Two-stage anonymisation (spaCy NER primary, regex `SimpleGermanLegalAnonymizer` fallback) preserving legal terminology.
- PostgreSQL persistence with German full-text search and structured filters (`src/filters/`, `src/database.py`).
- FastAPI REST API (~28 endpoints, `src/api/`).
- Flask 3 admin web UI with flask-login (bcrypt) and CSRF protection (`src/web/`).
- Celery + Redis asynchronous task pipeline (`src/tasks/`).
- Local and production Docker Compose setups; production uses `${ENV}` interpolation.
- Compliance documentation (German) under `docs/compliance/` covering §60d UrhG TDM, scope, and anonymisation backends.
- Showcase project files: LICENSE (MIT), README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CI workflow.

### Notes
- This is the first public version; no prior public history is reconstructed.
- Quantitative figures from internal pre-release notes (decision counts, test coverage) are intentionally **not** carried into this changelog because they were not re-verified for public release.
