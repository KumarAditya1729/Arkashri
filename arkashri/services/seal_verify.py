# pyre-ignore-all-errors
"""
services/seal_verify.py — Arkashri Seal Verification Service
=============================================================
The regulator weapon: POST /engagements/{id}/seal/verify

Verification steps:
  1. Load stored seal_bundle from engagement.seal_bundle (WORM source of truth)
  2. Reserialize deterministically using canonical_json — must produce byte-identical output
  3. Recompute SHA-256 hash → compare vs engagement.seal_hash
  4. Recompute HMAC using key_version stored in bundle → compare vs stored signature
  5. Verify each partner signature hash (SHA-256(session_id|partner_id|signed_at))
  6. Verify audit event merkle root still matches
  7. Return SealVerificationResult (VERIFIED | MISMATCH | ERROR)

Philosophy:
  - Verification never writes to the audit file
  - It only reads stored data + recomputes
  - Any mismatch is a tamper signal
  - Updates engagement.seal_verify_status for dashboard display
"""
from __future__ import annotations

import hashlib
import logging
import datetime
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import (
    Engagement, SealSession, SealSignature,
    AuditEvent,
)
from arkashri.services.seal import compute_seal_hash, verify_seal_signature

logger = logging.getLogger(__name__)

VerifyStatus = Literal["VERIFIED", "MISMATCH", "ERROR", "NOT_SEALED"]


@dataclass
class SealVerificationResult:
    status: VerifyStatus
    engagement_id: str
    stored_hash: str | None
    computed_hash: str | None
    hash_match: bool
    hmac_match: bool
    partner_sig_checks: list[dict]
    merkle_match: bool | None
    mismatch_details: list[str]
    key_version: str | None
    verified_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "status":               self.status,
            "engagement_id":        self.engagement_id,
            "stored_hash":          self.stored_hash,
            "computed_hash":        self.computed_hash,
            "hash_match":           self.hash_match,
            "hmac_match":           self.hmac_match,
            "partner_sig_checks":   self.partner_sig_checks,
            "merkle_match":         self.merkle_match,
            "mismatch_details":     self.mismatch_details,
            "key_version":          self.key_version,
            "verified_at":          self.verified_at,
        }


def _verify_partner_sig(sig: SealSignature, session_id: uuid.UUID) -> dict:
    """Recompute SHA-256(session_id|partner_id|signed_at) and compare."""
    raw = f"{session_id}|{sig.partner_user_id}|{sig.signed_at.isoformat()}"
    expected = hashlib.sha256(raw.encode()).hexdigest()
    match = (expected == sig.signature_hash)
    return {
        "partner_user_id": sig.partner_user_id,
        "partner_email":   sig.partner_email,
        "role":            sig.role.value,
        "signed_at":       sig.signed_at.isoformat(),
        "stored_hash":     sig.signature_hash,
        "computed_hash":   expected,
        "match":           match,
    }


