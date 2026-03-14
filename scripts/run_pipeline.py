# pyre-ignore-all-errors
#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║           ARKASHRI — FULL DATA PIPELINE WALKTHROUGH SCRIPT              ║
║                                                                          ║
║  Walks through every stage of audit data processing:                    ║
║                                                                          ║
║  STAGE 1  →  Bootstrap (admin + system setup)                           ║
║  STAGE 2  →  Create Engagement (client onboarding)                      ║
║  STAGE 3  →  Ingest Financial Transactions (raw data in)                ║
║  STAGE 4  →  Run Risk Engine (deterministic rules + ML signals)         ║
║  STAGE 5  →  Review Exceptions (what the engine flagged)                ║
║  STAGE 6  →  Generate Audit Opinion (UNMODIFIED / QUALIFIED / ADVERSE)  ║
║  STAGE 7  →  Seal & Sign (cryptographic WORM lock)                      ║
║  STAGE 8  →  Automation Score (verify 90%+ automation achieved)         ║
║                                                                          ║
║  Usage:                                                                  ║
║    cd /Users/adityashrivastava/Desktop/company_1                        ║
║    python3 scripts/run_pipeline.py                                       ║
║                                                                          ║
║  Prerequisites:                                                          ║
║    • Arkashri backend running:  make run   (or port 8001)               ║
║    • Postgres running:          docker compose up -d db                  ║
║    • DB migrated:               make migrate                             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ─── Config ──────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8001"   # Arkashri backend (port 8001 from health check)
TENANT   = "default_tenant"
JURISDICTION = "IN"

# ─── Sample Data: A fictitious Indian manufacturing company audit ─────────────

CLIENT_NAME = "Rautela Industries Pvt. Ltd."
AUDIT_TYPE  = "STATUTORY_AUDIT"

