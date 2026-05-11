from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import (
    AuditSLAStatus,
    ControlEntry,
    ControlStatus,
    ControlType,
    Engagement,
    EvidenceRecord,
    ReportJob,
    ReportStatus,
    RiskEntry,
    RiskImpact,
    RiskLikelihood,
    RiskStatus,
    Transaction,
    WorkflowReportStatus,
    WorkflowReviewStatus,
)
from arkashri.services.audit import append_audit_event
from arkashri.services.canonical import hash_object

RiskBand = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class AuditAutomationError(ValueError):
    pass


CONNECTOR_CATALOG: list[dict[str, Any]] = [
    {"key": "TALLY_PRIME", "name": "Tally Prime", "status": "available", "mode": "xml_upload_or_http_connector", "region": "IN"},
    {"key": "ZOHO_BOOKS", "name": "Zoho Books", "status": "available", "mode": "http_api_connector", "region": "global"},
    {"key": "BUSY", "name": "Busy Accounting", "status": "mapped_via_generic_csv", "mode": "csv_excel_export", "region": "IN"},
    {"key": "SAP_S4HANA", "name": "SAP S/4HANA", "status": "available", "mode": "http_api_connector", "region": "global"},
    {"key": "ORACLE_FUSION", "name": "Oracle Fusion", "status": "available", "mode": "http_api_connector", "region": "global"},
    {"key": "GST_PORTAL", "name": "GST Portal", "status": "credential_required", "mode": "offline_return_upload_or_authorized_api", "region": "IN"},
    {"key": "MCA", "name": "MCA Company Master", "status": "available_for_enrichment", "mode": "manual_snapshot_or_api_adapter", "region": "IN"},
    {"key": "INCOME_TAX", "name": "Income Tax e-Filing", "status": "credential_required", "mode": "offline_form_upload_or_authorized_api", "region": "IN"},
    {"key": "PDF_BANK_OCR", "name": "PDF Bank Statement OCR", "status": "provider_required", "mode": "ocr_provider_or_text_pdf_extract", "region": "global"},
]

GLOBAL_COMPLIANCE_PACKS: list[dict[str, Any]] = [
    {"key": "ICAI_SA_CARO", "jurisdiction": "IN", "frameworks": ["ICAI SA", "Companies Act", "CARO 2020", "GST", "Income Tax"]},
    {"key": "ISA_IFRS", "jurisdiction": "GLOBAL", "frameworks": ["ISA", "IFRS"]},
    {"key": "PCAOB_SOX", "jurisdiction": "US", "frameworks": ["PCAOB AS", "SOX 404", "US GAAP"]},
    {"key": "SOC_1_2", "jurisdiction": "GLOBAL", "frameworks": ["SOC 1", "SOC 2", "Trust Services Criteria"]},
    {"key": "ISO_27001", "jurisdiction": "GLOBAL", "frameworks": ["ISO 27001", "ISO 27002"]},
    {"key": "ESG_ASSURANCE", "jurisdiction": "GLOBAL", "frameworks": ["ISSB", "GRI", "BRSR", "GHG Protocol"]},
]

AI_AUDIT_AGENTS: list[dict[str, Any]] = [
    {"key": "revenue_agent", "name": "Revenue Audit Agent", "areas": ["Revenue", "Cut-off", "Receivables"]},
    {"key": "expense_agent", "name": "Expense Audit Agent", "areas": ["Purchases", "Payables", "Opex"]},
    {"key": "gst_agent", "name": "GST Reconciliation Agent", "areas": ["GSTR-1", "GSTR-3B", "2B/2A", "ITC"]},
    {"key": "bank_agent", "name": "Bank and Cash Agent", "areas": ["Bank reconciliation", "Cash", "Confirmations"]},
    {"key": "fraud_agent", "name": "Fraud and Forensic Agent", "areas": ["Manual entries", "Round amounts", "Related parties"]},
    {"key": "ifc_agent", "name": "IFC / Internal Controls Agent", "areas": ["ITGC", "Maker-checker", "SOD"]},
    {"key": "caro_agent", "name": "CARO Agent", "areas": ["CARO 2020 clauses", "Companies Act"]},
    {"key": "related_party_agent", "name": "Related Party Agent", "areas": ["RPT", "Directors", "MCA"]},
]


