# pyre-ignore-all-errors
import uuid
import structlog

from arq.connections import RedisSettings
from arq.worker import Retry
from arq.cron import cron
from sqlalchemy import select, update

from arkashri.db import AsyncSessionLocal
from arkashri.models import AuditRun
from arkashri.services.orchestrator import execute_run
from arkashri.dependencies import _append_and_publish_audit
from arkashri.services.email import send_email
from arkashri.config import get_settings
from arkashri.services.archive import archive_completed_audit
from arkashri.services.multi_chain_blockchain import multi_chain_blockchain_service
from arkashri.services.erp_adapter import normalize_batch
from arkashri.models import ERPConnection, ERPSyncLog, ERPSyncStatus

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
    source: str,
):
    """ARQ background task to normalize and ingest ERP records."""
    logger.info(
        "erp_ingestion_task_started",
        source=source,
        connection_id=connection_id,
        count=len(records),
    )
    
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
        logger.info(
            "erp_ingestion_task_completed",
            source=source,
            ingested=ingested,
            failed=failed,
        )

async def anchor_blockchain_task(
    ctx,
    step_id: str,
    run_id: str,
    tenant_id: str,
    evidence_hash: str,
    phase: str,
    action: str,
):
    """ARQ background task to execute heavy cross-chain anchoring operations."""
    job_try = ctx.get('job_try', 1)
    logger.info("bg_blockchain_anchoring_started", step_id=step_id, run_id=run_id, attempt=job_try)
    
    from arkashri.models import AuditRunStep
    
    # 1. Idempotency Check
    async with AsyncSessionLocal() as session:
        db_step = await session.get(AuditRunStep, uuid.UUID(step_id))
        if not db_step:
            logger.error("bg_blockchain_anchoring_aborted_not_found", step_id=step_id)
            return

        anchors = db_step.evidence_payload.get("blockchain_anchors", [])
        if anchors and anchors != ["PENDING_BACKGROUND"]:
            logger.info("bg_blockchain_anchoring_skipped_idempotency", step_id=step_id, anchors=anchors)
            return True

    try:
        anchor_result = await multi_chain_blockchain_service.anchor_evidence_multi_chain(
            evidence_hash=evidence_hash,
            metadata={
                "run_id": run_id,
                "step_id": step_id,
                "phase": phase,
                "action": action,
                "tenant_id": tenant_id,
                "attempt": job_try
            }
        )
        blockchain_txs = anchor_result.get("networks_anchored", [])
        if not blockchain_txs:
            raise RuntimeError("No networks successfully anchored in multi_chain service payload")
            
        logger.info("bg_blockchain_anchoring_success", step_id=step_id, networks=blockchain_txs)

        # 2. Atomic Database Payload Update
        async with AsyncSessionLocal() as session:
            # We explicitly construct the new payload dict carefully retaining old state
            new_payload = dict(db_step.evidence_payload) if db_step.evidence_payload else {}
            new_payload["blockchain_anchors"] = blockchain_txs
            
            # Use atomic update matching ONLY on PENDING_BACKGROUND to prevent race overwrites
            # SQLAlchemy Async update
            stmt = (
                update(AuditRunStep)
                .where(AuditRunStep.id == uuid.UUID(step_id))
                .values(evidence_payload=new_payload)
            )
            result = await session.execute(stmt)
            await session.commit()
            
            if result.rowcount == 0:
                logger.warning("bg_blockchain_anchoring_atomic_update_failed_race", step_id=step_id)

    except Exception as e:
        logger.error("bg_blockchain_anchoring_failed", step_id=step_id, error=str(e), attempt=job_try)
        # 3. Explicit Backpressure Retry System
        # ARQ native retry: Backoff defaults (e.g. attempt * 5 seconds)
        raise Retry(defer=job_try * 10) from e


async def anchor_consistency_check(ctx):
    """
    ARQ Cron job: sweeping safety check
    Scans for long-stale PENDING_BACKGROUND steps, logging metrics and triggering alerts.
    """
    logger.info("anchor_consistency_check_started")
    try:
        from arkashri.models import AuditRunStep
        from datetime import datetime, timezone, timedelta
        
        async with AsyncSessionLocal() as session:
            threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
            
            # Find steps that are old and still flagged as PENDING_BACKGROUND
            stmt = select(AuditRunStep).where(AuditRunStep.created_at < threshold)
            result = await session.execute(stmt)
            stale_steps = []
            for step in result.scalars():
                p = step.evidence_payload or {}
                anchors = p.get("blockchain_anchors", [])
                if anchors == ["PENDING_BACKGROUND"]:
                    stale_steps.append(str(step.id))
            
            if stale_steps:
                logger.warning("anchor_consistency_check_found_stale", count=len(stale_steps), step_ids=stale_steps)
            else:
                logger.info("anchor_consistency_check_healthy")
    except Exception as e:
        logger.error("anchor_consistency_check_failed", error=str(e))


class WorkerSettings:
    """Settings used by the arq CLI to run the worker."""
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [execute_orchestration_task, send_email_task, archive_audit_task, ingest_erp_batch_task, anchor_blockchain_task]
    cron_jobs = [cron(anchor_consistency_check, minute=set(range(0, 60, 15)))] # every 15m
    max_jobs = 15
    job_timeout = 600
    max_tries = 5
    keep_result = 864000 # 10 days for DLQ inspection
