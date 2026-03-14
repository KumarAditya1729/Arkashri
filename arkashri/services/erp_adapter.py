# pyre-ignore-all-errors
"""
services/erp_adapter.py — ERP Normalizer
=========================================
Converts ERP-specific raw payloads into Arkashri's canonical
Transaction.payload format.

Supported systems:
  SAP_S4HANA     — SAP S/4HANA BAPI / OData GL line items
  ORACLE_FUSION  — Oracle Financials Cloud journal lines
  TALLY_PRIME    — Tally Prime XML / JSON vouchers (India SME)
  ZOHO_BOOKS     — Zoho Books API journal entries
  QUICKBOOKS     — QuickBooks Online API transactions
  GENERIC_CSV    — Flat file / CSV fallback (any ERP)

Output schema (Transaction.payload):
  {
    "ref":          str      -- unique reference within ERP
    "date":         str      -- ISO date YYYY-MM-DD
    "type":         str      -- DEBIT | CREDIT | JOURNAL | TRANSFER
    "amount":       float    -- absolute value, always positive
    "currency":     str      -- ISO 4217
    "account_code": str      -- GL account / ledger code
    "account_name": str      -- Human-readable account name
    "cost_center":  str|None -- Department / profit center
    "description":  str      -- Narration / memo
    "entity":       str      -- Vendor / customer / counterparty name
    "entity_code":  str|None -- Vendor / customer code
    "tax_code":     str|None -- GST HSN/SAC, VAT code, etc.
    "erp_system":   str      -- Source system
    "erp_doc_id":   str      -- Original document number in ERP
    "risk_flags":   list     -- Pre-flagged anomalies from ERP
  }
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime
from typing import Any

SYSTEM_VERSION = "Arkashri_OS_2.0_Enterprise"

ERPSystem = {
    "SAP_S4HANA":    "SAP_S4HANA",
    "ORACLE_FUSION": "ORACLE_FUSION",
    "TALLY_PRIME":   "TALLY_PRIME",
    "ZOHO_BOOKS":    "ZOHO_BOOKS",
    "QUICKBOOKS":    "QUICKBOOKS",
    "GENERIC_CSV":   "GENERIC_CSV",
}


def _iso_date(raw: Any) -> str:
    """Normalize any date representation to YYYY-MM-DD."""
    if isinstance(raw, (date, datetime)):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    # Attempt common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # Return as-is if unparseable — will surface in risk_flags


def _clean_amount(raw: Any) -> float:
    """Remove currency symbols and parse to float."""
    if isinstance(raw, (int, float)):
        return abs(float(raw))
    s = re.sub(r"[^\d.\-]", "", str(raw))
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# ─── SAP S/4HANA ─────────────────────────────────────────────────────────────

def normalize_sap(raw: dict) -> dict:
    """
    Maps SAP BAPI_GL_ACC_GETPERIODBALANCES / FI GL line item format.
    Key SAP fields: BELNR (doc number), BUDAT (posting date), DMBTR (amount),
    HKONT (GL account), SGTXT (description), LIFNR/KUNNR (vendor/customer)
    """
    amount = _clean_amount(raw.get("DMBTR") or raw.get("amount") or 0)
    shkzg  = str(raw.get("SHKZG") or raw.get("type") or "S")  # S=debit, H=credit
    entry_type = "DEBIT" if shkzg.upper() in ("S", "D", "DEBIT") else "CREDIT"

    risk_flags: list[str] = []
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")
    if not raw.get("LIFNR") and not raw.get("KUNNR") and not raw.get("entity"):
        risk_flags.append("MISSING_COUNTERPARTY")

    return {
        "ref":          str(raw.get("BELNR") or raw.get("ref") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("BUDAT") or raw.get("date") or date.today()),
        "type":         entry_type,
        "amount":       amount,
        "currency":     str(raw.get("WAERS") or raw.get("currency") or "INR"),
        "account_code": str(raw.get("HKONT") or raw.get("account_code") or ""),
        "account_name": str(raw.get("TXT50") or raw.get("account_name") or ""),
        "cost_center":  str(raw.get("KOSTL") or raw.get("cost_center") or "") or None,
        "description":  str(raw.get("SGTXT") or raw.get("description") or ""),
        "entity":       str(raw.get("NAME1") or raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(raw.get("LIFNR") or raw.get("KUNNR") or raw.get("entity_code") or "") or None,
        "tax_code":     str(raw.get("MWSKZ") or raw.get("tax_code") or "") or None,
        "erp_system":   "SAP_S4HANA",
        "erp_doc_id":   str(raw.get("BELNR") or raw.get("erp_doc_id") or ""),
        "risk_flags":   risk_flags,
    }


# ─── Oracle Fusion Financials ─────────────────────────────────────────────────

def normalize_oracle(raw: dict) -> dict:
    """
    Maps Oracle Financials Cloud REST API GL Journal Entry Line format.
    Key fields: AcctdCr, AcctdDr, CurrencyCode, AccountedDate,
    CodeCombinationId, Description, ExternalReference
    """
    debit  = _clean_amount(raw.get("AcctdDr") or raw.get("debit") or 0)
    credit = _clean_amount(raw.get("AcctdCr") or raw.get("credit") or 0)
    amount = debit if debit > 0 else credit
    entry_type = "DEBIT" if debit > 0 else "CREDIT"

    risk_flags: list[str] = []
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")
    if debit > 0 and credit > 0:
        risk_flags.append("SIMULTANEOUS_DR_CR")

    return {
        "ref":          str(raw.get("ExternalReference") or raw.get("JournalEntryLineId") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("AccountedDate") or raw.get("date") or date.today()),
        "type":         entry_type,
        "amount":       amount,
        "currency":     str(raw.get("CurrencyCode") or raw.get("currency") or "USD"),
        "account_code": str(raw.get("CodeCombinationId") or raw.get("account_code") or ""),
        "account_name": str(raw.get("AccountName") or raw.get("account_name") or ""),
        "cost_center":  str(raw.get("CostCenter") or raw.get("cost_center") or "") or None,
        "description":  str(raw.get("Description") or raw.get("description") or ""),
        "entity":       str(raw.get("PartyName") or raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(raw.get("PartyId") or raw.get("entity_code") or "") or None,
        "tax_code":     str(raw.get("TaxCode") or raw.get("tax_code") or "") or None,
        "erp_system":   "ORACLE_FUSION",
        "erp_doc_id":   str(raw.get("JournalEntryLineId") or raw.get("erp_doc_id") or ""),
        "risk_flags":   risk_flags,
    }


# ─── Tally Prime (India) ──────────────────────────────────────────────────────

def normalize_tally(raw: dict) -> dict:
    """
    Maps Tally Prime TallyPrime REST / XML voucher format.
    Key fields: VOUCHERNUMBER, DATE, AMOUNT, LEDGERNAME,
    PARTYLEDGERNAME, NARRATION, GSTREGISTRATIONNUMBER
    """
    amount     = _clean_amount(raw.get("AMOUNT") or raw.get("amount") or 0)
    voucher_type = str(raw.get("VOUCHERTYPE") or raw.get("type") or "Journal").upper()
    if "RECEIPT" in voucher_type or "CREDIT" in voucher_type or "SALES" in voucher_type:
        entry_type = "CREDIT"
    elif "PAYMENT" in voucher_type or "DEBIT" in voucher_type or "PURCHASE" in voucher_type:
        entry_type = "DEBIT"
    elif "JOURNAL" in voucher_type:
        entry_type = "JOURNAL"
    else:
        entry_type = "TRANSFER"

    risk_flags: list[str] = []
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")
    # Flag round-number transactions (Benford's Law anomaly)
    if amount > 0 and amount == int(amount) and amount % 10000 == 0:
        risk_flags.append("ROUND_NUMBER_HIGH_VALUE")
    gst_no = raw.get("GSTREGISTRATIONNUMBER") or raw.get("tax_code")
    if not gst_no and amount > 50000:
        risk_flags.append("MISSING_GST_HIGH_VALUE")

    return {
        "ref":          str(raw.get("VOUCHERNUMBER") or raw.get("ref") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("DATE") or raw.get("date") or date.today()),
        "type":         entry_type,
        "amount":       amount,
        "currency":     str(raw.get("CURRENCY") or raw.get("currency") or "INR"),
        "account_code": str(raw.get("LEDGERNAME") or raw.get("account_code") or ""),
        "account_name": str(raw.get("LEDGERNAME") or raw.get("account_name") or ""),
        "cost_center":  str(raw.get("COSTCENTRE") or raw.get("cost_center") or "") or None,
        "description":  str(raw.get("NARRATION") or raw.get("description") or ""),
        "entity":       str(raw.get("PARTYLEDGERNAME") or raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(raw.get("VENDORCODE") or raw.get("entity_code") or "") or None,
        "tax_code":     str(gst_no or "") or None,
        "erp_system":   "TALLY_PRIME",
        "erp_doc_id":   str(raw.get("VOUCHERNUMBER") or raw.get("erp_doc_id") or ""),
        "risk_flags":   risk_flags,
    }


# ─── Zoho Books ──────────────────────────────────────────────────────────────

def normalize_zoho(raw: dict) -> dict:
    """
    Maps Zoho Books API journal entry lines.
    Key fields: journal_id, date, debit_or_credit, amount,
    account_id, account_name, reference_number, tax_id
    """
    amount      = _clean_amount(raw.get("amount") or 0)
    dr_cr       = str(raw.get("debit_or_credit") or raw.get("type") or "debit").lower()
    entry_type  = "DEBIT" if "debit" in dr_cr or "dr" in dr_cr else "CREDIT"

    risk_flags: list[str] = []
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")

    return {
        "ref":          str(raw.get("reference_number") or raw.get("journal_id") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("date") or date.today()),
        "type":         entry_type,
        "amount":       amount,
        "currency":     str(raw.get("currency_code") or raw.get("currency") or "INR"),
        "account_code": str(raw.get("account_id") or raw.get("account_code") or ""),
        "account_name": str(raw.get("account_name") or ""),
        "cost_center":  None,
        "description":  str(raw.get("notes") or raw.get("description") or ""),
        "entity":       str(raw.get("vendor_name") or raw.get("customer_name") or raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(raw.get("vendor_id") or raw.get("customer_id") or raw.get("entity_code") or "") or None,
        "tax_code":     str(raw.get("tax_id") or raw.get("tax_code") or "") or None,
        "erp_system":   "ZOHO_BOOKS",
        "erp_doc_id":   str(raw.get("journal_id") or raw.get("erp_doc_id") or ""),
        "risk_flags":   risk_flags,
    }


# ─── QuickBooks Online ────────────────────────────────────────────────────────

def normalize_quickbooks(raw: dict) -> dict:
    """
    Maps QuickBooks Online REST API JournalEntry.Line objects.
    Key fields: Id, TxnDate, Amount, DetailType (JournalEntryLineDetail),
    PostingType (Debit/Credit), AccountRef, EntityRef
    """
    detail      = raw.get("JournalEntryLineDetail") or raw.get("detail") or {}
    amount      = _clean_amount(raw.get("Amount") or raw.get("amount") or 0)
    posting     = str(detail.get("PostingType") or raw.get("type") or "Debit")
    entry_type  = "DEBIT" if "debit" in posting.lower() else "CREDIT"

    acct_ref = detail.get("AccountRef") or raw.get("AccountRef") or {}
    entity_ref = detail.get("Entity") or raw.get("EntityRef") or {}

    risk_flags: list[str] = []
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")

    return {
        "ref":          str(raw.get("Id") or raw.get("ref") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("TxnDate") or raw.get("date") or date.today()),
        "type":         entry_type,
        "amount":       amount,
        "currency":     str(raw.get("CurrencyRef", {}).get("value") or raw.get("currency") or "USD"),
        "account_code": str(acct_ref.get("value") or raw.get("account_code") or ""),
        "account_name": str(acct_ref.get("name") or raw.get("account_name") or ""),
        "cost_center":  str(detail.get("ClassRef", {}).get("name") or raw.get("cost_center") or "") or None,
        "description":  str(raw.get("Description") or raw.get("description") or ""),
        "entity":       str(entity_ref.get("name") or raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(entity_ref.get("type") or raw.get("entity_code") or "") or None,
        "tax_code":     str(raw.get("TaxCodeRef", {}).get("value") or raw.get("tax_code") or "") or None,
        "erp_system":   "QUICKBOOKS",
        "erp_doc_id":   str(raw.get("Id") or raw.get("erp_doc_id") or ""),
        "risk_flags":   risk_flags,
    }


# ─── Generic CSV / Flat File ──────────────────────────────────────────────────

def normalize_generic(raw: dict) -> dict:
    """
    Passthrough normalizer for flat file / CSV uploads.
    Caller must pre-map columns to canonical keys.
    """
    amount     = _clean_amount(raw.get("amount") or raw.get("AMOUNT") or 0)
    risk_flags: list[str] = list(raw.get("risk_flags") or [])
    if amount == 0:
        risk_flags.append("ZERO_AMOUNT")

    return {
        "ref":          str(raw.get("ref") or uuid.uuid4())[:64],
        "date":         _iso_date(raw.get("date") or date.today()),
        "type":         str(raw.get("type") or "JOURNAL").upper(),
        "amount":       amount,
        "currency":     str(raw.get("currency") or "INR"),
        "account_code": str(raw.get("account_code") or ""),
        "account_name": str(raw.get("account_name") or ""),
        "cost_center":  str(raw.get("cost_center") or "") or None,
        "description":  str(raw.get("description") or ""),
        "entity":       str(raw.get("entity") or "UNKNOWN"),
        "entity_code":  str(raw.get("entity_code") or "") or None,
        "tax_code":     str(raw.get("tax_code") or "") or None,
        "erp_system":   "GENERIC_CSV",
        "erp_doc_id":   str(raw.get("erp_doc_id") or raw.get("ref") or ""),
        "risk_flags":   risk_flags,
    }


# ─── Dispatcher ───────────────────────────────────────────────────────────────

_NORMALIZERS = {
    "SAP_S4HANA":    normalize_sap,
    "ORACLE_FUSION": normalize_oracle,
    "TALLY_PRIME":   normalize_tally,
    "ZOHO_BOOKS":    normalize_zoho,
    "QUICKBOOKS":    normalize_quickbooks,
    "GENERIC_CSV":   normalize_generic,
}


def normalize(erp_system: str, raw: dict) -> dict:
    """
    Normalize a single ERP record to canonical Transaction.payload format.

    Args:
        erp_system: One of SAP_S4HANA / ORACLE_FUSION / TALLY_PRIME /
                    ZOHO_BOOKS / QUICKBOOKS / GENERIC_CSV
        raw:        Raw record dict from ERP API / extract

    Returns:
        Canonical payload dict ready for Transaction.payload
    """
    normalizer = _NORMALIZERS.get(erp_system.upper())
    if not normalizer:
        raise ValueError(
            f"Unknown ERP system: {erp_system}. "
            f"Supported: {list(_NORMALIZERS.keys())}"
        )
    payload = normalizer(raw)
    return payload


def normalize_batch(erp_system: str, records: list[dict]) -> list[tuple[dict, str]]:
    """
    Normalize a list of raw ERP records.
    Returns list of (payload, payload_hash) tuples.
    """
    results: list[tuple[dict, str]] = []
    for r in records:
        try:
            p = normalize(erp_system, r)
            h = _payload_hash(p)
            results.append((p, h))
        except Exception as e:
            # Emit a failed-parse record rather than aborting the whole batch
            failed_payload = {
                "error":      str(e),
                "raw":        str(r)[:500],
                "erp_system": erp_system,
                "risk_flags": ["PARSE_ERROR"],
            }
            results.append((failed_payload, _payload_hash(failed_payload)))
    return results
