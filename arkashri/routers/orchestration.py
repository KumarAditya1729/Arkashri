# pyre-ignore-all-errors
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from arkashri.db import get_session
from arkashri.models import ClientRole, AuditRun
from arkashri.schemas import (
    OrchestrationRunCreate,
    OrchestrationRunOut,
    OrchestrationExecuteRequest,
    OrchestrationExecuteResponse,
)
from arkashri.services.orchestrator import create_run_from_template
from arkashri.dependencies import require_api_client, AuthContext, _append_and_publish_audit, _load_run_with_steps

router = APIRouter()


@router.post("/runs", response_model=OrchestrationRunOut, status_code=status.HTTP_201_CREATED)
async def create_orchestration_run(
    payload: OrchestrationRunCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> AuditRun:
    if payload.created_by != auth.client_name:
        raise HTTPException(status_code=403, detail="created_by must match authenticated API client")
    try:
        run = await create_run_from_template(
            session,
            tenant_id=payload.tenant_id,
            jurisdiction=payload.jurisdiction,
            audit_type=payload.audit_type,
            created_by=payload.created_by,
            input_payload=payload.input_payload,
        )
        await _append_and_publish_audit(
            session,
            tenant_id=payload.tenant_id,
            jurisdiction=payload.jurisdiction,
            event_type="ORCHESTRATION_RUN_CREATED",
            entity_type="audit_run",
            entity_id=str(run.id),
            payload={
                "audit_type": run.audit_type,
                "workflow_id": run.workflow_id,
                "workflow_version": run.workflow_version,
                "run_hash": run.run_hash,
            },
        )

        if payload.auto_execute:
            redis = request.app.state.redis_pool
            await redis.enqueue_job(
                "execute_orchestration_task", 
                run_id=str(run.id), 
                max_steps=500
            )

        await session.commit()
        stored = await _load_run_with_steps(session, run.id)
        if stored is None:
            raise HTTPException(status_code=500, detail="Failed to load orchestration run after creation")
        return stored
    except KeyError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Duplicate orchestration run hash") from exc
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{tenant_id}/{jurisdiction}", response_model=list[OrchestrationRunOut])
async def list_orchestration_runs(
    tenant_id: str,
    jurisdiction: str,
    limit: int = Query(default=20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> list[AuditRun]:
    run_ids = list(
        await session.scalars(
            select(AuditRun.id)
            .where(AuditRun.tenant_id == tenant_id, AuditRun.jurisdiction == jurisdiction)
            .order_by(AuditRun.created_at.desc())
            .limit(limit)
        )
    )
    runs: list[AuditRun] = []
    for run_id in run_ids:
        run = await _load_run_with_steps(session, run_id)
        if run is not None:
            runs.append(run)
    return runs


@router.get("/run/{run_id}", response_model=OrchestrationRunOut)
async def get_orchestration_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(
        require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})
    ),
) -> AuditRun:
    run = await _load_run_with_steps(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Orchestration run not found")
    return run


@router.post("/run/{run_id}/execute", response_model=OrchestrationExecuteResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_orchestration_run(
    run_id: uuid.UUID,
    payload: OrchestrationExecuteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> OrchestrationExecuteResponse:
    run = await session.scalar(select(AuditRun).where(AuditRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Orchestration run not found")

    redis = request.app.state.redis_pool
    job = await redis.enqueue_job(
        "execute_orchestration_task", 
        run_id=str(run.id), 
        max_steps=payload.max_steps
    )

    return OrchestrationExecuteResponse(
        run_id=run.id,
        job_id=job.job_id if job else None,
        status=run.status,
    )

@router.get("/runs/{run_id}/report")
async def fetch_audit_report(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY}))
):
    """Generates and downloads a legally formatted PDF Report for a completed Audit."""
    from fastapi.responses import Response
    from arkashri.services.report import generate_pdf_report
    
    try:
        run_uuid = uuid.UUID(run_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
        
    stored = await _load_run_with_steps(session, run_uuid)
    if not stored:
        raise HTTPException(status_code=404, detail="Run not found")
        
    run_dict = {
        "id": str(stored.id),
        "tenant_id": stored.tenant_id,
        "jurisdiction": stored.jurisdiction,
        "audit_type": stored.audit_type,
        "status": stored.status.value,
        "completed_at": stored.completed_at.isoformat() if stored.completed_at else None,
        "run_hash": stored.run_hash,
    }
    
    steps_list = [
        {
            "phase_id": step.phase_id,
            "step_id": step.step_id,
            "action": step.action,
            "evidence_payload": step.evidence_payload if isinstance(step.evidence_payload, dict) else {},
        }
        for step in stored.steps
    ]
    
    try:
        pdf_bytes = generate_pdf_report(run_dict, steps_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
        
    return Response(
        content=pdf_bytes, 
        media_type="application/pdf", 
        headers={"Content-Disposition": f'attachment; filename="audit_report_{run_id}.pdf"'}
    )
