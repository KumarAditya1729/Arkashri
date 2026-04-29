from __future__ import annotations

import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, Transaction

GST_RECON_KEY = "gst_reconciliations"
AMOUNT_TOLERANCE = 1.0


class GSTReconciliationError(ValueError):
    pass


@dataclass
class GSTReconciliationResult:
    recon_type: str
    reconciled_at: str
    summary: dict[str, Any]
    mismatches: list[dict[str, Any]]


def _round_amount(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return round(abs(float(value)), 2)


def _normalize_gstin(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _normalize_invoice_no(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_period(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _risk_level(*, variance_amount: float, reason_codes: set[str]) -> str:
    if {"missing_in_books", "missing_in_portal"} & reason_codes:
        return "HIGH"
    if variance_amount > 50000 or {"tax_amount_mismatch", "taxable_value_mismatch"} & reason_codes:
        return "HIGH"
    if {"gstin_mismatch", "period_mismatch"} & reason_codes:
        return "MEDIUM"
    return "LOW"


def _load_books_vouchers(transactions: list[Transaction]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for txn in transactions:
        payload = txn.payload or {}
        voucher_number = _normalize_invoice_no(payload.get("ref"))
        if not voucher_number:
            continue

        voucher = grouped.setdefault(
            voucher_number,
            {
                "invoice_no": voucher_number,
                "gstin": _normalize_gstin(payload.get("tax_code")),
                "date": payload.get("date"),
                "voucher_type": str(payload.get("voucher_type") or payload.get("type") or "").upper(),
                "revenue_amount": 0.0,
                "expense_amount": 0.0,
                "input_tax_amount": 0.0,
                "output_tax_amount": 0.0,
                "raw_payloads": [],
            },
        )
        voucher["raw_payloads"].append(payload)
        voucher["gstin"] = voucher["gstin"] or _normalize_gstin(payload.get("tax_code"))

        mapped_category = str(payload.get("mapped_category") or "")
        signed_amount = float(payload.get("signed_amount") or 0.0)
        debit = _round_amount(payload.get("debit"))
        credit = _round_amount(payload.get("credit"))
        voucher_type = voucher["voucher_type"]

        if mapped_category == "gst_and_indirect_tax":
            if signed_amount < 0 or credit > 0:
                voucher["output_tax_amount"] += max(_round_amount(signed_amount), credit)
            else:
                voucher["input_tax_amount"] += max(_round_amount(signed_amount), debit)
            continue

        if "SALE" in voucher_type or mapped_category == "revenue":
            if mapped_category not in {"trade_receivables", "trade_payables", "cash_and_bank", "gst_and_indirect_tax"}:
                voucher["revenue_amount"] += max(credit, _round_amount(signed_amount))
            continue

        if "PURCHASE" in voucher_type:
            if mapped_category not in {"trade_payables", "cash_and_bank", "gst_and_indirect_tax"}:
                voucher["expense_amount"] += max(debit, _round_amount(signed_amount))
            continue

        if mapped_category in {"inventory", "cost_of_goods_sold", "employee_benefits", "related_parties", "statutory_dues"}:
            voucher["expense_amount"] += max(debit, _round_amount(signed_amount))

    return grouped


def _coerce_portal_record(record: dict[str, Any]) -> dict[str, Any]:
    invoice_no = _normalize_invoice_no(
        record.get("invoice_no") or record.get("invoice_number") or record.get("voucher_number") or record.get("document_number")
    )
    if not invoice_no:
        raise GSTReconciliationError("Portal record is missing invoice_no/invoice_number.")

    taxable_value = _round_amount(
        record.get("taxable_value") or record.get("invoice_value") or record.get("books_taxable_value") or 0
    )
    tax_amount = _round_amount(
        record.get("tax_amount") or record.get("gst_amount") or record.get("tax_total") or record.get("portal_tax") or 0
    )

    return {
        "invoice_no": invoice_no,
        "gstin": _normalize_gstin(record.get("gstin") or record.get("counterparty_gstin")),
        "taxable_value": taxable_value,
        "tax_amount": tax_amount,
        "period": _normalize_period(record.get("period") or record.get("tax_period") or record.get("filing_period")),
    }


async def _load_engagement(session: AsyncSession, *, engagement_id: uuid.UUID, tenant_id: str) -> Engagement:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise GSTReconciliationError("Engagement not found.")
    return engagement


def _ensure_reconciliation_bucket(engagement: Engagement) -> dict[str, Any]:
    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata.setdefault("history", [])
    metadata.setdefault(GST_RECON_KEY, {})
    return metadata


async def _load_engagement_transactions(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> list[Transaction]:
    return list(
        await session.scalars(
            select(Transaction).where(
                Transaction.tenant_id == tenant_id,
            )
        )
    )


def _summarize_results(mismatches: list[dict[str, Any]], *, matched_count: int, total_books: int, total_portal: int) -> dict[str, Any]:
    by_risk: dict[str, int] = defaultdict(int)
    for mismatch in mismatches:
        by_risk[str(mismatch["risk_classification"])] += 1
    return {
        "matched_count": matched_count,
        "books_record_count": total_books,
        "portal_record_count": total_portal,
        "mismatch_count": len(mismatches),
        "risk_breakdown": dict(sorted(by_risk.items())),
    }


def reconcile_gstr1_books_data(
    *,
    books_vouchers: dict[str, dict[str, Any]],
    portal_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    portal_by_invoice = {record["invoice_no"]: record for record in (_coerce_portal_record(item) for item in portal_records)}
    mismatches: list[dict[str, Any]] = []
    matched_count = 0

    sales_books = {
        invoice_no: voucher
        for invoice_no, voucher in books_vouchers.items()
        if "SALE" in voucher["voucher_type"] or voucher["revenue_amount"] > 0
    }

    for invoice_no, book in sales_books.items():
        portal = portal_by_invoice.pop(invoice_no, None)
        if portal is None:
            mismatches.append(
                {
                    "invoice_no": invoice_no,
                    "gstin": book.get("gstin"),
                    "books_taxable_value": round(book["revenue_amount"], 2),
                    "portal_taxable_value": 0.0,
                    "books_tax_amount": round(book["output_tax_amount"], 2),
                    "portal_tax_amount": 0.0,
                    "variance_amount": round(book["revenue_amount"] + book["output_tax_amount"], 2),
                    "reason_codes": ["missing_in_portal"],
                    "risk_classification": "HIGH",
                }
            )
            continue

        reason_codes: set[str] = set()
        taxable_variance = round(abs(book["revenue_amount"] - portal["taxable_value"]), 2)
        tax_variance = round(abs(book["output_tax_amount"] - portal["tax_amount"]), 2)
        if taxable_variance > AMOUNT_TOLERANCE:
            reason_codes.add("taxable_value_mismatch")
        if tax_variance > AMOUNT_TOLERANCE:
            reason_codes.add("tax_amount_mismatch")
        if book.get("gstin") and portal.get("gstin") and book["gstin"] != portal["gstin"]:
            reason_codes.add("gstin_mismatch")
        if reason_codes:
            mismatches.append(
                {
                    "invoice_no": invoice_no,
                    "gstin": portal.get("gstin") or book.get("gstin"),
                    "books_taxable_value": round(book["revenue_amount"], 2),
                    "portal_taxable_value": portal["taxable_value"],
                    "books_tax_amount": round(book["output_tax_amount"], 2),
                    "portal_tax_amount": portal["tax_amount"],
                    "variance_amount": round(taxable_variance + tax_variance, 2),
                    "reason_codes": sorted(reason_codes),
                    "risk_classification": _risk_level(
                        variance_amount=taxable_variance + tax_variance,
                        reason_codes=reason_codes,
                    ),
                }
            )
        else:
            matched_count += 1

    for invoice_no, portal in portal_by_invoice.items():
        mismatches.append(
            {
                "invoice_no": invoice_no,
                "gstin": portal.get("gstin"),
                "books_taxable_value": 0.0,
                "portal_taxable_value": portal["taxable_value"],
                "books_tax_amount": 0.0,
                "portal_tax_amount": portal["tax_amount"],
                "variance_amount": round(portal["taxable_value"] + portal["tax_amount"], 2),
                "reason_codes": ["missing_in_books"],
                "risk_classification": "HIGH",
            }
        )

    return _summarize_results(
        mismatches,
        matched_count=matched_count,
        total_books=len(sales_books),
        total_portal=len(portal_records),
    ), mismatches


def reconcile_gstr2b_itc_data(
    *,
    books_vouchers: dict[str, dict[str, Any]],
    portal_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    portal_by_invoice = {record["invoice_no"]: record for record in (_coerce_portal_record(item) for item in portal_records)}
    mismatches: list[dict[str, Any]] = []
    matched_count = 0

    purchase_books = {
        invoice_no: voucher
        for invoice_no, voucher in books_vouchers.items()
        if "PURCHASE" in voucher["voucher_type"] or voucher["input_tax_amount"] > 0
    }

    for invoice_no, book in purchase_books.items():
        portal = portal_by_invoice.pop(invoice_no, None)
        if portal is None:
            mismatches.append(
                {
                    "invoice_no": invoice_no,
                    "gstin": book.get("gstin"),
                    "books_taxable_value": round(book["expense_amount"], 2),
                    "portal_taxable_value": 0.0,
                    "books_tax_amount": round(book["input_tax_amount"], 2),
                    "portal_tax_amount": 0.0,
                    "variance_amount": round(book["input_tax_amount"], 2),
                    "reason_codes": ["missing_in_portal"],
                    "risk_classification": "HIGH",
                }
            )
            continue

        reason_codes: set[str] = set()
        taxable_variance = round(abs(book["expense_amount"] - portal["taxable_value"]), 2)
        tax_variance = round(abs(book["input_tax_amount"] - portal["tax_amount"]), 2)
        if taxable_variance > AMOUNT_TOLERANCE:
            reason_codes.add("taxable_value_mismatch")
        if tax_variance > AMOUNT_TOLERANCE:
            if book["input_tax_amount"] > portal["tax_amount"]:
                reason_codes.add("excess_itc_claimed")
            else:
                reason_codes.add("itc_not_claimed")
        if book.get("gstin") and portal.get("gstin") and book["gstin"] != portal["gstin"]:
            reason_codes.add("gstin_mismatch")
        if reason_codes:
            mismatches.append(
                {
                    "invoice_no": invoice_no,
                    "gstin": portal.get("gstin") or book.get("gstin"),
                    "books_taxable_value": round(book["expense_amount"], 2),
                    "portal_taxable_value": portal["taxable_value"],
                    "books_tax_amount": round(book["input_tax_amount"], 2),
                    "portal_tax_amount": portal["tax_amount"],
                    "variance_amount": round(taxable_variance + tax_variance, 2),
                    "reason_codes": sorted(reason_codes),
                    "risk_classification": _risk_level(
                        variance_amount=taxable_variance + tax_variance,
                        reason_codes=reason_codes,
                    ),
                }
            )
        else:
            matched_count += 1

    for invoice_no, portal in portal_by_invoice.items():
        mismatches.append(
            {
                "invoice_no": invoice_no,
                "gstin": portal.get("gstin"),
                "books_taxable_value": 0.0,
                "portal_taxable_value": portal["taxable_value"],
                "books_tax_amount": 0.0,
                "portal_tax_amount": portal["tax_amount"],
                "variance_amount": round(portal["tax_amount"], 2),
                "reason_codes": ["missing_in_books"],
                "risk_classification": "HIGH",
            }
        )

    return _summarize_results(
        mismatches,
        matched_count=matched_count,
        total_books=len(purchase_books),
        total_portal=len(portal_records),
    ), mismatches


async def run_gst_reconciliation(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    recon_type: Literal["gstr1_vs_books", "gstr2b_vs_itc"],
    portal_records: list[dict[str, Any]],
) -> GSTReconciliationResult:
    if not portal_records:
        raise GSTReconciliationError("At least one portal record is required for GST reconciliation.")

    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    transactions = await _load_engagement_transactions(session, engagement_id=engagement_id, tenant_id=tenant_id)
    scoped_transactions = [
        txn
        for txn in transactions
        if str((txn.payload or {}).get("engagement_id") or "") == str(engagement.id)
    ]
    if not scoped_transactions:
        raise GSTReconciliationError("No imported Tally vouchers were found for this engagement.")

    books_vouchers = _load_books_vouchers(scoped_transactions)
    if recon_type == "gstr1_vs_books":
        summary, mismatches = reconcile_gstr1_books_data(
            books_vouchers=books_vouchers,
            portal_records=portal_records,
        )
    else:
        summary, mismatches = reconcile_gstr2b_itc_data(
            books_vouchers=books_vouchers,
            portal_records=portal_records,
        )

    reconciled_at = datetime.now(timezone.utc).isoformat()
    metadata = _ensure_reconciliation_bucket(engagement)
    metadata[GST_RECON_KEY][recon_type] = {
        "reconciled_at": reconciled_at,
        "summary": summary,
        "mismatches": mismatches,
    }
    metadata["history"].append(
        {
            "timestamp": reconciled_at,
            "actor": actor_id,
            "action": "GST_RECONCILIATION_COMPLETED",
            "recon_type": recon_type,
            "mismatch_count": len(mismatches),
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return GSTReconciliationResult(
        recon_type=recon_type,
        reconciled_at=reconciled_at,
        summary=summary,
        mismatches=mismatches,
    )


async def get_gst_reconciliations(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    return copy.deepcopy((engagement.state_metadata or {}).get(GST_RECON_KEY, {}))
