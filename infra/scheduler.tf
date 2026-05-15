# ── Cloud Scheduler service account ─────────────────────────────────────────
resource "google_service_account" "scheduler" {
  account_id   = "salon-scheduler"
  display_name = "Salon Cloud Scheduler"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# ── Daily briefing job — developer audience, 8am Toronto (email to Freddy) ──
# Scheduler jobs are gated by var.enable_schedulers so dev environments
# don't fire real email sends or run briefings on schedule.
resource "google_cloud_scheduler_job" "briefing_developer" {
  count            = var.enable_schedulers ? 1 : 0
  name             = "salon-briefing-developer"
  description      = "Daily market intelligence email to Freddy"
  schedule         = "0 8 * * *"
  time_zone        = "America/Toronto"
  attempt_deadline = "300s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/internal/run-briefing"
    body        = base64encode(jsonencode({ briefing_id = "developer-market-daily" }))
    headers = {
      "Content-Type"      = "application/json"
      "X-Internal-Secret" = var.internal_secret
    }

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.api.uri
    }
  }

  depends_on = [google_project_service.apis]
}

# ── Reminder dispatcher — every 15 minutes ──────────────────────────────────
resource "google_cloud_scheduler_job" "dispatch_reminders" {
  count            = var.enable_schedulers ? 1 : 0
  name             = "salon-dispatch-reminders"
  description      = "Trigger appointment reminder emails every 15 minutes"
  schedule         = "*/15 * * * *"
  time_zone        = "America/Toronto"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/internal/dispatch-reminders"
    body        = base64encode("{}")
    headers = {
      "Content-Type"      = "application/json"
      "X-Internal-Secret" = var.internal_secret
    }

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.api.uri
    }
  }

  depends_on = [google_project_service.apis]
}

# ── Daily briefing job — claude_code audience, 7am Toronto ──────────────────
resource "google_cloud_scheduler_job" "briefing_claude_code" {
  count            = var.enable_schedulers ? 1 : 0
  name             = "salon-briefing-claude-code"
  description      = "Daily market intelligence briefing for Claude Code"
  schedule         = "0 7 * * *"
  time_zone        = "America/Toronto"
  attempt_deadline = "300s"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}/internal/run-briefing"
    body        = base64encode(jsonencode({ briefing_id = "claude-code-market-daily" }))
    headers = {
      "Content-Type"       = "application/json"
      "X-Internal-Secret"  = var.internal_secret
    }

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.api.uri
    }
  }

  depends_on = [google_project_service.apis]
}
