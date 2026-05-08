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

## Remaining Market-Grade Work

- Run a real authenticated production smoke test using a seeded CA/operator account.
- Finish the CA-first UX pass for dashboard, planning, risks, controls, testing, review, reports, and seal flows.
- Add automated end-to-end tests for the full engagement lifecycle on real backend records.
- Complete a formal security review for tenant isolation, evidence file access, logs, backups, and immutability.
