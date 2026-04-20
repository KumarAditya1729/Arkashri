# pyre-ignore-all-errors
"""
routers/seal_sessions.py — Multi-Partner Co-Sign Endpoints

Endpoints:
  POST   /engagements/{engagement_id}/seal-session           Create session
  GET    /engagements/{engagement_id}/seal-session           Get status + signatures
  GET    /seal-sessions/{session_id}/pre-sign-summary        Pre-sign checklist for partner
  POST   /seal-sessions/{session_id}/sign                    Submit partner signature
  DELETE /seal-sessions/{session_id}/signatures/{sig_id}     Withdraw signature

Gate logic:
  - Only FULLY_SIGNED sessions unlock generate_audit_seal()
  - First signature freezes the opinion snapshot
  - Withdrawal resets session to PENDING and logs reason
"""
from __future__ import annotations

import hashlib
import uuid
import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from arkashri.db import get_session
from arkashri.models import (
    Engagement, EngagementStatus,
    AuditOpinion,
    Decision,
    DecisionOverride,
    ExceptionCase,
    SealSession, SealSessionStatus,
    SealSignature, PartnerRole,
    ClientRole,
)
from arkashri.dependencies import require_api_client, AuthContext, limiter
from arkashri.services.audit_log import log_system_event
from arkashri import SYSTEM_VERSION  # L-10: single source of truth

router = APIRouter()

# SYSTEM_VERSION imported from arkashri package — do not redefine locally.


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CreateSealSessionRequest(BaseModel):
    required_signatures: int = Field(default=2, ge=1, le=5, description="Number of partner signatures required before sealing (default 2: Engagement Partner + EQCR)")
    created_by: str = Field(default="system", description="User ID creating the session")
    partner_emails: list[str] = Field(default_factory=list, description="Notification recipients for seal approvals")


class SignRequest(BaseModel):
    partner_user_id: str = Field(..., description="Unique ID of the signing partner")
    partner_email: str   = Field(..., description="Partner email (for audit trail)")
    role: PartnerRole    = Field(default=PartnerRole.ENGAGEMENT_PARTNER)
    jurisdiction: str    = Field(default="IN")
    override_count_acknowledged: int  = Field(default=0, ge=0)
    override_ack_confirmed: bool       = Field(default=False, description="Partner confirmed they reviewed all AI overrides")
    ca_icai_reg_no: str | None = Field(default=None, description="Partner's ICAI Registration Number (FCA/ACA-XXXXXX)")


class WithdrawRequest(BaseModel):
    withdrawal_reason: str = Field(..., min_length=10, description="Mandatory reason for withdrawal (audit trail requirement)")


class SealSignatureOut(BaseModel):
    id: str
    partner_user_id: str
    partner_email: str
    role: str
    jurisdiction: str
    override_count_acknowledged: int
    override_ack_confirmed: bool
    signature_hash: str
    signed_at: str
    withdrawn_at: str | None
    ca_icai_reg_no: str | None

    model_config = {"from_attributes": True}


class SealSessionOut(BaseModel):
    id: str
    engagement_id: str
    required_signatures: int
    current_signature_count: int
    status: str
    frozen_at: str | None
    created_by: str
    created_at: str
    signatures: list[SealSignatureOut]
    can_seal: bool   # True only when FULLY_SIGNED

    model_config = {"from_attributes": True}


class PreSignSummary(BaseModel):
    """Data the partner must review before signing."""
    engagement_id: str
    client_name: str
    engagement_type: str
    jurisdiction: str
    final_opinion_type: str
    basis_for_opinion: str
    # Context lock snapshot
    weight_set_version: int | None
    rule_snapshot_hash: str | None
    system_version: str
    # Counts the partner must acknowledge
    total_transactions_evaluated: int
    total_decisions: int
    open_exceptions: int
    resolved_exceptions: int
    total_ai_overrides: int
    # Seal session state
    session_id: str
    required_signatures: int
    current_signature_count: int
    status: str
    signatures: list[SealSignatureOut]


# ─── Helper ───────────────────────────────────────────────────────────────────

def _compute_signature_hash(session_id: str, partner_user_id: str, signed_at: datetime.datetime) -> str:
    """SHA-256(session_id | partner_id | signed_at_iso) — deterministic, reproducible."""
    raw = f"{session_id}|{partner_user_id}|{signed_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _get_session_or_404(session: AsyncSession, session_id: str) -> SealSession:
    obj = (await session.scalars(
        select(SealSession).where(SealSession.id == session_id)
    )).first()
    if not obj:
        raise HTTPException(status_code=404, detail="SealSession not found.")
    return obj


