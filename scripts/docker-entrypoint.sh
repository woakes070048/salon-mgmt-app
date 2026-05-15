#!/bin/sh
set -e

# Print DB config (no secrets) and test connection before running alembic
python - <<'EOF'
import os, sys
cloud_sql = os.environ.get("CLOUD_SQL_INSTANCE", "")
db_url = os.environ.get("DATABASE_URL", "")
db_user = os.environ.get("DB_USER", "salon")
db_name = os.environ.get("DB_NAME", "salon_lyol")
db_pass_set = bool(os.environ.get("DB_PASSWORD", ""))
print(f"CLOUD_SQL_INSTANCE={cloud_sql or '<not set>'}")
print(f"DATABASE_URL={'<set, starts: ' + db_url[:40] + '>' if db_url else '<not set>'}")
print(f"DB_USER={db_user}  DB_NAME={db_name}  DB_PASSWORD={'<set>' if db_pass_set else '<empty>'}")
sys.stdout.flush()
EOF

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