_LIKELIHOOD_WEIGHT = {RiskLikelihood.HIGH: 3, RiskLikelihood.MEDIUM: 2, RiskLikelihood.LOW: 1}
_IMPACT_WEIGHT = {RiskImpact.CRITICAL: 4, RiskImpact.HIGH: 3, RiskImpact.MEDIUM: 2, RiskImpact.LOW: 1}


def _score(likelihood: RiskLikelihood, impact: RiskImpact) -> float:
    return min(_LIKELIHOOD_WEIGHT[likelihood] * _IMPACT_WEIGHT[impact] * 8.0, 99.0)


def _payload_engagement_id(transaction: Transaction) -> str | None:
    value = transaction.payload.get("engagement_id")
    return str(value) if value else None


def _signed_amount(transaction: Transaction) -> float:
    value = transaction.payload.get("signed_amount", transaction.payload.get("amount", 0))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _risk_band(score: float) -> RiskBand:
    if score >= 85:
        return "CRITICAL"
    if score >= 65:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _risk_levels(score: float) -> tuple[RiskLikelihood, RiskImpact]:
    if score >= 85:
        return RiskLikelihood.HIGH, RiskImpact.CRITICAL
    if score >= 65:
        return RiskLikelihood.HIGH, RiskImpact.HIGH
    if score >= 35:
        return RiskLikelihood.MEDIUM, RiskImpact.MEDIUM
    return RiskLikelihood.LOW, RiskImpact.LOW


def _area_from_category(category: str) -> str:
    return {
        "cash_and_bank": "Cash and Bank",
        "revenue": "Revenue",
        "expense": "Expenses",
        "gst_and_indirect_tax": "GST and Indirect Tax",
        "trade_receivables": "Trade Receivables",
        "trade_payables": "Trade Payables",
        "unmapped": "Unmapped Ledger",
    }.get(category, category.replace("_", " ").title())


async def _load_engagement(session: AsyncSession, engagement_id: uuid.UUID, tenant_id: str) -> Engagement:
    engagement = await session.scalar(
        select(Engagement).where(Engagement.id == engagement_id, Engagement.tenant_id == tenant_id)
    )
    if engagement is None:
        raise AuditAutomationError("Engagement not found.")
    return engagement


async def _engagement_transactions(session: AsyncSession, engagement: Engagement) -> list[Transaction]:
    rows = list(
        await session.scalars(
            select(Transaction)
            .where(Transaction.tenant_id == engagement.tenant_id, Transaction.jurisdiction == engagement.jurisdiction)
            .order_by(Transaction.created_at.asc())
        )
    )
    return [row for row in rows if _payload_engagement_id(row) == str(engagement.id)]


async def _engagement_risks(session: AsyncSession, engagement: Engagement) -> list[RiskEntry]:
    return list(
        await session.scalars(
            select(RiskEntry).where(
                RiskEntry.engagement_id == engagement.id,
                RiskEntry.tenant_id == engagement.tenant_id,
            )
        )
    )


async def _engagement_controls(session: AsyncSession, engagement: Engagement) -> list[ControlEntry]:
    return list(await session.scalars(select(ControlEntry).where(ControlEntry.engagement_id == engagement.id)))


async def _engagement_evidence(session: AsyncSession, engagement: Engagement) -> list[EvidenceRecord]:
    return list(
        await session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.engagement_id == engagement.id,
                EvidenceRecord.tenant_id == engagement.tenant_id,
            )
        )
    )


