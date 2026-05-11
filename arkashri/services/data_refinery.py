from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree as ET
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import Engagement, EngagementStatus, Transaction
from arkashri.services.audit import append_audit_event

RefinerySourceType = Literal["bank_statement", "books_ledger", "sales_register", "purchase_register", "generic_ledger"]
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_HEADER_COUNT = 200
MAX_CELL_CHARS = 5000
PREVIEW_ROW_LIMIT = 25
ISSUE_LIMIT = 100


class DataRefineryError(ValueError):
    pass


class DataRefineryCriticalIssuesError(DataRefineryError):
    pass


CANONICAL_FIELDS = {
    "date": ("date", "txn date", "transaction date", "posting date", "voucher date", "doc date", "value date"),
    "reference": ("ref", "reference", "voucher", "voucher no", "voucher number", "invoice no", "utr", "chq", "document no"),
    "description": ("description", "narration", "particulars", "ledger narration", "remarks", "details"),
    "debit": ("debit", "withdrawal", "dr", "paid", "payment"),
    "credit": ("credit", "deposit", "cr", "received", "receipt"),
    "amount": ("amount", "value", "transaction amount", "net amount"),
    "account_name": ("account", "ledger", "ledger name", "account name", "gl name", "bank account"),
    "counterparty": ("party", "party name", "vendor", "customer", "supplier", "counterparty"),
    "gstin": ("gstin", "gst no", "gst number", "party gstin", "counterparty gstin"),
    "tax_amount": ("gst", "gst amount", "tax", "tax amount", "igst", "cgst", "sgst"),
    "currency": ("currency", "curr", "ccy"),
}


@dataclass(frozen=True)
class RefineryIssue:
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    row_number: int | None
    field: str | None
    title: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "row_number": self.row_number,
            "field": self.field,
            "title": self.title,
            "recommended_action": self.recommended_action,
        }


