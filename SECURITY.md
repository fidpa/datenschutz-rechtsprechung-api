# Security Policy

## Supported Versions

This is an alpha-stage project. Only the latest release on `main` receives
security fixes.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, open a private
[GitHub Security Advisory](https://github.com/fidpa/datenschutz-rechtsprechung-api/security/advisories/new)
on this repository. Private disclosure lets a fix and release be coordinated
before the issue becomes public.

When reporting, please include:

- A description of the issue and its potential impact
- Steps to reproduce (proof of concept if possible)
- Affected version/commit
- Any suggested remediation

You can expect an initial acknowledgement within a few days. Please allow a
reasonable disclosure window before publishing details.

## Operational Hardening Notes

This codebase ships **development defaults that must not be used in
production**:

- The bootstrap admin account documented in `docs/quickstart/QUICK_START.md`
  (`admin@admin.com` / `admin`) is for local first-run only. **Change it
  immediately** and never expose a default-credentialed instance.
- Passwords in `docker-compose.yml` and `docker-compose.test.yml` are
  local-development values. Production deployments must use
  `docker-compose.production.yml`, which reads all secrets from environment
  variables (`${ENV}` interpolation, no secrets committed).
- Generate production secrets with `scripts/security/generate_secrets.sh`
  (uses `openssl`), and supply them via a `.env.production` file that is **never
  committed**.

## Scope

Data handled by this project is intended to be anonymised public court
decisions. If you discover a path where non-anonymised personal data can be
stored or exposed via the API, treat it as a security issue and report it
through the private channel above.
