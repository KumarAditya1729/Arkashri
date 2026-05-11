# Arkashri Production and Market Readiness Gates

Status: not ready for unrestricted client data until every hard gate below is passed in production.

## Hard Gates

1. Auth and tenant isolation
   - Frontend protected routes must verify the HttpOnly session against the backend before rendering live workspaces.
   - Backend must reject every tenant-scoped API call when `tenant_id`, user role, or engagement ownership do not match.
   - Session cookies must be HttpOnly, Secure in production, SameSite=Lax or stricter, and never exposed to browser JavaScript.

2. Environment configuration
   - Production deploys must fail when backend/app URLs are missing or placeholder values.
   - Frontend proxy calls must return the backend status directly, not mask backend auth or validation failures as generic UI errors.
   - Mutating proxy routes must enforce same-origin requests because they act on auth cookies.

3. CA audit workflow completeness
   - A real engagement must pass creation, planning, evidence upload, risk assessment, control mapping, testing, review, report generation, and partner sign-off.
   - Every step must persist backend records and recover cleanly after a browser refresh.
   - "Live record required" states are acceptable only as empty/error states, not as the normal production path.

4. AI governance
   - AI suggestions must show source bindings or remain non-actionable.
   - Any applied AI suggestion must create an audit log entry with model, rationale, source context, human reviewer note, and override flag.
   - AI output must never be treated as audit evidence without CA review and traceable citations.

5. Evidence and audit trail integrity
   - Evidence uploads must be immutable or versioned after sign-off.
   - File access must be tenant-scoped and role-scoped.
   - Audit logs must capture actor, tenant, object id, action, timestamp, request id, and material before/after fields.

6. Operational controls
   - Rate limits, request ids, structured logs, backups, restore drills, and production monitoring must be enabled.
   - Error screens must guide recovery without leaking backend internals or client data.
   - Production incidents must be traceable from frontend correlation id to backend logs.

## Current Production Startup Locks

The backend now refuses to boot in `APP_ENV=production` unless these unsafe defaults are replaced:

- `AUTH_ENFORCED=true`
- `ENABLE_MOCK_DATA=false`
- strong `SESSION_SECRET_KEY`
- `KMS_PROVIDER=aws` with `KMS_ASYMMETRIC_KEY_ID` for AWS KMS ECC_NIST_P256 seal signing
- strong `BOOTSTRAP_ADMIN_TOKEN`
- PostgreSQL `DATABASE_URL`
- managed `REDIS_URL`
- remote evidence storage, including `EVIDENCE_S3_BUCKET` for S3
- immutable `S3_WORM_BUCKET`
- production-only `CORS_ORIGINS`, with no wildcard or localhost origins

Run the environment/deployment gate before promotion:

```bash
APP_ENV=production \
ARKASHRI_BACKEND_URL="https://api.example.com" \
ARKASHRI_FRONTEND_URL="https://app.example.com" \
python3 scripts/production_readiness_check.py
```

## Current Frontend Controls Added

- Login/register tokens are stored only in HttpOnly cookies; browser JavaScript receives only user/session metadata.
- Protected UI routes verify the backend session before rendering persisted local auth state.
- `/api/auth/session` performs hard backend token verification and clears invalid cookies.
- `/api/proxy/*` streams backend responses, forwards real backend statuses, and rejects cross-origin mutations.
- AI actions require sourced suggestions plus a CA justification before recording a governance log.

## First-Audit Release Gate

The automated release gate is `tests/test_first_audit_release_gate.py`. It proves a first audit can move through real persisted backend records:

- create engagement using authenticated tenant ownership
- bootstrap the India statutory audit workspace
- record planning, materiality, risk, control testing, and evidence
- record a sourced AI governance log bound to the authenticated tenant
- persist workflow state through report-ready review
- generate statutory report and draft opinion
- create a seal session, load the partner pre-sign summary, sign as CA, seal, and reject post-seal evidence upload

Run the local gate:

```bash
.venv/bin/python -m pytest tests/test_first_audit_release_gate.py -q
```

Run the production/staging smoke after creating a seeded CA/operator account:

```bash
export ARKASHRI_BACKEND_URL="https://arkashri-backend-production.up.railway.app"
export ARKASHRI_SMOKE_TENANT="default_tenant"
export ARKASHRI_SMOKE_EMAIL="ca@example.com"
export ARKASHRI_SMOKE_PASSWORD="..."
export ARKASHRI_SMOKE_CA_ICAI_REG_NO="FCA-123456"
export ARKASHRI_SMOKE_ALLOW_WRITE=1
python3 scripts/first_audit_smoke.py
```

## 7-Day Sprint Books Health Gate

The pre-audit cleanup gate is `tests/test_books_health_readiness.py`. It converts messy client books into a CA-controlled cleanup workflow before report drafting:

- bank statement and bank ledger readiness
- GST reconciliation readiness from GSTR-1/GSTR-2B vs books results
- ledger hygiene checks for missing imports, duplicate vouchers, weekend entries, large round-number entries, and negative cash/bank indicators
- evidence readiness checks
- 0-100 readiness score with `READY`, `AT_RISK`, or `BLOCKED` 7-day sprint status
- optional client query creation for critical/high blockers, with duplicate open-query suppression

Run the local gate:

```bash
.venv/bin/python -m pytest tests/test_books_health_readiness.py -q
```

API surface:

```text
POST /api/v1/readiness/engagements/{engagement_id}/books-health
GET  /api/v1/readiness/engagements/{engagement_id}/books-health
```

## Remaining Market-Grade Work

- Finish the CA-first UX pass for dashboard, planning, risks, controls, testing, review, reports, and seal flows.
- Complete a formal security review for tenant isolation, evidence file access, logs, backups, and immutability.
- Provision and test real production dependencies: PostgreSQL, Redis, S3/WORM bucket, external KMS, observability, backups, and AI provider credentials.
- Run the first-audit release gate and deployed smoke checks against staging before accepting unrestricted client data.

## Big 4 Automation Completion Layer

The platform now exposes a CA-controlled automation layer for the remaining market-grade gaps:

- `POST /api/v1/data-refinery/preview-excel` previews multi-sheet `.xlsx` workbooks without requiring Excel macros or local desktop tools.
- `POST /api/v1/data-refinery/preview-bank-pdf` accepts PDF bank statements and blocks ingestion until a production OCR provider is configured and CA review is performed.
- `GET /api/v1/audit-automation/capabilities` reports connector readiness for Tally, Zoho, Busy, SAP, Oracle, GST Portal, MCA, Income Tax, and PDF OCR.
- `POST /api/v1/audit-automation/engagements/{id}/sampling-plan` generates deterministic risk-weighted samples.
- `POST /api/v1/audit-automation/engagements/{id}/agents/run` runs the revenue, expense, GST, bank, fraud, IFC, CARO, and related-party agent pack as human-review-required decision support.
- `POST /api/v1/audit-automation/engagements/{id}/confirmations` records bank/customer/vendor confirmation requests in the audit chain.
- `POST /api/v1/audit-automation/engagements/{id}/management-responses` records management responses and remediation ownership in the audit chain.

These features reduce manual manpower, but they do not remove CA responsibility. Opinion/sign-off still requires partner judgment, evidence review, legal/compliance review, and documented management representations.

Additional hard gates in `scripts/production_readiness_check.py` now cover OCR provider readiness, backups, restore-drill evidence, metrics/observability, and legal/compliance sign-off metadata.