def _clean_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_csv(csv_bytes: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    if not csv_bytes:
        raise DataRefineryError("CSV upload is empty.")
    if len(csv_bytes) > MAX_UPLOAD_BYTES:
        raise DataRefineryError("CSV upload exceeds the 100 MB refinery limit.")
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = list(reader)
    if not headers:
        raise DataRefineryError("CSV has no header row.")
    if len(headers) > MAX_HEADER_COUNT:
        raise DataRefineryError(f"CSV has too many columns. Maximum allowed: {MAX_HEADER_COUNT}.")
    duplicate_headers = sorted({header for header in headers if headers.count(header) > 1})
    if duplicate_headers:
        raise DataRefineryError(f"CSV has duplicate headers: {', '.join(duplicate_headers[:10])}.")
    if not rows:
        raise DataRefineryError("CSV has no data rows.")
    max_rows = get_settings().bank_csv_max_rows
    if len(rows) > max_rows:
        raise DataRefineryError(f"CSV upload exceeds the {max_rows} row limit.")
    for row_number, row in enumerate(rows, start=2):
        for header, value in row.items():
            if value is not None and len(str(value)) > MAX_CELL_CHARS:
                raise DataRefineryError(f"Cell at row {row_number}, column {header} exceeds {MAX_CELL_CHARS} characters.")
    return headers, rows


def suggest_column_mapping(headers: list[str]) -> dict[str, str]:
    normalized = {_clean_header(header): header for header in headers}
    mapping: dict[str, str] = {}
    for canonical, candidates in CANONICAL_FIELDS.items():
        for candidate in candidates:
            clean_candidate = _clean_header(candidate)
            if clean_candidate in normalized:
                mapping[canonical] = normalized[clean_candidate]
                break
        if canonical in mapping:
            continue
        for clean_header, raw_header in normalized.items():
            if any(_clean_header(candidate) in clean_header for candidate in candidates):
                mapping[canonical] = raw_header
                break
    return mapping


def _parse_date(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_amount(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    normalized = re.sub(r"[^\d.\-]", "", text)
    if normalized in {"", "-", "."}:
        return None
    try:
        amount = float(normalized)
    except ValueError:
        return None
    return -abs(amount) if negative else amount


def _amount_from_row(row: dict[str, Any], mapping: dict[str, str]) -> tuple[float | None, str | None]:
    debit = _parse_amount(row.get(mapping.get("debit", ""))) if mapping.get("debit") else None
    credit = _parse_amount(row.get(mapping.get("credit", ""))) if mapping.get("credit") else None
    if debit not in (None, 0) or credit not in (None, 0):
        debit_abs = abs(debit or 0)
        credit_abs = abs(credit or 0)
        return (credit_abs if credit_abs > 0 else -debit_abs), None
    amount = _parse_amount(row.get(mapping.get("amount", ""))) if mapping.get("amount") else None
    return amount, None


def _mapped_category(account_name: str, description: str, source_type: RefinerySourceType) -> str:
    text = f"{account_name} {description}".lower()
    if source_type == "bank_statement" or any(term in text for term in ["bank", "cash", "hdfc", "icici", "sbi", "axis"]):
        return "cash_and_bank"
    if any(term in text for term in ["sale", "sales", "revenue", "income", "receipt"]):
        return "revenue"
    if any(term in text for term in ["purchase", "vendor", "supplier", "expense", "payment"]):
        return "expense"
    if "gst" in text or "igst" in text or "cgst" in text or "sgst" in text:
        return "gst_and_indirect_tax"
    if any(term in text for term in ["debtor", "receivable", "customer"]):
        return "trade_receivables"
    if any(term in text for term in ["creditor", "payable"]):
        return "trade_payables"
    return "unmapped"


def _risk_flags(payload: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    amount = abs(float(payload.get("signed_amount") or payload.get("amount") or 0))
    description = str(payload.get("description") or "").lower()
    if amount >= 100000 and amount % 10000 == 0:
        flags.append("ROUND_AMOUNT")
    if any(term in description for term in ["cash", "manual", "adjustment", "write off", "write-off"]):
        flags.append("SENSITIVE_NARRATION")
    txn_date = _parse_date(payload.get("date"))
    if txn_date:
        parsed = datetime.strptime(txn_date, "%Y-%m-%d")
        if parsed.weekday() >= 5:
            flags.append("WEEKEND_ENTRY")
    return flags


def _payload_hash(payload: dict[str, Any]) -> str:
    material = {
        "engagement_id": payload.get("engagement_id"),
        "ref": payload.get("ref"),
        "date": payload.get("date"),
        "signed_amount": payload.get("signed_amount"),
        "account_name": payload.get("account_name"),
        "source_type": payload.get("source_type"),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_hash(csv_bytes: bytes) -> str:
    return hashlib.sha256(csv_bytes).hexdigest()


def normalize_rows(
    rows: list[dict[str, Any]],
    *,
    mapping: dict[str, str],
    source_type: RefinerySourceType,
    engagement_id: uuid.UUID | None = None,
    batch_id: str | None = None,
    file_hash: str | None = None,
    default_currency: str = "INR",
) -> tuple[list[dict[str, Any]], list[RefineryIssue]]:
    normalized: list[dict[str, Any]] = []
    issues: list[RefineryIssue] = []
    seen_refs: set[str] = set()

    for index, row in enumerate(rows, start=2):
        date = _parse_date(row.get(mapping.get("date", ""))) if mapping.get("date") else None
        if not date:
            issues.append(RefineryIssue("CRITICAL", index, "date", "Missing or invalid date", "Map the correct date column or correct the source row."))

        signed_amount, _ = _amount_from_row(row, mapping)
        if signed_amount in (None, 0):
            issues.append(RefineryIssue("CRITICAL", index, "amount", "Missing or zero amount", "Map debit/credit or amount column and correct blank amounts."))

        description = _clean_text(row.get(mapping.get("description", ""))) if mapping.get("description") else ""
        account_name = _clean_text(row.get(mapping.get("account_name", ""))) if mapping.get("account_name") else ""
        if not description and not account_name:
            issues.append(RefineryIssue("HIGH", index, "description", "Narration and ledger are missing", "Provide narration or ledger name for audit classification."))

        reference = _clean_text(row.get(mapping.get("reference", ""))) if mapping.get("reference") else ""
        if not reference:
            reference = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
            issues.append(RefineryIssue("MEDIUM", index, "reference", "Reference auto-generated", "Add voucher/reference number to improve matching and duplicate checks."))
        if reference in seen_refs:
            issues.append(RefineryIssue("HIGH", index, "reference", "Duplicate reference detected", "Review duplicate voucher/reference before ingestion."))
        seen_refs.add(reference)

        payload = {
            "engagement_id": str(engagement_id) if engagement_id else None,
            "ref": reference[:64],
            "date": date,
            "description": description or account_name,
            "signed_amount": round(float(signed_amount or 0), 2),
            "amount": round(abs(float(signed_amount or 0)), 2),
            "type": "CREDIT" if float(signed_amount or 0) > 0 else "DEBIT",
            "currency": _clean_text(row.get(mapping.get("currency", ""))) if mapping.get("currency") else default_currency,
            "account_name": account_name,
            "counterparty": _clean_text(row.get(mapping.get("counterparty", ""))) if mapping.get("counterparty") else "",
            "gstin": _clean_text(row.get(mapping.get("gstin", ""))) if mapping.get("gstin") else "",
            "tax_amount": _parse_amount(row.get(mapping.get("tax_amount", ""))) if mapping.get("tax_amount") else 0,
            "mapped_category": _mapped_category(account_name, description, source_type),
            "source": "DATA_REFINERY",
            "source_type": source_type,
            "batch_id": batch_id,
            "source_file_hash": file_hash,
            "raw_row": row,
        }
        payload["risk_flags"] = _risk_flags(payload)
        payload["payload_hash"] = _payload_hash(payload)
        normalized.append(payload)

    if not mapping.get("date"):
        issues.append(RefineryIssue("CRITICAL", None, "date", "Date column not mapped", "Select the transaction/voucher date column."))
    if not (mapping.get("amount") or mapping.get("debit") or mapping.get("credit")):
        issues.append(RefineryIssue("CRITICAL", None, "amount", "Amount columns not mapped", "Select amount or debit/credit columns."))

    return normalized, issues


def build_refinery_preview(
    csv_bytes: bytes,
    *,
    source_type: RefinerySourceType,
    column_mapping: dict[str, str] | None = None,
    default_currency: str = "INR",
) -> dict[str, Any]:
    file_hash = _file_hash(csv_bytes)
    headers, rows = _parse_csv(csv_bytes)
    mapping = suggest_column_mapping(headers)
    if column_mapping:
        mapping.update({key: value for key, value in column_mapping.items() if value})
    normalized, issues = normalize_rows(
        rows,
        mapping=mapping,
        source_type=source_type,
        file_hash=file_hash,
        default_currency=default_currency,
    )
    critical_count = sum(1 for issue in issues if issue.severity == "CRITICAL")
    high_count = sum(1 for issue in issues if issue.severity == "HIGH")
    audit_ready_rows = sum(1 for row in normalized if row["date"] and row["signed_amount"])
    readiness_score = max(0, min(100, round((audit_ready_rows / len(rows)) * 100) - critical_count * 10 - high_count * 5))
    return {
        "source_type": source_type,
        "source_file_hash": file_hash,
        "headers": headers,
        "suggested_mapping": mapping,
        "total_rows": len(rows),
        "audit_ready_rows": audit_ready_rows,
        "readiness_score": readiness_score,
        "can_ingest": critical_count == 0,
        "issues": [issue.to_dict() for issue in issues[:ISSUE_LIMIT]],
        "normalized_preview": [{k: v for k, v in row.items() if k not in {"raw_row", "payload_hash"}} for row in normalized[:PREVIEW_ROW_LIMIT]],
        "category_breakdown": _category_breakdown(normalized),
        "risk_flag_breakdown": _risk_flag_breakdown(normalized),
    }


def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
    inline = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is")
    if inline is not None:
        text = "".join(inline.itertext()).strip()
        return text
    if value is None or value.text is None:
        return ""
    raw = value.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def _xlsx_col_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha()).upper()
    result = 0
    for ch in letters:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return max(result - 1, 0)


def _read_xlsx_rows(xlsx_bytes: bytes) -> dict[str, list[list[str]]]:
    if not xlsx_bytes:
        raise DataRefineryError("Excel upload is empty.")
    if len(xlsx_bytes) > MAX_UPLOAD_BYTES:
        raise DataRefineryError("Excel upload exceeds the 100 MB refinery limit.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    except zipfile.BadZipFile as exc:
        raise DataRefineryError("Uploaded file is not a valid .xlsx workbook.") from exc

    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.findall("main:si", ns):
            shared_strings.append("".join(item.itertext()).strip())

    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pkg:Relationship", ns)
        if "Id" in rel.attrib and "Target" in rel.attrib
    }

    sheets: dict[str, list[list[str]]] = {}
    for sheet in workbook.findall("main:sheets/main:sheet", ns):
        sheet_name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rel_targets.get(str(rel_id), "")
        path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        if path not in archive.namelist():
            continue
        root = ET.fromstring(archive.read(path))
        rows: list[list[str]] = []
        for row in root.findall(".//main:sheetData/main:row", ns):
            values: list[str] = []
            for cell in row.findall("main:c", ns):
                ref = cell.attrib.get("r", "")
                col_index = _xlsx_col_index(ref)
                while len(values) < col_index:
                    values.append("")
                values.append(_xlsx_cell_value(cell, shared_strings))
            if any(value.strip() for value in values):
                rows.append(values)
        sheets[sheet_name] = rows
    if not sheets:
        raise DataRefineryError("Excel workbook has no readable sheets.")
    return sheets


def build_excel_refinery_preview(
    xlsx_bytes: bytes,
    *,
    source_type: RefinerySourceType,
    default_currency: str = "INR",
) -> dict[str, Any]:
    source_file_hash = _file_hash(xlsx_bytes)
    workbook = _read_xlsx_rows(xlsx_bytes)
    sheet_previews: list[dict[str, Any]] = []
    total_rows = 0
    audit_ready_rows = 0
    critical_count = 0
    for sheet_name, rows in workbook.items():
        if not rows:
            continue
        headers = [header.strip() or f"Column {index + 1}" for index, header in enumerate(rows[0])]
        if len(headers) > MAX_HEADER_COUNT:
            raise DataRefineryError(f"Sheet {sheet_name} has too many columns. Maximum allowed: {MAX_HEADER_COUNT}.")
        data_rows = []
        for raw in rows[1:]:
            row = {header: raw[index] if index < len(raw) else "" for index, header in enumerate(headers)}
            data_rows.append(row)
        if not data_rows:
            continue
        mapping = suggest_column_mapping(headers)
        normalized, issues = normalize_rows(
            data_rows,
            mapping=mapping,
            source_type=source_type,
            file_hash=source_file_hash,
            default_currency=default_currency,
        )
        total_rows += len(data_rows)
        audit_ready_rows += sum(1 for row in normalized if row["date"] and row["signed_amount"])
        critical_count += sum(1 for issue in issues if issue.severity == "CRITICAL")
        sheet_previews.append({
            "sheet_name": sheet_name,
            "headers": headers,
            "suggested_mapping": mapping,
            "total_rows": len(data_rows),
            "audit_ready_rows": sum(1 for row in normalized if row["date"] and row["signed_amount"]),
            "issues": [issue.to_dict() for issue in issues[:ISSUE_LIMIT]],
            "normalized_preview": [{k: v for k, v in row.items() if k not in {"raw_row", "payload_hash"}} for row in normalized[:PREVIEW_ROW_LIMIT]],
            "category_breakdown": _category_breakdown(normalized),
            "risk_flag_breakdown": _risk_flag_breakdown(normalized),
        })
    readiness_score = 0 if total_rows == 0 else max(0, min(100, round((audit_ready_rows / total_rows) * 100) - critical_count * 10))
    return {
        "source_type": source_type,
        "source_file_hash": source_file_hash,
        "sheet_count": len(sheet_previews),
        "total_rows": total_rows,
        "audit_ready_rows": audit_ready_rows,
        "readiness_score": readiness_score,
        "can_ingest": total_rows > 0 and critical_count == 0,
        "sheets": sheet_previews,
    }


def build_pdf_bank_statement_intake(pdf_bytes: bytes) -> dict[str, Any]:
    if not pdf_bytes:
        raise DataRefineryError("PDF upload is empty.")
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise DataRefineryError("PDF upload exceeds the 100 MB refinery limit.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise DataRefineryError("Uploaded file is not a valid PDF.")
    provider = (get_settings().ocr_provider or "").strip().lower()
    supported = {"aws_textract", "google_document_ai", "azure_document_intelligence"}
    provider_ready = provider in supported
    return {
        "source_type": "bank_statement",
        "source_file_hash": _file_hash(pdf_bytes),
        "status": "OCR_READY_FOR_EXTRACTION" if provider_ready else "OCR_PROVIDER_REQUIRED",
        "ocr_provider": provider or None,
        "can_ingest": False,
        "recommended_action": (
            "Run OCR extraction, review the extracted rows, then ingest only after CA approval."
            if provider_ready
            else "Connect an OCR provider or upload machine-readable CSV/XLSX bank data. Scanned bank statements must be reviewed by a CA before ingestion."
        ),
        "human_review_required": True,
    }


async def extract_bank_pdf_with_ocr(pdf_bytes: bytes) -> dict[str, Any]:
    intake = build_pdf_bank_statement_intake(pdf_bytes)
    provider = intake.get("ocr_provider")
    if not provider:
        raise DataRefineryError("OCR_PROVIDER is not configured.")
    raise DataRefineryError(
        f"{provider} OCR adapter is configured but live extraction requires provider credentials and implementation-specific document model setup."
    )


def _category_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        category = str(row.get("mapped_category") or "unmapped")
        result[category] = result.get(category, 0) + 1
    return result


def _risk_flag_breakdown(rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        for flag in row.get("risk_flags") or []:
            result[flag] = result.get(flag, 0) + 1
    return result


async def ingest_refined_csv(
    session: AsyncSession,
    *,
    tenant_id: str,
    engagement_id: uuid.UUID,
    csv_bytes: bytes,
    source_type: RefinerySourceType,
    column_mapping: dict[str, str] | None = None,
    default_currency: str = "INR",
) -> dict[str, Any]:
    file_hash = _file_hash(csv_bytes)
    engagement = await session.scalar(
        select(Engagement).where(Engagement.id == engagement_id, Engagement.tenant_id == tenant_id)
    )
    if engagement is None:
        raise DataRefineryError("Engagement not found.")
    if engagement.status == EngagementStatus.SEALED or engagement.sealed_at:
        raise DataRefineryError("Cannot ingest data into a sealed engagement.")

    headers, rows = _parse_csv(csv_bytes)
    mapping = suggest_column_mapping(headers)
    if column_mapping:
        mapping.update({key: value for key, value in column_mapping.items() if value})
    batch_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"arkashri:data-refinery:{tenant_id}:{engagement_id}:{file_hash}:{source_type}"))
    normalized, issues = normalize_rows(
        rows,
        mapping=mapping,
        source_type=source_type,
        engagement_id=engagement_id,
        batch_id=batch_id,
        file_hash=file_hash,
        default_currency=default_currency,
    )
    if any(issue.severity == "CRITICAL" for issue in issues):
        raise DataRefineryCriticalIssuesError("Critical data quality issues remain. Preview and fix mappings before ingestion.")

    ingested = 0
    duplicates: list[str] = []
    for row in normalized:
        payload_hash = row.pop("payload_hash")
        existing = await session.scalar(select(Transaction).where(Transaction.payload_hash == payload_hash))
        if existing is not None:
            duplicates.append(row["ref"])
            continue
        session.add(
            Transaction(
                tenant_id=tenant_id,
                jurisdiction=engagement.jurisdiction,
                payload=row,
                payload_hash=payload_hash,
            )
        )
        ingested += 1

    await append_audit_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        jurisdiction=engagement.jurisdiction,
        event_type="DATA_REFINERY_INGESTED",
        entity_type="financial_transaction",
        entity_id=batch_id,
        payload={
            "batch_id": batch_id,
            "source_type": source_type,
            "source_file_hash": file_hash,
            "records_submitted": len(rows),
            "records_ingested": ingested,
            "duplicate_count": len(duplicates),
            "mapping": mapping,
            "category_breakdown": _category_breakdown(normalized),
            "risk_flag_breakdown": _risk_flag_breakdown(normalized),
        },
    )
    await session.commit()
    return {
        "batch_id": batch_id,
        "engagement_id": str(engagement_id),
        "source_type": source_type,
        "source_file_hash": file_hash,
        "records_submitted": len(rows),
        "records_ingested": ingested,
        "duplicate_refs": duplicates[:50],
        "issues": [issue.to_dict() for issue in issues[:100]],
        "category_breakdown": _category_breakdown(normalized),
        "risk_flag_breakdown": _risk_flag_breakdown(normalized),
    }
