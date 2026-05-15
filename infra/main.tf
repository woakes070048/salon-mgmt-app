terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    bucket = "salon-mgmt-app-2026-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required GCP APIs ────────────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "sql-component.googleapis.com",
    "compute.googleapis.com",        # Cloud SQL provisions on Compute infra; required for instance create
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ── Artifact Registry ───────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "salon" {
  location      = var.region
  repository_id = "salon-mgmt"
  format        = "DOCKER"
  description   = "Salon Lyol container images"
  depends_on    = [google_project_service.apis]
}
