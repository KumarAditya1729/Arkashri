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

logger = structlog.get_logger("worker")
settings = get_settings()

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
            return None

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

class WorkerSettings:
    """Settings used by the arq CLI to run the worker."""
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [execute_orchestration_task, send_email_task, archive_audit_task]
    max_jobs = 10
    job_timeout = 600
