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


class ERPValidationError(ValueError):
    pass


def _iso_date(raw: Any) -> str:
    """Normalize any date representation to YYYY-MM-DD."""
    if raw is None or str(raw).strip() == "":
        raise ERPValidationError("Missing required transaction date.")
    if isinstance(raw, (date, datetime)):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    # Attempt common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ERPValidationError(f"Unsupported transaction date format: {s}")


def _clean_amount(raw: Any) -> float:
    """Remove currency symbols and parse to float."""
    if isinstance(raw, (int, float)):
        amount = abs(float(raw))
        if amount == 0.0:
            raise ERPValidationError("Transaction amount must be non-zero.")
        return amount
    s = re.sub(r"[^\d.\-]", "", str(raw))
    try:
        amount = abs(float(s))
        if amount == 0.0:
            raise ERPValidationError("Transaction amount must be non-zero.")
        return amount
    except ValueError:
        raise ERPValidationError(f"Invalid transaction amount: {raw}")


def _required_text(raw: dict[str, Any], *keys: str, label: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    raise ERPValidationError(f"Missing required field: {label}")


def _optional_text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


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
    amount = _clean_amount(raw.get("DMBTR") or raw.get("amount"))
    shkzg  = str(raw.get("SHKZG") or raw.get("type") or "S")  # S=debit, H=credit
    entry_type = "DEBIT" if shkzg.upper() in ("S", "D", "DEBIT") else "CREDIT"

    risk_flags: list[str] = []
    if not raw.get("LIFNR") and not raw.get("KUNNR") and not raw.get("entity"):
        risk_flags.append("MISSING_COUNTERPARTY")

    ref = _required_text(raw, "BELNR", "ref", label="BELNR/ref")
    txn_date = _iso_date(_required_text(raw, "BUDAT", "date", label="BUDAT/date"))
    currency = _required_text(raw, "WAERS", "currency", label="WAERS/currency")
    account_code = _required_text(raw, "HKONT", "account_code", label="HKONT/account_code")
    account_name = _required_text(raw, "TXT50", "account_name", label="TXT50/account_name")
    description = _required_text(raw, "SGTXT", "description", label="SGTXT/description")
    erp_doc_id = _required_text(raw, "BELNR", "erp_doc_id", label="BELNR/erp_doc_id")

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": account_code,
        "account_name": account_name,
        "cost_center":  _optional_text(raw, "KOSTL", "cost_center"),
        "description":  description,
        "entity":       _optional_text(raw, "NAME1", "entity") or "",
        "entity_code":  _optional_text(raw, "LIFNR", "KUNNR", "entity_code"),
        "tax_code":     _optional_text(raw, "MWSKZ", "tax_code"),
        "erp_system":   "SAP_S4HANA",
        "erp_doc_id":   erp_doc_id,
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_code,
        }),
    }


# ─── Oracle Fusion Financials ─────────────────────────────────────────────────

def normalize_oracle(raw: dict) -> dict:
    """
    Maps Oracle Financials Cloud REST API GL Journal Entry Line format.
    Key fields: AcctdCr, AcctdDr, CurrencyCode, AccountedDate,
    CodeCombinationId, Description, ExternalReference
    """
    debit_raw = raw.get("AcctdDr") or raw.get("debit")
    credit_raw = raw.get("AcctdCr") or raw.get("credit")
    debit = abs(float(re.sub(r"[^\d.\-]", "", str(debit_raw)))) if debit_raw not in (None, "") else 0.0
    credit = abs(float(re.sub(r"[^\d.\-]", "", str(credit_raw)))) if credit_raw not in (None, "") else 0.0
    amount = debit if debit > 0 else credit
    if amount <= 0:
        raise ERPValidationError("Oracle journal entry requires AcctdDr or AcctdCr.")
    entry_type = "DEBIT" if debit > 0 else "CREDIT"

    risk_flags: list[str] = []
    if debit > 0 and credit > 0:
        risk_flags.append("SIMULTANEOUS_DR_CR")

    ref = _required_text(raw, "ExternalReference", "JournalEntryLineId", label="ExternalReference/JournalEntryLineId")
    txn_date = _iso_date(_required_text(raw, "AccountedDate", "date", label="AccountedDate/date"))
    currency = _required_text(raw, "CurrencyCode", "currency", label="CurrencyCode/currency")
    account_code = _required_text(raw, "CodeCombinationId", "account_code", label="CodeCombinationId/account_code")
    account_name = _required_text(raw, "AccountName", "account_name", label="AccountName/account_name")
    description = _required_text(raw, "Description", "description", label="Description")
    erp_doc_id = _required_text(raw, "JournalEntryLineId", "erp_doc_id", label="JournalEntryLineId/erp_doc_id")

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": account_code,
        "account_name": account_name,
        "cost_center":  _optional_text(raw, "CostCenter", "cost_center"),
        "description":  description,
        "entity":       _optional_text(raw, "PartyName", "entity") or "",
        "entity_code":  _optional_text(raw, "PartyId", "entity_code"),
        "tax_code":     _optional_text(raw, "TaxCode", "tax_code"),
        "erp_system":   "ORACLE_FUSION",
        "erp_doc_id":   erp_doc_id,
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_code,
        }),
    }


