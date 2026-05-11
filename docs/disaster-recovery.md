
originSessionId: de6c960e-3d49-45f8-9685-28a7dbd184dd

Full restore is possible from GitHub alone. Everything needed to recover is either in the repo or in GitHub releases (database backups).

## What lives where

| Asset | Location | Recovery |
|---|---|---|
| All code | GitHub repo `freddy6ix/salon-mgmt-app` | Clone and redeploy |
| Original Milano data files | Repo `/data/` folder | Re-run import from the app |
| Live database | GCP Cloud SQL + **GitHub releases** (nightly backup) | pg_restore from latest release |
| GCP infrastructure config | Encoded in `deploy.yml` + Cloud Run env vars | Redeploy + set env vars |
| Secrets | GCP Secret Manager (recoverable — just regenerate) | Get new keys from Anthropic / Resend |

## Nightly database backup

A GitHub Actions workflow (`.github/workflows/backup.yml`) runs at 1am Toronto on GitHub-hosted runners. It:
1. Authenticates to GCP via Workload Identity
2. Connects to Cloud SQL via the proxy
3. Runs `pg_dump --format=custom --compress=9`
4. Uploads the dump as a GitHub **prerelease** tagged `backup-YYYY-MM-DD`
5. Keeps the last 30 days (rotates older ones)

Backups are visible at: `https://github.com/freddy6ix/salon-mgmt-app/releases`

To trigger a manual backup: `gh workflow run backup.yml`

## Full recovery procedure

### 1. Recover the code
```bash
git clone https://github.com/freddy6ix/salon-mgmt-app.git
```

### 2. Recover the database
```bash
# Download latest backup from GitHub releases
gh release download backup-YYYY-MM-DD --repo freddy6ix/salon-mgmt-app

# Restore to a fresh Postgres instance
createdb salon_lyol
pg_restore -h localhost -U salon -d salon_lyol --clean salon_lyol_YYYY-MM-DD.dump
```

### 3. Rebuild GCP infrastructure
- Create new GCP project
- Enable Cloud Run, Cloud SQL, Artifact Registry, Cloud Scheduler, Secret Manager
- Set up Workload Identity Federation for GitHub Actions (see existing `deploy.yml` for the pattern)
- Create Cloud SQL instance, create `salon` user
- Set GitHub repo vars: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `API_URL`, `FRONTEND_URL`
- `git push` → CI deploys everything automatically

### 4. Set secrets on Cloud Run after deploy
```bash
gcloud run services update salon-api \
  --update-env-vars "\
SECRET_KEY=<new>,\
DB_PASSWORD=<from Cloud SQL>,\
ANTHROPIC_API_KEY=<from console.anthropic.com>,\
INTERNAL_SECRET=<random>,\
BRIEFING_RESEND_API_KEY=<from resend.com>,\
BRIEFING_FROM_ADDRESS=briefings@inbound.roux.salon,\
BRIEFING_EMAIL_TO=frederick.ferguson@gmail.com"
```

### 5. Re-run the Cloud Scheduler job for briefings
```bash
bash scripts/setup_briefing_scheduler.sh
```

### 6. Re-import Milano data (if DB was not restored from backup)
Upload files via Admin → Import in the app. Files are in `/data/` folder.

## What you'd lose with no backup

If GCP AND all backups were gone:
- All data added via SalonOS after import (appointments, sales, payroll overrides, corrections)
- The corrected/fixed imported data (qty fixes, etc.) — would need re-running import + manual fixes
- Original Milano data is safe (it's in the GitHub repo `/data/` folder)

## Key contacts / accounts needed
- GitHub: `freddy6ix` account
- Anthropic Console: console.anthropic.com (Frederick Ferguson account)
- Resend: resend.com (for email delivery)
- GCP: console.cloud.google.com (freddy@meshentics.com)
- Domain registrar: Cloudflare (roux.salon, rouxsalon.com, joinroux.com)

---

## Finding Claude context after a machine loss

If you are starting a fresh Claude session and have lost the GCP VM:

1. Clone the repo: `git clone https://github.com/freddy6ix/salon-mgmt-app.git`
2. Open the project in Claude Code — it will read `CLAUDE.md` automatically
3. Read this file (`docs/disaster-recovery.md`) and `docs/backlog.md` for project context
4. Database backups: `https://github.com/freddy6ix/salon-mgmt-app/releases` — look for releases tagged `backup-YYYY-MM-DD`

The Claude Onboarding Guide link (if set up) will also restore context:
save that link in your password manager alongside your GCP credentials.
