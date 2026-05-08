FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies (cached layer — only re-runs if pyproject.toml/uv.lock changes)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --frozen

# Application code, migrations, Alembic config, and scripts
COPY backend/app/ app/
COPY backend/briefing_engine/ briefing_engine/
COPY migrations/ migrations/
COPY alembic.ini .
COPY scripts/seed.py scripts/seed.py
COPY scripts/run_import.py scripts/run_import.py
COPY data/ data/

ENV PATH="/app/.venv/bin:$PATH"

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

# PORT is set by Cloud Run to match the declared container port (8000).
# Locally it defaults to 8000 as well.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

ENTRYPOINT ["/docker-entrypoint.sh"]
