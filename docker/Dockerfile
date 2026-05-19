# Generic application image — used by docker-compose.yml for the api,
# celery_worker and celery_beat services. Each service supplies its own
# runtime command via the compose `command:` field, so this Dockerfile
# does not pin one. Dockerfile.api and Dockerfile.web add production
# hardening (multi-stage, non-root, healthcheck) for direct image builds.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System dependencies (kept in sync with Dockerfile.api / Dockerfile.web)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (installed before COPY for better layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Optional: bundle the German spaCy model for offline-first anonymisation.
# Disabled by default to keep the image small (~50 MB) — uncomment when
# you want a self-contained image.
# RUN python -m spacy download de_core_news_sm

# Non-root runtime user (matches Dockerfile.api / Dockerfile.web convention)
RUN groupadd -r dsr && useradd -r -g dsr dsr \
    && mkdir -p /app/logs /app/uploads /app/temp \
    && chown -R dsr:dsr /app

# Application source
COPY --chown=dsr:dsr . .

USER dsr

# No CMD on purpose: docker-compose.yml supplies the runtime command per
# service (uvicorn for `api`, `celery worker` for `celery_worker`,
# `celery beat` for `celery_beat`). Running this image without an explicit
# command falls through to /bin/sh, which exits — that is intentional and
# surfaces a misconfigured deployment immediately.
