#!/usr/bin/env bash
# One-time setup: create Cloud Scheduler jobs for the developer briefing
# and set required env vars on the salon-api Cloud Run service.
#
# Run from the project root once after setting the variables below.
# Requires: gcloud CLI authenticated as an account with Cloud Run Admin
# and Cloud Scheduler Admin roles.
#
# Usage:
#   export INTERNAL_SECRET="<your-secret>"          # already set on Cloud Run? use the same value
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   export BRIEFING_RESEND_API_KEY="re_..."          # Resend API key for sending email
#   export BRIEFING_FROM_ADDRESS="briefings@roux.salon"   # or whatever verified sender you use
#   export BRIEFING_EMAIL_TO="frederick.ferguson@gmail.com"
#   bash scripts/setup_briefing_scheduler.sh

set -euo pipefail

PROJECT="salon-mgmt-app-2026"
REGION="northamerica-northeast2"

: "${INTERNAL_SECRET:?Set INTERNAL_SECRET}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"
: "${BRIEFING_RESEND_API_KEY:?Set BRIEFING_RESEND_API_KEY}"
: "${BRIEFING_FROM_ADDRESS:?Set BRIEFING_FROM_ADDRESS}"
: "${BRIEFING_EMAIL_TO:?Set BRIEFING_EMAIL_TO}"

echo "→ Fetching API URL..."
API_URL=$(gcloud run services describe salon-api \
  --project "$PROJECT" \
  --region "$REGION" \
  --format="value(status.url)")
echo "  $API_URL"

# ── Set env vars on Cloud Run ─────────────────────────────────────────────────
echo "→ Updating Cloud Run env vars..."
gcloud run services update salon-api \
  --project "$PROJECT" \
  --region "$REGION" \
  --update-env-vars "\
INTERNAL_SECRET=${INTERNAL_SECRET},\
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},\
BRIEFING_RESEND_API_KEY=${BRIEFING_RESEND_API_KEY},\
BRIEFING_FROM_ADDRESS=${BRIEFING_FROM_ADDRESS},\
BRIEFING_EMAIL_TO=${BRIEFING_EMAIL_TO}" \
  --quiet
echo "  Done."

# ── developer-market-daily  (8am Toronto → email to Freddy) ───────────────────
echo "→ Creating Cloud Scheduler job: developer-market-daily..."
gcloud scheduler jobs create http developer-market-daily \
  --project "$PROJECT" \
  --location "$REGION" \
  --schedule "0 8 * * *" \
  --time-zone "America/Toronto" \
  --uri "${API_URL}/internal/run-briefing" \
  --message-body '{"briefing_id":"developer-market-daily"}' \
  --headers "Content-Type=application/json,X-Internal-Secret=${INTERNAL_SECRET}" \
  --attempt-deadline 300s \
  --description "Daily SalonOS market intelligence briefing → email to Freddy" \
  2>/dev/null \
  || gcloud scheduler jobs update http developer-market-daily \
       --project "$PROJECT" \
       --location "$REGION" \
       --schedule "0 8 * * *" \
       --time-zone "America/Toronto" \
       --uri "${API_URL}/internal/run-briefing" \
       --message-body '{"briefing_id":"developer-market-daily"}' \
       --headers "Content-Type=application/json,X-Internal-Secret=${INTERNAL_SECRET}" \
       --attempt-deadline 300s
echo "  Done."

echo ""
echo "✓ Setup complete."
echo ""
echo "The developer briefing will email ${BRIEFING_EMAIL_TO} every day at 8am Toronto."
echo ""
echo "── claude_code briefing (local) ─────────────────────────────────────────"
echo "This briefing writes to .claude/rules/market-intelligence.md and must run"
echo "on your local machine where Claude Code reads it."
echo ""
echo "Add to your crontab (crontab -e):"
echo "  0 7 * * * cd $(pwd) && ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY} python scripts/run_briefing.py claude-code-market-daily >> /tmp/briefing-claude-code.log 2>&1"
echo ""
echo "Or run manually any time:"
echo "  ANTHROPIC_API_KEY=... python scripts/run_briefing.py claude-code-market-daily"
