#!/bin/sh
set -e

echo "CLOUD_SQL_INSTANCE=${CLOUD_SQL_INSTANCE:-<not set>}"

# Wait for Cloud SQL socket to be ready (Gen2 sidecar may not be ready immediately)
if [ -n "$CLOUD_SQL_INSTANCE" ]; then
  SOCKET_FILE="/cloudsql/${CLOUD_SQL_INSTANCE}/.s.PGSQL.5432"
  echo "Waiting for Cloud SQL socket at $SOCKET_FILE..."
  i=0
  while [ $i -lt 30 ]; do
    if [ -e "$SOCKET_FILE" ]; then
      echo "Socket ready after ${i}s."
      break
    fi
    sleep 1
    i=$((i + 1))
  done
  if [ ! -e "$SOCKET_FILE" ]; then
    echo "WARNING: socket not found after 30s, attempting migration anyway..."
  fi
fi

echo "Running database migrations..."
alembic upgrade head

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Running seed..."
  PYTHONPATH=/app python scripts/seed.py || echo "WARNING: seed exited with errors (non-fatal)"
fi

echo "Starting server..."
exec "$@"
