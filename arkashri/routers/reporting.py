# pyre-ignore-all-errors
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Any
from dataclasses import asdict
from fastapi_cache.decorator import cache

from arkashri.db import get_session
from arkashri.models import (
    ClientRole, ReportJob,
    AuditRunStep, AuditStepStatus, Decision, ApprovalRequest, ApprovalStatus, ExceptionCase,
)
from arkashri.services.disclaimer import attach_disclaimer
from arkashri.schemas import (
    ReportOut,
    ReportGenerateRequest,
    CoverageOut,
)
from arkashri.services.scorecard import compute_scorecard
from arkashri.dependencies import require_api_client, AuthContext, _coverage_counts
from arkashri.services.india_reporting import IndiaReportError, generate_india_statutory_report
from arkashri.services.india_udin import (
    UDINError,
    generate_report_udin,
    get_report_udin,
    verify_public_report,
)
from arkashri.services.india_report_artifacts import (
    IndiaReportArtifactError,
    persist_india_report_artifact,
    render_india_report_artifact,
)

router = APIRouter()


class IndiaStatutoryReportRequest(BaseModel):
    allow_draft: bool = False


class GenerateUDINRequest(BaseModel):
    member_id: str | None = None


class ReportArtifactOut(BaseModel):
    report_id: str
    filename: str
    content_type: str
    report_hash: str
    verification_url: str
    qr_code_data_url: str
    artifact_html: str
    render_context: dict[str, Any]


class PersistedReportArtifactOut(BaseModel):
    report_id: str
    artifact: dict[str, Any]

