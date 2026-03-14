# pyre-ignore-all-errors
import uuid
import structlog

from arq.connections import RedisSettings
from sqlalchemy import select

from arkashri.db import AsyncSessionLocal
from arkashri.models import AuditRun
from arkashri.services.orchestrator import execute_run
from arkashri.dependencies import _append_and_publish_audit
from arkashri.services.email import send_email
from arkashri.config import get_settings
from arkashri.services.archive import archive_completed_audit
from arkashri.services.erp_adapter import normalize_batch
from arkashri.models import Transaction, ERPConnection, ERPSyncLog, ERPSyncStatus

logger = structlog.get_logger("worker")
settings = get_settings()

async def worker_startup(ctx):
    logger.info("worker_startup_initializing_resources")

async def worker_shutdown(ctx):
    logger.info("worker_shutdown_draining_pools")
    try:
        from arkashri.db import engine
        await engine.dispose()
        logger.info("worker_sqlalchemy_pool_disposed")
    except Exception as e:
        logger.warning("worker_sqlalchemy_pool_dispose_failed", error=str(e))

async def execute_orchestration_task(ctx, run_id: str, max_steps: int) -> dict:
    """ARQ background task to execute an orchestration run."""
    run_uuid = uuid.UUID(run_id)
    
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=run_id, execution_mode="arq_worker")
    
    logger.info("orchestration_task_started")

    async with AsyncSessionLocal() as session:
        run = await session.scalar(select(AuditRun).where(AuditRun.id == run_uuid))
        if run is None:
            logger.error("run_not_found_during_async_execution")
            return None # type: ignore

        assert run is not None
        summary = await execute_run(session, run, max_steps=max_steps)
        await _append_and_publish_audit(
            session,
            tenant_id=run.tenant_id,
            jurisdiction=run.jurisdiction,
            event_type="ORCHESTRATION_RUN_EXECUTED",
            entity_type="audit_run",
            entity_id=str(run.id),
            payload={
                "executed_steps": summary.executed_steps,
                "blocked_steps": summary.blocked_steps,
                "pending_steps": summary.pending_steps,
                "status": summary.run_status.value,
                "execution_mode": "async_worker",
            },
        )
        await session.commit()
        result = {
            "executed_steps": summary.executed_steps,
            "blocked_steps": summary.blocked_steps,
            "pending_steps": summary.pending_steps,
            "status": summary.run_status.value,
        }

    logger.info("orchestration_task_completed", result=result)
    return result

async def send_email_task(
    ctx, 
    to_addresses: list[str], 
    subject: str, 
    body_text: str, 
    body_html: str | None = None
) -> bool:
    """ARQ background task to execute AWS SES email dispatch."""
    logger.info("send_email_task_started", to=to_addresses, subject=subject)
    result = await send_email(
        to_addresses=to_addresses,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    logger.info("send_email_task_completed", result=result)
    return result

async def archive_audit_task(
    ctx, 
    run_id: str, 
    tenant_id: str, 
    jurisdiction: str, 
    evidence_payload: dict, 
    run_hash: str
):
    """ARQ background task to execute AWS S3 untamperable archiving."""
    logger.info("worker_processing_archive", run_id=run_id)
    s3_uri = await archive_completed_audit(
        run_id=run_id,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        evidence_payload=evidence_payload,
        run_hash=run_hash
    )
    if s3_uri:
        logger.info("worker_archive_success", s3_uri=s3_uri)
    else:
        logger.warning("worker_archive_skipped_or_failed")

async def ingest_erp_batch_task(
    ctx,
    connection_id: str,
    tenant_id: str,
    jurisdiction: str,
    records: list[dict],
    sync_log_id: str,
):
    """ARQ background task to normalize and ingest ERP records."""
    logger.info("erp_ingestion_task_started", connection_id=connection_id, count=len(records))
    
    conn_uuid = uuid.UUID(connection_id)
    log_uuid = uuid.UUID(sync_log_id)
    
    import time
    from datetime import datetime, timezone
    
    t0 = time.monotonic()
    ingested: int = 0
    failed: int = 0
    flagged: int = 0
    flagged_refs: list[str] = []

    async with AsyncSessionLocal() as session:
        conn = await session.scalar(select(ERPConnection).where(ERPConnection.id == conn_uuid))
        sync_log = await session.scalar(select(ERPSyncLog).where(ERPSyncLog.id == log_uuid))
        
        if not conn or not sync_log:
            logger.error("erp_ingestion_resources_not_found")
            return

        # Normalize in worker
        normalized = normalize_batch(conn.erp_system.value, records)

        for norm_payload, payload_hash in normalized:
            if "error" in norm_payload and "PARSE_ERROR" in norm_payload.get("risk_flags", []):
                failed = failed + 1
                continue

            # Skip exact duplicates
            from arkashri.models import Transaction
            dup = await session.scalar(select(Transaction).where(Transaction.payload_hash == payload_hash))
            if dup:
                continue

            txn = Transaction(
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
                payload=norm_payload,
                payload_hash=payload_hash,
            )
            session.add(txn)
            ingested = ingested + 1

            if norm_payload.get("risk_flags"):
                flagged = flagged + 1
                flagged_refs.append(norm_payload.get("ref", ""))

        # Final status
        if ingested == 0 and failed > 0:
            final_status = ERPSyncStatus.FAILED
        elif failed > 0:
            final_status = ERPSyncStatus.PARTIAL
        else:
            final_status = ERPSyncStatus.SUCCESS

        completed_at = datetime.now(timezone.utc)
        duration_ms = int((time.monotonic() - t0) * 1000)

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

        await session.commit()
        logger.info("erp_ingestion_task_completed", ingested=ingested, failed=failed)

class WorkerSettings:
    """Settings used by the arq CLI to run the worker."""
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [execute_orchestration_task, send_email_task, archive_audit_task, ingest_erp_batch_task]
    max_jobs = 10
    job_timeout = 600