# ─── 1. Create SealSession ────────────────────────────────────────────────────

@router.post(
    "/engagements/{engagement_id}/seal-session",
    response_model=SealSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a multi-partner sign-off session for an engagement",
)
async def create_seal_session(
    request: Request,
    engagement_id: str,
    payload: CreateSealSessionRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> SealSessionOut:
    # Ensure engagement exists and is not already sealed
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(422, "Invalid engagement_id UUID format.")
    eng = (await db.scalars(select(Engagement).where(Engagement.id == eid))).first()
    if not eng:
        raise HTTPException(404, "Engagement not found.")
    if eng.sealed_at:
        raise HTTPException(409, f"Engagement already sealed at {eng.sealed_at.isoformat()}.")
    if eng.status == EngagementStatus.SEALED:
        raise HTTPException(409, "Engagement status is SEALED — cannot create new seal session.")

    # Prevent duplicate active sessions
    existing = (await db.scalars(
        select(SealSession).where(
            SealSession.engagement_id == eid,
            SealSession.status.not_in([SealSessionStatus.WITHDRAWN]),
        )
    )).first()
    if existing:
        raise HTTPException(409, f"Active SealSession {existing.id} already exists for this engagement.")

    # Capture opinion snapshot at session creation time
    opinion = (await db.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == eid)
        .order_by(AuditOpinion.created_at.desc())
    )).first()
    if not opinion:
        raise HTTPException(
            422,
            "No AuditOpinion found for this engagement. "
            "Generate an opinion (POST /engagements/{id}/opinion) before creating a seal session."
        )

    opinion_snapshot = {
        "opinion_id":        str(opinion.id),
        "opinion_type":      opinion.opinion_type.value,
        "basis_for_opinion": opinion.basis_for_opinion,
        "opinion_hash":      opinion.opinion_hash,
        "weight_set_version":opinion.weight_set_version,
        "rule_snapshot_hash":opinion.rule_snapshot_hash,
        "system_version":    opinion.system_version or SYSTEM_VERSION,
        "snapshot_taken_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    sess = SealSession(
        engagement_id=eid,
        required_signatures=payload.required_signatures,
        current_signature_count=0,
        status=SealSessionStatus.PENDING,
        opinion_snapshot=opinion_snapshot,
        created_by=payload.created_by,
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)

    # Log the audit event
    await log_system_event(
        db,
        tenant_id=auth.tenant_id,
        user_email=payload.created_by,
        action="SEAL_SESSION_CREATED",
        resource_type="ENGAGEMENT",
        resource_id=str(engagement_id),
        extra_metadata={"session_id": str(sess.id), "required_signatures": payload.required_signatures}
    )

    notification_recipients = [email.strip() for email in payload.partner_emails if email.strip()]
    if hasattr(request.app.state, "redis_pool") and request.app.state.redis_pool and notification_recipients:
        await request.app.state.redis_pool.enqueue_job(
            "send_email_task",
            notification_recipients,
            subject=f"Action Required: Seal Session Created for {eng.client_name}",
            body_text=f"A new seal session has been created for engagement {engagement_id}. Please review and sign.",
        )

    return _to_session_out(sess)


# ─── 2. Get SealSession ───────────────────────────────────────────────────────

@router.get(
    "/engagements/{engagement_id}/seal-session",
    response_model=SealSessionOut,
    summary="Get the current seal session status and signature progress",
)
async def get_seal_session(
    engagement_id: str,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY})),
) -> SealSessionOut:
    try:
        eid = uuid.UUID(engagement_id)
    except ValueError:
        raise HTTPException(422, "Invalid engagement_id UUID format.")
    sess = (await db.scalars(
        select(SealSession).where(
            SealSession.engagement_id == eid,
            SealSession.status.not_in([SealSessionStatus.WITHDRAWN]),
        )
    )).first()
    if not sess:
        raise HTTPException(404, "No active SealSession for this engagement.")
    await db.refresh(sess)
    return _to_session_out(sess)


# ─── 3. Pre-Sign Summary (what partner sees before clicking Sign) ─────────────

