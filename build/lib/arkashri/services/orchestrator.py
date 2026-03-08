from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import (
    ApprovalAction,
    ApprovalActionType,
    ApprovalRequest,
    ApprovalStatus,
    AuditRun,
    AuditRunStatus,
    AuditRunStep,
    AuditStepStatus,
)
from arkashri.services.canonical import hash_object
from arkashri.services.workflow_pack import load_workflow_template

APPROVAL_ROLE_KEYWORDS = ("partner", "manager", "director", "head")

ROLE_AGENT_MAP = {
    "audit lead": "rule_linter",
    "audit manager": "override_auditor",
    "engagement partner": "incident_notary",
    "senior auditor": "forensic_replay",
    "audit pmo": "report_assembler",
    "it auditor": "schema_sentinel",
}


@dataclass
class ExecutionSummary:
    executed_steps: int
    blocked_steps: int
    pending_steps: int
    run_status: AuditRunStatus


def resolve_agent_key(owner_role: str) -> str | None:
    normalized = owner_role.strip().lower()
    if not normalized:
        return None
    for role_prefix, agent_key in ROLE_AGENT_MAP.items():
        if role_prefix in normalized:
            return agent_key
    return "coverage_guard"


def requires_approval(owner_role: str, step_data: dict) -> bool:
    """Respect absolute bypass flags set via template configurations."""
    if "requires_approval" in step_data:
        return bool(step_data["requires_approval"])
    normalized = owner_role.strip().lower()
    return any(keyword in normalized for keyword in APPROVAL_ROLE_KEYWORDS)


async def create_run_from_template(
    session: AsyncSession,
    *,
    tenant_id: str,
    jurisdiction: str,
    audit_type: str,
    created_by: str,
    input_payload: dict,
) -> AuditRun:
    template = load_workflow_template(audit_type)
    run_id = uuid.uuid4()

    run_material = {
        "run_id": str(run_id),
        "tenant_id": tenant_id,
        "jurisdiction": jurisdiction,
        "audit_type": audit_type,
        "workflow_id": template["workflow_id"],
        "workflow_version": template["version"],
        "input_payload": input_payload,
    }
    run_hash = hash_object(run_material)

    run = AuditRun(
        id=run_id,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        audit_type=audit_type,
        workflow_id=template["workflow_id"],
        workflow_version=template["version"],
        status=AuditRunStatus.READY,
        run_hash=run_hash,
        input_payload=input_payload,
        created_by=created_by,
    )
    session.add(run)
    await session.flush()

    sequence_no = 1
    for phase in template.get("phases", []):
        for step in phase.get("steps", []):
            owner_role = str(step.get("owner_role", "Audit Operator"))
            run_step = AuditRunStep(
                run_id=run.id,
                sequence_no=sequence_no,
                phase_id=str(phase["phase_id"]),
                phase_name=str(phase["name"]),
                step_id=str(step["step_id"]),
                action=str(step["action"]),
                owner_role=owner_role,
                agent_key=resolve_agent_key(owner_role),
                requires_approval=requires_approval(owner_role, step),
                status=AuditStepStatus.PENDING,
                input_payload={
                    "automation_mode": step.get("automation_mode", "deterministic_rulebook"),
                    "outputs_expected": step.get("outputs", []),
                    "evidence_expected": step.get("evidence", []),
                },
            )
            session.add(run_step)
            sequence_no += 1

    await session.flush()
    return run


async def execute_run(session: AsyncSession, run: AuditRun, *, max_steps: int = 100) -> ExecutionSummary:
    result = await session.scalars(
        select(AuditRunStep).where(AuditRunStep.run_id == run.id).order_by(AuditRunStep.sequence_no.asc())
    )
    steps = list(result)
    if not steps:
        run.status = AuditRunStatus.FAILED
        run.status_reason = "No steps available for run."
        run.completed_at = datetime.now(timezone.utc)
        session.add(run)
        return ExecutionSummary(
            executed_steps=0,
            blocked_steps=0,
            pending_steps=0,
            run_status=run.status,
        )

    executed_steps = 0
    blocked_steps = 0
    now = datetime.now(timezone.utc)

    if run.started_at is None:
        run.started_at = now

    run.status = AuditRunStatus.RUNNING

    for step in steps:
        if executed_steps >= max_steps:
            break
        if step.status == AuditStepStatus.COMPLETED:
            continue
        if step.status == AuditStepStatus.FAILED:
            run.status = AuditRunStatus.FAILED
            run.status_reason = f"Step failure: {step.phase_id}:{step.step_id}"
            break

        if step.requires_approval and await _step_requires_pending_approval(session, run, step):
            step.status = AuditStepStatus.WAITING_APPROVAL
            session.add(step)
            blocked_steps += 1
            continue

        step.status = AuditStepStatus.IN_PROGRESS
        step.started_at = step.started_at or now
        session.add(step)

        output_payload = await _build_step_output(run, step)
        step.output_payload = output_payload
        step.evidence_payload = {
            "output_hash": hash_object(output_payload),
            "evidence_hash": hash_object(
                {
                    "run_id": str(run.id),
                    "step_id": str(step.id),
                    "output_payload": output_payload,
                }
            ),
            "executed_at": now.isoformat(),
        }
        step.status = AuditStepStatus.COMPLETED
        step.completed_at = now
        session.add(step)
        executed_steps += 1

    pending_steps = int(
        await session.scalar(
            select(func.count(AuditRunStep.id)).where(
                AuditRunStep.run_id == run.id, AuditRunStep.status != AuditStepStatus.COMPLETED
            )
        )
        or 0
    )
    waiting_approvals = int(
        await session.scalar(
            select(func.count(AuditRunStep.id)).where(
                AuditRunStep.run_id == run.id,
                AuditRunStep.status == AuditStepStatus.WAITING_APPROVAL,
            )
        )
        or 0
    )

    if run.status != AuditRunStatus.FAILED:
        if pending_steps == 0:
            run.status = AuditRunStatus.COMPLETED
            run.completed_at = datetime.now(timezone.utc)
            run.status_reason = "All workflow steps completed."
            
            from arq import create_pool
            from arq.connections import RedisSettings
            from arkashri.config import get_settings
            
            conf = get_settings()
            redis_pool = await create_pool(RedisSettings.from_dsn(conf.redis_url))
            
            # Formulate the payload object to push to S3 WORM archive
            compiled_evidence = {
                step.step_id: step.evidence_payload 
                for step in steps 
                if step.status == AuditStepStatus.COMPLETED
            }
            
            await redis_pool.enqueue_job(
                "archive_audit_task",
                run_id=str(run.id),
                tenant_id=run.tenant_id,
                jurisdiction=run.jurisdiction,
                evidence_payload=compiled_evidence,
                run_hash=run.run_hash
            )

        elif waiting_approvals > 0:
            run.status = AuditRunStatus.BLOCKED
            run.status_reason = "Pending approvals required before execution can continue."
        else:
            run.status = AuditRunStatus.RUNNING
            run.status_reason = "Execution in progress."

    session.add(run)

    return ExecutionSummary(
        executed_steps=executed_steps,
        blocked_steps=blocked_steps,
        pending_steps=pending_steps,
        run_status=run.status,
    )


