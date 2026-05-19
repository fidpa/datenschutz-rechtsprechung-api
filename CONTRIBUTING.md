# Contributing

Thanks for your interest in `datenschutz-rechtsprechung-api`. This is a single-developer showcase
project; contributions are welcome but the scope is deliberately narrow.

## Scope

This repository collects, anonymises and exposes DACH data-protection court
decisions. We tend to **welcome**:

- Bug fixes
- New or improved collectors for additional public legal databases
- Anonymisation quality improvements (with before/after examples)
- Documentation clarifications
- Performance improvements with benchmarks

We tend to **decline**:

- Sources that are not publicly available or whose terms forbid crawling
- Storing non-anonymised personal data
- Datastore backends other than PostgreSQL
- Generic "make it pluggable" refactors without a concrete use case

When in doubt, **open an issue first**.

## Language

- **Code, identifiers, commit messages, PR descriptions:** English.
- **Issues:** English preferred; German accepted.
- **Compliance documentation** under `docs/compliance/`: stays German on
  purpose — it tracks DACH statutes verbatim.

## Local development

```bash
git clone https://github.com/fidpa/datenschutz-rechtsprechung-api.git
cd datenschutz-rechtsprechung-api
pip install -r requirements.txt
cp .env.example .env        # never commit .env
docker compose up -d        # postgres + redis for integration tests
```

## Quality gates (must pass before a PR)

The project uses `black`, `flake8` and `pytest` (see `requirements.txt` and
`.flake8` / `pyproject.toml` for config):

```bash
black --check .          # formatting (line-length 100)
flake8 src               # correctness lint (CI gates `src`)
pytest -v --cov=src      # curated unit suite — must stay green
```

- New code needs tests. The default suite runs against in-memory SQLite, so
  unit tests need no external services. Scope and the quarantine list are
  documented in [`tests/README.md`](tests/README.md); un-quarantining a
  drifted test (with a fix) is welcome first-contribution work.
- Do not commit secrets, real credentials, personal data, real internal
  hostnames/IPs, or local filesystem paths. Use placeholders
  (`*.example.com`, RFC 5737 IPs).
- Never commit `.env`, `CLAUDE.md`, internal reports, or anything matched by
  `.gitignore`.

## Reporting security issues

Do **not** open public issues for vulnerabilities. See
[SECURITY.md](SECURITY.md) for the responsible-disclosure process.
