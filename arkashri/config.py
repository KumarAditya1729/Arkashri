# pyre-ignore-all-errors
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://arkashri:arkashri@localhost:5432/arkashri"
    witness_node_urls: list[str] = []  # Added for H-14 Witness Network broadcast

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
    auth_enforced: bool = True
    bootstrap_admin_token: str = "CHANGE_ME_BOOTSTRAP_TOKEN"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 15
    # jwt_secret_key maps JWT_SECRET_KEY env var — kept separate from session cookie secret
    jwt_secret_key: str | None = None
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
    # REQUIRED — no default. App will fail fast at startup if not set.
    # Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
    # This field is mandatory: app will refuse to start without a 32+ char secret.
    session_secret_key: str = "CHANGE_ME_BEFORE_PRODUCTION_USE_python3_secrets_token_hex_32"

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
    whatsapp_webhook_url: str | None = None
    whatsapp_bearer_token: str | None = None
    whatsapp_from_number: str | None = None

    # ── ERP credential encryption ─────────────────────────────────────────────
    # AES-256 key for encrypting connection_config in erp_connection table
    erp_config_encryption_key: str | None = None
    field_data_encryption_key: str | None = None

    # ── Observability (Sentry) ────────────────────────────────────────────────
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
    enable_performance_monitoring: bool = False

    # ── Artificial Intelligence Fabric (OpenAI) ───────────────────────────────
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ai_model_primary: str = "gpt-4-turbo"
    ai_model_fallback: str = "gpt-4o"
    ai_confidence_threshold: float = 0.85
    ai_max_tokens: int = 4096
    ai_temperature: float = 0.3

    # ── File Storage ──────────────────────────────────────────────────────────────
    storage_provider: str = "local"
    upload_dir: str = "./uploads"
    evidence_s3_bucket: str | None = None
    report_artifact_s3_bucket: str | None = None
    max_file_size: int = 52428800
    allowed_file_types: str = "application/pdf,image/jpeg,image/png,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    erp_request_timeout_seconds: int = 30
    bank_csv_max_rows: int = 10000
    mca_master_data_url: str | None = None
    mca_api_key: str | None = None
    mca_request_timeout_seconds: int = 20

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
    cors_origins: str | list[str] = [
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str] | None) -> list[str] | None:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value
    
    # Graceful shutdown
    shutdown_timeout: int = 30
    worker_timeout: int = 120
    
    # Feature flags for production
    enable_compression: bool = True
    enable_request_id: bool = True
    enable_user_context: bool = True

    def validate_runtime_configuration(self) -> None:
        env = self.app_env.strip().lower()
        is_prod = env in {"prod", "production"}

        if is_prod and self.enable_mock_data:
            raise RuntimeError("ENABLE_MOCK_DATA must remain false in production environments.")

        # ── SECURITY GATE 1: Auth must be enforced in production ──────────────
        if is_prod and not self.auth_enforced:
            raise RuntimeError(
                "FATAL: AUTH_ENFORCED must be True in production. "
                "Unauthenticated access to all APIs is currently open. "
                "Set AUTH_ENFORCED=true in your environment."
            )

        # ── SECURITY GATE 2: JWT secret must be real and strong ───────────────
        insecure_placeholder = "CHANGE_ME_BEFORE_PRODUCTION_USE_python3_secrets_token_hex_32"
        if is_prod and (
            not self.session_secret_key
            or self.session_secret_key == insecure_placeholder
            or len(self.session_secret_key) < 32
        ):
            raise RuntimeError(
                "FATAL: SESSION_SECRET_KEY is not set or is the insecure placeholder. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\" "
                "and set it as an environment variable."
            )

        # ── SECURITY GATE 3: Warn loudly in any non-prod env if using placeholder
        if self.session_secret_key == insecure_placeholder:
            import warnings
            warnings.warn(
                "SESSION_SECRET_KEY is set to the insecure placeholder value. "
                "This is acceptable for local dev only. "
                "Replace before any staging/production deployment.",
                stacklevel=2,
            )

        # ── PRODUCTION LOCK MODE ──────────────────────────────────────────────
        # Hard startup gates that refuse to boot in production until all
        # critical pre-conditions are satisfied. This is the last line of
        # defence against misconfiguration reaching live traffic.
        if is_prod:
            # Gate 4: Ephemeral in-memory KMS must NOT be used in production (C-3).
            # Ephemeral keys are lost on restart and diverge across workers,
            # making seal verification permanently impossible.
            kms = getattr(self, "kms_provider", "env").lower()
            if kms not in {"aws", "gcp", "vault"}:
                raise RuntimeError(
                    "FATAL [Production Lock]: KMS_PROVIDER must be 'aws', 'gcp', or 'vault' "
                    "in production. The default 'env' provider uses ephemeral in-memory ECDSA "
                    "keys that are lost on every restart and diverge across workers — seal "
                    "verification becomes impossible. Configure an external KMS and set "
                    "KMS_PROVIDER=aws (or gcp/vault) in your environment."
                )

            # Gate 5: Trivially-guessable bootstrap token must be replaced (H-3).
            _weak = {"arkashri-bootstrap", "bootstrap", "admin", "secret",
                     "change_me_bootstrap_token", "password", "test"}
            if (self.bootstrap_admin_token.lower() in _weak
                    or len(self.bootstrap_admin_token) < 24):
                raise RuntimeError(
                    "FATAL [Production Lock]: BOOTSTRAP_ADMIN_TOKEN is weak or default. "
                    "Generate with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\" "
                    "and set in your environment."
                )

            # Gate 6: APP_ENV must be explicitly set — not silently defaulting to 'dev'.
            # (If we reach here, we already know is_prod=True, but double-check
            #  the raw value wasn't something ambiguous like 'development'.)
            if self.app_env.strip().lower() not in {"production", "prod"}:
                raise RuntimeError(
                    "FATAL [Production Lock]: APP_ENV must be set to 'production' or 'prod'. "
                    f"Current value: '{self.app_env}'. Set APP_ENV=production in your "
                    "Railway/Kubernetes/Docker environment variables."
                )

            # Gate 7: Database URL must be PostgreSQL to support ROW LEVEL LOCKS (preventing forks)
            if "sqlite" in self.database_url.lower():
                raise RuntimeError(
                    "FATAL [Production Lock]: DATABASE_URL uses SQLite. SQLite does not support "
                    "the SELECT FOR UPDATE row-level locking necessary for audit chain integrity "
                    "under load. You must use a PostgreSQL adapter in production."
                )

            # Gate 8: REDIS_URL must be configured for the ARQ Workers to function natively
            if not self.redis_url or "localhost" in self.redis_url.lower():
                import warnings
                warnings.warn(
                    "WARNING [Production Lock]: REDIS_URL appears to be localhost or empty. "
                    "The anchor verification and async background processes require a valid Redis instance "
                    "unless strictly testing workers on the same container."
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