# ─── Tally Prime (India) ──────────────────────────────────────────────────────

def normalize_tally(raw: dict) -> dict:
    """
    Maps Tally Prime TallyPrime REST / XML voucher format.
    Key fields: VOUCHERNUMBER, DATE, AMOUNT, LEDGERNAME,
    PARTYLEDGERNAME, NARRATION, GSTREGISTRATIONNUMBER
    """
    amount     = _clean_amount(raw.get("AMOUNT") or raw.get("amount"))
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
    # Flag round-number transactions (Benford's Law anomaly)
    if amount > 0 and amount == int(amount) and amount % 10000 == 0:
        risk_flags.append("ROUND_NUMBER_HIGH_VALUE")
    gst_no = raw.get("GSTREGISTRATIONNUMBER") or raw.get("tax_code")
    if not gst_no and amount > 50000:
        risk_flags.append("MISSING_GST_HIGH_VALUE")

    ref = _required_text(raw, "VOUCHERNUMBER", "ref", label="VOUCHERNUMBER/ref")
    txn_date = _iso_date(_required_text(raw, "DATE", "date", label="DATE/date"))
    currency = _required_text(raw, "CURRENCY", "currency", label="CURRENCY/currency")
    account_name = _required_text(raw, "LEDGERNAME", "account_name", label="LEDGERNAME/account_name")
    description = _required_text(raw, "NARRATION", "description", label="NARRATION/description")

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": _optional_text(raw, "account_code", "LEDGERNAME") or account_name,
        "account_name": account_name,
        "cost_center":  _optional_text(raw, "COSTCENTRE", "cost_center"),
        "description":  description,
        "entity":       _optional_text(raw, "PARTYLEDGERNAME", "entity") or "",
        "entity_code":  _optional_text(raw, "VENDORCODE", "entity_code"),
        "tax_code":     str(gst_no).strip() if gst_no else None,
        "erp_system":   "TALLY_PRIME",
        "erp_doc_id":   _required_text(raw, "VOUCHERNUMBER", "erp_doc_id", label="VOUCHERNUMBER/erp_doc_id"),
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_name,
        }),
    }


# ─── Zoho Books ──────────────────────────────────────────────────────────────

def normalize_zoho(raw: dict) -> dict:
    """
    Maps Zoho Books API journal entry lines.
    Key fields: journal_id, date, debit_or_credit, amount,
    account_id, account_name, reference_number, tax_id
    """
    amount      = _clean_amount(raw.get("amount"))
    dr_cr       = str(raw.get("debit_or_credit") or raw.get("type") or "debit").lower()
    entry_type  = "DEBIT" if "debit" in dr_cr or "dr" in dr_cr else "CREDIT"

    risk_flags: list[str] = []
    ref = _required_text(raw, "reference_number", "journal_id", label="reference_number/journal_id")
    txn_date = _iso_date(_required_text(raw, "date", label="date"))
    currency = _required_text(raw, "currency_code", "currency", label="currency_code/currency")
    account_code = _required_text(raw, "account_id", "account_code", label="account_id/account_code")
    account_name = _required_text(raw, "account_name", label="account_name")
    erp_doc_id = _required_text(raw, "journal_id", "erp_doc_id", label="journal_id/erp_doc_id")

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": account_code,
        "account_name": account_name,
        "cost_center":  None,
        "description":  _required_text(raw, "notes", "description", label="notes/description"),
        "entity":       _optional_text(raw, "vendor_name", "customer_name", "entity") or "",
        "entity_code":  _optional_text(raw, "vendor_id", "customer_id", "entity_code"),
        "tax_code":     _optional_text(raw, "tax_id", "tax_code"),
        "erp_system":   "ZOHO_BOOKS",
        "erp_doc_id":   erp_doc_id,
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_code,
        }),
    }


