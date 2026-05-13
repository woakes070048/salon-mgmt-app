#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade q3r4s5t6u7v8

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Running seed..."
  PYTHONPATH=/app python scripts/seed.py || echo "WARNING: seed exited with errors (non-fatal)"
fi

echo "Starting server..."
exec "$@"
