from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database — used for local dev and docker-compose
    database_url: str = "postgresql+asyncpg://salon:salon@localhost:5432/salon_lyol"

    # Cloud SQL — set these in Cloud Run instead of database_url
    cloud_sql_instance: str = ""  # e.g. "project:region:instance"
    db_user: str = "salon"
    db_password: str = ""
    db_name: str = "salon_lyol"

    # Auth
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours — full working day

    # Guest registration — slug of the tenant guests register under
    default_tenant_slug: str = "salon-lyol"

    # App
    environment: str = "development"
    debug: bool = False

    # CORS — comma-separated list of allowed origins
    cors_origins: str = "http://localhost:5173"

    # Email — SMTP reset link base URL
    frontend_url: str = "http://localhost:5173"

    # Internal endpoints — shared secret for Cloud Scheduler calls
    internal_secret: str = ""

    # Anthropic — required for the Briefing Engine
    anthropic_api_key: str = ""

    # Briefing Engine — base directory for file delivery (defaults to project root)
    briefing_base_dir: str = ""

    # Briefing Engine — GCS bucket for cloud delivery (Cloud Run writes here; local script syncs down)
    briefing_gcs_bucket: str = ""

    # Briefing Engine — email delivery via Resend
    briefing_resend_api_key: str = ""
    briefing_from_address: str = ""
    briefing_email_to: str = ""

    # Inbound email webhook — Resend svix signing secret (whsec_...)
    # Leave empty in development to skip signature validation.
    resend_webhook_secret: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