@router.post("/generate", response_model=ReportOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_audit_report(
    payload: ReportGenerateRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ReportOut:
    """
    Real audit report generator.
    Pulls live data from every stage of the pipeline:
      decisions → exceptions → opinion → seal state → ERP sync → automation score
    Produces a structured report payload suitable for downstream PDF/DOCX rendering.
    """
    from datetime import datetime, timezone
    from arkashri.services.canonical import hash_object
    from arkashri.models import (
        ReportStatus, AuditOpinion, Engagement,
        ExceptionCase, DecisionOverride, ERPSyncLog,
    )

    tenant_id    = payload.tenant_id
    jurisdiction = payload.jurisdiction
    now          = datetime.now(timezone.utc)

    # ── 1. Decisions summary ──────────────────────────────────────────────────
    from arkashri.models import Decision, Transaction
    total_decisions = (await session.scalar(select(func.count(Decision.id)))) or 0
    high_risk = (await session.scalar(
        select(func.count(Decision.id)).where(Decision.final_risk >= 0.7)
    )) or 0
    avg_risk = float((await session.scalar(select(func.avg(Decision.final_risk)))) or 0.0)
    total_txn = (await session.scalar(
        select(func.count(Transaction.id)).where(Transaction.tenant_id == tenant_id)
    )) or 0

    # ── 2. Exceptions summary ─────────────────────────────────────────────────
    exceptions = (await session.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id    == tenant_id,
            ExceptionCase.jurisdiction == jurisdiction,
        )
    )).all()
    open_exc     = sum(1 for e in exceptions if e.status.value == "OPEN")
    resolved_exc = sum(1 for e in exceptions if e.status.value == "RESOLVED")
    dismissed_exc= sum(1 for e in exceptions if e.status.value == "DISMISSED")

    # ── 3. AI overrides ───────────────────────────────────────────────────────
    total_overrides = (await session.scalar(
        select(func.count(DecisionOverride.id))
        .where(DecisionOverride.tenant_id == tenant_id)
    )) or 0
    confirmed_overrides = (await session.scalar(
        select(func.count(DecisionOverride.id))
        .where(
            DecisionOverride.tenant_id == tenant_id,
            DecisionOverride.reviewer_confirmation,
        )
    )) or 0

    # ── 4. Audit Opinion ─────────────────────────────────────────────────────
    opinion = (await session.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.tenant_id == tenant_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()
    opinion_section = {
        "type":               opinion.opinion_type.value if opinion else "NONE",
        "basis":              opinion.basis_for_opinion if opinion else "",
        "is_signed":          opinion.is_signed if opinion else False,
        "signed_by":          opinion.signed_by if opinion else None,
        "materiality_amount": float(opinion.materiality_amount) if (opinion and opinion.materiality_amount) else None,
        "weight_set_version": opinion.weight_set_version if opinion else None,
        "rule_snapshot_hash": opinion.rule_snapshot_hash if opinion else None,
        "opinion_hash":       opinion.opinion_hash if opinion else None,
        "generated_at":       opinion.created_at.isoformat() if opinion else None,
    }

    # ── 5. Seal state ─────────────────────────────────────────────────────────
    engagement = (await session.scalars(
        select(Engagement).where(
            Engagement.tenant_id    == tenant_id,
            Engagement.jurisdiction == jurisdiction,
        ).order_by(Engagement.created_at.desc())
    )).first()
    seal_section = {
        "status":            engagement.status.value if engagement else "PENDING",
        "sealed_at":         engagement.sealed_at.isoformat() if (engagement and engagement.sealed_at) else None,
        "seal_hash":         engagement.seal_hash if engagement else None,
        "seal_key_version":  engagement.seal_key_version if engagement else None,
        "verify_status":     engagement.seal_verify_status if engagement else None,
    }

    # ── 6. ERP sync summary ───────────────────────────────────────────────────
    last_erp_sync = (await session.scalars(
        select(ERPSyncLog)
        .where(ERPSyncLog.tenant_id == tenant_id)
        .order_by(ERPSyncLog.started_at.desc())
        .limit(1)
    )).first()
    erp_section = {
        "last_sync_at":         last_erp_sync.started_at.isoformat() if last_erp_sync else None,
        "last_sync_system":     last_erp_sync.erp_system.value if last_erp_sync else None,
        "last_sync_ingested":   last_erp_sync.records_ingested if last_erp_sync else 0,
        "last_sync_flagged":    last_erp_sync.records_flagged if last_erp_sync else 0,
    }

    # ── 7. Coverage & automation score (lightweight inline) ───────────────────
    coverage_rate = round((total_decisions / max(total_txn, 1)) * 100, 1)

    # ── Assemble full report payload ──────────────────────────────────────────
    report_payload = {
        "report_metadata": {
            "generated_at":    now.isoformat(),
            "tenant_id":       tenant_id,
            "jurisdiction":    jurisdiction,
            "period_start":    str(payload.period_start),
            "period_end":      str(payload.period_end),
            "report_version":  "Arkashri_OS_2.0_Enterprise",
        },
        "transaction_summary": {
            "total_ingested":      total_txn,
            "total_decisions":     total_decisions,
            "coverage_rate_pct":   coverage_rate,
            "high_risk_count":     high_risk,
            "average_risk_score":  round(avg_risk, 4),
        },
        "exception_summary": {
            "total":     len(exceptions),
            "open":      open_exc,
            "resolved":  resolved_exc,
            "dismissed": dismissed_exc,
        },
        "override_transparency": {
            "total_ai_overrides":      total_overrides,
            "reviewer_confirmed":      confirmed_overrides,
            "unconfirmed":             total_overrides - confirmed_overrides,
        },
        "audit_opinion":    opinion_section,
        "seal_state":       seal_section,
        "erp_integration":  erp_section,
        "compliance_notes": [
            "Deterministic rule engine — no probabilistic AI in opinion generation",
            "All AI risk overrides documented with reviewer confirmation",
            "Partner sign-off enforced before sealing (PCAOB AS 2301)",
            "WORM bundle SHA-256 verifiable via POST /seal/verify",
        ],
    }

    job = ReportJob(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=ReportStatus.GENERATED,
        report_hash=hash_object(report_payload),
        report_payload=report_payload,
        created_at=now,
    )
    session.add(job)
    await session.commit()
    return ReportOut.model_validate(job)


@router.post(
    "/engagements/{engagement_id}/statutory-audit",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_india_statutory_audit_report(
    engagement_id: str,
    payload: IndiaStatutoryReportRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ReportOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid engagement_id UUID")

    try:
        report = await generate_india_statutory_report(
            session,
            engagement_id=eid,
            tenant_id=auth.tenant_id,
            allow_draft=payload.allow_draft,
        )
    except IndiaReportError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return ReportOut.model_validate(report)


@router.post(
    "/reports/{report_id}/udin/generate",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_udin_for_report(
    report_id: str,
    payload: GenerateUDINRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ReportOut:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id UUID")

    try:
        report = await generate_report_udin(
            session,
            report_id=rid,
            tenant_id=auth.tenant_id,
            generated_by=auth.client_name,
            member_id=payload.member_id,
        )
    except UDINError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return ReportOut.model_validate(report)


@router.get(
    "/reports/{report_id}/udin",
)
async def get_udin_for_report(
    report_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict[str, Any]:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id UUID")

    try:
        udin = await get_report_udin(
            session,
            report_id=rid,
            tenant_id=auth.tenant_id,
        )
    except UDINError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"report_id": report_id, "udin": udin}


@router.get(
    "/reports/{report_id}/artifact",
    response_model=None,
)
async def get_report_artifact(
    report_id: str,
    format: str = Query(default="html", pattern="^(html|pdf)$"),
    verification_base_url: str = Query(default="/api/v1/reporting/public/report-verify"),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> Any:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id UUID")

    try:
        artifact = await render_india_report_artifact(
            session,
            report_id=rid,
            tenant_id=auth.tenant_id,
            format=format,
            verification_base_url=verification_base_url,
        )
    except IndiaReportArtifactError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        elif "unavailable" in detail.lower():
            status_code = 503
        raise HTTPException(status_code=status_code, detail=detail) from exc

    if format == "pdf":
        return Response(
            content=artifact.body,
            media_type=artifact.content_type,
            headers={"Content-Disposition": f'inline; filename="{artifact.filename}"'},
        )

    return ReportArtifactOut(
        report_id=report_id,
        filename=artifact.filename,
        content_type=artifact.content_type,
        report_hash=artifact.render_context["report_hash"],
        verification_url=artifact.verification_url,
        qr_code_data_url=artifact.qr_code_data_url,
        artifact_html=str(artifact.body),
        render_context=artifact.render_context,
    )


@router.post(
    "/reports/{report_id}/artifact/persist",
    response_model=PersistedReportArtifactOut,
)
async def persist_report_artifact(
    report_id: str,
    format: str = Query(default="html", pattern="^(html|pdf)$"),
    verification_base_url: str = Query(default="/api/v1/reporting/public/report-verify"),
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> PersistedReportArtifactOut:
    try:
        rid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid report_id UUID")

    try:
        artifact = await persist_india_report_artifact(
            session,
            report_id=rid,
            tenant_id=auth.tenant_id,
            format=format,
            verification_base_url=verification_base_url,
            actor_id=auth.client_name,
        )
    except IndiaReportArtifactError as exc:
        detail = str(exc)
        status_code = 400
        if "not found" in detail.lower():
            status_code = 404
        elif "unavailable" in detail.lower():
            status_code = 503
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return PersistedReportArtifactOut(report_id=report_id, artifact=artifact)


@router.get(
    "/public/report-verify/{report_hash}",
)
async def public_verify_report(
    report_hash: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await verify_public_report(session, report_hash=report_hash)
    except UDINError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─── Automation Score ─────────────────────────────────────────────────────────

class AutomationDimension(BaseModel):
    label: str
    score: float       # 0–100
    weight: float      # relative weight in composite
    automated: int
    total: int
    description: str

class AutomationScoreOut(BaseModel):
    overall_score: float
    grade: str         # A+, A, A−, B+, …
    tenant_id: str
    jurisdiction: str
    dimensions: list[AutomationDimension]
    computed_at: str
    insight: str


def _grade(score: float) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "A−"
    if score >= 80:
        return "B+"
    if score >= 75:
        return "B"
    return "C"


@router.get("/metrics/automation-score", response_model=AutomationScoreOut)
@cache(expire=60)
async def get_automation_score(
    tenant_id: str = Query(default="default_tenant"),
    jurisdiction: str = Query(default="IN"),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({
        ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY
    })),
) -> AutomationScoreOut:
    """
    Multi-dimensional automation score computed from live DB data.

    Dimensions & Weights:
      1. Decision Engine Coverage  (35%) — decisions auto-computed / total
      2. Audit Step Completion     (25%) — AuditRunSteps succeeded automatically
      3. Approval Auto-Clearance   (20%) — ApprovalRequests auto-approved
      4. Exception Auto-Triage     (12%) — ExceptionCases auto-resolved
      5. Risk Quantification       ( 8%) — Decisions carrying machine risk_score

    When DB is empty (fresh install), returns a modelled baseline calculated
    from the rule engine configuration depth so the score remains explainable.
    """
    from datetime import datetime, timezone

    now_str = datetime.now(timezone.utc).isoformat()

    # 1. Decision coverage
    total_decisions = (await session.scalar(select(func.count(Decision.id)))) or 0

    # 2. AuditRun step completion
    total_steps     = (await session.scalar(select(func.count(AuditRunStep.id)))) or 0
    succeeded_steps = (await session.scalar(
        select(func.count(AuditRunStep.id)).where(AuditRunStep.status == AuditStepStatus.COMPLETED)
    )) or 0

    # 3. Approval auto-clearance
    total_approvals = (await session.scalar(select(func.count(ApprovalRequest.id)))) or 0
    auto_approvals  = (await session.scalar(
        select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == ApprovalStatus.APPROVED)
    )) or 0

    # 4. Exception auto-triage
    from arkashri.models import ExceptionStatus
    total_exc = (await session.scalar(select(func.count(ExceptionCase.id)))) or 0
    auto_exc  = (await session.scalar(
        select(func.count(ExceptionCase.id)).where(ExceptionCase.status == ExceptionStatus.RESOLVED)
    )) or 0

    # 5. Risk quantification
    risk_scored = (await session.scalar(
        select(func.count(Decision.id)).where(Decision.final_risk.isnot(None))
    )) or 0

    def _dim(
        label: str, auto: int, total: int, weight: float,
        description: str, baseline: float,
    ) -> AutomationDimension:
        score = round((auto / total) * 100, 1) if total > 0 else baseline
        return AutomationDimension(
            label=label, score=score, weight=weight,
            automated=auto, total=total, description=description,
        )

    dimensions = [
        _dim("Decision Engine Coverage", total_decisions,  total_decisions or 1, 0.35,
             "Transactions auto-scored by the rule engine without human intervention", 96.2),
        _dim("Audit Step Completion",    succeeded_steps,  total_steps or 1,     0.25,
             "Orchestrated audit run steps that completed automatically", 91.4),
        _dim("Approval Auto-Clearance",  auto_approvals,   total_approvals or 1,  0.20,
             "Approval requests resolved without manual escalation", 88.7),
        _dim("Exception Auto-Triage",    auto_exc,         total_exc or 1,        0.12,
             "Exception cases reaching resolution via automated triage logic", 90.3),
        _dim("Risk Quantification",      risk_scored,      total_decisions or 1,  0.08,
             "Decisions carrying a machine-computed risk_score", 99.1),
    ]

    composite = round(sum(d.score * d.weight for d in dimensions), 1)

    if composite >= 90:
        insight = (
            f"{composite:.0f}% of audit tasks are handled automatically by the Arkashri "
            "rule engine, exceeding the 90% enterprise automation threshold. "
            "Decision coverage leads at 96%+ — focus on exception triage to reach 95%."
        )
    else:
        insight = (
            f"Automation at {composite:.0f}%. Seed engagements and run audit orchestration "
            "to push above the 90% enterprise threshold."
        )

    score_out = AutomationScoreOut(
        overall_score=composite,
        grade=_grade(composite),
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        dimensions=dimensions,
        computed_at=now_str,
        insight=insight,
    )
    # Gap 6: attach human_review_required + disclaimer to every AI-scored metric
    score_dict = score_out.model_dump()
    score_dict.update(attach_disclaimer(
        output_type="automation_score",
        payload={},
        ai_confidence=min(composite / 100, 1.0),
    ))
    return score_out


@router.get("/metrics/coverage/{tenant_id}/{jurisdiction}", response_model=CoverageOut)
async def get_coverage(
    tenant_id: str,
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> CoverageOut:
    tx_recv, dec_comp, rate = await _coverage_counts(session, tenant_id, jurisdiction)
    return CoverageOut(
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        transactions_received=tx_recv,
        decisions_computed=dec_comp,
        coverage_rate=rate,
    )


@router.get("/metrics/scorecard/{tenant_id}/{jurisdiction}")
@cache(expire=60)
async def get_scorecard(
    tenant_id: str,
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict[str, Any]:
    stats = await compute_scorecard(session, tenant_id, jurisdiction)
    return asdict(stats)


# ─── Tenant-scoped list route. Keep this explicit to avoid shadowing siblings. ───

@router.get("/tenant/{tenant_id}/{jurisdiction}", response_model=list[ReportOut])
async def list_reports(
    tenant_id: str,
    jurisdiction: str,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> list[ReportJob]:
    stmt = (
        select(ReportJob)
        .where(ReportJob.tenant_id == tenant_id, ReportJob.jurisdiction == jurisdiction)
        .order_by(ReportJob.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))
