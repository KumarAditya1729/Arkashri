from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, EvidenceRecord, Transaction
from arkashri.services.client_query_workflow import create_client_query, get_client_portal_workflow
from arkashri.services.gst_reconciliation import GST_RECON_KEY

BOOKS_HEALTH_KEY = "books_health_checks"

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class BooksHealthError(ValueError):
    pass


@dataclass(frozen=True)
class HealthIssue:
    category: str
    severity: Severity
    title: str
    description: str
    recommended_action: str
    amount: float | None = None
    source_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": _issue_id(self.category, self.title, self.source_refs),
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "recommended_action": self.recommended_action,
            "amount": self.amount,
            "source_refs": list(self.source_refs),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue_id(category: str, title: str, source_refs: tuple[str, ...]) -> str:
    seed = "|".join([category, title, *source_refs])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:books-health:{seed}"))


def _score_from_issues(base_score: int, issues: list[HealthIssue]) -> int:
    penalty = 0
    for issue in issues:
        penalty += {
            "CRITICAL": 35,
            "HIGH": 22,
            "MEDIUM": 10,
            "LOW": 4,
        }[issue.severity]
    return max(0, min(100, base_score - penalty))


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _payload_ref(payload: dict[str, Any]) -> str:
    return str(payload.get("ref") or payload.get("erp_doc_id") or payload.get("voucher_number") or "UNREFERENCED")


def _parse_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def _load_engagement(session: AsyncSession, *, engagement_id: uuid.UUID, tenant_id: str) -> Engagement:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise BooksHealthError("Engagement not found.")
    return engagement


async def _load_transactions(session: AsyncSession, *, engagement_id: uuid.UUID, tenant_id: str) -> list[Transaction]:
    transactions = list(await session.scalars(select(Transaction).where(Transaction.tenant_id == tenant_id)))
    return [
        txn
        for txn in transactions
        if str((txn.payload or {}).get("engagement_id") or "") in {"", str(engagement_id)}
    ]


async def _load_evidence(session: AsyncSession, *, engagement_id: uuid.UUID, tenant_id: str) -> list[EvidenceRecord]:
    return list(
        await session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.engagement_id == engagement_id,
                EvidenceRecord.tenant_id == tenant_id,
            )
        )
    )


def _bank_readiness(transactions: list[Transaction]) -> dict[str, Any]:
    issues: list[HealthIssue] = []
    bank_statement_rows = []
    bank_book_rows = []
    for txn in transactions:
        payload = txn.payload or {}
        if payload.get("erp_system") == "BANK_STATEMENT":
            bank_statement_rows.append(payload)
        if payload.get("mapped_category") == "cash_and_bank" or "BANK" in str(payload.get("account_name") or "").upper():
            bank_book_rows.append(payload)

    if not bank_statement_rows:
        issues.append(
            HealthIssue(
                category="BANK",
                severity="CRITICAL",
                title="Bank statement not imported",
                description="The audit cannot complete a bank reconciliation readiness check without bank statement data.",
                recommended_action="Ask the client to upload bank statements for the audit period.",
                source_refs=("BANK_STATEMENT",),
            )
        )
    if not bank_book_rows:
        issues.append(
            HealthIssue(
                category="BANK",
                severity="HIGH",
                title="Bank ledger not identified in books",
                description="Arkashri could not identify cash/bank ledger entries from the imported books.",
                recommended_action="Import a Tally/ERP ledger dump with bank ledger mappings or review the account mapping.",
                source_refs=("CASH_AND_BANK_LEDGER",),
            )
        )

    statement_total = round(sum(_safe_float(row.get("signed_amount") or row.get("amount")) for row in bank_statement_rows), 2)
    book_total = round(sum(_safe_float(row.get("signed_amount")) for row in bank_book_rows), 2)
    variance = round(abs(statement_total - book_total), 2)
    if bank_statement_rows and bank_book_rows and variance > max(1000.0, abs(statement_total) * 0.01):
        issues.append(
            HealthIssue(
                category="BANK",
                severity="HIGH",
                title="Bank statement and books movement do not agree",
                description=f"Bank statement movement and book bank movement differ by INR {variance:,.2f}.",
                recommended_action="Prepare reconciliation for unreconciled deposits, stale cheques, bank charges, and missing entries.",
                amount=variance,
                source_refs=("BANK_RECON_VARIANCE",),
            )
        )

    return {
        "score": _score_from_issues(100 if bank_statement_rows and bank_book_rows else 70, issues),
        "statement_rows": len(bank_statement_rows),
        "book_rows": len(bank_book_rows),
        "statement_total": statement_total,
        "book_total": book_total,
        "variance": variance,
        "issues": [issue.to_dict() for issue in issues],
    }


