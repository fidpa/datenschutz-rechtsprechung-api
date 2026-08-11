# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] — 2026-08-11

### Fixed

- **19 scripts under `scripts/` are executable again.** `scripts/backup-system.sh`,
  `scripts/backup/*.sh`, `scripts/security/generate_secrets.sh`,
  `scripts/setup-*.sh`, `scripts/start*.sh`, `scripts/test-production.sh` and the
  remaining operational scripts listed under `scripts/` had lost their `+x` bit
  (mode `644` instead of `755`), so running them directly (`./scripts/foo.sh`)
  failed with `Permission denied` even though the shebang and content were
  correct. No script content changed.

## [0.1.1] — 2026-08-08

A maintenance release with no functional changes to the crawler, the API or the
anonymisation pipeline. It repairs the parts of the project that were supposed
to catch mistakes and weren't: the CI had failed on every run since the initial
release, and the version the software reported about itself was invented.

### Fixed

- **The project version is now declared once, in `pyproject.toml`.** Four places
  carried a version and three of them were wrong: the FastAPI app advertised
  `1.0.0` in `/docs` and `/openapi.json`, and `src/logging/` plus
  `scripts/claude_analysis/` carried `12.1.0` — a number that never corresponded
  to a release and that was stamped onto every log event. A new `src/_version.py`
  reads `pyproject.toml` (falling back to installed distribution metadata) and is
  the only reader; everything else imports `PROJECT_VERSION` from it.
- **Three `NameError` defects in scripts and tests.**
  `scripts/apply_staging_migration.py` used `json` and `text` without importing
  them (both on paths that run outside `--dry-run`), and
  `tests/integration/ui/test_assets.py` used `json` without importing it.
- **`flake8` gates the whole tree again.** `ci.yml` runs `flake8 .`, but `.flake8`
  documented that only `src` was linted and carried no waivers for the rest, so
  the job had failed on every run since the initial release — which is why the
  three undefined names above went unnoticed. Housekeeping codes (`F401`, `F841`)
  are now waived per directory for `tests/` and `scripts/`, keeping correctness
  checks such as `F821` active everywhere.
- Removed a redefined `Path` import in three `scripts/admin.py` subcommands and a
  duplicate `structlog` import in `scripts/setup_fulltext_search.py`.
- Replaced `!= None` with `.is_not(None)` in a SQLAlchemy filter
  (`tests/integration/test_real_import.py`).
- **The test suite runs on current Python 3.12 again.** Python 3.12.4 made
  `recursive_guard` a keyword-only argument of `ForwardRef._evaluate()`, but the
  `pydantic.v1` compatibility shim — which spaCy reaches through thinc — still
  called it positionally up to pydantic 2.7.0. On the CI runner (3.12.13) that
  aborted collection of `tests/test_anonymizer.py` and took the whole `test` job
  with it; on a 3.12.3 workstation the same tree passed. `pydantic` is now
  pinned to `2.7.4`, the first release carrying the fix.
- **The admin CLI starts from a clean install.** `scripts/admin.py` imports
  `rich`, but no requirements file listed it, so following the documented setup
  and running the tool produced a `ModuleNotFoundError`. No test imports that
  module, which is why CI never noticed. `rich==13.7.1` is now pinned.

### Changed

- **`black` is pinned to major version 23 via `required-version`** in
  `pyproject.toml`, matching `requirements.txt` and CI. A newer `black` now stops
  with an error instead of silently reformatting: 26.3.1 wanted to reformat 50
  files in a tree that 23.11.0 considers clean.
- `.gitignore` now covers `.claude/`.

### Security

- **The five MD5 call sites are marked `usedforsecurity=False`.** They compute
  fallback identifiers, duplicate-detection fingerprints, a resume file
  fingerprint and cache keys — none of them a security digest. The annotation
  says so in code rather than in a comment nobody reads, and clears bandit's
  five `B324` HIGH findings (`src/collectors/base.py`,
  `src/importers/swiss_datasets.py`, `src/processors/deduplicator.py`,
  `src/processors/resume_manager.py`, `src/utils/cache.py`). No hashing
  behaviour changes.

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
