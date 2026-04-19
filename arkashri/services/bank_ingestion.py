# pyre-ignore-all-errors
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import Transaction

logger = structlog.get_logger(__name__)


class BankIngestionError(ValueError):
    pass


@dataclass
class BankIngestionResult:
    records_submitted: int
    records_ingested: int
    records_failed: int
    duplicate_refs: list[str]


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _parse_date(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        raise BankIngestionError("Bank transaction is missing a date.")

    value = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise BankIngestionError(f"Unsupported bank transaction date format: {value}")


def _parse_amount(raw: Any) -> float:
    if raw is None or str(raw).strip() == "":
        raise BankIngestionError("Bank transaction is missing an amount.")
    value = re.sub(r"[^\d.\-]", "", str(raw))
    try:
        amount = float(value)
    except ValueError as exc:
        raise BankIngestionError(f"Invalid bank transaction amount: {raw}") from exc
    if amount == 0.0:
        raise BankIngestionError("Bank transaction amount must be non-zero.")
    return amount


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def parse_bank_csv(
    csv_bytes: bytes,
    *,
    column_mapping: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    settings = get_settings()
    rows = list(reader)
    if not rows:
        raise BankIngestionError("CSV upload did not contain any bank transaction rows.")
    if len(rows) > settings.bank_csv_max_rows:
        raise BankIngestionError(f"CSV upload exceeds the {settings.bank_csv_max_rows} row limit.")

    mapping = {
        "date": "date",
        "description": "description",
        "amount": "amount",
        "debit": "debit",
        "credit": "credit",
        "reference": "reference",
        "currency": "currency",
        "account_number": "account_number",
        "account_name": "account_name",
        "entity": "entity",
    }
    if column_mapping:
        mapping.update(column_mapping)

    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        debit_raw = row.get(mapping["debit"]) if mapping.get("debit") else None
        credit_raw = row.get(mapping["credit"]) if mapping.get("credit") else None
        signed_amount: float
        if debit_raw not in (None, "") or credit_raw not in (None, ""):
            debit = abs(_parse_amount(debit_raw)) if debit_raw not in (None, "") else 0.0
            credit = abs(_parse_amount(credit_raw)) if credit_raw not in (None, "") else 0.0
            signed_amount = credit if credit > 0 else -debit
            if signed_amount == 0.0:
                raise BankIngestionError(f"Row {index} must include a debit or credit amount.")
        else:
            signed_amount = _parse_amount(row.get(mapping["amount"]))

        reference = _clean_text(row.get(mapping["reference"]))
        if not reference:
            reference = hashlib.sha256(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:32]
        description = _clean_text(row.get(mapping["description"]))
        if not description:
            raise BankIngestionError(f"Row {index} is missing a transaction description.")

        records.append(
            {
                "date": _parse_date(row.get(mapping["date"])),
                "description": description,
                "signed_amount": signed_amount,
                "reference": reference,
                "currency": _clean_text(row.get(mapping["currency"])),
                "account_number": _clean_text(row.get(mapping["account_number"])),
                "account_name": _clean_text(row.get(mapping["account_name"])),
                "entity": _clean_text(row.get(mapping["entity"])),
            }
        )

    return records


def normalize_bank_record(
    record: dict[str, Any],
    *,
    default_currency: str,
    source: str,
) -> dict[str, Any]:
    signed_amount = _parse_amount(record.get("signed_amount") or record.get("amount"))
    entry_type = "CREDIT" if signed_amount > 0 else "DEBIT"
    amount = abs(signed_amount)
    currency = _clean_text(record.get("currency")) or default_currency
    if not currency:
        raise BankIngestionError("Bank transaction is missing a currency.")

    reference = _clean_text(record.get("reference") or record.get("ref"))
    if not reference:
        raise BankIngestionError("Bank transaction is missing a reference.")

    description = _clean_text(record.get("description"))
    if not description:
        raise BankIngestionError("Bank transaction is missing a description.")

    payload = {
        "ref": reference[:64],
        "date": _parse_date(record.get("date")),
        "type": entry_type,
        "amount": amount,
        "currency": currency,
        "account_code": _clean_text(record.get("account_number")),
        "account_name": _clean_text(record.get("account_name")),
        "cost_center": None,
        "description": description,
        "entity": _clean_text(record.get("entity")),
        "entity_code": None,
        "tax_code": None,
        "erp_system": "BANK_STATEMENT",
        "erp_doc_id": reference[:64],
        "risk_flags": [],
        "source": source,
    }
    payload["payload_hash"] = _payload_hash(
        {
            "ref": payload["ref"],
            "date": payload["date"],
            "amount": payload["amount"],
            "account_code": payload["account_code"],
            "source": payload["source"],
        }
    )
    return payload


async def ingest_bank_records(
    session: AsyncSession,
    *,
    tenant_id: str,
    jurisdiction: str,
    records: list[dict[str, Any]],
    source: str,
    default_currency: str,
) -> BankIngestionResult:
    ingested = 0
    failed = 0
    duplicate_refs: list[str] = []

    for record in records:
        try:
            payload = normalize_bank_record(record, default_currency=default_currency, source=source)
        except BankIngestionError:
            failed += 1
            continue

        payload_hash = payload.pop("payload_hash")
        existing = await session.scalar(select(Transaction).where(Transaction.payload_hash == payload_hash))
        if existing is not None:
            duplicate_refs.append(payload["ref"])
            continue

        session.add(
            Transaction(
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
                payload=payload,
                payload_hash=payload_hash,
            )
        )
        ingested += 1

    await session.commit()
    logger.info(
        "bank_records_ingested",
        source=source,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        records_submitted=len(records),
        records_ingested=ingested,
        records_failed=failed,
    )
    return BankIngestionResult(
        records_submitted=len(records),
        records_ingested=ingested,
        records_failed=failed,
        duplicate_refs=duplicate_refs[:50],
    )
