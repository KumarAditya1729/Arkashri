# pyre-ignore-all-errors
"""
routers/erp_ingestion.py — ERP Integration & Sync Endpoints

Endpoints:
  POST  /erp/connections                          Register ERP connection for a tenant
  GET   /erp/connections                          List all ERP connections for tenant
  POST  /erp/connections/{id}/sync                Run ERP sync (bulk ingest)
  GET   /erp/connections/{id}/sync-logs           Last N sync logs for a connection
  GET   /erp/connections/{id}/trial-balance       Fetch live trial balance from the configured ERP
  GET   /erp/connections/{id}/chart-of-accounts   Fetch live chart of accounts from the configured ERP
"""
from __future__ import annotations

import time
import datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
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
from arkashri.services.erp_connectors import ERPConnectorError, get_connector
from arkashri.services.crypto import encrypt_dict
from arkashri.services.tally_ingestion import (
    TallyIngestionError,
    get_tally_summary,
    import_trial_balance,
    import_vouchers,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

IngestionSource = Literal["ERP_API", "CSV_UPLOAD"]

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
    records: list[dict] | None = Field(
        default=None,
        max_length=5000,
        description="Raw ERP records to sync. Omit to pull directly from the configured ERP connector.",
    )
    date_range_from: str | None = Field(None, description="YYYY-MM-DD")
    date_range_to:   str | None = Field(None, description="YYYY-MM-DD")
    jurisdiction: str = Field(default="IN")
    source: IngestionSource | None = Field(default=None, description="External ingestion source for logging and audit.")


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


class ExternalERPOut(BaseModel):
    erp_system: str
    source: str
    trial_balance: list[dict] | None = None
    accounts: list[dict] | None = None


class TallyImportRequest(BaseModel):
    connection_id: UUID | None = None
    raw_xml: str | None = Field(
        default=None,
        description="Raw Tally XML payload. Use for manual upload/testing when live connectivity is unavailable.",
    )
    from_date: str | None = Field(default=None, description="YYYY-MM-DD")
    to_date: str | None = Field(default=None, description="YYYY-MM-DD")


class TallyImportOut(BaseModel):
    import_type: str
    source: str
    imported_at: str
    summary: dict[str, Any]


class TallySummaryOut(BaseModel):
    imports: dict[str, Any]


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
    connection_id: str,
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

    records = payload.records
    source = payload.source
    if records is None:
        try:
            fetched = await get_connector(conn.erp_system).fetch_journal_entries(
                conn,
                date_range_from=payload.date_range_from,
                date_range_to=payload.date_range_to,
            )
        except ERPConnectorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        records = fetched.records
        source = fetched.source
    elif len(records) == 0:
        raise HTTPException(status_code=400, detail="At least one ERP record is required for sync.")
    elif source is None:
        source = "CSV_UPLOAD" if conn.erp_system == ERPSystem.GENERIC_CSV else "ERP_API"

    now = datetime.datetime.now(datetime.timezone.utc)
    count = len(records)
    logger.info(
        "erp_sync_requested",
        source=source,
        erp_system=conn.erp_system.value,
        connection_id=str(conn.id),
        tenant_id=auth.tenant_id,
        record_count=count,
    )

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
            records=records,
            sync_log_id=str(sync_log.id),
            source=source,
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

    normalized = normalize_batch(conn.erp_system.value, records)

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
    logger.info(
        "erp_sync_completed",
        source=source,
        erp_system=conn.erp_system.value,
        connection_id=str(conn.id),
        tenant_id=auth.tenant_id,
        records_ingested=ingested,
        records_failed=failed,
        records_flagged=flagged,
    )

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
    connection_id: str,
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


@router.get(
    "/erp/connections/{connection_id}/trial-balance",
    response_model=ExternalERPOut,
    summary="Fetch the live trial balance from the configured ERP connection",
)
async def get_trial_balance(
    connection_id: str,
    fiscal_year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> ExternalERPOut:
    conn = (await db.scalars(
        select(ERPConnection).where(
            ERPConnection.id == connection_id,
            ERPConnection.tenant_id == auth.tenant_id,
        )
    )).first()
    if not conn:
        raise HTTPException(404, "ERP connection not found.")

    try:
        payload = await get_connector(conn.erp_system).fetch_trial_balance(conn, fiscal_year=fiscal_year)
    except ERPConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExternalERPOut(**payload)


@router.get(
    "/erp/connections/{connection_id}/chart-of-accounts",
    response_model=ExternalERPOut,
    summary="Fetch the live chart of accounts from the configured ERP connection",
)
async def get_chart_of_accounts(
    connection_id: str,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> ExternalERPOut:
    conn = (await db.scalars(
        select(ERPConnection).where(
            ERPConnection.id == connection_id,
            ERPConnection.tenant_id == auth.tenant_id,
        )
    )).first()
    if not conn:
        raise HTTPException(404, "ERP connection not found.")

    try:
        payload = await get_connector(conn.erp_system).fetch_chart_of_accounts(conn)
    except ERPConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExternalERPOut(**payload)


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


@router.post(
    "/erp/engagements/{engagement_id}/tally/trial-balance/import",
    response_model=TallyImportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Import a Tally trial balance into an engagement workspace",
)
@limiter.limit("5/minute")
async def import_tally_trial_balance(
    request: Request,
    engagement_id: UUID,
    payload: TallyImportRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> TallyImportOut:
    try:
        result = await import_trial_balance(
            db,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            raw_xml=payload.raw_xml,
            connection_id=payload.connection_id,
            from_date=payload.from_date,
            to_date=payload.to_date,
        )
    except TallyIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TallyImportOut(
        import_type=result.import_type,
        source=result.source,
        imported_at=result.imported_at,
        summary=result.summary,
    )


@router.post(
    "/erp/engagements/{engagement_id}/tally/vouchers/import",
    response_model=TallyImportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Import Tally vouchers into the engagement ledger workspace",
)
@limiter.limit("5/minute")
async def import_tally_vouchers(
    request: Request,
    engagement_id: UUID,
    payload: TallyImportRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> TallyImportOut:
    try:
        result = await import_vouchers(
            db,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
            actor_id=auth.client_name,
            jurisdiction="IN",
            raw_xml=payload.raw_xml,
            connection_id=payload.connection_id,
            from_date=payload.from_date,
            to_date=payload.to_date,
        )
    except TallyIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TallyImportOut(
        import_type=result.import_type,
        source=result.source,
        imported_at=result.imported_at,
        summary=result.summary,
    )


@router.get(
    "/erp/engagements/{engagement_id}/tally/summary",
    response_model=TallySummaryOut,
    summary="Get the latest Tally import summaries and ledger mapping snapshot for an engagement",
)
async def get_engagement_tally_summary(
    engagement_id: UUID,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> TallySummaryOut:
    try:
        summary = await get_tally_summary(
            db,
            engagement_id=engagement_id,
            tenant_id=auth.tenant_id,
        )
    except TallyIngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TallySummaryOut(imports=summary)