def build_risk_intelligence(transactions: list[Transaction]) -> dict[str, Any]:
    total = len(transactions)
    amounts = [abs(_signed_amount(transaction)) for transaction in transactions]
    total_value = round(sum(amounts), 2)
    materiality_proxy = max(100000.0, total_value * 0.01) if total_value else 100000.0
    category_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    duplicate_refs: Counter[str] = Counter()
    missing_gstin = 0
    high_value_count = 0
    findings: list[dict[str, Any]] = []

    for transaction in transactions:
        payload = transaction.payload
        category = str(payload.get("mapped_category") or "unmapped")
        reference = str(payload.get("ref") or "")
        amount = abs(_signed_amount(transaction))
        flags = [str(flag) for flag in payload.get("risk_flags") or []]
        category_counts[category] += 1
        flag_counts.update(flags)
        if reference:
            duplicate_refs[reference] += 1
        if category in {"revenue", "expense", "gst_and_indirect_tax"} and not payload.get("gstin"):
            missing_gstin += 1
        if amount >= materiality_proxy:
            high_value_count += 1

    if high_value_count:
        score = min(99.0, 45 + high_value_count * 8)
        findings.append(
            {
                "code": "HIGH_VALUE_TESTING",
                "title": "High-value transactions need targeted substantive testing",
                "area": "Substantive Testing",
                "score": score,
                "band": _risk_band(score),
                "transaction_count": high_value_count,
                "recommended_control": "Prepare top-value sample schedule and link invoice, approval and bank evidence before report review.",
            }
        )
    if flag_counts:
        score = min(99.0, 50 + sum(flag_counts.values()) * 6)
        findings.append(
            {
                "code": "ANOMALY_FLAGS",
                "title": "Anomaly flags detected in converted ledger data",
                "area": "Fraud and Journal Entry Risk",
                "score": score,
                "band": _risk_band(score),
                "flag_breakdown": dict(flag_counts),
                "recommended_control": "Review round amounts, manual adjustments, weekend entries and sensitive narrations with supporting evidence.",
            }
        )
    if duplicate_refs:
        duplicate_count = sum(count - 1 for count in duplicate_refs.values() if count > 1)
        if duplicate_count:
            score = min(99.0, 55 + duplicate_count * 10)
            findings.append(
                {
                    "code": "DUPLICATE_REFERENCE",
                    "title": "Duplicate voucher or reference numbers detected",
                    "area": "Completeness and Occurrence",
                    "score": score,
                    "band": _risk_band(score),
                    "duplicate_count": duplicate_count,
                    "recommended_control": "Match duplicate references to invoices, approvals and ledger reversal entries before accepting the population.",
                }
            )
    if missing_gstin:
        score = min(92.0, 40 + missing_gstin * 5)
        findings.append(
            {
                "code": "GST_MASTER_DATA_GAP",
                "title": "GSTIN missing on taxable or party-ledger rows",
                "area": "GST and Indirect Tax",
                "score": score,
                "band": _risk_band(score),
                "transaction_count": missing_gstin,
                "recommended_control": "Reconcile party GSTINs with sales, purchase and GST return data before tax audit sign-off.",
            }
        )
    if category_counts.get("unmapped", 0):
        unmapped = category_counts["unmapped"]
        score = min(90.0, 35 + unmapped * 4)
        findings.append(
            {
                "code": "UNMAPPED_LEDGER",
                "title": "Unmapped ledger rows need auditor classification",
                "area": "Data Quality",
                "score": score,
                "band": _risk_band(score),
                "transaction_count": unmapped,
                "recommended_control": "Map every material ledger to an audit area before sampling and report generation.",
            }
        )

    return {
        "transaction_count": total,
        "total_value": total_value,
        "materiality_proxy": round(materiality_proxy, 2),
        "category_breakdown": dict(category_counts),
        "risk_flag_breakdown": dict(flag_counts),
        "findings": sorted(findings, key=lambda item: item["score"], reverse=True),
    }


def build_working_paper_pack(
    engagement: Engagement,
    transactions: list[Transaction],
    risks: list[RiskEntry],
    controls: list[ControlEntry],
    evidence: list[EvidenceRecord],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    category_totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"rows": 0, "absolute_value": 0.0})
    for transaction in transactions:
        category = str(transaction.payload.get("mapped_category") or "unmapped")
        category_totals[category]["rows"] += 1
        category_totals[category]["absolute_value"] += abs(_signed_amount(transaction))

    schedules = []
    for index, (category, values) in enumerate(sorted(category_totals.items()), start=1):
        schedules.append(
            {
                "wp_ref": f"WP-{index:03d}",
                "area": _area_from_category(category),
                "population_count": values["rows"],
                "population_value": round(values["absolute_value"], 2),
                "suggested_procedure": "Perform risk-based sampling, inspect source evidence, document exception conclusion and reviewer sign-off.",
            }
        )

    open_risks = [risk for risk in risks if risk.risk_status in {RiskStatus.OPEN, RiskStatus.IN_REVIEW}]
    untested_controls = [control for control in controls if control.status == ControlStatus.NOT_TESTED]
    return {
        "pack_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:wp:{engagement.tenant_id}:{engagement.id}:{len(transactions)}:{len(risks)}")),
        "client_name": engagement.client_name,
        "standards_framework": engagement.standards_framework.value,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": [
            {"wp_ref": "WP-000", "title": "Planning and Materiality", "status": "ready" if transactions else "needs_data"},
            {"wp_ref": "WP-100", "title": "Risk Assessment", "status": "ready" if risks else "needs_risk_creation"},
            {"wp_ref": "WP-200", "title": "Internal Controls", "status": "ready" if controls and not untested_controls else "needs_testing"},
            {"wp_ref": "WP-300", "title": "Substantive Testing", "status": "ready" if schedules else "needs_population"},
            {"wp_ref": "WP-900", "title": "Completion and Reporting", "status": "ready" if evidence and not open_risks else "needs_review"},
        ],
        "schedules": schedules,
        "top_findings": intelligence["findings"][:10],
        "evidence_count": len(evidence),
        "open_risk_count": len(open_risks),
        "untested_control_count": len(untested_controls),
    }


