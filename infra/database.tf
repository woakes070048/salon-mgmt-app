# ── Cloud SQL PostgreSQL 16 ─────────────────────────────────────────────────
resource "google_sql_database_instance" "main" {
  name             = "salon-lyol-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier    = var.db_tier
    edition = var.db_edition

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    ip_configuration {
      ipv4_enabled = true
      # No authorized_networks needed — Cloud SQL Python Connector uses IAM auth
    }

    insights_config {
      query_insights_enabled = false # enable in production for query profiling
    }
  }

  deletion_protection = false # set to true before going to production
  depends_on          = [google_project_service.apis]
}

resource "google_sql_database" "salon_lyol" {
  name     = "salon_lyol"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = "salon"
  instance = google_sql_database_instance.main.name
  password = var.db_password
}

# ── Secrets ─────────────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "db_password" {
  secret_id = "salon-db-password"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret" "secret_key" {
  secret_id = "salon-secret-key"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "secret_key" {
  secret      = google_secret_manager_secret.secret_key.id
  secret_data = var.secret_key
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "salon-anthropic-api-key"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "internal_secret" {
  secret_id = "salon-internal-secret"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "internal_secret" {
  secret      = google_secret_manager_secret.internal_secret.id
  secret_data = var.internal_secret
}

resource "google_secret_manager_secret" "briefing_resend_api_key" {
  secret_id = "salon-briefing-resend-api-key"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "briefing_resend_api_key" {
  secret      = google_secret_manager_secret.briefing_resend_api_key.id
  secret_data = var.briefing_resend_api_key
}

resource "google_secret_manager_secret" "resend_webhook_secret" {
  secret_id = "salon-resend-webhook-secret"
  replication {
    auto {
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "resend_webhook_secret" {
  secret      = google_secret_manager_secret.resend_webhook_secret.id
  secret_data = var.resend_webhook_secret
}
