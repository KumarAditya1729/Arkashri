# pyre-ignore-all-errors
"""
routers/erp_ingestion.py — ERP Integration & Sync Endpoints

Endpoints:
  POST  /erp/connections                          Register ERP connection for a tenant
  GET   /erp/connections                          List all ERP connections for tenant
  POST  /erp/connections/{id}/sync                Run ERP sync (bulk ingest)
  GET   /erp/connections/{id}/sync-logs           Last N sync logs for a connection

  POST  /mock/erp/{system}/trial-balance          Mock ERP trial balance extract
  POST  /mock/erp/{system}/journal-entries        Mock ERP journal entry batch
  GET   /mock/erp/{system}/chart-of-accounts      Mock chart of accounts

All mock endpoints return realistic-looking data for each ERP system
so the integration can be demoed without a live ERP instance.
"""

import time
import uuid
import datetime
import random
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.db import get_session
from arkashri.models import (
    Transaction,
    ERPConnection, ERPSyncLog, ERPSystem, ERPSyncStatus,
    ClientRole,
)
from arkashri.dependencies import require_api_client, AuthContext, limiter
from arkashri.services.erp_adapter import normalize_batch
from arkashri.services.crypto import encrypt_dict

router = APIRouter()

ERPSystemLiteral = Literal[
    "SAP_S4HANA", "ORACLE_FUSION", "TALLY_PRIME", "ZOHO_BOOKS", "QUICKBOOKS", "GENERIC_CSV"
]

# ─── Schemas ─────────────────────────────────────────────────────────────────

class CreateConnectionRequest(BaseModel):
    erp_system: ERPSystem
    display_name: str = Field(..., min_length=1, max_length=255)
    connection_config: dict = Field(default_factory=dict, description="Encrypted credentials / endpoint config")
    is_active: bool = True


class ConnectionOut(BaseModel):
    id: str
    tenant_id: str
    erp_system: str
    display_name: str
    is_active: bool
    last_synced_at: str | None
    last_sync_status: str
    sync_count: int
    total_records_ingested: int
    created_at: str


class SyncRequest(BaseModel):
    records: list[dict] = Field(..., min_length=1, max_length=5000,
        description="Raw ERP records to sync (already extracted from ERP API)")
    date_range_from: str | None = Field(None, description="YYYY-MM-DD")
    date_range_to:   str | None = Field(None, description="YYYY-MM-DD")
    jurisdiction: str = Field(default="IN")


class SyncResult(BaseModel):
    sync_log_id: str
    erp_system: str
    status: str
    records_submitted: int
    records_ingested: int
    records_failed: int
    records_flagged: int
    sync_duration_ms: int
    flagged_refs: list[str]


class SyncLogOut(BaseModel):
    id: str
    erp_system: str
    status: str
    records_submitted: int
    records_ingested: int
    records_failed: int
    records_flagged: int
    sync_duration_ms: int | None
    date_range_from: str | None
    date_range_to:   str | None
    started_at: str
    completed_at: str | None


# ─── 1. Register ERP Connection ───────────────────────────────────────────────

