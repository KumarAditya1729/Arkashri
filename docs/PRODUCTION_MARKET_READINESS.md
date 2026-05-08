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

## Remaining Market-Grade Work

- Finish the CA-first UX pass for dashboard, planning, risks, controls, testing, review, reports, and seal flows.
- Complete a formal security review for tenant isolation, evidence file access, logs, backups, and immutability.
