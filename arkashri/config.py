# pyre-ignore-all-errors
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://arkashri:arkashri@localhost:5432/arkashri"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url_scheme(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql://", 1)
            if v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    db_pool_size: int = 5
    db_max_overflow: int = 5
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "dev"
    enable_mock_data: bool = False
    auth_enforced: bool = False
    bootstrap_admin_token: str = "arkashri-bootstrap"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 15
    refresh_token_expiry_days: int = 7
    ws_ticket_expiry_seconds: int = 30

    independence_webhook_url: str | None = None
    hash_notary_url: str | None = None
    hash_notary_api_key: str | None = None
    hash_notary_timeout_seconds: int = 15

    polkadot_enabled: bool = False
    polkadot_ws_url: str = "wss://rpc.polkadot.io"
    polkadot_keypair_uri: str | None = None
    polkadot_wait_for_inclusion: bool = True
    ethereum_rpc_url: str | None = None
    ethereum_private_key: str | None = None
    polygon_rpc_url: str | None = None
    polygon_private_key: str | None = None

    # OAuth2 / OIDC Config
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_server_metadata_url: str | None = None
    # REQUIRED — no default. App will fail fast at startup if not set in production.
    # Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
    session_secret_key: str | None = None

    # ── Cryptographic Seal (HMAC key) ─────────────────────────────────────────
    # Set to a base64-encoded 32-byte key in production (AWS KMS / HashiCorp Vault)
    # If unset, the system will fail to seal records.
    seal_key_v1: str | None = None
    kms_provider: str = "env"  # Options: env, aws, gcp

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
    sms_webhook_url: str | None = None
    sms_webhook_bearer_token: str | None = None

    # ── ERP credential encryption ─────────────────────────────────────────────
    # AES-256 key for encrypting connection_config in erp_connection table
    erp_config_encryption_key: str | None = None

    # ── Observability (Sentry) ────────────────────────────────────────────────
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
    enable_performance_monitoring: bool = False

    # ── Artificial Intelligence Fabric (OpenAI) ───────────────────────────────
    openai_api_key: str | None = None
    ai_model_primary: str = "gpt-4-turbo"
    ai_model_fallback: str = "gpt-4o"
    ai_confidence_threshold: float = 0.85
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.3

    # ── File Storage ──────────────────────────────────────────────────────────────
    storage_provider: str = "local"
    upload_dir: str = "./uploads"
    evidence_s3_bucket: str | None = None
    max_file_size: int = 52428800
    allowed_file_types: str = "application/pdf,image/jpeg,image/png,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    erp_request_timeout_seconds: int = 30
    bank_csv_max_rows: int = 10000

    # ── Production Settings ───────────────────────────────────────────────────────
    # Database connection settings
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600
    db_echo: bool = False
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds
    
    # Caching
    cache_ttl: int = 300  # seconds
    cache_max_size: int = 1000
    
    # Request/Response settings
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    request_timeout: int = 30
    max_concurrent_requests: int = 1000
    
    # Health check settings
    health_check_interval: int = 30
    health_check_timeout: int = 5
    
    # Backup settings
    backup_enabled: bool = False
    backup_retention_days: int = 30
    backup_schedule: str = "0 2 * * *"  # cron format
    
    # Performance monitoring
    enable_request_logging: bool = True
    enable_performance_metrics: bool = True
    metrics_port: int = 9090
    
    # Security headers
    allowed_hosts: str = "*"
    cors_origins: list[str] = [
        # Local development
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:4173", "http://localhost:4173",
        "http://localhost:3000", "http://127.0.0.1:3000",
        # Production — Vercel frontend (specific URLs only — wildcards break credentialed CORS)
        "https://arkashri.vercel.app",
        "https://arkashri-kumaraditya1729s-projects.vercel.app",
        # Railway backend url (for inter-service calls)
        "https://arkashri-production-95ea.up.railway.app",
    ]
    
    # Graceful shutdown
    shutdown_timeout: int = 30
    worker_timeout: int = 120
    
    # Feature flags for production
    enable_compression: bool = True
    enable_request_id: bool = True
    enable_user_context: bool = True

    def validate_runtime_configuration(self) -> None:
        env = self.app_env.strip().lower()

        if env in {"prod", "production"} and self.enable_mock_data:
            raise RuntimeError("ENABLE_MOCK_DATA must remain false in production environments.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
