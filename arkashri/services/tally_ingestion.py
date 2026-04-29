from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.models import ERPConnection, ERPSystem, Engagement, Transaction
from arkashri.services.crypto import decrypt_dict
from arkashri.services.erp_adapter import normalize_batch

TALLY_SUMMARY_KEY = "tally_imports"
DEFAULT_CURRENCY = "INR"
TB_TOLERANCE = 1.0
VOUCHER_TOLERANCE = 1.0

LEDGER_CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\b(cash|bank|hdfc|icici|sbi)\b", "cash_and_bank"),
    (r"\b(debtor|debtors|receivable|receivables|customer|customers)\b", "trade_receivables"),
    (r"\b(creditor|creditors|payable|payables|vendor|vendors|supplier|suppliers)\b", "trade_payables"),
    (r"\b(sales|revenue|turnover)\b", "revenue"),
    (r"\b(purchase|cogs|consumption|material)\b", "cost_of_goods_sold"),
    (r"\b(gst|cgst|sgst|igst|input tax|output tax)\b", "gst_and_indirect_tax"),
    (r"\b(salary|wages|bonus|staff welfare)\b", "employee_benefits"),
    (r"\b(pf|esi|tds|income tax)\b", "statutory_dues"),
    (r"\b(fixed asset|plant|machinery|furniture|vehicle)\b", "property_plant_equipment"),
    (r"\b(stock|inventory|closing stock|raw material|wip)\b", "inventory"),
    (r"\b(loan|od account|cc account|borrowing|interest)\b", "borrowings"),
    (r"\b(partner|director|related party)\b", "related_parties"),
]


class TallyIngestionError(ValueError):
    pass


@dataclass
class TallyImportResult:
    import_type: str
    source: str
    imported_at: str
    summary: dict[str, Any]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def _text(node: ET.Element | None, *names: str) -> str | None:
    if node is None:
        return None
    wanted = {name.upper() for name in names}
    for child in node.iter():
        if child is node:
            continue
        if _local_name(child.tag) in wanted:
            value = (child.text or "").strip()
            if value:
                return value
    return None


def _direct_children(node: ET.Element, *names: str) -> list[ET.Element]:
    wanted = {name.upper() for name in names}
    return [child for child in list(node) if _local_name(child.tag) in wanted]


def _parse_amount(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)

    text = str(raw).strip()
    if not text:
        return 0.0

    normalized = text.replace(",", "")
    direction = None
    upper = normalized.upper()
    if upper.endswith(" DR"):
        direction = "DR"
        normalized = normalized[:-3].strip()
    elif upper.endswith(" CR"):
        direction = "CR"
        normalized = normalized[:-3].strip()

    cleaned = re.sub(r"[^\d.\-]", "", normalized)
    if cleaned in {"", "-", ".", "-."}:
        return 0.0

    amount = float(cleaned)
    if direction == "CR":
        return -abs(amount)
    if direction == "DR":
        return abs(amount)
    return amount


def _split_signed_amount(value: float) -> tuple[float, float]:
    if value >= 0:
        return round(value, 2), 0.0
    return 0.0, round(abs(value), 2)


def _parse_iso_date(raw: str) -> str:
    value = raw.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise TallyIngestionError(f"Unsupported Tally date format: {raw}")