async def _build_step_output(run: AuditRun, step: AuditRunStep) -> dict:
    completion_time = datetime.now(timezone.utc).isoformat()
    
    automation_mode = "deterministic_rulebook"
    if isinstance(step.input_payload, dict):
        automation_mode = step.input_payload.get("automation_mode", "deterministic_rulebook")
        
    if automation_mode == "deterministic_llm":
        from arkashri.services.ai_fabric import analyze_step_evidence
        
        instruction = f"Execute action '{step.action}' for phase '{step.phase_name}'."
        evidence_data = step.input_payload.get("evidence_expected", {})
        
        ai_verdict = await analyze_step_evidence(instruction, evidence_data)
        
        return {
            "run_id": str(run.id),
            "step_ref": f"{step.phase_id}:{step.step_id}",
            "agent_key": step.agent_key,
            "automation_mode": "deterministic_llm",
            "result": ai_verdict.get("verdict", "FAIL"),
            "completion_time": completion_time,
            "ai_confidence_score": ai_verdict.get("confidence_score", 0.0),
            "notes": ai_verdict.get("reasoning", "LLM evaluation produced no reasoning string."),
            "extracted_anomalies": ai_verdict.get("extracted_anomalies", []),
        }

    return {
        "run_id": str(run.id),
        "step_ref": f"{step.phase_id}:{step.step_id}",
        "agent_key": step.agent_key,
        "automation_mode": "deterministic_rulebook",
        "result": "PASS",
        "completion_time": completion_time,
        "notes": f"Executed deterministic workflow step for {run.audit_type}.",
    }


async def _step_requires_pending_approval(session: AsyncSession, run: AuditRun, step: AuditRunStep) -> bool:
    approved_count = int(
        await session.scalar(
            select(func.count(ApprovalRequest.id)).where(
                ApprovalRequest.step_id == step.id,
                ApprovalRequest.status == ApprovalStatus.APPROVED,
            )
        )
        or 0
    )
    if approved_count > 0:
        return False

    existing_open = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.step_id == step.id,
            ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.ESCALATED)),
        )
        .order_by(ApprovalRequest.opened_at.desc())
        .limit(1)
    )
    if existing_open is not None:
        return True

    # Get connection to ARQ redis to enqueue notification emails
    from arq import create_pool
    from arq.connections import RedisSettings
    from arkashri.config import get_settings
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    request = ApprovalRequest(
        tenant_id=run.tenant_id,
        jurisdiction=run.jurisdiction,
        request_type="STEP_EXECUTION",
        reference_type="orchestration_step",
        reference_id=str(step.id),
        requested_by=run.created_by,
        reason=f"Approval required for role '{step.owner_role}' on step {step.phase_id}:{step.step_id}.",
        current_level=1,
        required_level=1,
        status=ApprovalStatus.PENDING,
        payload={
            "run_id": str(run.id),
            "step_id": str(step.id),
            "audit_type": run.audit_type,
        },
        step_id=step.id,
    )
    session.add(request)
    await session.flush()

    action = ApprovalAction(
        request_id=request.id,
        action_type=ApprovalActionType.SUBMITTED,
        actor_id=run.created_by,
        notes="Auto-created due to workflow approval gate.",
        action_payload={"origin": "orchestration_gate"},
    )
    session.add(action)

    # Dispatch target emails to the partner / auditor roles over AWS SES via ARQ
    # For now, resolving the mock recipient from the role
    mock_recipient = f"{step.owner_role.lower().replace(' ', '_')}@arkashri-demo.io"
    await redis.enqueue_job(
        "send_email_task",
        [mock_recipient],
        f"Action Required: Arkashri Audit Approval [{run.audit_type}]",
        f"Hello,\n\nYour review is required to unblock the audit '{run.audit_type}' at phase '{step.phase_id}'.\n\nLogin to the Arkashri dashboard to digitally sign this step.",
        None # Optional HTML body
    )
    await redis.close()
    return True
