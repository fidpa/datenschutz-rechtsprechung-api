# Quick Start

> **Status: Alpha.** Single-developer engineering showcase. The verifiable
> path below (unit tests + walking skeleton) is green on a fresh checkout;
> the full stack is documented but not production-hardened. See the
> [README](../../README.md) for scope and Known Issues.

## 1. Fastest verifiable path (no services)

This is the path the CI runs and the one to use for a first look. It needs
only Python 3.10–3.12 — no PostgreSQL, no Redis, no network.

```bash
git clone https://github.com/fidpa/datenschutz-rechtsprechung-api.git
cd datenschutz-rechtsprechung-api
pip install -r requirements.txt
python -m spacy download de_core_news_sm   # optional: enables spaCy-NER anonymisation

# Offline smoke test — anonymiser + GDPR/BDSG reference extractor on a fixture
python examples/walking_skeleton.py

# Curated unit suite (in-memory SQLite, no external services)
pytest -v --cov=src
```

`pytest` runs the stable unit subset and is green by design. Integration
tests and a set of older, drifted unit tests are excluded transparently —
see [`tests/README.md`](../../tests/README.md) for the exact scope and how to
run *everything*. Coverage is reported but not asserted (it is low and
honest for an Alpha).

## 2. Full stack (PostgreSQL + Redis)

The persistence layer uses PostgreSQL-only features (German full-text
search, `UUID`/`ARRAY`/`TSVECTOR`), so the full pipeline and the
integration tests require a real database.

```bash
cp .env.example .env          # edit values; never commit .env

# Local development: start PostgreSQL + Redis only
docker compose up -d          # starts the `postgres` and `redis` services

# Initialise schema, German FTS triggers and indexes
python scripts/init_db.py

# Run the API (FastAPI, ~28 endpoints under /api/v1)
uvicorn src.api.main:app --reload
# → http://localhost:8000/docs   (OpenAPI UI)
# → http://localhost:8000/health

# Run the Flask admin UI (separate process)
python src/web/development_server.py
# → http://localhost:5001/admin/dashboard
```

Run the integration tests against the running stack:

```bash
pytest tests/integration
```

### First-run admin credentials

The admin UI bootstraps with the default login **`admin@admin.com` /
`admin`**. This is a **local bootstrap only** — change it immediately and
never expose a default-credentialed instance. The full hardening checklist
is in [`SECURITY.md`](../../SECURITY.md).

## 3. Container build (optional)

A generic `docker/Dockerfile` backs the `api` / `worker` / `scheduler`
services; production deployments use `docker-compose.production.yml`, which
reads every secret from the environment (`${ENV}` interpolation, no secrets
committed). The container path is spot-checked, not end-to-end validated —
the pytest path above is the authoritative verifiable Quickstart (see README
§ Known Issues).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `import spacy` fails | `numpy` must stay `<2.0` (pinned in `requirements.txt`); reinstall with `pip install -r requirements.txt` |
| spaCy model missing | `python -m spacy download de_core_news_sm` (the regex fallback works without it) |
| DB connection error | ensure `docker compose up -d` is running, then re-run `python scripts/init_db.py` |
| Rate-limit / 429 from GDPRhub | lower `GDPRHUB_RATE_LIMIT` in `.env` (default 0.5 req/s) |

## Next steps

- Architecture & schema: [`docs/architecture/database.md`](../architecture/database.md)
- Compliance & legal basis (German): [`docs/compliance/`](../compliance/)
- Contributing & quality gates: [`CONTRIBUTING.md`](../../CONTRIBUTING.md)