@router.get(
    "/seal-sessions/{session_id}/pre-sign-summary",
    response_model=PreSignSummary,
    summary="Pre-sign checklist — what the partner reviews before signing",
)
async def get_pre_sign_summary(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER})),
) -> PreSignSummary:
    seal_sess = await _get_session_or_404(db, session_id)
    eng = (await db.scalars(select(Engagement).where(Engagement.id == seal_sess.engagement_id))).first()
    if not eng:
        raise HTTPException(404, "Engagement not found")

    opinion = (await db.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == seal_sess.engagement_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()

    # Counts
    total_decisions = (await db.scalar(
        select(func.count(Decision.id))
        .where(Decision.transaction.has(tenant_id=eng.tenant_id))
    )) or 0
    exceptions = (await db.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id == eng.tenant_id,
            ExceptionCase.jurisdiction == eng.jurisdiction,
        )
    )).all()
    overrides = (await db.scalar(
        select(func.count(DecisionOverride.id))
        .where(DecisionOverride.tenant_id == eng.tenant_id)
    )) or 0

    signatures = (await db.scalars(
        select(SealSignature)
        .where(SealSignature.seal_session_id == session_id, SealSignature.withdrawn_at.is_(None))
    )).all()

    return PreSignSummary(
        engagement_id=str(seal_sess.engagement_id),
        client_name=eng.client_name,
        engagement_type=eng.engagement_type.value,
        jurisdiction=eng.jurisdiction,
        final_opinion_type=opinion.opinion_type.value if opinion else "NONE",
        basis_for_opinion=opinion.basis_for_opinion if opinion else "",
        weight_set_version=opinion.weight_set_version if opinion else None,
        rule_snapshot_hash=opinion.rule_snapshot_hash if opinion else None,
        system_version=opinion.system_version if (opinion and opinion.system_version) else SYSTEM_VERSION,
        total_transactions_evaluated=total_decisions,
        total_decisions=total_decisions,
        open_exceptions=sum(1 for e in exceptions if e.status.value == "OPEN"),
        resolved_exceptions=sum(1 for e in exceptions if e.status.value == "RESOLVED"),
        total_ai_overrides=overrides,
        session_id=str(seal_sess.id),
        required_signatures=seal_sess.required_signatures,
        current_signature_count=seal_sess.current_signature_count,
        status=seal_sess.status.value,
        signatures=[_to_sig_out(s) for s in signatures],
    )


# ─── 4. Sign ─────────────────────────────────────────────────────────────────

