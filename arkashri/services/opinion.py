# pyre-ignore-all-errors
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import AuditOpinion, AuditOpinionType, ExceptionCase, ExceptionStatus
from arkashri.schemas import OpinionCreate

logger = logging.getLogger(__name__)


async def generate_draft_opinion(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    tenant_id: str,
    jurisdiction: str,
    payload: OpinionCreate,
) -> AuditOpinion:
    """
    AI Draft Opinion Generator.
    Determines the opinion type based on open exceptions and run status.
    """
    # Find all AuditRuns associated with this engagement (tenant + jurisdiction approximation for now)
    # Or ideally from a direct link, but simulating behavior based on open exception cases in this scope
    
    stmt = select(ExceptionCase).where(
        ExceptionCase.tenant_id == tenant_id,
        ExceptionCase.jurisdiction == jurisdiction,
        ExceptionCase.status == ExceptionStatus.OPEN
    )
    result = await session.scalars(stmt)
    open_exceptions = result.all()
    
    # Simple deterministic logic to generate Draft Opinion
    opinion_type = AuditOpinionType.UNMODIFIED
    basis = "The financial statements present fairly, in all material respects."
    key_matters = {}
    
    if len(open_exceptions) > 0:
        # Check if there are critical/high risk exceptions
        critical_count = sum(1 for exc in open_exceptions if "CRITICAL" in exc.reason_code.upper() or "FRAUD" in exc.reason_code.upper())
        if critical_count > 0:
            opinion_type = AuditOpinionType.ADVERSE
            basis = f"Adverse opinion issued due to {critical_count} critical unresolved exception(s) indicating pervasive material misstatement."
        else:
            opinion_type = AuditOpinionType.QUALIFIED
            basis = f"Qualified opinion issued due to {len(open_exceptions)} unresolved exception(s) that are material but not pervasive."
            
        key_matters = {
            "unresolved_exceptions": len(open_exceptions),
            "exception_details": [exc.reason_code for exc in open_exceptions]
        }
    
    opinion = AuditOpinion(
        engagement_id=engagement_id,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        opinion_type=opinion_type,
        basis_for_opinion=basis,
        key_audit_matters=key_matters,
        is_signed=False
    )
    
    session.add(opinion)
    await session.commit()
    await session.refresh(opinion)
    return opinion
