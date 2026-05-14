#!/bin/sh

echo "=== ENTRYPOINT: env snapshot ==="
echo "CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-<not set>}"
echo "DATABASE_URL prefix=${DATABASE_URL:0:40}"
echo "DB_USER=${DB_USER:-<not set>}"
echo "DB_NAME=${DB_NAME:-<not set>}"
echo "================================"

echo "Running database migrations..."
if ! alembic upgrade head 2>&1; then
  echo "ERROR: alembic upgrade head failed with exit code $?" >&2
  echo "Starting server anyway so you can inspect logs in GCP console..." >&2
else
  echo "Migrations complete."
fi

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Running seed..."
  PYTHONPATH=/app python scripts/seed.py || echo "WARNING: seed exited with errors (non-fatal)"
fi

echo "Starting server..."
exec "$@"
