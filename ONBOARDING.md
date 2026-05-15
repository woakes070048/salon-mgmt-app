# SalonOS — Claude Code Onboarding

**Owner:** Freddy Ferguson (freddy@meshentics.com) · Salon Lyol, Toronto
**Repo:** https://github.com/freddy6ix/salon-mgmt-app
**Stack:** Python/FastAPI · PostgreSQL · GCP (Cloud Run + Cloud SQL) · React/TypeScript

## What this project is

SalonOS replaces Milano Software (Canadian on-premises salon platform, est. 1990) at Salon Lyol. Cloud-native, AI-first. Salon Lyol goes live first, then multi-tenant SaaS.

P1 (appointment book + client management) and P2 (POS, reporting, payroll, inventory) are complete. P3 (AI/briefing engine, smart booking) is in progress. UAT is active with real Salon Lyol data imported from Milano.

## Repo layout

```
backend/          FastAPI app (Python 3.12)
frontend/         React + TypeScript + Tailwind
migrations/       Alembic migrations
briefing_engine/  Daily market intelligence briefing (Claude API)
data/             Original Milano export files (source of truth for historical data)
docs/             Backlog, specs, disaster recovery playbook
scripts/          run_briefing.py, setup_briefing_scheduler.sh, purge_since_oct2025.sql
.github/
  workflows/
    deploy.yml    CI/CD — push to main → Cloud Run staging
    backup.yml    Nightly pg_dump → GitHub releases (1am Toronto)
```

## Key standing rules

- Every table needs `tenant_id` (multi-tenant from day one)
- Booking confirmation is staff-only — never auto-confirm
- Gender-free pricing only
- No Co-Authored-By trailers in commits
- `BriefingConfig` is single source of truth for briefing features

## GCP infrastructure

**Prod project: `salon-mgmt-app-2026`**
- Region: `northamerica-northeast2`
- Cloud Run services: `salon-api`, `salon-frontend`
- Cloud SQL: `salon-lyol-pg` in `northamerica-northeast2`
- Deploys from `main` branch via `.github/workflows/deploy.yml`

**Dev project: `salon-mgmt-app-dev`** (stood up 2026-05-15)
- Region: `northamerica-northeast2` (compute), `us-central1` (Cloud SQL — Toronto rejects new SQL instances for new projects)
- Cloud Run services: `salon-api`, `salon-frontend` (same names, different project = no conflict)
- Frontend URL: https://salon-frontend-scy7cjvrfa-pd.a.run.app
- API URL: https://salon-api-scy7cjvrfa-pd.a.run.app
- Yellow `DEV ENVIRONMENT` banner across the top of every page
- `ENVIRONMENT=dev` runtime — backend `send_email()` no-ops, schedulers not created
- Deploys from `dev` branch via `.github/workflows/deploy-dev.yml`
- All `DEV_*` GitHub Actions vars/secrets prefixed (DEV_GCP_PROJECT_ID, etc.)

**Shared infra:**
- Self-hosted GitHub Actions runner: `github-runner` VM (in prod project, deploys to both envs)
- Dev/Claude workstation: `dev-workstation` VM

## Secrets

**GCP Secret Manager:** `salon-db-password`, `salon-secret-key`, `salon-admin-password`

**GitHub Secrets (read by CI, pushed to Cloud Run as plain env vars):**
`RESEND_WEBHOOK_SECRET`, `AUTH0_CLIENT_SECRET`, `QZ_TRAY_PRIVATE_KEY`
— rotate these from the GitHub UI (Settings → Secrets and variables → Actions)
or `gh secret set <name>`. To pick up the new value, push any commit that
touches `backend/`, `migrations/`, `scripts/`, `alembic.ini`, or `.github/`
(or trigger `Deploy to Staging` via workflow_dispatch).

**Env vars set directly on Cloud Run (not Secret Manager):**
`ANTHROPIC_API_KEY`, `INTERNAL_SECRET`, `BRIEFING_RESEND_API_KEY`,
`BRIEFING_FROM_ADDRESS` (briefings@inbound.roux.salon),
`BRIEFING_EMAIL_TO` (frederick.ferguson@gmail.com)

## Disaster recovery

Full playbook: `docs/disaster-recovery.md` in the repo.

**Short version:**
1. Code → clone from GitHub
2. Database → download latest release tagged `backup-YYYY-MM-DD` from GitHub releases, restore with `pg_restore`
3. Secrets → regenerate from Anthropic Console + resend.com
4. Infrastructure → push to new GCP project, CI deploys automatically

## Common operational tasks

**Runner disk full** (builds fail with "no space left on device"):
```bash
gcloud compute ssh github-runner --project salon-mgmt-app-2026 \
  --zone northamerica-northeast2-a --tunnel-through-iap \
  --command "sudo docker system prune -af --volumes"
git commit --allow-empty -m "ci: redeploy after runner disk cleanup" && git push
```

**Cloud SQL proxy** (for direct DB access from dev-workstation):
```bash
/tmp/cloud-sql-proxy "salon-mgmt-app-2026:northamerica-northeast2:salon-lyol-pg" --port 5434
# Uses ADC from ~/.config/gcloud/application_default_credentials.json — permanent, no re-auth needed
```

**Daily briefing** (market intelligence email at 8am Toronto):
- Cloud Scheduler job `developer-market-daily` → POST /internal/run-briefing
- Manual trigger: `gh workflow run backup.yml` or curl the endpoint

**Nightly DB backup**: GitHub Actions `backup.yml` — check releases at github.com/freddy6ix/salon-mgmt-app/releases

## Current work focus

- Mar 16–Apr 15 payroll reconciliation (in progress — most issues resolved)
- P3 briefing audiences: salon_owner, stylist, client (not started)
- QuickBooks integration: P4-1 on backlog
- Historical payment data for year-end: Oct 2025–Apr 2026 loaded

## Inbound email inbox setup (in progress — May 13 2026)

Booking inbox (`/inbox`) receives emails via Resend inbound on `inbound.roux.salon`.

**Status:** MX record set, webhook configured, waiting for DNS propagation (~2-3 hrs).

To complete:
1. Once MX propagates, click "Re-send email" on Gmail forwarding settings for `info@salonlyol.ca`
2. Gmail verification email will POST to `POST /webhooks/email/inbound` 
3. Grab confirmation code from Cloud Run logs, paste back in Gmail to activate forwarding

**Config already done:**
- Cloudflare: `inbound.roux.salon` MX → `inbound-smtp.us-east-1.amazonaws.com` (priority 10)
- Resend: webhook `https://salon-api-qc33oa7roq-pd.a.run.app/webhooks/email/inbound` listening for `email.received`
- Signing secret: stored as GitHub Secret `RESEND_WEBHOOK_SECRET`, pushed to Cloud Run as an env var by the deploy workflow
- DB: `tenants.booking_inbound_address` = `booking@inbound.roux.salon`

## Recently shipped (May 2026)

- Business Reimbursed flag on sale items — provider commissioned on full amount when salon absorbs a discount
- Sales admin page (Finance → Sales) — searchable list with inline edit; no calendar navigation needed
- Historical sale editing unlocked for admins — BR flag, discount, and payments editable on any completed sale
- Nightly DB backup fixed — `salon-github-deployer` now has `cloudsql.client` + Secret Manager access; backup verified running
