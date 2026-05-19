# Tests

> **Status: Alpha.** The default `pytest` run is curated to the stable,
> service-free unit subset and is green on a fresh checkout. Coverage is
> reported but **not asserted** — it is low and honest for an Alpha. Run
> `pytest --cov=src` to measure your checkout.

## Test scope

`pytest` (config in `pytest.ini`, scoping in `conftest.py`) runs only the
unit tests that pass without external services. Two groups are excluded
**transparently** — nothing is silently dropped:

| Group | Mechanism | Why | How to run it |
|---|---|---|---|
| Integration tests (`tests/integration/**`) | `collect_ignore_glob` in `conftest.py` | Need a real **PostgreSQL + Redis**. The ORM schema uses PostgreSQL-only column types (`UUID`/`ARRAY`/`TSVECTOR`) that in-memory SQLite cannot create. | `pytest tests/integration` against a running stack (`docker compose up -d` + `python scripts/init_db.py`) |
| 3 import-broken modules (`test_legal_parser.py`, `test_pdf_extractor.py`, `test_load.py`) | `collect_ignore` in `conftest.py` | Stale symbols / legacy harness / load test needing a live API. | fix-then-unquarantine (see below) |
| ~33 drifted unit tests | `_QUARANTINE` skip-list in `conftest.py` (visible `SKIPPED` with reason) | Older tests drifted from the current model/API during the project's evolution and rebrand, or require PostgreSQL. | `pytest - rs` shows each skip + reason |

Run everything (expect failures — see below):

```bash
pytest -p no:cacheprovider -o addopts="" tests
```

## Why the quarantine

This project predates several refactors and a rename. The production code
is internally consistent (the offline `examples/walking_skeleton.py` and the
~136 green unit tests exercise the real pipeline), but a set of older tests
assert against pre-rename behaviour or a previous `Decision` schema. Rather
than silently delete them or fake green by hiding them, they are skipped
with an explicit reason in `conftest.py::_QUARANTINE`. Un-quarantining them
(fixing the drift) is good first-contribution work — see `CONTRIBUTING.md`.

## Layout

```
tests/
├── conftest.py              # fixtures + curated-scope config (_QUARANTINE)
├── fixtures/                # golden test data
├── test_*.py                # unit tests (default `pytest` scope)
└── integration/             # PostgreSQL/Redis/Selenium — opt-in
```

## Fixtures (conftest.py)

`test_settings`, `test_session` (async SQLAlchemy), `test_redis` (fakeredis),
`sample_decision`, `mock_pdf_file`. `test_api_client` builds the FastAPI app
and is used only by integration tests.

## Markers

`requires_db`, `requires_redis`, `requires_network`, `load`, `e2e`,
`performance`, `security`, `accessibility`, `smoke` (registered in
`conftest.py`; `--strict-markers` is on). Deselect e.g. with `-m "not slow"`.

## CI

`.github/workflows/ci.yml` runs this curated path on Python 3.10/3.11/3.12
plus `black --check .` and `flake8 src`. Integration tests are not run in CI
(no service containers wired up yet — tracked as an Alpha limitation).
