# pyre-ignore-all-errors
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole, EngagementType
from arkashri.schemas import AuditPlaybookCreate, AuditPlaybookOut
from arkashri.services.playbook import create_playbook, generate_playbook_for_engagement
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("", response_model=AuditPlaybookOut, status_code=status.HTTP_201_CREATED)
async def usas_create_playbook(
    payload: AuditPlaybookCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> AuditPlaybookOut:
    pb = await create_playbook(session, payload)
    return AuditPlaybookOut.model_validate(pb)


@router.get("/generate", response_model=AuditPlaybookOut)
async def usas_generate_playbook(
    audit_type: EngagementType,
    sector: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> AuditPlaybookOut:
    pb = await generate_playbook_for_engagement(session, audit_type, sector)
    if not pb:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No matching playbook active for parameters.")
    return AuditPlaybookOut.model_validate(pb)