def build_report_readiness(
    transactions: list[Transaction],
    risks: list[RiskEntry],
    controls: list[ControlEntry],
    evidence: list[EvidenceRecord],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    high_findings = [finding for finding in intelligence["findings"] if finding["band"] in {"HIGH", "CRITICAL"}]
    open_high_risks = [
        risk
        for risk in risks
        if risk.risk_status in {RiskStatus.OPEN, RiskStatus.IN_REVIEW} and risk.risk_score >= 65
    ]
    effective_controls = sum(1 for control in controls if control.status in {ControlStatus.EFFECTIVE, ControlStatus.COMPENSATING})

    checks = [
        {"code": "DATA_POPULATION", "passed": bool(transactions), "message": "At least one transaction population is available."},
        {"code": "RISK_REGISTER", "passed": bool(risks), "message": "Risk register has been created from the population."},
        {
            "code": "CONTROL_COVERAGE",
            "passed": bool(controls) and effective_controls >= max(1, len(controls) // 2),
            "message": "Controls are linked and at least half are effective or compensating.",
        },
        {"code": "EVIDENCE_REPOSITORY", "passed": bool(evidence), "message": "Evidence has been uploaded or linked."},
        {"code": "HIGH_RISK_REVIEW", "passed": not open_high_risks, "message": "No high-scoring risks remain open."},
        {"code": "AI_FINDING_REVIEW", "passed": not high_findings, "message": "No unresolved high AI risk findings remain."},
    ]
    passed = sum(1 for check in checks if check["passed"])
    score = round((passed / len(checks)) * 100)
    if not transactions:
        opinion = "DISCLAIMER"
    elif open_high_risks or any(finding["band"] == "CRITICAL" for finding in high_findings):
        opinion = "QUALIFIED"
    elif score < 50:
        opinion = "DISCLAIMER"
    elif score < 80:
        opinion = "QUALIFIED"
    else:
        opinion = "UNMODIFIED"
    return {
        "score": score,
        "checks": checks,
        "open_high_risk_count": len(open_high_risks),
        "high_ai_finding_count": len(high_findings),
        "suggested_opinion_type": opinion,
        "human_review_required": True,
        "basis": "System-generated decision support only. Engagement partner must review evidence, materiality, legal requirements and professional judgment before signing.",
    }


def build_capability_matrix() -> dict[str, Any]:
    return {
        "connectors": CONNECTOR_CATALOG,
        "ai_audit_agents": AI_AUDIT_AGENTS,
        "global_compliance_packs": GLOBAL_COMPLIANCE_PACKS,
        "manual_gate_required": [
            "Production GST/MCA/Income Tax portal credentials and client authorization",
            "OCR provider contract for scanned PDF bank statements",
            "Legal/compliance review before unrestricted sensitive client data",
            "External certification audits such as SOC 2 / ISO 27001",
        ],
    }


def build_sampling_plan(transactions: list[Transaction], *, sample_size: int = 25) -> dict[str, Any]:
    scored: list[tuple[float, Transaction]] = []
    for transaction in transactions:
        amount = abs(_signed_amount(transaction))
        flags = transaction.payload.get("risk_flags") or []
        score = amount + len(flags) * 100000
        if transaction.payload.get("mapped_category") == "unmapped":
            score += 50000
        scored.append((score, transaction))
    selected = [
        {
            "transaction_id": str(transaction.id),
            "ref": transaction.payload.get("ref"),
            "date": transaction.payload.get("date"),
            "amount": abs(_signed_amount(transaction)),
            "category": transaction.payload.get("mapped_category"),
            "risk_flags": transaction.payload.get("risk_flags") or [],
            "reason": "High-value/risk-weighted deterministic selection",
        }
        for _, transaction in sorted(scored, key=lambda item: item[0], reverse=True)[:sample_size]
    ]
    return {
        "method": "risk_weighted_deterministic",
        "population_count": len(transactions),
        "sample_size": len(selected),
        "coverage_value": round(sum(float(item["amount"]) for item in selected), 2),
        "samples": selected,
    }


def build_agent_run_pack(transactions: list[Transaction]) -> dict[str, Any]:
    intelligence = build_risk_intelligence(transactions)
    category_counts = intelligence["category_breakdown"]
    flag_counts = intelligence["risk_flag_breakdown"]
    outputs = []
    for agent in AI_AUDIT_AGENTS:
        agent_key = agent["key"]
        if agent_key == "revenue_agent":
            trigger_count = int(category_counts.get("revenue", 0))
        elif agent_key == "expense_agent":
            trigger_count = int(category_counts.get("expense", 0))
        elif agent_key == "gst_agent":
            trigger_count = int(category_counts.get("gst_and_indirect_tax", 0)) + int(flag_counts.get("MISSING_GST_HIGH_VALUE", 0))
        elif agent_key == "bank_agent":
            trigger_count = int(category_counts.get("cash_and_bank", 0))
        elif agent_key == "fraud_agent":
            trigger_count = sum(int(flag_counts.get(key, 0)) for key in ["ROUND_AMOUNT", "ROUND_NUMBER_HIGH_VALUE", "SENSITIVE_NARRATION", "WEEKEND_ENTRY"])
        elif agent_key == "ifc_agent":
            trigger_count = len(transactions)
        elif agent_key == "caro_agent":
            trigger_count = int(category_counts.get("unmapped", 0))
        else:
            trigger_count = sum(1 for txn in transactions if str(txn.payload.get("counterparty") or txn.payload.get("entity") or "").strip())
        outputs.append({
            **agent,
            "trigger_count": trigger_count,
            "status": "needs_review" if trigger_count else "no_population",
            "human_review_required": True,
        })
    return {"agents": outputs, "risk_intelligence": intelligence}


def render_working_paper_html(pack: dict[str, Any]) -> str:
    wp = pack["working_papers"]
    readiness = pack["report_readiness"]
    rows = "\n".join(
        f"<tr><td>{schedule.get('wp_ref')}</td><td>{schedule.get('area')}</td><td>{schedule.get('population_count')}</td><td>{schedule.get('population_value')}</td><td>{schedule.get('suggested_procedure')}</td></tr>"
        for schedule in wp.get("schedules", [])
    )
    findings = "\n".join(
        f"<li><strong>{finding.get('title')}</strong> ({finding.get('band')}): {finding.get('recommended_control')}</li>"
        for finding in wp.get("top_findings", [])
    )
    checks = "\n".join(
        f"<li>{'PASS' if check.get('passed') else 'OPEN'} - {check.get('code')}: {check.get('message')}</li>"
        for check in readiness.get("checks", [])
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Arkashri Working Paper Pack</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #111827; margin: 32px; }}
    h1, h2 {{ color: #002776; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; font-size: 12px; }}
    th {{ background: #f3f4f6; }}
    .meta {{ color: #4b5563; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Working Paper Pack</h1>
  <p class="meta">Client: {pack.get('client_name')} | Pack: {wp.get('pack_id')} | Framework: {pack.get('standards_framework')}</p>
  <h2>Report Readiness</h2>
  <p>Score: {readiness.get('score')}% | Suggested opinion support: {readiness.get('suggested_opinion_type')} | Human review required: Yes</p>
  <ul>{checks}</ul>
  <h2>Risk Findings</h2>
  <ul>{findings or '<li>No automated findings.</li>'}</ul>
  <h2>Schedules</h2>
  <table>
    <thead><tr><th>WP Ref</th><th>Area</th><th>Rows</th><th>Population Value</th><th>Suggested Procedure</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""


async def build_automation_pack(session: AsyncSession, *, tenant_id: str, engagement_id: uuid.UUID) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id, tenant_id)
    transactions = await _engagement_transactions(session, engagement)
    risks = await _engagement_risks(session, engagement)
    controls = await _engagement_controls(session, engagement)
    evidence = await _engagement_evidence(session, engagement)
    intelligence = build_risk_intelligence(transactions)
    working_papers = build_working_paper_pack(engagement, transactions, risks, controls, evidence, intelligence)
    readiness = build_report_readiness(transactions, risks, controls, evidence, intelligence)
    return {
        "engagement_id": str(engagement.id),
        "client_name": engagement.client_name,
        "audit_type": engagement.audit_type.value,
        "standards_framework": engagement.standards_framework.value,
        "risk_intelligence": intelligence,
        "working_papers": working_papers,
        "report_readiness": readiness,
    }


async def run_big4_automation_pack(
    session: AsyncSession,
    *,
    tenant_id: str,
    engagement_id: uuid.UUID,
    actor: str,
    create_risks: bool = True,
    create_controls: bool = True,
    persist_report: bool = True,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id, tenant_id)
    existing_risks = await _engagement_risks(session, engagement)
    risk_titles = {risk.title for risk in existing_risks}
    next_risk_number = len(existing_risks) + 1
    created_risks: list[RiskEntry] = []

    pack = await build_automation_pack(session, tenant_id=tenant_id, engagement_id=engagement_id)
    for finding in pack["risk_intelligence"]["findings"]:
        if not create_risks or finding["title"] in risk_titles or finding["band"] == "LOW":
            continue
        likelihood, impact = _risk_levels(float(finding["score"]))
        risk = RiskEntry(
            engagement_id=engagement.id,
            tenant_id=engagement.tenant_id,
            risk_ref=f"RSK-{next_risk_number:03d}",
            title=finding["title"],
            area=finding["area"],
            likelihood=likelihood,
            impact=impact,
            risk_score=_score(likelihood, impact),
            owner="Arkashri Automation",
            control_ref=f"AUTO-{finding['code']}",
            risk_status=RiskStatus.OPEN,
        )
        session.add(risk)
        created_risks.append(risk)
        risk_titles.add(risk.title)
        next_risk_number += 1

    if created_risks:
        await session.flush()

    existing_controls = await _engagement_controls(session, engagement)
    control_titles = {control.title for control in existing_controls}
    created_controls: list[ControlEntry] = []
    if create_controls:
        for risk in created_risks:
            title = f"Automated response plan for {risk.area}"
            if title in control_titles:
                continue
            control = ControlEntry(
                engagement_id=engagement.id,
                risk_id=risk.id,
                title=title,
                area=risk.area,
                control_type=ControlType.DETECTIVE,
                frequency="Per audit cycle",
                owner="Engagement Team",
                status=ControlStatus.NOT_TESTED,
            )
            session.add(control)
            created_controls.append(control)
            control_titles.add(title)

    if created_controls:
        await session.flush()

    pack = await build_automation_pack(session, tenant_id=tenant_id, engagement_id=engagement_id)
    report_job: ReportJob | None = None
    if persist_report:
        now = datetime.now(timezone.utc)
        report_payload = {
            "report_type": "BIG4_AUTOMATION_PACK",
            "human_review_required": True,
            "engagement_id": str(engagement.id),
            "client_name": engagement.client_name,
            "automation_pack": pack,
        }
        report_job = ReportJob(
            tenant_id=engagement.tenant_id,
            jurisdiction=engagement.jurisdiction,
            period_start=engagement.period_start or engagement.start_date,
            period_end=engagement.period_end or now,
            status=ReportStatus.GENERATED,
            report_hash=hash_object(report_payload),
            report_payload=report_payload,
            created_at=now,
        )
        session.add(report_job)
        engagement.report_status = WorkflowReportStatus.DRAFT
        engagement.review_status = WorkflowReviewStatus.IN_REVIEW
        if pack["report_readiness"]["score"] < 80:
            engagement.sla_status = AuditSLAStatus.AT_RISK

    await append_audit_event(
        session,
        tenant_id=engagement.tenant_id,
        engagement_id=engagement.id,
        jurisdiction=engagement.jurisdiction,
        event_type="BIG4_AUTOMATION_PACK_RUN",
        entity_type="engagement",
        entity_id=str(engagement.id),
        payload={
            "actor": actor,
            "created_risk_count": len(created_risks),
            "created_control_count": len(created_controls),
            "report_job_id": str(report_job.id) if report_job else None,
            "readiness_score": pack["report_readiness"]["score"],
            "suggested_opinion_type": pack["report_readiness"]["suggested_opinion_type"],
            "human_review_required": True,
        },
    )
    await session.commit()
    return {
        "created_risk_count": len(created_risks),
        "created_control_count": len(created_controls),
        "report_job_id": str(report_job.id) if report_job else None,
        "pack": pack,
    }
