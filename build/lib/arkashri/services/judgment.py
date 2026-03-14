# pyre-ignore-all-errors
"""
services/judgment.py — Human Judgment Layer Logic
=================================================
Handles the escalation of complex accounting estimates (Fair Value, Going Concern,
Related Party Transactions) that require mandatory human professional judgment.
If AI confidence in an audit area falls below the threshold, a ProfessionalJudgment
record is created which blocks sealing until a CA formally signs off on it.
"""

import uuid
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import ProfessionalJudgment, JudgmentStatus, Engagement

# If AI confidence drops below this, human judgment is mandatory.
AI_CONFIDENCE_THRESHOLD = 85.0 

async def flag_complex_estimate(
    session: AsyncSession, 
    engagement_id: uuid.UUID, 
    area: str, 
    description: str, 
    ai_confidence: float
) -> ProfessionalJudgment | None:
    """
    Creates a pending ProfessionalJudgment record if AI confidence is below the threshold.
    If it's above the threshold, no mandatory judgment is required.
    """
    if ai_confidence >= AI_CONFIDENCE_THRESHOLD:
        return None # Confident enough, no escalation needed.
        
    # Check if a judgment for this area already exists
    existing = (await session.scalars(
        select(ProfessionalJudgment).where(
            ProfessionalJudgment.engagement_id == engagement_id,
            ProfessionalJudgment.area == area
        )
    )).first()
    
    if existing:
        return existing
        
    judgment = ProfessionalJudgment(
        engagement_id=engagement_id,
        area=area,
        description=description,
        ai_confidence=ai_confidence,
        status=JudgmentStatus.PENDING
    )
    session.add(judgment)
    await session.commit()
    await session.refresh(judgment)
    return judgment


async def check_judgments_complete(session: AsyncSession, engagement_id: uuid.UUID) -> bool:
    """
    Returns True if ALL flagged judgments for an engagement are explicitly SIGNED.
    Used as a hard-gate by the sealing engine.
    """
    pending_judgments = (await session.scalars(
        select(ProfessionalJudgment).where(
            ProfessionalJudgment.engagement_id == engagement_id,
            ProfessionalJudgment.status == JudgmentStatus.PENDING
        )
    )).all()
    
    return len(pending_judgments) == 0