def _payload_hash(payload: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _resolve_connection_config(connection: ERPConnection) -> dict[str, Any]:
    config = connection.connection_config or {}
    encrypted_payload = config.get("aes_gcm_payload")
    if isinstance(encrypted_payload, str) and encrypted_payload:
        resolved = decrypt_dict(encrypted_payload)
        if resolved:
            return resolved
    return config


def suggest_ledger_mapping(ledger_name: str, group_name: str | None = None) -> dict[str, Any]:
    candidate = " ".join(filter(None, [ledger_name, group_name or ""])).lower()
    for pattern, category in LEDGER_CATEGORY_RULES:
        if re.search(pattern, candidate):
            return {"mapped_category": category, "confidence": "RULE_BASED", "matched_pattern": pattern}
    return {"mapped_category": "unmapped", "confidence": "REVIEW_REQUIRED", "matched_pattern": None}


def _build_trial_balance_request_xml(
    *,
    company_name: str | None,
    from_date: str | None,
    to_date: str | None,
) -> str:
    static_vars = []
    if company_name:
        static_vars.append(f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>")
    if from_date:
        static_vars.append(f"<SVFROMDATE>{from_date.replace('-', '')}</SVFROMDATE>")
    if to_date:
        static_vars.append(f"<SVTODATE>{to_date.replace('-', '')}</SVTODATE>")
    static_vars_xml = "".join(static_vars)
    return f"""
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>ArkashriTrialBalance</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>{static_vars_xml}</STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="ArkashriTrialBalance" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FETCH>Name, Parent, OpeningBalance, Debit, Credit, ClosingBalance</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>
""".strip()


def _build_vouchers_request_xml(
    *,
    company_name: str | None,
    from_date: str | None,
    to_date: str | None,
) -> str:
    static_vars = []
    if company_name:
        static_vars.append(f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>")
    if from_date:
        static_vars.append(f"<SVFROMDATE>{from_date.replace('-', '')}</SVFROMDATE>")
    if to_date:
        static_vars.append(f"<SVTODATE>{to_date.replace('-', '')}</SVTODATE>")
    static_vars_xml = "".join(static_vars)
    return f"""
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>ArkashriVouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>{static_vars_xml}</STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="ArkashriVouchers" ISMODIFY="No">
            <TYPE>Voucher</TYPE>
            <FETCH>Date, VoucherNumber, VoucherTypeName, Narration, PartyLedgerName, GSTRegistrationNumber, AllLedgerEntries.List</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>
""".strip()


async def _fetch_tally_xml(connection: ERPConnection, envelope: str) -> str:
    if connection.erp_system != ERPSystem.TALLY_PRIME:
        raise TallyIngestionError("Tally import requires a TALLY_PRIME ERP connection.")

    config = _resolve_connection_config(connection)
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        raise TallyIngestionError("Tally connection is missing base_url.")

    endpoint = str(config.get("xml_endpoint") or "/").strip()
    timeout_seconds = get_settings().erp_request_timeout_seconds
    headers = {
        "Content-Type": "application/xml; charset=utf-8",
        "Accept": "application/xml, text/xml",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.post(
            urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/")),
            content=envelope.encode("utf-8"),
            headers=headers,
        )
        response.raise_for_status()
        return response.text


def parse_trial_balance_xml(xml_payload: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        raise TallyIngestionError("Invalid Tally XML payload for trial balance.") from exc

    lines: list[dict[str, Any]] = []
    for node in root.iter():
        if _local_name(node.tag) not in {"LEDGER", "LEDGERENTRY", "STOCKITEM", "ACCOUNT"}:
            continue
        ledger_name = _text(node, "NAME", "LEDGERNAME", "ACCOUNTNAME")
        if not ledger_name:
            continue

        group_name = _text(node, "PARENT", "GROUP", "GROUPNAME")
        opening_amount = _parse_amount(_text(node, "OPENINGBALANCE", "OPENING"))
        period_debit = abs(_parse_amount(_text(node, "DEBIT", "DEBITTOTAL", "AMOUNTDR")))
        period_credit = abs(_parse_amount(_text(node, "CREDIT", "CREDITTOTAL", "AMOUNTCR")))
        closing_amount = _parse_amount(_text(node, "CLOSINGBALANCE", "CLOSING"))

        opening_debit, opening_credit = _split_signed_amount(opening_amount)
        closing_debit, closing_credit = _split_signed_amount(closing_amount)
        mapping = suggest_ledger_mapping(ledger_name, group_name)

        lines.append(
            {
                "ledger_name": ledger_name,
                "group_name": group_name,
                "opening_debit": opening_debit,
                "opening_credit": opening_credit,
                "period_debit": round(period_debit, 2),
                "period_credit": round(period_credit, 2),
                "closing_debit": closing_debit,
                "closing_credit": closing_credit,
                **mapping,
            }
        )

    if not lines:
        raise TallyIngestionError("No trial balance ledgers were found in the Tally XML payload.")
    return lines


def summarize_trial_balance(lines: list[dict[str, Any]]) -> dict[str, Any]:
    total_debit = round(sum(float(line["closing_debit"]) for line in lines), 2)
    total_credit = round(sum(float(line["closing_credit"]) for line in lines), 2)
    mismatch_amount = round(abs(total_debit - total_credit), 2)
    unmapped_ledgers = [line["ledger_name"] for line in lines if line["mapped_category"] == "unmapped"]

    coverage_base = max(len(lines), 1)
    mapped_ratio = round((coverage_base - len(unmapped_ledgers)) / coverage_base, 4)
    return {
        "line_count": len(lines),
        "total_closing_debit": total_debit,
        "total_closing_credit": total_credit,
        "mismatch_amount": mismatch_amount,
        "is_balanced": mismatch_amount <= TB_TOLERANCE,
        "mapped_ratio": mapped_ratio,
        "unmapped_ledgers": unmapped_ledgers[:25],
    }


def parse_vouchers_xml(xml_payload: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError as exc:
        raise TallyIngestionError("Invalid Tally XML payload for vouchers.") from exc

    lines: list[dict[str, Any]] = []
    for voucher in root.iter():
        if _local_name(voucher.tag) != "VOUCHER":
            continue

        voucher_number = _text(voucher, "VOUCHERNUMBER", "REFERENCE")
        voucher_type = _text(voucher, "VOUCHERTYPENAME", "VOUCHERTYPE", "TYPE") or "Journal"
        raw_date = _text(voucher, "DATE")
        if not voucher_number or not raw_date:
            continue

        narration = _text(voucher, "NARRATION") or f"{voucher_type} voucher {voucher_number}"
        party_ledger = _text(voucher, "PARTYLEDGERNAME")
        gstin = _text(voucher, "GSTREGISTRATIONNUMBER", "PARTYGSTIN")
        currency = _text(voucher, "CURRENCYNAME", "CURRENCY") or DEFAULT_CURRENCY

        entry_nodes = []
        for child in voucher.iter():
            child_name = _local_name(child.tag)
            if child_name in {"ALLLEDGERENTRIES.LIST", "LEDGERENTRIES.LIST", "ENTRY"}:
                entry_nodes.append(child)

        for entry in entry_nodes:
            ledger_name = _text(entry, "LEDGERNAME", "NAME")
            amount = _parse_amount(_text(entry, "AMOUNT"))
            if not ledger_name or amount == 0:
                continue

            mapping = suggest_ledger_mapping(ledger_name)
            lines.append(
                {
                    "voucher_number": voucher_number,
                    "voucher_type": voucher_type,
                    "date": _parse_iso_date(raw_date),
                    "ledger_name": ledger_name,
                    "party_ledger_name": party_ledger or ledger_name,
                    "narration": narration,
                    "currency": currency,
                    "signed_amount": round(amount, 2),
                    "debit": round(abs(amount), 2) if amount > 0 else 0.0,
                    "credit": round(abs(amount), 2) if amount < 0 else 0.0,
                    "gstin": gstin,
                    **mapping,
                }
            )

    if not lines:
        raise TallyIngestionError("No voucher ledger lines were found in the Tally XML payload.")
    return lines


def summarize_vouchers(lines: list[dict[str, Any]]) -> dict[str, Any]:
    voucher_totals: dict[str, float] = {}
    by_voucher: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        voucher_number = str(line["voucher_number"])
        voucher_totals[voucher_number] = voucher_totals.get(voucher_number, 0.0) + float(line["signed_amount"])
        by_voucher.setdefault(voucher_number, []).append(line)

    unbalanced_vouchers = [
        voucher_number
        for voucher_number, total in voucher_totals.items()
        if abs(round(total, 2)) > VOUCHER_TOLERANCE
    ]
    unmapped_ledgers = sorted(
        {str(line["ledger_name"]) for line in lines if line["mapped_category"] == "unmapped"}
    )
    return {
        "line_count": len(lines),
        "voucher_count": len(by_voucher),
        "is_balanced": not unbalanced_vouchers,
        "unbalanced_vouchers": unbalanced_vouchers[:25],
        "unmapped_ledgers": unmapped_ledgers[:25],
    }


async def _load_engagement(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> Engagement:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise TallyIngestionError("Engagement not found.")
    return engagement


async def _load_connection(
    session: AsyncSession,
    *,
    connection_id: uuid.UUID,
    tenant_id: str,
) -> ERPConnection:
    connection = await session.scalar(
        select(ERPConnection).where(
            ERPConnection.id == connection_id,
            ERPConnection.tenant_id == tenant_id,
        )
    )
    if connection is None:
        raise TallyIngestionError("ERP connection not found.")
    if connection.erp_system != ERPSystem.TALLY_PRIME:
        raise TallyIngestionError("Only TALLY_PRIME connections are supported for this import.")
    return connection


def _ensure_tally_bucket(engagement: Engagement) -> dict[str, Any]:
    metadata = copy.deepcopy(engagement.state_metadata or {})
    if "history" not in metadata:
        metadata["history"] = []
    if TALLY_SUMMARY_KEY not in metadata:
        metadata[TALLY_SUMMARY_KEY] = {}
    return metadata


def _build_mapping_snapshot(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    snapshot: list[dict[str, Any]] = []
    for line in lines:
        ledger_name = str(line["ledger_name"])
        mapped_category = str(line["mapped_category"])
        key = (ledger_name, mapped_category)
        if key in seen:
            continue
        seen.add(key)
        snapshot.append(
            {
                "ledger_name": ledger_name,
                "group_name": line.get("group_name"),
                "mapped_category": mapped_category,
                "confidence": line.get("confidence"),
                "matched_pattern": line.get("matched_pattern"),
            }
        )
    return snapshot


async def import_trial_balance(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    raw_xml: str | None = None,
    connection_id: uuid.UUID | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> TallyImportResult:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    source = "MANUAL_XML"

    if raw_xml is None:
        if connection_id is None:
            raise TallyIngestionError("Provide raw_xml or connection_id for trial balance import.")
        connection = await _load_connection(session, connection_id=connection_id, tenant_id=tenant_id)
        config = _resolve_connection_config(connection)
        raw_xml = await _fetch_tally_xml(
            connection,
            _build_trial_balance_request_xml(
                company_name=str(config.get("company_name") or "").strip() or None,
                from_date=from_date,
                to_date=to_date,
            ),
        )
        source = "TALLY_XML_API"

    lines = parse_trial_balance_xml(raw_xml)
    summary = summarize_trial_balance(lines)
    metadata = _ensure_tally_bucket(engagement)
    imported_at = datetime.now(timezone.utc).isoformat()
    metadata[TALLY_SUMMARY_KEY]["trial_balance"] = {
        "source": source,
        "imported_at": imported_at,
        "summary": summary,
        "lines": lines,
        "ledger_mappings": _build_mapping_snapshot(lines),
    }
    metadata["history"].append(
        {
            "timestamp": imported_at,
            "actor": actor_id,
            "action": "TALLY_TRIAL_BALANCE_IMPORTED",
            "source": source,
            "engagement_id": str(engagement.id),
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return TallyImportResult(import_type="trial_balance", source=source, imported_at=imported_at, summary=summary)


def _prepare_voucher_records(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        records.append(
            {
                "VOUCHERNUMBER": line["voucher_number"],
                "VOUCHERTYPE": line["voucher_type"],
                "DATE": line["date"],
                "AMOUNT": abs(float(line["signed_amount"])),
                "CURRENCY": line["currency"],
                "LEDGERNAME": line["ledger_name"],
                "PARTYLEDGERNAME": line["party_ledger_name"],
                "NARRATION": line["narration"],
                "GSTREGISTRATIONNUMBER": line["gstin"],
                "account_code": line["ledger_name"],
                "mapped_category": line["mapped_category"],
            }
        )
    return records


async def import_vouchers(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    actor_id: str,
    jurisdiction: str,
    raw_xml: str | None = None,
    connection_id: uuid.UUID | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> TallyImportResult:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    source = "MANUAL_XML"

    if raw_xml is None:
        if connection_id is None:
            raise TallyIngestionError("Provide raw_xml or connection_id for voucher import.")
        connection = await _load_connection(session, connection_id=connection_id, tenant_id=tenant_id)
        config = _resolve_connection_config(connection)
        raw_xml = await _fetch_tally_xml(
            connection,
            _build_vouchers_request_xml(
                company_name=str(config.get("company_name") or "").strip() or None,
                from_date=from_date,
                to_date=to_date,
            ),
        )
        source = "TALLY_XML_API"

    lines = parse_vouchers_xml(raw_xml)
    summary = summarize_vouchers(lines)
    if not summary["is_balanced"]:
        raise TallyIngestionError(
            f"Voucher import aborted because {len(summary['unbalanced_vouchers'])} voucher(s) are not balanced."
        )

    normalized = normalize_batch("TALLY_PRIME", _prepare_voucher_records(lines))
    ingested = flagged = failed = duplicates = 0
    ingested_refs: list[str] = []
    for payload, _ in normalized:
        if "error" in payload:
            failed += 1
            continue

        line = next(
            (
                item
                for item in lines
                if item["voucher_number"] == payload["ref"] and item["ledger_name"] == payload["account_name"]
            ),
            None,
        )
        payload["engagement_id"] = str(engagement.id)
        payload["source"] = source
        payload["mapped_category"] = line["mapped_category"] if line else "unmapped"
        payload["voucher_type"] = line["voucher_type"] if line else payload["type"]
        payload["signed_amount"] = line["signed_amount"] if line else payload["amount"]
        payload["debit"] = line["debit"] if line else 0.0
        payload["credit"] = line["credit"] if line else 0.0
        payload_hash = _payload_hash(payload)

        duplicate = await session.scalar(select(Transaction).where(Transaction.payload_hash == payload_hash))
        if duplicate is not None:
            duplicates += 1
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
        ingested_refs.append(str(payload.get("ref", "")))
        if payload.get("risk_flags"):
            flagged += 1

    metadata = _ensure_tally_bucket(engagement)
    imported_at = datetime.now(timezone.utc).isoformat()
    metadata[TALLY_SUMMARY_KEY]["vouchers"] = {
        "source": source,
        "imported_at": imported_at,
        "summary": {
            **summary,
            "records_ingested": ingested,
            "records_failed": failed,
            "duplicates_skipped": duplicates,
            "records_flagged": flagged,
            "ingested_refs": ingested_refs[:50],
        },
        "ledger_mappings": _build_mapping_snapshot(lines),
    }
    metadata["history"].append(
        {
            "timestamp": imported_at,
            "actor": actor_id,
            "action": "TALLY_VOUCHERS_IMPORTED",
            "source": source,
            "engagement_id": str(engagement.id),
            "records_ingested": ingested,
        }
    )
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return TallyImportResult(
        import_type="vouchers",
        source=source,
        imported_at=imported_at,
        summary=metadata[TALLY_SUMMARY_KEY]["vouchers"]["summary"],
    )


async def get_tally_summary(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
) -> dict[str, Any]:
    engagement = await _load_engagement(session, engagement_id=engagement_id, tenant_id=tenant_id)
    metadata = engagement.state_metadata or {}
    return metadata.get(TALLY_SUMMARY_KEY, {})