# ─── QuickBooks Online ────────────────────────────────────────────────────────

def normalize_quickbooks(raw: dict) -> dict:
    """
    Maps QuickBooks Online REST API JournalEntry.Line objects.
    Key fields: Id, TxnDate, Amount, DetailType (JournalEntryLineDetail),
    PostingType (Debit/Credit), AccountRef, EntityRef
    """
    detail      = raw.get("JournalEntryLineDetail") or raw.get("detail") or {}
    amount      = _clean_amount(raw.get("Amount") or raw.get("amount"))
    posting     = str(detail.get("PostingType") or raw.get("type") or "Debit")
    entry_type  = "DEBIT" if "debit" in posting.lower() else "CREDIT"

    acct_ref = detail.get("AccountRef") or raw.get("AccountRef") or {}
    entity_ref = detail.get("Entity") or raw.get("EntityRef") or {}

    risk_flags: list[str] = []
    ref = _required_text(raw, "Id", "ref", label="Id/ref")
    txn_date = _iso_date(_required_text(raw, "TxnDate", "date", label="TxnDate/date"))
    currency = _required_text(raw.get("CurrencyRef") or {}, "value", label="CurrencyRef.value") if isinstance(raw.get("CurrencyRef"), dict) else _required_text(raw, "currency", label="currency")
    account_code = _required_text(acct_ref, "value", label="AccountRef.value")
    account_name = _required_text(acct_ref, "name", label="AccountRef.name")
    description = _required_text(raw, "Description", "description", label="Description")

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": account_code,
        "account_name": account_name,
        "cost_center":  _optional_text(detail.get("ClassRef") or {}, "name") if isinstance(detail.get("ClassRef"), dict) else _optional_text(raw, "cost_center"),
        "description":  description,
        "entity":       _optional_text(entity_ref, "name") if isinstance(entity_ref, dict) else _optional_text(raw, "entity") or "",
        "entity_code":  _optional_text(entity_ref, "type") if isinstance(entity_ref, dict) else _optional_text(raw, "entity_code"),
        "tax_code":     _optional_text(raw.get("TaxCodeRef") or {}, "value") if isinstance(raw.get("TaxCodeRef"), dict) else _optional_text(raw, "tax_code"),
        "erp_system":   "QUICKBOOKS",
        "erp_doc_id":   _required_text(raw, "Id", "erp_doc_id", label="Id/erp_doc_id"),
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_code,
        }),
    }


# ─── Generic CSV / Flat File ──────────────────────────────────────────────────

def normalize_generic(raw: dict) -> dict:
    """
    Passthrough normalizer for flat file / CSV uploads.
    Caller must pre-map columns to canonical keys.
    """
    amount     = _clean_amount(raw.get("amount") or raw.get("AMOUNT"))
    risk_flags: list[str] = list(raw.get("risk_flags") or [])
    ref = _required_text(raw, "ref", label="ref")
    txn_date = _iso_date(_required_text(raw, "date", label="date"))
    currency = _required_text(raw, "currency", label="currency")
    account_code = _required_text(raw, "account_code", label="account_code")
    account_name = _required_text(raw, "account_name", label="account_name")
    description = _required_text(raw, "description", label="description")
    entry_type = _required_text(raw, "type", label="type").upper()

    return {
        "ref":          ref[:64],
        "date":         txn_date,
        "type":         entry_type,
        "amount":       amount,
        "currency":     currency,
        "account_code": account_code,
        "account_name": account_name,
        "cost_center":  _optional_text(raw, "cost_center"),
        "description":  description,
        "entity":       _optional_text(raw, "entity") or "",
        "entity_code":  _optional_text(raw, "entity_code"),
        "tax_code":     _optional_text(raw, "tax_code"),
        "erp_system":   "GENERIC_CSV",
        "erp_doc_id":   _required_text(raw, "erp_doc_id", "ref", label="erp_doc_id/ref"),
        "risk_flags":   risk_flags,
        "payload_hash": _payload_hash({
            "ref": ref,
            "date": txn_date,
            "amount": amount,
            "account_code": account_code,
        }),
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