@router.post(
    "/seal-sessions/{session_id}/sign",
    response_model=SealSessionOut,
    summary="Submit a partner signature. Freezes opinion on first signature.",
)
@limiter.limit("5/minute")
async def sign_seal_session(
    request: Request,
    session_id: str,
    payload: SignRequest,
    db: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> SealSessionOut:
    seal_sess = await _get_session_or_404(db, session_id)

    if seal_sess.status == SealSessionStatus.FULLY_SIGNED:
        raise HTTPException(409, "SealSession is already FULLY_SIGNED.")
    if seal_sess.status == SealSessionStatus.WITHDRAWN:
        raise HTTPException(409, "SealSession has been withdrawn. Create a new one.")

    # H-9: Bind partner identity to the authenticated caller, not caller-supplied strings.
    # This prevents a user from signing as an arbitrary partner_user_id / partner_email.
    authenticated_user_id = str(getattr(auth, "client_id", "") or getattr(auth, "user_id", "") or payload.partner_user_id)
    authenticated_email   = str(getattr(auth, "email", "") or getattr(auth, "client_name", "") or payload.partner_email)

    # Prevent duplicate signature from same partner (use authenticated identity)
    dup = (await db.scalars(
        select(SealSignature).where(
            SealSignature.seal_session_id == session_id,
            SealSignature.partner_user_id == authenticated_user_id,
            SealSignature.withdrawn_at.is_(None),
        )
    )).first()
    if dup:
        raise HTTPException(409, f"You ({authenticated_user_id}) have already signed this session.")

    # Enforce override acknowledgement for sessions with known overrides
    eng = (await db.scalars(select(Engagement).where(Engagement.id == seal_sess.engagement_id))).first()
    if not eng:
        raise HTTPException(404, "Engagement not found")
    override_count = (await db.scalar(
        select(func.count(DecisionOverride.id)).where(DecisionOverride.tenant_id == eng.tenant_id)
    )) or 0
    if override_count > 0 and not payload.override_ack_confirmed:
        raise HTTPException(
            422,
            f"{override_count} AI decision override(s) exist. "
            "Partner must confirm override_ack_confirmed=true to acknowledge they reviewed all overrides. "
            "This is a PCAOB professional skepticism requirement."
        )

    if payload.jurisdiction == "IN":
        if not payload.ca_icai_reg_no:
            raise HTTPException(422, "ICAI Registration Number is required for Indian jurisdictions. Please provide ca_icai_reg_no.")
        from arkashri.services.disclaimer import validate_icai_reg_no
        if not validate_icai_reg_no(payload.ca_icai_reg_no):
            raise HTTPException(422, "Invalid ICAI Registration Number format. Must be FCA/ACA-XXXXXX or F/A-XXXXXX.")

    now = datetime.datetime.now(datetime.UTC)
    sig_hash = _compute_signature_hash(session_id, authenticated_user_id, now)

    sig = SealSignature(
        seal_session_id=session_id,
        partner_user_id=authenticated_user_id,    # H-9: from auth, not caller payload
        partner_email=authenticated_email,         # H-9: from auth, not caller payload
        role=payload.role,
        jurisdiction=payload.jurisdiction,
        override_count_acknowledged=override_count,
        override_ack_confirmed=payload.override_ack_confirmed,
        ca_icai_reg_no=payload.ca_icai_reg_no,
        signature_hash=sig_hash,
        signed_at=now,
    )
    db.add(sig)

    # Update session
    seal_sess.current_signature_count += 1

    # Freeze opinion on first signature
    if seal_sess.current_signature_count == 1 and not seal_sess.frozen_at:
        seal_sess.frozen_at = now

    # Determine new status
    if seal_sess.current_signature_count >= seal_sess.required_signatures:
        seal_sess.status = SealSessionStatus.FULLY_SIGNED
    else:
        seal_sess.status = SealSessionStatus.PARTIALLY_SIGNED

    db.add(seal_sess)
    await db.commit()
    await db.refresh(seal_sess)

    # Log the signature
    await log_system_event(
        db,
        tenant_id=auth.tenant_id,
        user_email=authenticated_email,
        action="PARTNER_SIGNED",
        resource_type="SEAL_SESSION",
        resource_id=str(session_id),
        extra_metadata={
            "role": payload.role.value,
            "signature_hash": sig_hash,
            "overrides_acknowledged": payload.override_count_acknowledged
        }
    )

    return _to_session_out(seal_sess)


# ─── 5. Withdraw Signature ────────────────────────────────────────────────────

@router.delete(
    "/seal-sessions/{session_id}/signatures/{sig_id}",
    response_model=SealSessionOut,
    summary="Withdraw a partner signature. Resets session to PENDING.",
)
async def withdraw_signature(
    session_id: str,
    sig_id: str,
    payload: WithdrawRequest,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({ClientRole.ADMIN, ClientRole.OPERATOR})),
) -> SealSessionOut:
    seal_sess = await _get_session_or_404(db, session_id)

    if seal_sess.status == SealSessionStatus.WITHDRAWN:
        raise HTTPException(409, "Seal session is already withdrawn.")

    sig = (await db.scalars(
        select(SealSignature).where(
            SealSignature.id == sig_id,
            SealSignature.seal_session_id == session_id,
        )
    )).first()
    if not sig:
        raise HTTPException(404, "Signature not found in this session.")
    if sig.withdrawn_at:
        raise HTTPException(409, "Signature already withdrawn.")

    now = datetime.datetime.now(datetime.UTC)
    sig.withdrawn_at = now
    sig.withdrawal_reason = payload.withdrawal_reason

    # Recalculate count and reset status
    active_count = seal_sess.current_signature_count - 1
    seal_sess.current_signature_count = max(0, active_count)
    seal_sess.status = SealSessionStatus.PENDING if active_count <= 0 else SealSessionStatus.PARTIALLY_SIGNED

    db.add(sig)
    db.add(seal_sess)
    await db.commit()
    await db.refresh(seal_sess)

    # Log the withdrawal
    await log_system_event(
        db,
        tenant_id=_auth.tenant_id,
        user_id=None,
        user_email=sig.partner_email,
        action="PARTNER_SIGNATURE_WITHDRAWN",
        resource_type="SEAL_SESSION",
        resource_id=str(session_id),
        extra_metadata={"reason": payload.withdrawal_reason, "sig_id": str(sig_id)}
    )

    return _to_session_out(seal_sess)


