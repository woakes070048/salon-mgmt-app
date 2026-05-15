#!/bin/sh
set -e

# Retry alembic up to 5 times to handle Cloud SQL socket startup delay
echo "Running database migrations..."
i=1
while [ $i -le 5 ]; do
  if alembic upgrade head; then
    break
  fi
  if [ $i -eq 5 ]; then
    echo "ERROR: migrations failed after 5 attempts" >&2
    exit 1
  fi
  echo "Migration attempt $i failed, retrying in 5s..."
  sleep 5
  i=$((i + 1))
done

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Running seed..."
  PYTHONPATH=/app python scripts/seed.py || echo "WARNING: seed exited with errors (non-fatal)"
fi

echo "Starting server..."
exec "$@"