def _gst_readiness(engagement: Engagement) -> dict[str, Any]:
    issues: list[HealthIssue] = []
    reconciliations = copy.deepcopy((engagement.state_metadata or {}).get(GST_RECON_KEY, {}))
    if not reconciliations:
        issues.append(
            HealthIssue(
                category="GST",
                severity="CRITICAL",
                title="GST reconciliation not run",
                description="Books have not yet been reconciled against GSTR-1/GSTR-2B data.",
                recommended_action="Import GST portal records and run GSTR-1 vs books and GSTR-2B vs ITC reconciliation.",
                source_refs=("GST_RECONCILIATION",),
            )
        )
        return {"score": 0, "reconciliations": {}, "issues": [issue.to_dict() for issue in issues]}

    mismatch_count = 0
    high_mismatch_count = 0
    for recon_name, recon in reconciliations.items():
        summary = recon.get("summary") or {}
        mismatch_count += int(summary.get("mismatch_count") or 0)
        high_mismatch_count += int((summary.get("risk_breakdown") or {}).get("HIGH") or 0)
        if summary.get("mismatch_count"):
            issues.append(
                HealthIssue(
                    category="GST",
                    severity="HIGH" if high_mismatch_count else "MEDIUM",
                    title=f"{recon_name} has unresolved mismatches",
                    description=f"{recon_name} has {summary.get('mismatch_count')} mismatch(es).",
                    recommended_action="Review mismatch list, ask client for explanations, and approve any adjustment separately.",
                    source_refs=(recon_name,),
                )
            )

    base = 100 if {"gstr1_vs_books", "gstr2b_vs_itc"} <= set(reconciliations) else 80
    return {
        "score": _score_from_issues(base, issues),
        "mismatch_count": mismatch_count,
        "high_mismatch_count": high_mismatch_count,
        "reconciliations": reconciliations,
        "issues": [issue.to_dict() for issue in issues],
    }


