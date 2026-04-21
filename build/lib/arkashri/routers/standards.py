# pyre-ignore-all-errors
import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.dependencies import get_session, require_api_client
from arkashri.dependencies import AuthContext
from arkashri.models import SAChecklistItem, Engagement, EngagementStatus, ClientRole
from arkashri.services.sa_compliance import generate_sa_checklist, generate_nfra_package

router = APIRouter(prefix="/v1/standards", tags=["Regulatory Standards"])

@router.get("/sa")
async def list_sa_standards(
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict:
    from arkashri.services.sa_compliance import SA_REQUIREMENTS
    return {"standards_on_auditing": SA_REQUIREMENTS}

@router.post("/engagements/{engagement_id}/sa-checklist")
async def create_engagement_sa_checklist(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    checklist = await generate_sa_checklist(session, engagement_id)
    return {
        "engagement_id": engagement_id,
        "items_count": len(checklist),
        "status": "generated"
    }

@router.get("/engagements/{engagement_id}/sa-checklist")
async def get_engagement_sa_checklist(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict:
    items = (await session.scalars(select(SAChecklistItem).where(SAChecklistItem.engagement_id == engagement_id))).all()
    return {
        "engagement_id": engagement_id,
        "items": [
            {
                "id": str(i.id),
                "standard": i.standard_ref,
                "requirement": i.requirement,
                "status": i.status.value,
                "verified_by": i.verified_by,
                "verified_at": i.verified_at.isoformat() if i.verified_at else None
            } for i in items
        ]
    }

class SAChecklistUpdate(BaseModel):
    status: str

@router.put("/sa-checklist/{item_id}")
async def update_sa_checklist_item(
    item_id: str,
    payload: SAChecklistUpdate,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    from arkashri.models import SAChecklistStatus
    item = await session.scalar(select(SAChecklistItem).where(SAChecklistItem.id == item_id))
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
        
    try:
        new_status = SAChecklistStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    item.status = new_status
    item.verified_by = _auth.user_id
    item.verified_at = datetime.datetime.now(datetime.timezone.utc)
    
    session.add(item)
    await session.commit()
    
    return {"id": str(item.id), "status": item.status.value}

@router.post("/engagements/{engagement_id}/nfra-package", response_class=Response)
async def download_nfra_package(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
):
    engagement = await session.scalar(select(Engagement).where(Engagement.id == engagement_id))
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
        
    if engagement.status != EngagementStatus.SEALED:
        raise HTTPException(status_code=400, detail="Cannot generate NFRA package for unsealed engagements.")
        
    zip_bytes = await generate_nfra_package(session, engagement_id)
    
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=NFRA_Submission_{engagement.client_name}_{engagement_id}.zip"
        }
    )
