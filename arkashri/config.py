from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://arkashri:arkashri@localhost:5432/arkashri"
    db_pool_size: int = 50
    db_max_overflow: int = 20
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "dev"
    auth_enforced: bool = False
    bootstrap_admin_token: str = "arkashri-bootstrap"

    independence_webhook_url: str | None = None

    polkadot_enabled: bool = False
    polkadot_ws_url: str = "wss://rpc.polkadot.io"
    polkadot_keypair_uri: str | None = None
    polkadot_wait_for_inclusion: bool = True

    # OAuth2 / OIDC Config
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_server_metadata_url: str | None = None
    # REQUIRED — no default. App will fail fast at startup if not set.
    # Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
    session_secret_key: str = "super-secret-session-key-for-dev"   # overridden by .env

    # ── Cryptographic Seal (HMAC key) ─────────────────────────────────────────
    # Set to a base64-encoded 32-byte key in production (AWS KMS / HashiCorp Vault)
    # If unset, falls back to the insecure dev constant in seal.py (_KEY_REGISTRY)
    seal_key_v1: str | None = None

    # ── S3 WORM Archive ───────────────────────────────────────────────────────
    s3_worm_bucket: str | None = None         # e.g. "arkashri-audit-worm"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "ap-south-1"

    # ── SMTP (partner email notifications) ───────────────────────────────────
    smtp_host: str | None = None              # e.g. "smtp.sendgrid.net"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "audit@arkashri.io"

    # ── ERP credential encryption ─────────────────────────────────────────────
    # AES-256 key for encrypting connection_config in erp_connection table
    erp_config_encryption_key: str | None = None

    # ── Observability (Sentry) ────────────────────────────────────────────────
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
    enable_performance_monitoring: bool = False

    # ── Artificial Intelligence Fabric (OpenAI) ───────────────────────────────
    openai_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
