#!/usr/bin/env python3
"""Check whether an Arkashri environment is safe to promote to production."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


PLACEHOLDER_SESSION_SECRET = "CHANGE_ME_BEFORE_PRODUCTION_USE_python3_secrets_token_hex_32"
WEAK_BOOTSTRAP_TOKENS = {
    "arkashri-bootstrap",
    "bootstrap",
    "admin",
    "secret",
    "change_me_bootstrap_token",
    "password",
    "test",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def check_env() -> list[Check]:
    checks: list[Check] = []

    app_env = env("APP_ENV")
    checks.append(Check(
        "APP_ENV",
        "pass" if app_env.lower() in {"production", "prod"} else "fail",
        "APP_ENV must be production or prod.",
    ))

    auth = env("AUTH_ENFORCED", "true")
    checks.append(Check(
        "AUTH_ENFORCED",
        "pass" if truthy(auth) else "fail",
        "Production APIs must enforce authentication.",
    ))

    mock_data = env("ENABLE_MOCK_DATA", "false")
    checks.append(Check(
        "ENABLE_MOCK_DATA",
        "pass" if not truthy(mock_data) else "fail",
        "Mock data must be disabled in production.",
    ))

    session_secret = env("SESSION_SECRET_KEY")
    checks.append(Check(
        "SESSION_SECRET_KEY",
        "pass" if session_secret and session_secret != PLACEHOLDER_SESSION_SECRET and len(session_secret) >= 32 else "fail",
        "Use a real 32+ character session secret.",
    ))

    kms = env("KMS_PROVIDER")
    checks.append(Check(
        "KMS_PROVIDER",
        "pass" if kms.lower() == "aws" else "fail",
        "Use the implemented production KMS provider: aws.",
    ))
    checks.append(Check(
        "KMS_ASYMMETRIC_KEY_ID",
        "pass" if kms.lower() == "aws" and env("KMS_ASYMMETRIC_KEY_ID") else "fail",
        "AWS KMS requires an ECC_NIST_P256 asymmetric signing key id, arn, or alias.",
    ))

    bootstrap = env("BOOTSTRAP_ADMIN_TOKEN")
    checks.append(Check(
        "BOOTSTRAP_ADMIN_TOKEN",
        "pass" if bootstrap.lower() not in WEAK_BOOTSTRAP_TOKENS and len(bootstrap) >= 24 else "fail",
        "Use a strong bootstrap token and rotate it after initial admin setup.",
    ))

    database_url = env("DATABASE_URL")
    checks.append(Check(
        "DATABASE_URL",
        "pass" if database_url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")) and "sqlite" not in database_url.lower() else "fail",
        "Production must use PostgreSQL, not SQLite.",
    ))

    redis_url = env("REDIS_URL")
    redis = urllib.parse.urlparse(redis_url)
    redis_host = (redis.hostname or "").lower()
    checks.append(Check(
        "REDIS_URL",
        "pass" if redis.scheme in {"redis", "rediss"} and redis_host not in {"localhost", "127.0.0.1", "::1"} else "fail",
        "Use managed Redis with redis:// or rediss://.",
    ))

    storage = env("STORAGE_PROVIDER", "local").lower()
    checks.append(Check(
        "STORAGE_PROVIDER",
        "pass" if storage != "local" else "fail",
        "Use durable object storage for production evidence.",
    ))
    if storage == "s3":
        checks.append(Check(
            "EVIDENCE_S3_BUCKET",
            "pass" if env("EVIDENCE_S3_BUCKET") else "fail",
            "S3 evidence storage requires EVIDENCE_S3_BUCKET.",
        ))

    checks.append(Check(
        "S3_WORM_BUCKET",
        "pass" if env("S3_WORM_BUCKET") else "fail",
        "Immutable WORM archive storage is required for production audit evidence.",
    ))

    cors_origins = [item.strip() for item in env("CORS_ORIGINS").split(",") if item.strip()]
    cors_bad = any(origin == "*" or "localhost" in origin.lower() or "127.0.0.1" in origin for origin in cors_origins)
    checks.append(Check(
        "CORS_ORIGINS",
        "pass" if cors_origins and not cors_bad else "fail",
        "CORS must list only production frontend origins.",
    ))

    checks.append(Check(
        "SENTRY_DSN",
        "pass" if env("SENTRY_DSN") else "warn",
        "Recommended for production incident tracing.",
    ))
    checks.append(Check(
        "OPENAI_API_KEY",
        "pass" if env("OPENAI_API_KEY") else "warn",
        "Required before shipping AI-assisted workflows to customers.",
    ))
    checks.append(Check(
        "OCR_PROVIDER",
        "pass" if env("OCR_PROVIDER") else "warn",
        "Required for scanned PDF bank statement OCR; CSV/XLSX imports work without it.",
    ))
    checks.append(Check(
        "BACKUP_ENABLED",
        "pass" if truthy(env("BACKUP_ENABLED", "false")) else "fail",
        "Backups must be enabled before unrestricted client data.",
    ))
    checks.append(Check(
        "BACKUP_RESTORE_DRILL_AT",
        "pass" if env("BACKUP_RESTORE_DRILL_AT") else "fail",
        "Record the latest successful restore drill timestamp before production launch.",
    ))
    checks.append(Check(
        "ENABLE_METRICS",
        "pass" if truthy(env("ENABLE_METRICS", env("ENABLE_PERFORMANCE_METRICS", "false"))) else "warn",
        "Enable metrics/observability for production incident response.",
    ))
    checks.append(Check(
        "LEGAL_COMPLIANCE_REVIEW_SIGNED_AT",
        "pass" if env("LEGAL_COMPLIANCE_REVIEW_SIGNED_AT") else "fail",
        "Legal/compliance review sign-off is required before real sensitive client data.",
    ))

    return checks


def fetch(url: str, timeout: int = 10) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(200).decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read(200).decode("utf-8", errors="replace")
        return exc.code, body
    except Exception as exc:
        return None, str(exc)


def check_http() -> list[Check]:
    checks: list[Check] = []
    backend = env("ARKASHRI_BACKEND_URL").rstrip("/")
    frontend = env("ARKASHRI_FRONTEND_URL").rstrip("/")

    if not backend:
        checks.append(Check("ARKASHRI_BACKEND_URL", "skip", "Set to run deployed backend smoke checks."))
    else:
        for path in ["/readyz", "/health", "/api/v1/workflow-pack", "/api/v1/workflow-pack/service-catalog", "/api/v1/audit-automation/capabilities"]:
            status, body = fetch(backend + path)
            checks.append(Check(
                "backend " + path,
                "pass" if status is not None and 200 <= status < 400 else "fail",
                f"HTTP {status}: {body[:120]}",
            ))

    if not frontend:
        checks.append(Check("ARKASHRI_FRONTEND_URL", "skip", "Set to run deployed frontend smoke checks."))
    else:
        status, body = fetch(frontend)
        checks.append(Check(
            "frontend /",
            "pass" if status is not None and 200 <= status < 400 else "fail",
            f"HTTP {status}: {body[:120]}",
        ))

    return checks


def main() -> int:
    checks = check_env() + check_http()
    failures = [check for check in checks if check.status == "fail"]
    print(json.dumps([check.__dict__ for check in checks], indent=2))
    if failures:
        print(f"\nProduction readiness failed: {len(failures)} blocking check(s).", file=sys.stderr)
        return 1
    print("\nProduction readiness passed. Review any warnings before customer launch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
