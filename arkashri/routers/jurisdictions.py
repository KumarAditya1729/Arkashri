from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.db import get_session
from arkashri.models import ClientRole
from arkashri.schemas import RegulatoryFrameworkCreate, RegulatoryFrameworkOut
from arkashri.services.jurisdiction import create_regulatory_framework, get_frameworks_by_jurisdiction
from arkashri.dependencies import require_api_client, AuthContext

router = APIRouter()

@router.post("/frameworks", response_model=RegulatoryFrameworkOut, status_code=status.HTTP_201_CREATED)
async def usas_create_framework(
    payload: RegulatoryFrameworkCreate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> RegulatoryFrameworkOut:
    fw = await create_regulatory_framework(session, payload)
    return RegulatoryFrameworkOut.model_validate(fw)


@router.get("/frameworks/{jurisdiction}", response_model=list[RegulatoryFrameworkOut])
async def usas_get_frameworks_by_jurisdiction(
    jurisdiction: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.READ_ONLY, ClientRole.REVIEWER})),
) -> list[RegulatoryFrameworkOut]:
    fws = await get_frameworks_by_jurisdiction(session, jurisdiction)
    return [RegulatoryFrameworkOut.model_validate(fw) for fw in fws]
