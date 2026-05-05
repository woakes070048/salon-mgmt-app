variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region (Toronto)"
  type        = string
  default     = "northamerica-northeast2"
}

variable "db_password" {
  description = "PostgreSQL password for the app database user"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "JWT signing secret — generate with: openssl rand -hex 32"
  type        = string
  sensitive   = true
}

variable "github_repo" {
  description = "GitHub repository for Workload Identity Federation, e.g. 'owner/repo'"
  type        = string
}

variable "anthropic_api_key" {
  description = "Anthropic API key for the Briefing Engine"
  type        = string
  sensitive   = true
}

variable "internal_secret" {
  description = "Shared secret for Cloud Scheduler → Cloud Run internal endpoints (generate with: openssl rand -hex 32)"
  type        = string
  sensitive   = true
}

variable "briefing_resend_api_key" {
  description = "Resend API key for briefing email delivery"
  type        = string
  sensitive   = true
}

variable "briefing_from_address" {
  description = "From address for briefing emails (must be a verified Resend sender)"
  type        = string
}

variable "briefing_email_to" {
  description = "Recipient address for the developer daily briefing"
  type        = string
}

variable "resend_webhook_secret" {
  description = "Resend svix webhook signing secret (whsec_...) for inbound email signature validation"
  type        = string
  sensitive   = true
}