def _ledger_readiness(transactions: list[Transaction]) -> dict[str, Any]:
    issues: list[HealthIssue] = []
    refs_seen: set[str] = set()
    duplicate_refs: set[str] = set()
    weekend_refs: list[str] = []
    round_amount_refs: list[str] = []
    negative_cash_refs: list[str] = []

    for txn in transactions:
        payload = txn.payload or {}
        ref = _payload_ref(payload)
        if ref in refs_seen:
            duplicate_refs.add(ref)
        refs_seen.add(ref)

        amount = abs(_safe_float(payload.get("signed_amount") or payload.get("amount") or payload.get("debit") or payload.get("credit")))
        txn_date = _parse_date(payload.get("date"))
        if txn_date and txn_date.weekday() >= 5:
            weekend_refs.append(ref)
        if amount >= 100000 and amount % 10000 == 0:
            round_amount_refs.append(ref)
        if payload.get("mapped_category") == "cash_and_bank" and _safe_float(payload.get("closing_balance")) < 0:
            negative_cash_refs.append(ref)

    if not transactions:
        issues.append(
            HealthIssue(
                category="LEDGER",
                severity="CRITICAL",
                title="Books data not imported",
                description="No financial transactions were found for this engagement.",
                recommended_action="Import Tally/ERP/CSV books before audit planning starts.",
                source_refs=("BOOKS_IMPORT",),
            )
        )
    if duplicate_refs:
        issues.append(
            HealthIssue(
                category="LEDGER",
                severity="HIGH",
                title="Duplicate voucher references detected",
                description=f"{len(duplicate_refs)} duplicate voucher reference(s) were detected.",
                recommended_action="Ask the client to explain duplicate vouchers or provide corrected books export.",
                source_refs=tuple(sorted(duplicate_refs)[:10]),
            )
        )
    if weekend_refs:
        issues.append(
            HealthIssue(
                category="LEDGER",
                severity="MEDIUM",
                title="Weekend entries require review",
                description=f"{len(weekend_refs)} transaction(s) are dated on weekends.",
                recommended_action="Review weekend entries for unusual manual postings or backdated adjustments.",
                source_refs=tuple(weekend_refs[:10]),
            )
        )
    if round_amount_refs:
        issues.append(
            HealthIssue(
                category="LEDGER",
                severity="MEDIUM",
                title="Large round-number entries require review",
                description=f"{len(round_amount_refs)} large round-number transaction(s) were detected.",
                recommended_action="Sample large round-number entries and request supporting evidence.",
                source_refs=tuple(round_amount_refs[:10]),
            )
        )
    if negative_cash_refs:
        issues.append(
            HealthIssue(
                category="LEDGER",
                severity="HIGH",
                title="Negative cash or bank balances detected",
                description="Negative cash/bank balances may indicate missing entries or posting errors.",
                recommended_action="Ask the client to provide corrected cash/bank ledger and reconciliation.",
                source_refs=tuple(negative_cash_refs[:10]),
            )
        )

    return {
        "score": _score_from_issues(100, issues),
        "transaction_count": len(transactions),
        "duplicate_ref_count": len(duplicate_refs),
        "weekend_entry_count": len(weekend_refs),
        "round_amount_entry_count": len(round_amount_refs),
        "issues": [issue.to_dict() for issue in issues],
    }