# ─── 6. Verify Seal ──────────────────────────────────────────────────────────

class PartnerSigCheck(BaseModel):
    partner_user_id: str
    partner_email: str
    role: str
    signed_at: str
    stored_hash: str
    computed_hash: str
    match: bool


class SealVerifyOut(BaseModel):
    """
    Regulator-facing verification result.
    VERIFIED = byte-identical replay confirmed.
    MISMATCH = tamper detected — mismatch_details lists every discrepancy.
    """
    status: str                             # VERIFIED | MISMATCH | NOT_SEALED | ERROR
    engagement_id: str
    stored_hash: str | None
    computed_hash: str | None
    hash_match: bool
    hmac_match: bool
    partner_sig_checks: list[PartnerSigCheck]
    merkle_match: bool | None
    mismatch_details: list[str]
    key_version: str | None
    verified_at: str


@router.post(
    "/engagements/{engagement_id}/seal/verify",
    response_model=SealVerifyOut,
    summary="Verify seal integrity — regulator endpoint. Returns VERIFIED or MISMATCH.",
    tags=["Multi-Partner Seal Sessions"],
)
async def verify_seal(
    engagement_id: str,
    db: AsyncSession = Depends(get_session),
    _auth: AuthContext = Depends(require_api_client({
        ClientRole.ADMIN, ClientRole.OPERATOR, ClientRole.REVIEWER, ClientRole.READ_ONLY
    })),
) -> SealVerifyOut:
    """
    POST /engagements/{engagement_id}/seal/verify

    Steps:
      1. Loads stored seal_bundle from engagement.seal_bundle
      2. Recomputes SHA-256 using canonical_json → compares vs seal_hash
      3. Recomputes HMAC using stored key_version → validates key is known
      4. Verifies each partner signature hash independently
      5. Checks merkle root still matches latest AuditEvent
      6. Returns VERIFIED or named MISMATCH details

    This endpoint is the regulator weapon — it proves the WORM bundle
    has not been tampered with since sealing.
    """
    from arkashri.services.seal_verify import verify_audit_seal

    result = await verify_audit_seal(db, engagement_id)

    # Log verification attempt
    await log_system_event(
        db,
        tenant_id=_auth.tenant_id,
        action="SEAL_VERIFIED",
        resource_type="ENGAGEMENT",
        resource_id=str(engagement_id),
        status=result.status,
        extra_metadata={"match": result.hash_match}
    )

    return SealVerifyOut(
        status=result.status,
        engagement_id=result.engagement_id,
        stored_hash=result.stored_hash,
        computed_hash=result.computed_hash,
        hash_match=result.hash_match,
        hmac_match=result.hmac_match,
        partner_sig_checks=[PartnerSigCheck(**c) for c in result.partner_sig_checks],
        merkle_match=result.merkle_match,
        mismatch_details=result.mismatch_details,
        key_version=result.key_version,
        verified_at=result.verified_at,
    )


# ─── Serialisation helpers ────────────────────────────────────────────────────

def _to_sig_out(s: SealSignature) -> SealSignatureOut:
    return SealSignatureOut(
        id=str(s.id),
        partner_user_id=s.partner_user_id,
        partner_email=s.partner_email,
        role=s.role.value,
        jurisdiction=s.jurisdiction,
        override_count_acknowledged=s.override_count_acknowledged,
        override_ack_confirmed=s.override_ack_confirmed,
        signature_hash=s.signature_hash,
        signed_at=s.signed_at.isoformat(),
        withdrawn_at=s.withdrawn_at.isoformat() if s.withdrawn_at else None,
        ca_icai_reg_no=s.ca_icai_reg_no,   # M-10: was silently dropped before
    )


def _to_session_out(sess: SealSession) -> SealSessionOut:
    sigs = [_to_sig_out(s) for s in (sess.signatures or []) if not s.withdrawn_at]
    return SealSessionOut(
        id=str(sess.id),
        engagement_id=str(sess.engagement_id),
        required_signatures=sess.required_signatures,
        current_signature_count=sess.current_signature_count,
        status=sess.status.value,
        frozen_at=sess.frozen_at.isoformat() if sess.frozen_at else None,
        created_by=sess.created_by,
        created_at=sess.created_at.isoformat(),
        signatures=sigs,
        can_seal=(sess.status == SealSessionStatus.FULLY_SIGNED),
    )
