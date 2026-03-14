# pyre-ignore-all-errors

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole
from arkashri.schemas import (
    CrisisEventCreate,
    CrisisEventOut,
    ContinuousAuditRuleCreate,
    ContinuousAuditRuleOut,
    ForensicInvestigationCreate,
    ForensicInvestigationOut,
    ESGMetricCreate,
    ESGMetricOut,
    AIGovernanceLogCreate,
    AIGovernanceLogOut,
    SovereignArchiveCreate,
    SovereignArchiveOut,
)
from arkashri.services.usas import (
    trigger_crisis_event,
    create_continuous_audit_rule,
    open_forensic_investigation,
    log_esg_metric,
    record_ai_governance_log,
    seal_sovereign_archive,
)
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("/crisis", response_model=CrisisEventOut, status_code=status.HTTP_201_CREATED)
async def usas_trigger_crisis(
    payload: CrisisEventCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> CrisisEventOut:
    return CrisisEventOut.model_validate(await trigger_crisis_event(session, payload))


@router.post("/continuous-audit/rules", response_model=ContinuousAuditRuleOut, status_code=status.HTTP_201_CREATED)
async def usas_add_continuous_rule(
    payload: ContinuousAuditRuleCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ContinuousAuditRuleOut:
    return ContinuousAuditRuleOut.model_validate(await create_continuous_audit_rule(session, payload))


@router.post("/forensic-investigations", response_model=ForensicInvestigationOut, status_code=status.HTTP_201_CREATED)
async def usas_open_investigation(
    payload: ForensicInvestigationCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ForensicInvestigationOut:
    return ForensicInvestigationOut.model_validate(await open_forensic_investigation(session, payload))


@router.post("/esg-metrics", response_model=ESGMetricOut, status_code=status.HTTP_201_CREATED)
async def usas_log_esg(
    payload: ESGMetricCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> ESGMetricOut:
    return ESGMetricOut.model_validate(await log_esg_metric(session, payload))


@router.post("/ai-governance-logs", response_model=AIGovernanceLogOut, status_code=status.HTTP_201_CREATED)
async def usas_log_ai_governance(
    payload: AIGovernanceLogCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> AIGovernanceLogOut:
    return AIGovernanceLogOut.model_validate(await record_ai_governance_log(session, payload))


@router.post("/sovereign-archives", response_model=SovereignArchiveOut, status_code=status.HTTP_201_CREATED)
async def usas_seal_archive(
    payload: SovereignArchiveCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> SovereignArchiveOut:
    return SovereignArchiveOut.model_validate(await seal_sovereign_archive(session, payload))
