# pyre-ignore-all-errors
import uuid
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from arkashri.dependencies import get_session, require_api_client
from arkashri.dependencies import AuthContext
from arkashri.models import ProfessionalJudgment, JudgmentStatus, User, ClientRole

router = APIRouter(prefix="/v1/judgments", tags=["Human Judgment"])


@router.get("/{engagement_id}")
async def list_judgments(
    engagement_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> dict:
    judgments = (await session.scalars(
        select(ProfessionalJudgment)
        .where(ProfessionalJudgment.engagement_id == engagement_id)
        .order_by(ProfessionalJudgment.created_at.desc())
    )).all()
    
    return {
        "engagement_id": engagement_id,
        "judgments": [
            {
                "id": str(j.id),
                "area": j.area,
                "description": j.description,
                "ai_confidence": j.ai_confidence,
                "status": j.status.value,
                "signed_by": j.signed_by,
                "icai_reg_no": j.icai_reg_no,
                "signed_at": j.signed_at.isoformat() if j.signed_at else None
            } for j in judgments
        ]
    }


class JudgmentSignOff(BaseModel):
    notes: str | None = None


@router.post("/{judgment_id}/sign-off")
async def sign_off_judgment(
    judgment_id: str,
    payload: JudgmentSignOff,
    session: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> dict:
    judgment = await session.scalar(select(ProfessionalJudgment).where(ProfessionalJudgment.id == judgment_id))
    if not judgment:
        raise HTTPException(status_code=404, detail="Judgment not found")
        
    if judgment.status == JudgmentStatus.SIGNED:
        raise HTTPException(status_code=400, detail="Judgment is already signed off")
        
    user = await session.scalar(select(User).where(User.id == uuid.UUID(_auth.user_id)))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not user.icai_reg_no:
        raise HTTPException(
            status_code=403, 
            detail="Cannot sign off on professional judgments without a valid ICAI Registration Number on your profile."
        )

    judgment.status = JudgmentStatus.SIGNED
    judgment.signed_by = user.full_name
    judgment.icai_reg_no = user.icai_reg_no
    judgment.signed_at = datetime.datetime.now(datetime.timezone.utc)
    
    # payload.notes can be ignored or stored, but currently the model has no column for signoff notes.
    # For now, it's just required to initiate the POST.
    
    session.add(judgment)
    await session.commit()
    
    return {
        "status": "success", 
        "judgment_id": str(judgment.id), 
        "signed_by": judgment.signed_by,
        "icai_reg_no": judgment.icai_reg_no
    }