def _evidence_readiness(evidence: list[EvidenceRecord], transactions: list[Transaction]) -> dict[str, Any]:
    issues: list[HealthIssue] = []
    evidence_count = len(evidence)
    transaction_count = len(transactions)

    if evidence_count == 0:
        issues.append(
            HealthIssue(
                category="EVIDENCE",
                severity="CRITICAL",
                title="No evidence uploaded",
                description="No invoices, statements, confirmations, or support files are attached to the engagement.",
                recommended_action="Generate a client evidence request list before substantive testing.",
                source_refs=("EVIDENCE_VAULT",),
            )
        )
    elif transaction_count and evidence_count < max(3, transaction_count // 20):
        issues.append(
            HealthIssue(
                category="EVIDENCE",
                severity="MEDIUM",
                title="Evidence coverage appears low",
                description="Uploaded evidence volume is low compared with the number of imported transactions.",
                recommended_action="Review sampling coverage and request missing support for high-risk areas.",
                source_refs=("EVIDENCE_COVERAGE",),
            )
        )

    pending_review = sum(1 for item in evidence if str(item.ev_status).upper() in {"PENDING REVIEW", "PENDING"})
    if pending_review:
        issues.append(
            HealthIssue(
                category="EVIDENCE",
                severity="MEDIUM",
                title="Evidence pending CA review",
                description=f"{pending_review} evidence item(s) are still pending review.",
                recommended_action="Assign evidence review before report drafting.",
                source_refs=("EVIDENCE_REVIEW",),
            )
        )

    return {
        "score": _score_from_issues(100 if evidence_count else 60, issues),
        "evidence_count": evidence_count,
        "pending_review_count": pending_review,
        "issues": [issue.to_dict() for issue in issues],
    }


def _query_payload(issue: dict[str, Any]) -> dict[str, Any]:
    priority = {
        "CRITICAL": "HIGH",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
    }[issue["severity"]]
    return {
        "title": issue["title"],
        "question": f"{issue['description']} Required action: {issue['recommended_action']}",
        "priority": priority,
        "requested_documents": issue["source_refs"],
    }


async def run_books_health_check(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    create_queries: bool = False,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    transactions = await _load_transactions(session, engagement_id=engagement_id, tenant_id=tenant_id)
    evidence = await _load_evidence(session, engagement_id=engagement_id, tenant_id=tenant_id)

    categories = {
        "bank_reconciliation": _bank_readiness(transactions),
        "gst_reconciliation": _gst_readiness(engagement),
        "ledger_hygiene": _ledger_readiness(transactions),
        "evidence_readiness": _evidence_readiness(evidence, transactions),
    }
    all_issues = [
        issue
        for category in categories.values()
        for issue in category["issues"]
    ]
    critical_blockers = [issue for issue in all_issues if issue["severity"] == "CRITICAL"]
    high_risk_items = [issue for issue in all_issues if issue["severity"] == "HIGH"]
    readiness_score = round(
        sum(
            [
                categories["bank_reconciliation"]["score"] * 0.25,
                categories["gst_reconciliation"]["score"] * 0.25,
                categories["ledger_hygiene"]["score"] * 0.25,
                categories["evidence_readiness"]["score"] * 0.25,
            ]
        )
    )
    sprint_status = "READY" if readiness_score >= 85 and not critical_blockers else "AT_RISK"
    if readiness_score < 60 or critical_blockers:
        sprint_status = "BLOCKED"

    created_queries: list[dict[str, Any]] = []
    if create_queries:
        workflow = await get_client_portal_workflow(session, engagement_id=engagement_id, tenant_id=tenant_id)
        existing_open_titles = {
            str(query.get("title"))
            for query in workflow["queries"]
            if query.get("status") in {"OPEN", "CLIENT_RESPONDED"}
        }
        for issue in all_issues:
            if issue["severity"] not in {"CRITICAL", "HIGH"}:
                continue
            payload = _query_payload(issue)
            if payload["title"] in existing_open_titles:
                continue
            created_queries.append(
                await create_client_query(
                    session,
                    engagement_id=engagement_id,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    due_at=None,
                    client_phone=None,
                    portal_url=None,
                    **payload,
                )
            )
            existing_open_titles.add(payload["title"])
        engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)

    checked_at = _now_iso()
    result = {
        "engagement_id": str(engagement_id),
        "tenant_id": tenant_id,
        "checked_at": checked_at,
        "readiness_score": readiness_score,
        "seven_day_sprint_status": sprint_status,
        "critical_blocker_count": len(critical_blockers),
        "high_risk_item_count": len(high_risk_items),
        "client_query_count_created": len(created_queries),
        "categories": categories,
        "issues": all_issues,
        "created_queries": created_queries,
        "next_actions": _next_actions(sprint_status, all_issues),
    }

    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata.setdefault("history", [])
    metadata.setdefault(BOOKS_HEALTH_KEY, [])
    metadata[BOOKS_HEALTH_KEY].append({key: value for key, value in result.items() if key != "created_queries"})
    metadata["history"].append(
        {
            "timestamp": checked_at,
            "actor": actor_id,
            "action": "BOOKS_HEALTH_CHECK_COMPLETED",
            "readiness_score": readiness_score,
            "seven_day_sprint_status": sprint_status,
            "critical_blocker_count": len(critical_blockers),
            "client_query_count_created": len(created_queries),
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return result


def _next_actions(status: str, issues: list[dict[str, Any]]) -> list[str]:
    if status == "READY":
        return [
            "Proceed to planning and materiality.",
            "Use the evidence vault and AI governance log for all CA-reviewed findings.",
            "Keep the seven-day sprint timer active through report and seal.",
        ]
    actions = [
        "Close all critical blockers before report drafting.",
        "Send client queries for missing bank, GST, ledger, and evidence support.",
        "CA must approve or reject any suggested adjustment before it affects the audit file.",
    ]
    if any(issue["category"] == "GST" for issue in issues):
        actions.append("Run GST reconciliation after fresh GSTR-1/GSTR-2B data is imported.")
    if any(issue["category"] == "BANK" for issue in issues):
        actions.append("Complete bank statement import and reconciliation before substantive testing.")
    return actions


async def list_books_health_checks(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> list[dict[str, Any]]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    return copy.deepcopy((engagement.state_metadata or {}).get(BOOKS_HEALTH_KEY, []))
