#!/bin/sh
set -e

# Migrations are NOT run here. They run as a separate CI step before the
# Cloud Run revision is deployed (.github/workflows/deploy.yml). This keeps
# container startup fast and decouples schema changes from the Cloud SQL
# socket proxy timing race that used to cause "container failed to start"
# errors during the entrypoint.

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "Running seed..."
  PYTHONPATH=/app python scripts/seed.py || echo "WARNING: seed exited with errors (non-fatal)"
fi

if [ "${RUN_IMPORT:-false}" = "true" ]; then
  echo "Running legacy import..."
  PYTHONPATH=/app python scripts/run_import.py || echo "WARNING: import exited with errors (non-fatal)"
fi

echo "Starting server..."
exec "$@"
