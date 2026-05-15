variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region (Toronto)"
  type        = string
  default     = "northamerica-northeast2"
}

variable "environment" {
  description = "Deployment environment — controls db tier, scheduler jobs, and runtime ENV var"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod", "dev"], var.environment)
    error_message = "environment must be 'prod' or 'dev'"
  }
}

variable "db_tier" {
  description = "Cloud SQL tier. Override for cost savings in dev. Prod default keeps current sizing."
  type        = string
  default     = "db-perf-optimized-N-2"
}

variable "db_edition" {
  description = "Cloud SQL edition. ENTERPRISE_PLUS for prod (perf-optimized tiers); ENTERPRISE for dev (shared-core tiers like db-g1-small)."
  type        = string
  default     = "ENTERPRISE_PLUS"
}

variable "db_region" {
  description = "Region for Cloud SQL. May differ from var.region if the primary region is rejecting new instances. Empty string = use var.region."
  type        = string
  default     = ""
}

variable "enable_schedulers" {
  description = "Whether to create Cloud Scheduler jobs (briefings, reminders). Disable in dev to avoid sending real emails."
  type        = bool
  default     = true
}

variable "cors_origins" {
  description = "Comma-separated list of allowed frontend origins for the API. Override per env."
  type        = string
  default     = ""
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