@router.post(
    "/erp/connections",
    response_model=ConnectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new ERP connection for a tenant",
)
async def create_connection(
    payload: CreateConnectionRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN})),
) -> ConnectionOut:
    tenant_id = auth.tenant_id

    # Prevent duplicate active connection for same ERP system
    existing = (await db.scalars(
        select(ERPConnection).where(
            ERPConnection.tenant_id == tenant_id,
            ERPConnection.erp_system == payload.erp_system,
            ERPConnection.is_active,
        )
    )).first()
    if existing:
        raise HTTPException(
            409,
            f"Active {payload.erp_system.value} connection already exists for this tenant. "
            "Deactivate it before registering a new one."
        )

    conn = ERPConnection(
        tenant_id=tenant_id,
        erp_system=payload.erp_system,
        display_name=payload.display_name,
        is_active=payload.is_active,
        connection_config={"aes_gcm_payload": encrypt_dict(payload.connection_config)},
        last_sync_status=ERPSyncStatus.IDLE,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _conn_out(conn)


# ─── 2. List ERP Connections ──────────────────────────────────────────────────

@router.get(
    "/erp/connections",
    response_model=list[ConnectionOut],
    summary="List all ERP connections for the tenant",
)
async def list_connections(
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> list[ConnectionOut]:
    conns = (await db.scalars(
        select(ERPConnection)
        .where(ERPConnection.tenant_id == auth.tenant_id)
        .order_by(ERPConnection.erp_system)
    )).all()
    return [_conn_out(c) for c in conns]


# ─── 3. Run ERP Sync (Bulk Ingest) ───────────────────────────────────────────

@router.post(
    "/erp/connections/{connection_id}/sync",
    response_model=SyncResult,
    summary="Sync a batch of raw ERP records → normalize → ingest into financial_transaction",
)
@limiter.limit("2/minute")
async def run_erp_sync(
    request: Request,
    connection_id: uuid.UUID,
    payload: SyncRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> SyncResult:
    conn = (await db.scalars(
        select(ERPConnection).where(
            ERPConnection.id == connection_id,
            ERPConnection.tenant_id == auth.tenant_id,
        )
    )).first()
    if not conn:
        raise HTTPException(404, "ERP connection not found.")
    if not conn.is_active:
        raise HTTPException(409, "ERP connection is inactive.")

    now = datetime.datetime.now(datetime.timezone.utc)
    count = len(payload.records)

    sync_log = ERPSyncLog(
        connection_id=connection_id,
        tenant_id=auth.tenant_id,
        erp_system=conn.erp_system,
        status=ERPSyncStatus.RUNNING,
        records_submitted=count,
        date_range_from=payload.date_range_from,
        date_range_to=payload.date_range_to,
        started_at=now,
    )
    db.add(sync_log)
    await db.commit()
    await db.refresh(sync_log)

    # If large batch (> 100), offload to ARQ worker
    if count > 100 and request.app.state.redis_pool:
        await request.app.state.redis_pool.enqueue_job(
            "ingest_erp_batch_task",
            connection_id=str(connection_id),
            tenant_id=auth.tenant_id,
            jurisdiction=payload.jurisdiction,
            records=payload.records,
            sync_log_id=str(sync_log.id),
        )
        return SyncResult(
            sync_log_id=str(sync_log.id),
            erp_system=conn.erp_system.value,
            status="ACCEPTED",
            records_submitted=count,
            records_ingested=0,
            records_failed=0,
            records_flagged=0,
            sync_duration_ms=0,
            flagged_refs=[],
        )

    # Otherwise, process synchronously (same logic as before)
    t0 = time.monotonic()
    ingested = failed = flagged = 0
    flagged_refs: list[str] = []

    normalized = normalize_batch(conn.erp_system.value, payload.records)

    for norm_payload, payload_hash in normalized:
        if "error" in norm_payload and "PARSE_ERROR" in norm_payload.get("risk_flags", []):
            failed += 1
            continue

        dup = (await db.scalars(
            select(Transaction).where(Transaction.payload_hash == payload_hash)
        )).first()
        if dup:
            continue

        txn = Transaction(
            tenant_id=auth.tenant_id,
            jurisdiction=payload.jurisdiction,
            payload=norm_payload,
            payload_hash=payload_hash,
        )
        db.add(txn)
        ingested += 1

        if norm_payload.get("risk_flags"):
            flagged += 1
            flagged_refs.append(norm_payload.get("ref", ""))

    if ingested == 0 and failed > 0:
        final_status = ERPSyncStatus.FAILED
    elif failed > 0:
        final_status = ERPSyncStatus.PARTIAL
    else:
        final_status = ERPSyncStatus.SUCCESS

    completed_at = datetime.datetime.now(datetime.timezone.utc)
    duration_ms  = int((time.monotonic() - t0) * 1000)

    sync_log.status = final_status
    sync_log.records_ingested = ingested
    sync_log.records_failed = failed
    sync_log.records_flagged = flagged
    sync_log.sync_duration_ms = duration_ms
    sync_log.completed_at = completed_at

    conn.last_synced_at = completed_at
    conn.last_sync_status = final_status
    conn.sync_count += 1
    conn.total_records_ingested += ingested

    db.add(sync_log)
    db.add(conn)
    await db.commit()

    return SyncResult(
        sync_log_id=str(sync_log.id),
        erp_system=conn.erp_system.value,
        status=final_status.value,
        records_submitted=count,
        records_ingested=ingested,
        records_failed=failed,
        records_flagged=flagged,
        sync_duration_ms=duration_ms,
        flagged_refs=flagged_refs[:50],
    )


# ─── 4. Sync Logs ─────────────────────────────────────────────────────────────

@router.get(
    "/erp/connections/{connection_id}/sync-logs",
    response_model=list[SyncLogOut],
    summary="Last N sync logs for an ERP connection",
)
async def get_sync_logs(
    connection_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> list[SyncLogOut]:
    logs = (await db.scalars(
        select(ERPSyncLog)
        .where(
            ERPSyncLog.connection_id == connection_id,
            ERPSyncLog.tenant_id == auth.tenant_id,
        )
        .order_by(ERPSyncLog.started_at.desc())
        .limit(limit)
    )).all()
    return [_log_out(log) for log in logs]


# ─── 5. Mock ERP Endpoints ────────────────────────────────────────────────────
# These return realistic mock data per ERP system.
# Remove in production — replace with live ERP API calls.

_MOCK_ACCOUNTS = {
    "SAP_S4HANA": [
        {"HKONT": "100000", "TXT50": "Cash and Bank", "type": "ASSET"},
        {"HKONT": "200000", "TXT50": "Trade Payables", "type": "LIABILITY"},
        {"HKONT": "400000", "TXT50": "Revenue - Products", "type": "REVENUE"},
        {"HKONT": "500000", "TXT50": "Cost of Goods Sold", "type": "EXPENSE"},
        {"HKONT": "600000", "TXT50": "Operating Expenses", "type": "EXPENSE"},
    ],
    "ORACLE_FUSION": [
        {"CodeCombinationId": "01.1000", "AccountName": "Cash", "type": "ASSET"},
        {"CodeCombinationId": "01.2000", "AccountName": "Accounts Payable", "type": "LIABILITY"},
        {"CodeCombinationId": "01.4000", "AccountName": "Revenue", "type": "REVENUE"},
    ],
    "TALLY_PRIME": [
        {"LEDGERNAME": "Bank Account", "GROUPNAME": "Bank Accounts"},
        {"LEDGERNAME": "Sundry Creditors", "GROUPNAME": "Sundry Creditors"},
        {"LEDGERNAME": "Sales Account", "GROUPNAME": "Sales Accounts"},
        {"LEDGERNAME": "Purchase Account", "GROUPNAME": "Purchase Accounts"},
    ],
    "ZOHO_BOOKS": [
        {"account_id": "460000000000348", "account_name": "Cash", "account_type": "cash"},
        {"account_id": "460000000000352", "account_name": "Accounts Receivable", "account_type": "accounts_receivable"},
    ],
    "QUICKBOOKS": [
        {"Id": "35", "Name": "Checking", "AccountType": "Bank"},
        {"Id": "33", "Name": "Accounts Payable", "AccountType": "Accounts Payable"},
    ],
    "GENERIC_CSV": [
        {"account_code": "1001", "account_name": "Cash"},
        {"account_code": "2001", "account_name": "Payables"},
    ],
}

def _mock_sap_entry(i: int) -> dict:
    amounts = [12500.00, 87430.50, 230000.00, 5000.00, 450000.00, 100000.00]
    return {
        "BELNR": f"5100{i:05d}", "BUDAT": f"2026-01-{(i % 28) + 1:02d}",
        "HKONT": random.choice(["100000", "200000", "400000", "500000"]),
        "TXT50": "Operating Account", "DMBTR": random.choice(amounts),
        "SHKZG": random.choice(["S", "S", "H"]),
        "WAERS": "INR", "SGTXT": f"SAP Auto-posting {i}",
        "NAME1": random.choice(["Infosys Ltd", "TCS Ltd", "Wipro Ltd", "HCL Tech"]),
        "LIFNR": f"V{i:05d}", "MWSKZ": "A1", "KOSTL": f"CC{100 + (i % 5)}",
    }

def _mock_oracle_entry(i: int) -> dict:
    amounts = [8750.00, 145000.75, 22000.00, 680000.00]
    dr = random.choice([True, False])
    amt = random.choice(amounts)
    return {
        "JournalEntryLineId": f"ORA-{i:06d}",
        "AccountedDate": f"2026-01-{(i % 28) + 1:02d}",
        "CodeCombinationId": random.choice(["01.1000", "01.2000", "01.4000"]),
        "AccountName": "GL Account", "CurrencyCode": "USD",
        "AcctdDr": amt if dr else 0.0, "AcctdCr": 0.0 if dr else amt,
        "PartyName": random.choice(["Oracle Corp", "Deloitte", "EY", "PwC"]),
        "PartyId": f"P{i:05d}", "Description": f"Oracle journal {i}",
    }

def _mock_tally_entry(i: int) -> dict:
    amounts = [50000.00, 100000.00, 250000.00, 75000.00, 1000000.00]
    vtype = random.choice(["Payment", "Receipt", "Journal", "Purchase"])
    return {
        "VOUCHERNUMBER": f"PV-2026-{i:05d}", "VOUCHERTYPE": vtype,
        "DATE": f"20260{(i % 3) + 1}{(i % 28) + 1:02d}",
        "LEDGERNAME": random.choice(["Bank Account", "Sundry Creditors", "Sales Account"]),
        "PARTYLEDGERNAME": random.choice(["Reliance Ind", "HDFC Ltd", "TCS", "Infosys"]),
        "AMOUNT": random.choice(amounts), "NARRATION": f"Tally voucher {i}",
        "GSTREGISTRATIONNUMBER": f"27AABCT{i:04d}Q1Z{i % 9}",
        "CURRENCY": "INR",
    }

def _mock_zoho_entry(i: int) -> dict:
    amounts = [4200.00, 18900.50, 75000.00, 230000.00]
    return {
        "journal_id": f"J-{i:06d}",
        "date": f"2026-01-{(i % 28) + 1:02d}",
        "reference_number": f"ZB-REF-{i:05d}",
        "debit_or_credit": random.choice(["debit", "credit"]),
        "amount": random.choice(amounts), "currency_code": "INR",
        "account_id": random.choice(["460000000000348", "460000000000352"]),
        "account_name": "Operating Account",
        "vendor_name": random.choice(["Zoho Corp", "Freshworks", "BrowserStack"]),
        "vendor_id": f"ZV{i:04d}",
        "notes": f"Zoho journal entry {i}", "tax_id": f"GST-{i:04d}",
    }

def _mock_qbo_entry(i: int) -> dict:
    amounts = [1250.00, 42000.00, 8900.75, 175000.00]
    posting = random.choice(["Debit", "Credit"])
    return {
        "Id": str(i), "TxnDate": f"2026-01-{(i % 28) + 1:02d}",
        "Amount": random.choice(amounts),
        "JournalEntryLineDetail": {
            "PostingType": posting,
            "AccountRef": {"value": random.choice(["35", "33"]), "name": "Checking"},
            "Entity": {"name": random.choice(["Intuit Inc", "Stripe", "Shopify"]), "type": "CUSTOMER"},
            "ClassRef": {"name": "Operations"},
        },
        "CurrencyRef": {"value": "USD"},
        "Description": f"QBO transaction {i}",
    }

_MOCK_GENERATORS = {
    "SAP_S4HANA":    _mock_sap_entry,
    "ORACLE_FUSION": _mock_oracle_entry,
    "TALLY_PRIME":   _mock_tally_entry,
    "ZOHO_BOOKS":    _mock_zoho_entry,
    "QUICKBOOKS":    _mock_qbo_entry,
}


@router.post(
    "/mock/erp/{system}/journal-entries",
    summary="[MOCK] Generate realistic ERP journal entries for the given system",
    tags=["Mock ERP Data"],
)
async def mock_journal_entries(
    system: ERPSystemLiteral = Path(...),
    count: int = Query(default=20, ge=1, le=200, description="Number of entries to generate"),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    """
    Returns simulated journal entries in the native format of the given ERP.
    Feed these directly into POST /erp/connections/{id}/sync to test the pipeline.
    """
    generator = _MOCK_GENERATORS.get(system)
    if not generator:
        # GENERIC_CSV has no dedicated generator
        entries = [
            {
                "ref": f"CSV-{i:05d}", "date": f"2026-01-{(i % 28) + 1:02d}",
                "amount": round(random.uniform(1000, 500000), 2),
                "type": random.choice(["DEBIT", "CREDIT"]),
                "account_code": f"ACC{i % 10:03d}", "account_name": "General Account",
                "entity": "Unknown Entity", "description": f"CSV row {i}",
                "currency": "INR",
            }
            for i in range(1, count + 1)
        ]
    else:
        entries = [generator(i) for i in range(1, count + 1)]

    return {
        "erp_system": system,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "count": len(entries),
        "entries": entries,
        "note": "MOCK DATA — safe to ingest via POST /erp/connections/{id}/sync",
    }


@router.post(
    "/mock/erp/{system}/trial-balance",
    summary="[MOCK] Generate a trial balance extract for the given ERP system",
    tags=["Mock ERP Data"],
)
async def mock_trial_balance(
    system: ERPSystemLiteral = Path(...),
    fiscal_year: int = Query(default=2025),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    accounts = _MOCK_ACCOUNTS.get(system, _MOCK_ACCOUNTS["GENERIC_CSV"])
    tb_lines = []
    for acct in accounts:
        debit  = round(random.uniform(100000, 5000000), 2)
        credit = round(random.uniform(100000, 5000000), 2)
        tb_lines.append({
            **acct,
            "fiscal_year":    fiscal_year,
            "period":         "12",
            "debit_balance":  debit,
            "credit_balance": credit,
            "net_balance":    round(debit - credit, 2),
            "currency":       "INR" if system in ("SAP_S4HANA", "TALLY_PRIME") else "USD",
        })
    return {
        "erp_system":    system,
        "fiscal_year":   fiscal_year,
        "generated_at":  datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_accounts": len(tb_lines),
        "trial_balance": tb_lines,
        "note": "MOCK DATA",
    }


@router.get(
    "/mock/erp/{system}/chart-of-accounts",
    summary="[MOCK] Return the chart of accounts for the given ERP system",
    tags=["Mock ERP Data"],
)
async def mock_chart_of_accounts(
    system: ERPSystemLiteral = Path(...),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> dict:
    accounts = _MOCK_ACCOUNTS.get(system, _MOCK_ACCOUNTS["GENERIC_CSV"])
    return {
        "erp_system":  system,
        "fetched_at":  datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "account_count": len(accounts),
        "accounts":    accounts,
        "note": "MOCK DATA",
    }


# ─── Serialisation helpers ────────────────────────────────────────────────────

def _conn_out(c: ERPConnection) -> ConnectionOut:
    return ConnectionOut(
        id=str(c.id),
        tenant_id=c.tenant_id,
        erp_system=c.erp_system.value,
        display_name=c.display_name,
        is_active=c.is_active,
        last_synced_at=c.last_synced_at.isoformat() if c.last_synced_at else None,
        last_sync_status=c.last_sync_status.value,
        sync_count=c.sync_count,
        total_records_ingested=c.total_records_ingested,
        created_at=c.created_at.isoformat(),
    )


def _log_out(log: ERPSyncLog) -> SyncLogOut:
    return SyncLogOut(
        id=str(log.id),
        erp_system=log.erp_system.value,
        status=log.status.value,
        records_submitted=log.records_submitted,
        records_ingested=log.records_ingested,
        records_failed=log.records_failed,
        records_flagged=log.records_flagged,
        sync_duration_ms=log.sync_duration_ms,
        date_range_from=log.date_range_from,
        date_range_to=log.date_range_to,
        started_at=log.started_at.isoformat(),
        completed_at=log.completed_at.isoformat() if log.completed_at else None,
    )