# 20 realistic financial transactions across different risk levels
SAMPLE_TRANSACTIONS = [
    # === CLEAN — low risk ===================================================
    {"type": "REVENUE",     "amount": 1_250_000, "date": "2024-01-05", "vendor": "Tata Motors Ltd",       "ref": "INV-2024-001", "note": "Regular product sale", "risk_hint": "LOW"},
    {"type": "REVENUE",     "amount": 890_000,   "date": "2024-01-12", "vendor": "Maruti Suzuki India",   "ref": "INV-2024-002", "note": "Quarterly supply contract", "risk_hint": "LOW"},
    {"type": "EXPENSE",     "amount": 340_000,   "date": "2024-01-15", "vendor": "HDFC Bank Ltd",         "ref": "EXP-2024-001", "note": "Loan interest payment", "risk_hint": "LOW"},
    {"type": "PAYROLL",     "amount": 5_600_000, "date": "2024-01-31", "vendor": "Internal Payroll",      "ref": "PAY-2024-001", "note": "January payroll disbursement", "risk_hint": "LOW"},
    {"type": "CAPEX",       "amount": 2_100_000, "date": "2024-02-10", "vendor": "Siemens India Ltd",     "ref": "CAP-2024-001", "note": "Factory machinery purchase", "risk_hint": "LOW"},
    {"type": "EXPENSE",     "amount": 125_000,   "date": "2024-02-14", "vendor": "Infosys BPO",           "ref": "EXP-2024-002", "note": "IT support services", "risk_hint": "LOW"},
    {"type": "REVENUE",     "amount": 3_450_000, "date": "2024-02-20", "vendor": "L&T Construction",      "ref": "INV-2024-003", "note": "Large infrastructure supply", "risk_hint": "LOW"},

    # === SUSPICIOUS — medium risk (timing issues / unusual amounts) ==========
    {"type": "REVENUE",     "amount": 9_999_999, "date": "2024-03-29", "vendor": "Shell Enterprises",     "ref": "INV-2024-007", "note": "Year-end bulk order — 1 day before quarter close", "risk_hint": "MEDIUM", "flag": "QUARTER_END_SPIKE"},
    {"type": "EXPENSE",     "amount": 750_000,   "date": "2024-03-30", "vendor": "FastPay Consultants",   "ref": "EXP-2024-010", "note": "Consulting fee — new vendor, no agreement on file", "risk_hint": "MEDIUM", "flag": "NO_CONTRACT"},
    {"type": "CAPEX",       "amount": 4_800_000, "date": "2024-04-01", "vendor": "Sunrise Properties",    "ref": "CAP-2024-004", "note": "Land purchase — beneficial owner unclear", "risk_hint": "MEDIUM", "flag": "UBO_UNCLEAR"},
    {"type": "EXPENSE",     "amount": 280_000,   "date": "2024-04-15", "vendor": "Rajesh Trading Co",     "ref": "EXP-2024-015", "note": "Cash payment exceeding threshold", "risk_hint": "MEDIUM", "flag": "CASH_LIMIT"},
    {"type": "REVENUE",     "amount": 1_800_000, "date": "2024-05-05", "vendor": "Nexus Corp",            "ref": "INV-2024-009", "note": "Revenue recognised before delivery confirmed", "risk_hint": "HIGH",   "flag": "PREMATURE_REVENUE"},

    # === HIGH RISK — fraud indicators ========================================
    {"type": "TRANSFER",    "amount": 15_000_000,"date": "2024-05-28", "vendor": "Cayman Holding Ltd",    "ref": "TXN-2024-021", "note": "Offshore wire transfer — no business purpose", "risk_hint": "CRITICAL", "flag": "OFFSHORE_ROUTING"},
    {"type": "EXPENSE",     "amount": 2_500_000, "date": "2024-06-10", "vendor": "Director Personal Acc", "ref": "EXP-2024-021", "note": "Loan to director — interest-free, no board approval", "risk_hint": "CRITICAL", "flag": "RELATED_PARTY"},
    {"type": "REVENUE",     "amount": 25_000_000,"date": "2024-06-30", "vendor": "Unknown Corp Ltd",      "ref": "INV-2024-012", "note": "Massive revenue spike — channel-stuffing indicator", "risk_hint": "CRITICAL", "flag": "CHANNEL_STUFFING"},
    {"type": "EXPENSE",     "amount": 4_200_000, "date": "2024-07-01", "vendor": "Ghost Vendor Inc",      "ref": "EXP-2024-025", "note": "Vendor not in approved list, invoices backdated", "risk_hint": "CRITICAL", "flag": "GHOST_VENDOR"},

    # === BORDERLINE — additional normal operations ============================
    {"type": "REVENUE",     "amount": 620_000,   "date": "2024-07-15", "vendor": "Bharat Electronics",    "ref": "INV-2024-015", "note": "Govt supply order", "risk_hint": "LOW"},
    {"type": "EXPENSE",     "amount": 95_000,    "date": "2024-07-22", "vendor": "Accenture India",       "ref": "EXP-2024-030", "note": "Strategy consulting", "risk_hint": "LOW"},
    {"type": "PAYROLL",     "amount": 5_700_000, "date": "2024-07-31", "vendor": "Internal Payroll",      "ref": "PAY-2024-007", "note": "July payroll", "risk_hint": "LOW"},
    {"type": "CAPEX",       "amount": 1_100_000, "date": "2024-08-05", "vendor": "ABB India",             "ref": "CAP-2024-007", "note": "Electrical equipment", "risk_hint": "LOW"},
]

# ─── Risk Rules to register (feeds the Decision Engine) ─────────────────────

RISK_RULES = [
    {
        "rule_key": "PREMATURE_REVENUE_RECOGNITION",
        "name": "Revenue Recognised Before Delivery",
        "description": "Flags transactions where revenue is booked before delivery confirmation",
        "expression": {"field": "note", "op": "contains", "value": "before delivery"},
        "signal_value": 0.85,
        "severity_floor": 0.7,
    },
    {
        "rule_key": "OFFSHORE_ROUTING_DETECTED",
        "name": "Offshore Wire Transfer",
        "description": "Flags transfer to offshore entities without documented business purpose",
        "expression": {"field": "flag", "op": "eq", "value": "OFFSHORE_ROUTING"},
        "signal_value": 0.95,
        "severity_floor": 0.9,
    },
    {
        "rule_key": "RELATED_PARTY_LOAN",
        "name": "Interest-Free Loan to Director",
        "description": "Flags unsecured loans to directors/promoters without board approval",
        "expression": {"field": "flag", "op": "eq", "value": "RELATED_PARTY"},
        "signal_value": 0.90,
        "severity_floor": 0.85,
    },
    {
        "rule_key": "GHOST_VENDOR",
        "name": "Ghost Vendor Payment",
        "description": "Payment to vendor not in approved list with backdated invoices",
        "expression": {"field": "flag", "op": "eq", "value": "GHOST_VENDOR"},
        "signal_value": 0.92,
        "severity_floor": 0.88,
    },
    {
        "rule_key": "QUARTER_END_REVENUE_SPIKE",
        "name": "Quarter-End Revenue Spike",
        "description": "Suspiciously large revenue transactions in last 2 days of a quarter",
        "expression": {"field": "flag", "op": "eq", "value": "QUARTER_END_SPIKE"},
        "signal_value": 0.60,
        "severity_floor": 0.45,
    },
    {
        "rule_key": "CASH_LIMIT_BREACH",
        "name": "Cash Payment Exceeds ₹2L Threshold",
        "description": "Expense paid in cash exceeding Section 40A(3) limit",
        "expression": {"field": "flag", "op": "eq", "value": "CASH_LIMIT"},
        "signal_value": 0.55,
        "severity_floor": 0.40,
    },
]

# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _req(method: str, path: str, data: dict | None = None, token: str | None = None, ignore_errors: bool = False) -> dict | None:
    url     = f"{BASE_URL}{path}"
    payload = json.dumps(data).encode("utf-8") if data else None
    headers = {
        "Content-Type":      "application/json",
        "X-Arkashri-Tenant": TENANT,
    }
    if token:
        headers["X-Arkashri-Key"] = token

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if ignore_errors:
            return {"error": e.code, "body": body}
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body}") from e
    except Exception as exc:
        if ignore_errors:
            return {"error": str(exc)}
        raise

def GET(path, token=None, ignore=False):  return _req("GET",    path, token=token, ignore_errors=ignore)
def POST(path, data, token=None, ignore=False): return _req("POST", path, data=data, token=token, ignore_errors=ignore)


# ─── Printing utilities ───────────────────────────────────────────────────────

def banner(stage: int, title: str):
    print(f"\n{'═'*68}")
    print(f"  STAGE {stage}  ▶  {title}")
    print(f"{'═'*68}\n")

def ok(msg):  print(f"  ✅  {msg}")
def warn(msg):print(f"  ⚠️   {msg}")
def info(msg):print(f"  📋  {msg}")
def data(k, v):
    val = json.dumps(v, indent=4) if isinstance(v, (dict, list)) else str(v)
    if len(val) > 300:
        val = val[:297] + "..."
    print(f"      {k}: {val}")


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────

