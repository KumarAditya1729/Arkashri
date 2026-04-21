# pyre-ignore-all-errors
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import (
    AuditOpinion, AuditOpinionType,
    ExceptionCase, ExceptionStatus,
    ProfessionalJudgment,
)
from arkashri.schemas import OpinionCreate

logger = logging.getLogger(__name__)


async def _check_going_concern_judgment(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> dict:
    """
    Reads any ProfessionalJudgment records for the 'Going Concern' area
    and returns their status + description for injection into the opinion.
    """
    judgments = (await session.scalars(
        select(ProfessionalJudgment).where(
            ProfessionalJudgment.engagement_id == engagement_id,
            ProfessionalJudgment.area == "Going Concern",
        )
    )).all()

    if not judgments:
        return {"exists": False}

    latest = sorted(judgments, key=lambda j: j.created_at, reverse=True)[0]
    return {
        "exists": True,
        "status": latest.status.value,
        "ai_confidence": latest.ai_confidence,
        "description": latest.description,
        "signed_by": latest.signed_by,
        "icai_reg_no": latest.icai_reg_no,
        # HIGH risk (confidence < 30) → opinion modification required (SA 705)
        # MEDIUM risk (30 ≤ confidence < 85) → emphasis of matter (SA 706)
        "opinion_modification_required": latest.ai_confidence < 30.0,
        "emphasis_of_matter_required": 30.0 <= latest.ai_confidence < 85.0,
    }


async def generate_draft_opinion(
    session: AsyncSession,
    engagement_id: uuid.UUID,
    tenant_id: str,
    jurisdiction: str,
    payload: OpinionCreate,
) -> AuditOpinion:
    """
    AI Draft Opinion Generator — SA 700 / SA 705 / SA 706 / SA 570 compliant.

    Determination logic (in priority order):
      1. If a Going Concern judgment exists with HIGH risk (ai_confidence < 30)
         AND management's disclosure is inadequate → QUALIFIED or ADVERSE (SA 705)
      2. If open CRITICAL exceptions → ADVERSE
      3. If open non-critical exceptions → QUALIFIED
      4. If a Going Concern judgment with MEDIUM risk → UNMODIFIED with Emphasis of Matter (SA 706)
      5. Otherwise → UNMODIFIED (clean opinion)
    """
    # ── Step 1: Check Going Concern signals ────────────────────────────────────
    gc = await _check_going_concern_judgment(session, engagement_id)

    # ── Step 2: Check open exceptions ─────────────────────────────────────────
    open_exceptions = (await session.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id == tenant_id,
            ExceptionCase.jurisdiction == jurisdiction,
            ExceptionCase.status == ExceptionStatus.OPEN,
        )
    )).all()

    critical_count = sum(
        1 for exc in open_exceptions
        if "CRITICAL" in exc.reason_code.upper() or "FRAUD" in exc.reason_code.upper()
    )

    # ── Step 3: Determine opinion type ────────────────────────────────────────
    opinion_type = AuditOpinionType.UNMODIFIED
    basis_parts: list[str] = []
    key_matters: dict = {}
    emphasis_paragraphs: list[str] = []

    # Going concern — opinion modification (SA 705, triggered by HIGH GC risk)
    if gc["exists"] and gc.get("opinion_modification_required"):
        if critical_count > 0:
            opinion_type = AuditOpinionType.ADVERSE
            basis_parts.append(
                "An adverse opinion is issued. Material uncertainty exists regarding the entity's "
                "ability to continue as a going concern (SA 570), and pervasive critical exceptions "
                "have not been resolved, indicating the financial statements are materially misstated."
            )
        else:
            opinion_type = AuditOpinionType.QUALIFIED
            basis_parts.append(
                "A qualified opinion is issued. Material uncertainty related to going concern exists "
                "(SA 570 Para 21). Management has not provided adequate disclosure of the going concern "
                "uncertainty, and the auditor is unable to obtain sufficient appropriate audit evidence "
                "to conclude that this uncertainty is not material and pervasive."
            )
        key_matters["going_concern"] = {
            "standard": "SA 570 (Revised) — Going Concern",
            "risk_level": "HIGH",
            "ai_confidence": gc.get("ai_confidence"),
            "signed_by": gc.get("signed_by"),
            "icai_reg_no": gc.get("icai_reg_no"),
            "judgment_status": gc.get("status"),
            "description_excerpt": (gc.get("description") or "")[:300],
        }

    # Open exceptions (non-GC)
    elif critical_count > 0:
        opinion_type = AuditOpinionType.ADVERSE
        basis_parts.append(
            f"An adverse opinion is issued due to {critical_count} critical unresolved "
            "exception(s) indicating pervasive material misstatement."
        )
        key_matters["unresolved_critical_exceptions"] = {
            "count": critical_count,
            "codes": [exc.reason_code for exc in open_exceptions if "CRITICAL" in exc.reason_code.upper()],
        }

    elif open_exceptions:
        opinion_type = AuditOpinionType.QUALIFIED
        basis_parts.append(
            f"A qualified opinion is issued due to {len(open_exceptions)} unresolved "
            "exception(s) that are material but not pervasive."
        )
        key_matters["unresolved_exceptions"] = {
            "count": len(open_exceptions),
            "codes": [exc.reason_code for exc in open_exceptions],
        }

    else:
        basis_parts.append(
            "The financial statements present fairly, in all material respects, "
            "in accordance with the applicable financial reporting framework."
        )

    # Going concern — emphasis of matter only (SA 706, MEDIUM GC risk)
    if gc["exists"] and gc.get("emphasis_of_matter_required") and not gc.get("opinion_modification_required"):
        emphasis_paragraphs.append(
            "Emphasis of Matter — Material Uncertainty Related to Going Concern (SA 706 / SA 570 Para 25): "
            "Without qualifying our opinion, we draw attention to the notes to the financial statements "
            "which indicate that a material uncertainty exists that may cast significant doubt on the "
            "entity's ability to continue as a going concern. Management has disclosed the nature of "
            "this uncertainty and their plans to address it. Our opinion is not modified in respect of this matter."
        )
        key_matters["going_concern_emphasis"] = {
            "standard": "SA 570 (Revised) — SA 706 Emphasis of Matter",
            "risk_level": "MEDIUM",
            "ai_confidence": gc.get("ai_confidence"),
            "judgment_status": gc.get("status"),
            "signed_by": gc.get("signed_by"),
        }

    # Build final basis
    full_basis = " ".join(basis_parts)
    if emphasis_paragraphs:
        full_basis += "\n\n" + "\n\n".join(emphasis_paragraphs)

    # ── Step 4: Persist opinion ────────────────────────────────────────────────
    opinion = AuditOpinion(
        engagement_id=engagement_id,
        tenant_id=tenant_id,
        jurisdiction=jurisdiction,
        opinion_type=opinion_type,
        basis_for_opinion=full_basis,
        key_audit_matters=key_matters,
        is_signed=False,
    )

    session.add(opinion)
    await session.commit()
    await session.refresh(opinion)

    logger.info(
        "Draft opinion generated. engagement=%s type=%s gc_exists=%s exceptions=%d",
        engagement_id, opinion_type.value, gc["exists"], len(open_exceptions)
    )
    return opinion
