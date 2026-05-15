locals {
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/salon-mgmt"
}

# ── API (FastAPI) ────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "api" {
  name                = "salon-api"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      ports {
        container_port = 8000
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "CLOUD_SQL_INSTANCE"
        value = google_sql_database_instance.main.connection_name
      }
      env {
        name  = "DB_USER"
        value = "salon"
      }
      env {
        name  = "DB_NAME"
        value = "salon_lyol"
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "INTERNAL_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.internal_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "BRIEFING_GCS_BUCKET"
        value = google_storage_bucket.briefings.name
      }
      env {
        name = "BRIEFING_RESEND_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.briefing_resend_api_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "BRIEFING_FROM_ADDRESS"
        value = var.briefing_from_address
      }
      env {
        name  = "BRIEFING_EMAIL_TO"
        value = var.briefing_email_to
      }
      env {
        name = "RESEND_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.resend_webhook_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins != "" ? var.cors_origins : "https://salon-frontend-qc33oa7roq-pd.a.run.app"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_version.secret_key,
    google_secret_manager_secret_version.anthropic_api_key,
    google_secret_manager_secret_version.internal_secret,
    google_secret_manager_secret_version.briefing_resend_api_key,
    google_secret_manager_secret_version.resend_webhook_secret,
    google_storage_bucket.briefings,
  ]
}

# ── Frontend (nginx + React) ─────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "frontend" {
  name                = "salon-frontend"
  location            = var.region
  deletion_protection = false

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
        cpu_idle = true
      }

      ports {
        container_port = 8080
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [google_project_service.apis]
}

# Public access — org policy was overridden at the project level via:
#   gcloud resource-manager org-policies set-policy ... allValues: ALLOW
# These bindings are safe to re-apply after terraform apply.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
