# Dev Environment Setup Runbook

**Goal:** stand up a completely isolated `salon-mgmt-app-dev` GCP project that mirrors prod and is deployed automatically from the `dev` branch.

After this runbook is complete:
- Pushes to `main` → prod (existing project `salon-mgmt-app-2026`)
- Pushes to `dev` → dev (new project `salon-mgmt-app-dev`)
- Code env-awareness: yellow `DEV ENVIRONMENT — DO NOT USE FOR REAL APPOINTMENTS` banner across the top in dev; backend `send_email()` is a no-op when `ENVIRONMENT=dev`; Cloud Scheduler jobs (briefings, reminders) are not created in dev.

---

## 0. Prerequisites

- Billing account with capacity for a second small GCP project (~$30–50/mo for `db-f1-micro` Cloud SQL plus negligible Cloud Run cost)
- `gcloud` CLI authenticated as a user with **Project Creator** + **Billing Account User** on your billing account
- Terraform ≥ 1.9 installed locally (or in a Cloud Shell)

---

## 1. Create the dev GCP project

```bash
# Pick a unique project ID — must be globally unique across all of GCP
DEV_PROJECT_ID="salon-mgmt-app-dev"
BILLING_ACCOUNT_ID="$(gcloud billing accounts list --format='value(name)' | head -1)"

gcloud projects create "$DEV_PROJECT_ID" --name="Salon Mgmt App (Dev)"
gcloud billing projects link "$DEV_PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
gcloud config set project "$DEV_PROJECT_ID"
```

## 2. Create the Terraform state bucket

```bash
gcloud storage buckets create "gs://${DEV_PROJECT_ID}-tfstate" \
  --location=northamerica-northeast2 \
  --uniform-bucket-level-access
gcloud storage buckets update "gs://${DEV_PROJECT_ID}-tfstate" --versioning
```

## 3. Apply the Terraform config to the dev project

The same `infra/` config that built prod works for dev — variables differ.

```bash
cd infra/

# Point Terraform at the dev state bucket
cat > backend-dev.tfbackend <<EOF
bucket = "${DEV_PROJECT_ID}-tfstate"
prefix = "terraform/state"
EOF

# Initialize against the dev backend
terraform init -reconfigure -backend-config=backend-dev.tfbackend

# Copy the dev tfvars template and fill in the secrets
cp terraform.tfvars.dev.example terraform.tfvars.dev
# Edit terraform.tfvars.dev — generate fresh secrets for dev (do NOT reuse prod):
#   openssl rand -hex 32        # for secret_key and internal_secret
#   db_password: pick a strong password
#   anthropic_api_key: create a separate Anthropic API key for dev usage tracking
#   briefing_resend_api_key: Resend sandbox/test key (or leave a prod key — schedulers are disabled in dev)
#   resend_webhook_secret: not used in dev (no inbound emails) — placeholder is fine

terraform apply -var-file=terraform.tfvars.dev
```

Terraform applies will create: APIs, Artifact Registry, Cloud SQL instance (`db-f1-micro`), database, Secret Manager secrets, GCS bucket, service accounts, Cloud Run service stubs, Workload Identity Federation. **No Cloud Scheduler jobs in dev.**

## 4. Note the Terraform outputs

```bash
terraform output
```

You will need these for the GitHub Actions vars in step 5:
- `workload_identity_provider`
- `deployer_service_account`
- `cloud_sql_instance` (format: `salon-mgmt-app-dev:northamerica-northeast2:salon-lyol-pg`)
- `api_url`
- `frontend_url`

## 5. Add GitHub Actions vars and secrets

Repo Settings → Secrets and variables → Actions.

**Variables** (Settings → Variables tab):
```
DEV_GCP_PROJECT_ID                = salon-mgmt-app-dev
DEV_GCP_REGION                    = northamerica-northeast2
DEV_GCP_SERVICE_ACCOUNT           = <deployer SA email from terraform output>
DEV_GCP_WORKLOAD_IDENTITY_PROVIDER = <WIF provider from terraform output>
DEV_CLOUD_SQL_INSTANCE            = salon-mgmt-app-dev:northamerica-northeast2:salon-lyol-pg
DEV_API_URL                       = <api Cloud Run URL>
DEV_FRONTEND_URL                  = <frontend Cloud Run URL>
DEV_ASSETS_GCS_BUCKET             = (leave empty for now — uses dev briefings bucket if not set)
DEV_AUTH0_DOMAIN                  = <separate Auth0 tenant, or reuse prod with a callback override>
DEV_AUTH0_CLIENT_ID               = <Auth0 client ID for the dev tenant/app>
DEV_AUTH0_CALLBACK_URL            = <DEV_API_URL>/auth/callback
```

**Secrets** (Settings → Secrets tab):
```
DEV_AUTH0_CLIENT_SECRET    = <Auth0 client secret for dev>
DEV_RESEND_WEBHOOK_SECRET  = whsec_dev_placeholder  (dev has no inbound emails)
DEV_QZ_TRAY_PRIVATE_KEY    = <same as prod QZ_TRAY_PRIVATE_KEY — cert is env-agnostic>
```

## 6. First dev deploy

```bash
git checkout -b dev
git push -u origin dev
```

This triggers `.github/workflows/deploy-dev.yml`. After it finishes:
- Visit `DEV_FRONTEND_URL` — you should see the **yellow DEV banner** across the top
- Login flow works against the dev DB (empty — fresh install)
- Run `scripts/seed.py` against dev to seed initial data (run locally with Cloud SQL proxy pointed at the dev instance)

## 7. Restore a sanitized prod snapshot into dev (optional)

If you want realistic data shape for testing without exposing client PII:

```bash
# Pull latest prod backup
gh release download backup-$(date -u +%Y-%m-%d) -p '*.dump' -R freddy6ix/salon-mgmt-app

# Restore into dev (use Cloud SQL proxy pointed at the dev instance)
PGPASSWORD="<dev db password>" pg_restore \
  -h 127.0.0.1 -p 5433 -U salon -d salon_lyol \
  --clean --if-exists \
  salon_lyol.dump

# Run an anonymization script (TODO — write one when needed)
# At minimum: scrub clients.email, clients.cell_phone, appointment_requests.email/phone
```

## 8. Day-to-day workflow after setup

```
# New feature work
git checkout dev
git pull
# make changes
git commit -m "feat: ..."
git push    # → triggers deploy-dev.yml → deploys to dev env

# Promote to prod when stable
git checkout main
git merge dev
git push    # → triggers deploy.yml → deploys to prod env
```

---

## Cost summary (dev env, monthly)

| Resource | Tier | ~Cost |
|---|---|---|
| Cloud SQL | `db-f1-micro` | $9 |
| Cloud Run (api+frontend) | scale to 0 when idle | <$5 |
| Cloud Storage (briefings bucket, tfstate) | minimal | <$1 |
| Artifact Registry | one repo | <$1 |
| **Total** | | **~$15–20/mo** |

Prod stays on the current sizing.

---

## Rollback plan

If something goes catastrophically wrong with the dev setup:

```bash
# Tear down the entire dev project — prod is in a different project and is untouched
cd infra/
terraform destroy -var-file=terraform.tfvars.dev

gcloud projects delete "$DEV_PROJECT_ID"
```

The strong isolation via separate projects means dev mistakes literally cannot affect prod.