async def verify_audit_seal(
    session: AsyncSession,
    engagement_id: uuid.UUID,
) -> SealVerificationResult:
    """
    Deterministically verify a sealed engagement.

    Returns VERIFIED if and only if:
      - SHA-256 of stored bundle == engagement.seal_hash
      - HMAC of stored bundle == stored signature (using stored key_version)
      - All partner signature hashes verify correctly
    """
    mismatches: list[str] = []

    # ── 1. Load Engagement ────────────────────────────────────────────────────
    engagement = (await session.scalars(
        select(Engagement).where(Engagement.id == engagement_id)
    )).first()
    if not engagement:
        return SealVerificationResult(
            status="ERROR", engagement_id=str(engagement_id),
            stored_hash=None, computed_hash=None,
            hash_match=False, hmac_match=False,
            partner_sig_checks=[], merkle_match=None,
            mismatch_details=["Engagement not found."],
            key_version=None,
        )

    if not engagement.sealed_at or not engagement.seal_hash:
        return SealVerificationResult(
            status="NOT_SEALED", engagement_id=str(engagement_id),
            stored_hash=None, computed_hash=None,
            hash_match=False, hmac_match=False,
            partner_sig_checks=[], merkle_match=None,
            mismatch_details=["Engagement has not been sealed yet."],
            key_version=None,
        )

    stored_hash   = engagement.seal_hash
    stored_bundle = engagement.seal_bundle   # Full payload dict — stored at seal time
    key_version   = engagement.seal_key_version or "v1"

    if not stored_bundle:
        return SealVerificationResult(
            status="ERROR", engagement_id=str(engagement_id),
            stored_hash=stored_hash, computed_hash=None,
            hash_match=False, hmac_match=False,
            partner_sig_checks=[], merkle_match=None,
            mismatch_details=[
                "seal_bundle not found on engagement. "
                "This engagement was sealed before bundle persistence was implemented. "
                "Cannot verify without stored payload."
            ],
            key_version=key_version,
        )

    # ── 2. Recompute SHA-256 hash ─────────────────────────────────────────────
    try:
        computed_hash = compute_seal_hash(stored_bundle)
    except Exception as e:
        logger.exception("Hash recomputation failed for %s", engagement_id)
        return SealVerificationResult(
            status="ERROR", engagement_id=str(engagement_id),
            stored_hash=stored_hash, computed_hash=None,
            hash_match=False, hmac_match=False,
            partner_sig_checks=[], merkle_match=None,
            mismatch_details=[f"Hash recomputation failed: {e}"],
            key_version=key_version,
        )

    hash_match = (computed_hash == stored_hash)
    if not hash_match:
        mismatches.append(
            f"SHA-256 MISMATCH: stored={stored_hash[:16]}… computed={computed_hash[:16]}… "
            "— bundle contents have been altered since sealing."
        )

    # ── 3. Verify ECDSA signature ───────────────────────────────────────────
    hmac_match = False
    try:
        # The stored ECDSA signature is not in the engagement table — it's in the original
        # sealed_bundle that was returned by generate_audit_seal(). We verify it directly using the public key.
        
        stored_signature = engagement.seal_bundle.get("signature") if engagement.seal_bundle else None
        if not stored_signature:
            mismatches.append("Signature not found in the stored seal bundle.")
        else:
            hmac_match = verify_seal_signature(engagement.tenant_id, stored_bundle, stored_signature)
            
            if hmac_match:
                logger.info("ECDSA signature verified for engagement=%s", engagement_id)
            else:
                mismatches.append("ECDSA signature verification failed: Cryptographic mismatch")
    except ValueError as e:
        mismatches.append(f"Signature key version error: {e}")
    except Exception as e:
        mismatches.append(f"Signature verification failed unexpectedly: {e}")

    # ── 4. Verify partner signature hashes ────────────────────────────────────
    seal_sess = (await session.scalars(
        select(SealSession).where(SealSession.engagement_id == engagement_id)
    )).first()

    partner_sig_checks: list[dict] = []
    if seal_sess:
        sigs = (await session.scalars(
            select(SealSignature)
            .where(SealSignature.seal_session_id == seal_sess.id)
            .where(SealSignature.withdrawn_at.is_(None))
        )).all()

        for sig in sigs:
            check = _verify_partner_sig(sig, seal_sess.id)
            partner_sig_checks.append(check)
            if not check["match"]:
                mismatches.append(
                    f"Partner signature MISMATCH for {sig.partner_email}: "
                    f"stored={sig.signature_hash[:16]}… computed={check['computed_hash'][:16]}…"
                )
    else:
        mismatches.append("SealSession not found — cannot verify partner signatures.")

    # ── 5. Verify merkle root ─────────────────────────────────────────────────
    merkle_match: bool | None = None
    stored_merkle = stored_bundle.get("cryptographic_anchors", {}).get("audit_event_merkle_root")
    if stored_merkle:
        latest_event = (await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == engagement.tenant_id)
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )).first()
        live_merkle = latest_event.event_hash if latest_event else None
        merkle_match = (live_merkle == stored_merkle)
        if not merkle_match:
            mismatches.append(
                f"Merkle root MISMATCH: stored={stored_merkle[:16]}… live={str(live_merkle)[:16]}… "
                "— audit chain has been extended or altered since sealing."
            )
    else:
        merkle_match = None   # Bundle predates merkle tracking

    # ── 6. Determine final status + persist ───────────────────────────────────
    all_partner_sigs_ok = all(c["match"] for c in partner_sig_checks) if partner_sig_checks else True
    verified = hash_match and hmac_match and all_partner_sigs_ok

    final_status: VerifyStatus = "VERIFIED" if verified else "MISMATCH"

    # Update cached verify status on engagement (non-critical write)
    try:
        engagement.seal_verify_status = final_status
        session.add(engagement)
        await session.commit()
    except Exception:
        pass   # Verification result is still returned even if status update fails

    logger.info(
        "Seal verify engagement=%s status=%s hash_match=%s hmac_match=%s partner_sigs=%d/%d",
        engagement_id, final_status, hash_match, hmac_match,
        sum(1 for c in partner_sig_checks if c["match"]), len(partner_sig_checks),
    )

    return SealVerificationResult(
        status=final_status,
        engagement_id=str(engagement_id),
        stored_hash=stored_hash,
        computed_hash=computed_hash,
        hash_match=hash_match,
        hmac_match=hmac_match,
        partner_sig_checks=partner_sig_checks,
        merkle_match=merkle_match,
        mismatch_details=mismatches,
        key_version=key_version,
    )