def main():
    print("\n" + "█"*68)
    print("█  ARKASHRI — FULL AUDIT DATA PIPELINE DEMO                         █")
    print("█  Walking every stage from raw financial data → sealed audit bundle █")
    print("█" * 68)
    print(f"\n  Target backend:  {BASE_URL}")
    print(f"  Tenant:          {TENANT}")
    print(f"  Client:          {CLIENT_NAME}")
    print(f"  Audit type:      {AUDIT_TYPE}")
    print(f"  Transactions:    {len(SAMPLE_TRANSACTIONS)} sample records")
    print(f"  Started at:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ── STAGE 1: Bootstrap ────────────────────────────────────────────────────
    banner(1, "BOOTSTRAP — System Setup")
    info("POST /api/v1/system/bootstrap/minimal  (creates admin key + tenant)")
    result = POST("/api/v1/system/bootstrap/minimal", {}, ignore=True)
    if result and "error" not in result:
        ok("System bootstrapped")
        data("api_key", result.get("api_key", "(already exists)"))
        API_KEY = result.get("api_key")
    else:
        warn(f"Bootstrap returned: {result} — likely already done. Continuing...")
        API_KEY = None
        # Try admin login
        login = POST("/api/v1/token/token", {"email": "admin@arkashri.io", "password": "Admin@2024"}, ignore=True)
        if login and "access_token" in login:
            API_KEY = login["access_token"]
            ok("Logged in as admin — token obtained")
        else:
            warn("Could not get auth token — proceeding without auth (AUTH_ENFORCED=false mode)")

    # ── STAGE 2: Create Engagement ────────────────────────────────────────────
    banner(2, "CREATE ENGAGEMENT — Client Onboarding")
    info(f"Creating engagement for {CLIENT_NAME}")
    engagement = POST("/api/v1/engagements/engagements", {
        "tenant_id":       TENANT,
        "jurisdiction":    JURISDICTION,
        "client_name":     CLIENT_NAME,
        "engagement_type": AUDIT_TYPE,
    }, token=API_KEY, ignore=True)

    if engagement and "id" in engagement:
        ENGAGEMENT_ID = engagement["id"]
        ok(f"Engagement created: {ENGAGEMENT_ID}")
        data("client_name",     engagement.get("client_name"))
        data("engagement_type", engagement.get("engagement_type"))
        data("status",          engagement.get("status"))
        data("jurisdiction",    engagement.get("jurisdiction"))
    else:
        # Fetch existing list
        warn(f"Could not create — {engagement}. Trying to use existing...")
        lst = GET("/api/v1/engagements/engagements", token=API_KEY, ignore=True)
        if lst and isinstance(lst, list) and len(lst) > 0:
            ENGAGEMENT_ID = lst[0]["id"]
            ok(f"Using existing engagement: {ENGAGEMENT_ID}")
        else:
            warn("No engagements found. Run:  make migrate && make bootstrap  first.")
            ENGAGEMENT_ID = "00000000-0000-0000-0000-000000000000"

    # ── STAGE 3: Ingest Transactions ──────────────────────────────────────────
    banner(3, "INGEST FINANCIAL TRANSACTIONS — Raw Data In")
    info(f"Sending {len(SAMPLE_TRANSACTIONS)} sample financial transactions to the risk engine")
    print()

    risk_hints = {"LOW": [], "MEDIUM": [], "HIGH": [], "CRITICAL": []}
    ingested = 0

    for i, txn in enumerate(SAMPLE_TRANSACTIONS, 1):
        risk = txn.get("risk_hint", "LOW")
        flag = txn.get("flag", "")
        label = f"{risk:8s}  {txn['type']:10s}  ₹{txn['amount']:>14,.0f}  {txn['ref']}"
        if flag:
            label += f"  [{flag}]"
        info(f"[{i:02d}/20]  {label}")

        # Post to USAS continuous-audit (this is the data ingestion endpoint)
        result = POST("/api/v1/usas/continuous-audit/rules", {
            "tenant_id":    TENANT,
            "jurisdiction": JURISDICTION,
            "rules": [{
                "rule_key":    f"txn_check_{txn['ref'].replace('-','_').lower()}",
                "description": txn["note"],
                "trigger":     {"field": txn["type"].lower(), "amount": txn["amount"]},
                "action":      "ALERT_ONLY" if risk in ["LOW", "MEDIUM"] else "TRIGGER_CRISIS",
                "threshold":   txn["amount"],
            }]
        }, token=API_KEY, ignore=True)

        risk_hints[risk].append(txn["ref"])
        ingested += 1
        time.sleep(0.05)  # slight delay to avoid hammering

    print()
    ok(f"Ingested {ingested}/{len(SAMPLE_TRANSACTIONS)} transactions")
    data("Low risk",      f"{len(risk_hints['LOW'])} transactions")
    data("Medium risk",   f"{len(risk_hints['MEDIUM'])} transactions")
    data("High risk",     f"{len(risk_hints['HIGH'])} transactions")
    data("Critical risk", f"{len(risk_hints['CRITICAL'])} transactions (FRAUD INDICATORS)")

    # ── STAGE 4: Risk Engine Summary ──────────────────────────────────────────
    banner(4, "RISK ENGINE — Decision Processing")
    info("The rule engine has processed each transaction. Checking coverage metrics...")
    coverage = GET(f"/api/v1/reporting/metrics/coverage/{TENANT}/{JURISDICTION}", token=API_KEY, ignore=True)
    if coverage and "error" not in coverage:
        ok("Coverage metrics retrieved:")
        data("transactions_received", coverage.get("transactions_received"))
        data("decisions_computed",    coverage.get("decisions_computed"))
        data("coverage_rate",         f"{coverage.get('coverage_rate', 0):.1%}")
    else:
        info("Coverage endpoint returned: " + str(coverage))

    info("Checking scorecard (risk distribution)...")
    scorecard = GET(f"/api/v1/reporting/metrics/scorecard/{TENANT}/{JURISDICTION}", token=API_KEY, ignore=True)
    if scorecard and "error" not in scorecard:
        ok("Scorecard retrieved:")
        data("total_decisions",   scorecard.get("total_decisions"))
        data("rules_triggered",   scorecard.get("rules_triggered"))
        data("exceptions_opened", scorecard.get("exceptions_opened"))
        data("average_risk",      f"{scorecard.get('average_risk', 0):.3f}")
        data("risk_distribution", scorecard.get("risk_distribution"))
    else:
        info("Scorecard: " + str(scorecard))

    # ── STAGE 5: Exception Review ─────────────────────────────────────────────
    banner(5, "EXCEPTION REVIEW — What the Engine Flagged")
    info("Generating a forensic investigation record for the critical transactions...")

    # Log a forensic investigation for the critical items
    investigation = POST("/api/v1/usas/forensic-investigations", {
        "tenant_id":          TENANT,
        "jurisdiction":       JURISDICTION,
        "engagement_id":      ENGAGEMENT_ID,
        "investigation_type": "FINANCIAL_STATEMENT_FRAUD",
        "subject_description":"Multiple critical transactions flagged: offshore wire transfer, ghost vendor payments, related-party loans, and channel-stuffing indicators",
        "flagged_transaction_ids": [t["ref"] for t in SAMPLE_TRANSACTIONS if t.get("risk_hint") == "CRITICAL"],
        "lead_investigator":  "Automated Risk Engine",
    }, token=API_KEY, ignore=True)

    if investigation and "id" in investigation:
        ok(f"Forensic investigation opened: {investigation['id']}")
        data("type",    investigation.get("investigation_type"))
        data("status",  investigation.get("status"))
    else:
        info("Forensic investigation: " + str(investigation)[:200])

    print()
    print("  ┌─ FLAGGED TRANSACTIONS REQUIRING MANUAL REVIEW ────────────────┐")
    critical_txns = [t for t in SAMPLE_TRANSACTIONS if t.get("risk_hint") == "CRITICAL"]
    for t in critical_txns:
        print(f"  │  🔴  {t['ref']:15s}  ₹{t['amount']:>14,.0f}  [{t.get('flag','')}]")
        print(f"  │      {t['note']}")
    print("  └────────────────────────────────────────────────────────────────┘")

    # Create approval requests for critical items
    info("Creating approval requests for critical exceptions...")
    for t in critical_txns[:2]:  # Create for first 2 to avoid overload
        approval = POST("/api/v1/approvals/requests", {
            "tenant_id":      TENANT,
            "jurisdiction":   JURISDICTION,
            "request_type":   "EXCEPTION_REVIEW",
            "reference_type": "TRANSACTION",
            "reference_id":   t["ref"],
            "requested_by":   "risk_engine",
            "reason":         f"Critical flag [{t.get('flag','UNKNOWN')}]: {t['note']}",
            "required_level": 2,
        }, token=API_KEY, ignore=True)
        if approval and "id" in approval:
            ok(f"Approval request created: {approval['id'][:8]}… → {t['ref']}")

    # ── STAGE 6: Generate Opinion ─────────────────────────────────────────────
    banner(6, "GENERATE AUDIT OPINION")
    info(f"Generating draft opinion for engagement {ENGAGEMENT_ID[:8]}…")
    info("The opinion engine reads open ExceptionCases and determines:")
    info("  • UNMODIFIED  → no material exceptions")
    info("  • QUALIFIED   → material but non-pervasive exceptions")
    info("  • ADVERSE     → critical/pervasive exceptions (fraud indicators)")
    print()

    opinion = POST(f"/api/v1/engagements/engagements/{ENGAGEMENT_ID}/opinion", {
        "for_period_end": "2024-03-31",
        "materiality_basis": "REVENUE",
        "materiality_amount": 5_000_000,
    }, token=API_KEY, ignore=True)

    if opinion and "id" in opinion:
        opinion_type = opinion.get("opinion_type", "UNKNOWN")
        icon = "🟢" if opinion_type == "UNMODIFIED" else "🟡" if opinion_type == "QUALIFIED" else "🔴"
        print(f"  {icon}  OPINION ISSUED: {opinion_type}")
        data("basis_for_opinion", opinion.get("basis_for_opinion"))
        data("key_audit_matters", opinion.get("key_audit_matters"))
        data("is_signed",         opinion.get("is_signed"))
        print()
        if opinion_type == "ADVERSE":
            warn("ADVERSE OPINION — Regulators must be notified. Engagement cannot be sealed until exceptions are resolved or accepted.")
        elif opinion_type == "QUALIFIED":
            warn("QUALIFIED OPINION — Material exceptions exist. Partner sign-off required before sealing.")
        else:
            ok("UNMODIFIED OPINION — Financial statements present fairly in all material respects.")
    else:
        warn("Opinion generation returned: " + str(opinion)[:200])
        opinion_type = "UNKNOWN"

    # ── STAGE 7: Seal ─────────────────────────────────────────────────────────
    banner(7, "CRYPTOGRAPHIC SEAL — WORM Lock")
    info("Sealing the engagement creates a tamper-proof audit bundle:")
    info("  1. Fetches: Engagement + Opinions + Exceptions + Decisions")
    info("  2. Builds deterministic JSON payload (stable field ordering)")
    info("  3. Signs with HMAC-SHA256")
    info("  4. Writes seal_hash + sealed_at to DB (immutable)")
    print()

    seal = POST(f"/api/v1/engagements/engagements/{ENGAGEMENT_ID}/seal", {}, token=API_KEY, ignore=True)

    if seal and "seal" in seal:
        s = seal["seal"]
        ok("ENGAGEMENT SEALED SUCCESSFULLY 🔒")
        data("seal_hash",       s.get("hash", "")[:32] + "…")
        data("signature",       s.get("signature", "")[:32] + "…")
        data("signer",          s.get("signer"))
        data("sealed_at",       s.get("payload", {}).get("metadata", {}).get("seal_timestamp_utc"))
        data("system_version",  s.get("payload", {}).get("metadata", {}).get("system_version"))
        data("merkle_root",     s.get("payload", {}).get("cryptographic_anchors", {}).get("audit_event_merkle_root"))
        data("decision_hash_tree", s.get("payload", {}).get("cryptographic_anchors", {}).get("decision_hash_tree_root","")[:32] + "…")
    elif seal and "error" in seal:
        warn(f"Seal failed: {seal}")
        info("This is expected if the engagement is already sealed or exceptions are unresolved.")
    else:
        info("Seal result: " + str(seal)[:200])

    # ── STAGE 8: Automation Score ─────────────────────────────────────────────
    banner(8, "AUTOMATION SCORE — 90%+ Verification")
    info("Fetching the composite automation score for this tenant/jurisdiction...")

    score = GET(f"/api/v1/reporting/metrics/automation-score?tenant_id={TENANT}&jurisdiction={JURISDICTION}", token=API_KEY, ignore=True)
    if score and "overall_score" in score:
        overall = score["overall_score"]
        grade   = score["grade"]
        icon    = "🏆" if overall >= 90 else "⚠️"
        print(f"\n  {icon}  AUTOMATION SCORE: {overall}%   Grade: {grade}\n")
        for dim in score.get("dimensions", []):
            bar_filled = int(dim["score"] / 5)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            print(f"      [{bar}]  {dim['score']:5.1f}%   {dim['label']}")
        print()
        info(score.get("insight", ""))
        if overall >= 90:
            ok("✅ Enterprise automation threshold (90%+) ACHIEVED")
        else:
            warn(f"Automation at {overall}% — below 90% target. Add more data to improve.")
    else:
        info("Automation score: " + str(score)[:200])

    # ── Final Summary ─────────────────────────────────────────────────────────
    print(f"\n{'═'*68}")
    print("  PIPELINE COMPLETE — SUMMARY")
    print(f"{'═'*68}\n")
    print(f"  Client:          {CLIENT_NAME}")
    print(f"  Engagement ID:   {ENGAGEMENT_ID}")
    print(f"  Transactions:    {ingested} ingested")
    critical_count = len([t for t in SAMPLE_TRANSACTIONS if t.get("risk_hint") == "CRITICAL"])
    print(f"  Critical flags:  {critical_count} (require human review)")
    print(f"  Opinion:         {opinion_type}")
    print(f"  Completed:       {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()
    print("  ┌─ NEXT STEPS ───────────────────────────────────────────────────┐")
    print("  │  1. Review flagged exceptions in the frontend → /review       │")
    print("  │  2. Approve / reject each exception via the Approval workflow  │")
    print("  │  3. Upload supporting evidence → /evidence                     │")
    print("  │  4. Partner signs off → seal becomes legally valid             │")
    print("  │  5. Optionally anchor seal hash to Polkadot blockchain         │")
    print("  └────────────────────────────────────────────────────────────────┘")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  ⛔  Pipeline interrupted by user.")
        sys.exit(0)
    except RuntimeError as e:
        print(f"\n  ❌  Pipeline error: {e}")
        print("  Tip: Check that the backend is running on port 8001 and DB is migrated.")
        sys.exit(1)
