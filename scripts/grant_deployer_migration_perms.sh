#!/usr/bin/env bash
# Grants the IAM permissions the GitHub Actions deployer SA needs to run
# alembic migrations from CI via the Cloud SQL Auth Proxy. Idempotent.
#
# Run once from a machine with a human account that has resourcemanager
# admin and secretmanager admin on the project — not from the runner VM.
#
# These same grants live in infra/iam.tf (source of truth). This script
# exists so we can apply them without a full `terraform apply` cycle.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-salon-mgmt-app-2026}"
DEPLOYER_SA="salon-github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
DB_SECRET="salon-db-password"

echo "Granting roles/cloudsql.client on project ${PROJECT_ID} to ${DEPLOYER_SA}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/cloudsql.client" \
  --condition=None \
  --quiet >/dev/null

echo "Granting roles/secretmanager.secretAccessor on ${DB_SECRET} to ${DEPLOYER_SA}..."
gcloud secrets add-iam-policy-binding "${DB_SECRET}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOYER_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

echo "Done."
