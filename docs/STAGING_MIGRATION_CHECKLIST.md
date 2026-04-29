# Arkashri Staging PostgreSQL Migration Checklist

Use this checklist only for staging. Do not point these commands at production, and do not paste real secrets into this document, GitHub issues, PRs, logs, screenshots, or chat.

## 1. Required Staging Infrastructure

- Create a separate staging backend service on Railway, Render, or AWS.
- Create a separate staging PostgreSQL database.
- Create a separate staging Redis instance.
- Do not reuse production PostgreSQL, Redis, S3 buckets, KMS keys, or secrets for staging.
- Deploy backend branch `codex/backend-quality-gates` or the merged `main` commit that includes PR #6.

## 2. Required Staging Environment Variables

Set these in the hosting provider secret manager. Values below are placeholders only.

```bash
APP_ENV=staging
DATABASE_URL=postgresql+asyncpg://STAGING_USER:STAGING_PASSWORD@STAGING_HOST:5432/STAGING_DB
REDIS_URL=redis://STAGING_REDIS_USER:STAGING_REDIS_PASSWORD@STAGING_REDIS_HOST:6379/0
SESSION_SECRET_KEY=REPLACE_WITH_STAGING_RANDOM_SECRET
JWT_SECRET_KEY=REPLACE_WITH_STAGING_RANDOM_SECRET
BOOTSTRAP_ADMIN_TOKEN=REPLACE_WITH_STAGING_RANDOM_TOKEN
KMS_PROVIDER=aws
STORAGE_PROVIDER=s3
EVIDENCE_S3_BUCKET=arkashri-staging-evidence
S3_WORM_BUCKET=arkashri-staging-worm
SENTRY_DSN=REPLACE_WITH_STAGING_SENTRY_DSN_OR_EMPTY
AUTH_ENFORCED=true
ENABLE_MOCK_DATA=false
CORS_ORIGINS=https://STAGING_FRONTEND_URL
```

If using AWS KMS/S3, also configure provider-specific staging credentials in the host secret manager:

```bash
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=REPLACE_WITH_STAGING_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=REPLACE_WITH_STAGING_SECRET_KEY
AWS_KMS_KEY_ID=REPLACE_WITH_STAGING_KMS_KEY_ID
```

## 3. Confirm This Is Staging, Not Production

Before running migrations, verify all of the following:

- `APP_ENV` is `staging`, not `production`.
- `DATABASE_URL` host/name clearly contains staging identifiers.
- `DATABASE_URL` is not the production hostname, production database name, or production Railway/Render/AWS resource.
- `REDIS_URL` host/name clearly contains staging identifiers.
- Evidence buckets are staging buckets, not production buckets.
- The hosting dashboard shows the staging service selected.

Safe verification commands:

```bash
echo "$APP_ENV"
python - <<'PY'
import os
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(url.replace("+asyncpg", ""))
print("database_scheme=", parsed.scheme)
print("database_host=", parsed.hostname)
print("database_name=", parsed.path.lstrip("/"))
print("is_probably_staging=", "stag" in f"{parsed.hostname or ''}/{parsed.path}".lower())
PY
```

Do not print passwords, tokens, or full connection strings.

## 4. Safe Migration Command

Run this only from the staging backend environment or a secure staging shell that has the staging env vars loaded:

```bash
alembic upgrade head
```

If the deployed environment requires the project virtualenv:

```bash
PATH=.venv/bin:$PATH alembic upgrade head
```

## 5. Verify Migration Success

After `alembic upgrade head` completes:

```bash
alembic current
alembic heads
```

Expected result:

- `alembic current` returns the current head revision.
- `alembic heads` shows the expected latest head.
- No traceback or failed SQL statement appears in logs.
- The staging PostgreSQL database contains expected Arkashri tables, including engagements, users/sessions, evidence, approvals, audit logs, RAG documents/chunks, ERP connections, seal sessions, and workflow-related tables.

Optional read-only SQL checks in staging:

```sql
select version_num from alembic_version;
select table_name from information_schema.tables where table_schema = 'public' order by table_name;
```

## 6. If Migration Fails

Stop immediately if any migration step fails.

- Do not retry blindly.
- Do not switch to production to compare.
- Save the failing migration revision name, exception type, and SQL error only.
- Do not paste secrets or full `DATABASE_URL` into logs or tickets.
- Keep the staging database as-is for debugging unless the team decides to recreate it.

Safe rollback options depend on failure point:

- If the migration failed before any changes committed, fix the migration/code and rerun on staging.
- If partial changes committed, inspect `alembic current`, the failed revision, and database schema before any downgrade.
- Use `alembic downgrade -1` only on staging and only after confirming the failed revision is safe to reverse.
- If staging is disposable, the safest path may be recreating the staging database and rerunning from an empty database.

## 7. Health Checks After Migration

After migration and backend restart, verify:

```bash
curl -fsS https://STAGING_BACKEND_URL/health
curl -fsS https://STAGING_BACKEND_URL/readyz
```

Expected:

- `/health` returns successful liveness status.
- `/readyz` returns readiness with database connectivity healthy.
- Logs do not show startup migration, database, Redis, auth, or settings failures.

## 8. Final Safety Warning

Never run:

```bash
alembic upgrade head
```

against production until staging migration, staging deployment, and full live smoke tests pass.

Production `DATABASE_URL` must never be used for this checklist.

## 9. Next Action After Migration Passes

After staging migration passes:

- Deploy/restart staging backend.
- Set frontend staging/Vercel env vars to the staging backend URL.
- Run the full smoke test: login, dashboard, create engagement, audit type selection, evidence upload/download/delete, risk creation, review comments/approvals, report page, logout/session expiry, and mobile responsiveness.
- Only after smoke test passes, continue to security review and real India CA workflow validation.
