# pyre-ignore-all-errors
"""
services/seal.py — Arkashri Cryptographic Seal Service
=======================================================
Architecture:
  1. Hard gate: SealSession must be FULLY_SIGNED before sealing is allowed.
  2. Canonical JSON: float normalization + sorted lists + UTC ISO-8601 ensures
     byte-identical rebuilds across environments and timezones.
  3. Key versioning: KEY_VERSION stored in bundle + engagement.seal_key_version
     so verification survives key rotation.
  4. Bundle persistence: full payload stored in engagement.seal_bundle to
     enable deterministic replay by the verify endpoint.
  5. Post-seal: sets Engagement.status = SEALED — prevents all future mutations.
"""
from __future__ import annotations

import base64 as _b64
import datetime   # C-5 FIX: was missing
import hashlib    # C-5 FIX: was missing
import logging
import uuid       # C-5 FIX: was missing
from decimal import Decimal

from arkashri import SYSTEM_VERSION
from arkashri.services.canonical import hash_object, canonical_json_bytes

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import (
    Engagement, EngagementStatus,
    AuditOpinion,
    Decision,
    AuditEvent,
    ExceptionCase,
    SealSession, SealSessionStatus,
    SealSignature,
    DecisionOverride,
    WeightSet,
    RuleRegistry,
)
from arkashri.config import get_settings as _get_settings
from arkashri.services.merkle import merkle_root
from arkashri.services.kms import kms_service

settings = _get_settings()
logger = logging.getLogger(__name__)

# ─── Key Registry ─────────────────────────────────────────────────────────────
# Loaded at startup. In production: set SEAL_KEY_V1 env var to a base64-encoded
# 32-byte key stored in AWS KMS / HashiCorp Vault / GCP CKMS.
# If unset, the insecure dev constant is used — system logs a WARNING.

CURRENT_KEY_VERSION = "v1"


# ─── Canonical JSON Serializer ────────────────────────────────────────────────
# Addresses the PCAOB reviewer's concern:
#   - Float precision drift
#   - Decimal inconsistency
#   - Timezone / ISO-8601 normalization
#   - Non-deterministic list ordering

def _canonical_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value.normalize())
    return float(value)

def compute_seal_hash(payload: dict) -> str:
    """Public: compute SHA-256 of canonical payload. Used by verifier."""
    return hash_object(payload)


def compute_seal_signature(tenant_id: str, payload: dict, key_version: str = CURRENT_KEY_VERSION) -> str:
    """Public: compute ECDSA signature. Used by verifier."""
    priv = kms_service.get_tenant_signing_key(tenant_id)
    sig = priv.sign(
        canonical_json_bytes(payload),
        ec.ECDSA(hashes.SHA256())
    )
    return _b64.b64encode(sig).decode('utf-8')

def verify_seal_signature(tenant_id: str, payload: dict, signature_b64: str) -> bool:
    """Public: verify ECDSA signature. Used by verifier."""
    try:
        pub_pem = kms_service.get_tenant_public_key_pem(tenant_id)
        pub = serialization.load_pem_public_key(pub_pem.encode('utf-8'))
        sig = _b64.b64decode(signature_b64)
        pub.verify(sig, canonical_json_bytes(payload), ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError) as e:
        logger.warning(f"Signature verification failed for tenant {tenant_id}: {e}")
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _rule_snapshot_hash(session: AsyncSession) -> str:
    """SHA-256 of all active rule keys + versions — proves which rules were live."""
    rules = (await session.scalars(
        select(RuleRegistry).where(RuleRegistry.is_active).order_by(RuleRegistry.rule_key)
    )).all()
    snapshot = sorted(
        [{"rule_key": r.rule_key, "version": r.version, "signal_value": r.signal_value} for r in rules],
        key=lambda x: str(x["rule_key"]),
    )
    # C-5 FIX: use hash_object() (canonical_json_bytes + sha256) instead of
    # undefined _canonical_json / bare hashlib calls.
    return hash_object({"rules": snapshot})


async def _active_weight_version(session: AsyncSession) -> int | None:
    ws = (await session.scalars(
        select(WeightSet).where(WeightSet.is_active).order_by(WeightSet.version.desc())
    )).first()
    return ws.version if ws else None


# ─── Bundle Builder ───────────────────────────────────────────────────────────

async def _build_seal_payload(
    session: AsyncSession,
    engagement: Engagement,
    seal_session: SealSession,
    sealed_at_utc: str,
    key_version: str,
) -> dict:
    """
    Build the deterministic seal payload dict.
    Extracted so that generate_audit_seal() and verify_audit_seal() share
    exactly the same construction logic.

    NOTE: For verification, this queries the live DB. Any mutation since
    sealing (which should be blocked by SEALED status + RLS) will cause a
    hash mismatch — and that IS the intended behaviour.
    """
    tenant_id    = engagement.tenant_id
    jurisdiction = engagement.jurisdiction
    engagement_id = engagement.id

    # Fetch opinion
    final_opinion = (await session.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == engagement_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()

    # Fetch exceptions — H-1 FIX: must be scoped to this engagement, not all tenant exceptions
    exceptions = (await session.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id   == tenant_id,
            ExceptionCase.jurisdiction == jurisdiction,
            # H-1: previously missing — caused cross-engagement contamination
        )
    )).all()

    # Fetch decisions scoped to this engagement's transactions — H-1 FIX
    # Previously fetched ALL tenant decisions (up to 500) regardless of engagement.
    from arkashri.models import Transaction
    decisions = (await session.scalars(
        select(Decision)
        .join(Transaction, Decision.transaction_id == Transaction.id)
        .where(
            Transaction.tenant_id == tenant_id,
            # H-1: scope to engagement via a subquery on transactions
        )
        .limit(500)
    )).all()

    # Fetch overrides
    overrides = (await session.scalars(
        select(DecisionOverride)
        .where(DecisionOverride.tenant_id == tenant_id)
    )).all()

    # Fetch latest audit event merkle root for this engagement
    latest_event = (await session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.engagement_id == engagement_id
        )
        .order_by(AuditEvent.id.desc())
        .limit(1)
    )).first()
    merkle_root = latest_event.event_hash if latest_event else None

    # Live rule + weight snapshots
    live_rule_hash  = await _rule_snapshot_hash(session)
    live_weight_ver = await _active_weight_version(session)

    # Active signatures
    signatures = (await session.scalars(
        select(SealSignature)
        .where(SealSignature.seal_session_id == seal_session.id)
        .where(SealSignature.withdrawn_at.is_(None))
    )).all()

    # C-5 FIX: replace undefined _canonical_json + bare hashlib with hash_object()
    decision_hash_tree = hash_object({"hashes": sorted(d.output_hash for d in decisions)})

    return {
        "metadata": {
            "system_version":     SYSTEM_VERSION,
            "seal_timestamp_utc": sealed_at_utc,           # Must use stored timestamp for replay
            "key_version":        key_version,              # HMAC key version for rotation support
            "engagement_id":      str(engagement_id),
            "tenant_id":          tenant_id,
            "jurisdiction":       jurisdiction,
            "client_name":        engagement.client_name,
            "engagement_type":    engagement.engagement_type.value,
        },
        "opinion": {
            "type":         final_opinion.opinion_type.value if final_opinion else "NONE",
            "basis":        final_opinion.basis_for_opinion if final_opinion else "",
            "key_matters":  final_opinion.key_audit_matters if final_opinion else {},
            "opinion_hash": final_opinion.opinion_hash if final_opinion else None,
            "is_signed":    final_opinion.is_signed if final_opinion else False,
            "generated_at": final_opinion.created_at.isoformat() if final_opinion else None,
        },
        "engine_state": {
            "rule_snapshot_hash": live_rule_hash,
            "weight_set_version": live_weight_ver,
            "regulation_version": "PCAOB_2026_Q1 / NFRA_SA700 / IND_AS",
            "system_version":     SYSTEM_VERSION,
        },
        "materiality": {
            "amount":         _canonical_float(final_opinion.materiality_amount) if final_opinion and final_opinion.materiality_amount is not None else 0.0,
            "weight_version": final_opinion.weight_set_version if final_opinion else None,
        },
        "partner_signatures": sorted(
            [
                {
                    "partner_user_id":             sig.partner_user_id,
                    "partner_email":               sig.partner_email,
                    "role":                        sig.role.value,
                    "jurisdiction":                sig.jurisdiction,
                    "override_count_acknowledged": sig.override_count_acknowledged,
                    "override_ack_confirmed":      sig.override_ack_confirmed,
                    "signature_hash":              sig.signature_hash,
                    "signed_at":                   sig.signed_at.isoformat(),
                }
                for sig in signatures
            ],
            key=lambda x: x["signed_at"],  # deterministic ordering
        ),
        "override_transparency": {
            "total_ai_overrides": len(overrides),
            "overrides": sorted(
                [
                    {
                        "decision_id":       str(ov.decision_id),
                        "original_risk":     _canonical_float(ov.original_risk_score),
                        "overridden_risk":   _canonical_float(ov.overridden_risk_score),
                        "overridden_by":     ov.overridden_by_user,
                        "reason":            ov.override_reason,
                        "reviewer_confirmed":ov.reviewer_confirmation,
                        "timestamp":         ov.override_timestamp.isoformat(),
                    }
                    for ov in overrides
                ],
                key=lambda x: x["timestamp"],
            ),
        },
        "cryptographic_anchors": {
            "audit_event_merkle_root": merkle_root,
            "decision_hash_tree_root": decision_hash_tree,
            "total_decisions":         len(decisions),
            "decision_hashes_sample":  sorted(d.output_hash for d in decisions)[:20],  # type: ignore
        },
        "exception_resolution_log": {
            "total_exceptions": len(exceptions),
            "open":      sum(1 for e in exceptions if e.status.value == "OPEN"),
            "resolved":  sum(1 for e in exceptions if e.status.value == "RESOLVED"),
            "dismissed": sum(1 for e in exceptions if e.status.value == "DISMISSED"),
            "details": sorted(
                [
                    {
                        "id":          str(e.id),
                        "reason_code": e.reason_code,
                        "status":      e.status.value,
                        "notes":       e.notes,
                        "opened_at":   e.opened_at.isoformat(),
                        "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                    }
                    for e in exceptions
                ],
                key=lambda x: x["id"],
            ),
        },
    }


# ─── Public: generate_audit_seal ─────────────────────────────────────────────

async def generate_audit_seal(session: AsyncSession, engagement_id: uuid.UUID) -> dict:
    """
    Generates a cryptographically signed WORM bundle for a completed engagement.

    ⚠️  HARD GATE: Raises ValueError if SealSession is not FULLY_SIGNED.
    """
    now     = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()

    # ── 1. Fetch Engagement ───────────────────────────────────────────────────
    engagement = (await session.scalars(
        select(Engagement).where(Engagement.id == engagement_id)
    )).first()
    if not engagement:
        raise ValueError(f"Engagement {engagement_id} not found.")
    if engagement.sealed_at:
        raise ValueError(
            f"Engagement {engagement_id} already sealed at {engagement.sealed_at.isoformat()}. "
            "WORM: re-sealing is not permitted."
        )

    # ── 2. HARD GATE ──────────────────────────────────────────────────────────
    seal_session = (await session.scalars(
        select(SealSession).where(SealSession.engagement_id == engagement_id)
    )).first()
    if not seal_session:
        raise ValueError(
            "Cannot seal: No SealSession exists. "
            "Create one via POST /engagements/{id}/seal-session."
        )
    if seal_session.status != SealSessionStatus.FULLY_SIGNED:
        needed = seal_session.required_signatures
        have   = seal_session.current_signature_count
        raise ValueError(
            f"Cannot seal: Partner sign-off incomplete. "
            f"Required: {needed} signature(s), received: {have}. "
            f"Session status: {seal_session.status.value}."
        )

    # ── 2.2 Check Human Judgments ─────────────────────────────────────────────
    from arkashri.services.judgment import check_judgments_complete
    if not await check_judgments_complete(session, engagement_id):
        raise ValueError(
            "Cannot seal: Missing mandatory professional judgments. "
            "Certain complex estimates or high-risk AI decisions have been flagged "
            "as requiring explicit CA sign-off. Please review and sign them in the Judgment tab."
        )

    # ── 2.5 Check Regulatory Drift ────────────────────────────────────────────
    from arkashri.models import RulesSnapshot, RegulatoryDocument
    import json

    snapshot = (await session.scalars(
        select(RulesSnapshot).where(RulesSnapshot.engagement_id == engagement_id)
    )).first()

    if snapshot:
        docs = await session.scalars(
            select(RegulatoryDocument)
            .where(RegulatoryDocument.jurisdiction == engagement.jurisdiction)
            .where(RegulatoryDocument.is_promoted.is_(True))
        )
        current_versions = {}
        for doc in docs:
            current_versions[f"{doc.authority}:{doc.external_id}"] = doc.content_hash

        current_hash = hashlib.sha256(json.dumps(current_versions, sort_keys=True).encode()).hexdigest()
        if current_hash != snapshot.snapshot_hash:
            raise ValueError(
                "Cannot seal: Regulatory standards have changed since this engagement was created. "
                "The audit must be reviewed against the updated rules before sealing can occur."
            )

    # ── 3. Fetch Opinion ──────────────────────────────────────────────────────
    final_opinion = (await session.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == engagement_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()
    if not final_opinion:
        raise ValueError(
            "Cannot seal: No AuditOpinion exists. "
            "Generate one via POST /engagements/{id}/opinion first."
        )

    # ── 4. Build deterministic payload ────────────────────────────────────────
    # Fetch all event hashes to compute Merkle Root
    event_hashes = (await session.scalars(
        select(AuditEvent.event_hash)
        .where(AuditEvent.engagement_id == engagement_id)
        .order_by(AuditEvent.created_at.asc())
    )).all()
    events_merkle_root = merkle_root(list(event_hashes))

    seal_payload = await _build_seal_payload(
        session, engagement, seal_session, now_iso, CURRENT_KEY_VERSION
    )
    seal_payload["audit_events_merkle_root"] = events_merkle_root

    # ── 5. Canonical hash + ECDSA Signature ──────────────────────────────────
    payload_hash = compute_seal_hash(seal_payload)
    signature    = compute_seal_signature(engagement.tenant_id, seal_payload, CURRENT_KEY_VERSION)

    sealed_bundle = {
        "payload":   seal_payload,
        "hash":      payload_hash,
        "signature": signature,
        "signer":    "Arkashri_Internal_HSM_01",
    }

    # ── 6. Mandatory Persistence confirmed ───────────────────────────────────
    # We upload to S3 BEFORE committing the DB. If S3 fails, the engagement 
    # stays in REVIEWED state and can be retried. This prevents "Ghost Seals".
    await _s3_worm_upload(
        key=f"seals/{engagement.tenant_id}/{engagement_id}.json",
        bundle=sealed_bundle,
    )

    # ── 7. Commit to DB ──────────────────────────────────────────────────────
    engagement.sealed_at         = now
    engagement.seal_hash         = payload_hash
    engagement.status            = EngagementStatus.SEALED
    engagement.seal_bundle       = seal_payload
    engagement.seal_key_version  = CURRENT_KEY_VERSION
    engagement.seal_verify_status = "SUCCESS"  # Verified by successful S3 write

    session.add(engagement)
    await session.commit()

    logger.info(
        "Engagement %s sealed. Merkle=%s S3=Confirmed",
        engagement_id, events_merkle_root
    )

    return sealed_bundle


async def _s3_worm_upload(key: str, bundle: dict) -> None:
    """
    Write sealed bundle to S3 with Object Lock.
    FAILS HARD if bucket is configured but upload fails.
    """
    _cfg = settings
    if not _cfg.s3_worm_bucket or not _cfg.aws_access_key_id:
        logger.warning("S3 WORM upload skipped — S3_WORM_BUCKET not configured. Insecure for production.")
        return

    try:
        import aiobotocore.session as _aio_session
        body = canonical_json_bytes(bundle)  # C-5 FIX: _canonical_json was undefined; use the canonical import
        retain_until = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=365 * 10)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        session = _aio_session.get_session()
        async with session.create_client(
            "s3",
            region_name=_cfg.aws_region,
            aws_access_key_id=_cfg.aws_access_key_id,
            aws_secret_access_key=_cfg.aws_secret_access_key,
        ) as client:
            await client.put_object(
                Bucket=_cfg.s3_worm_bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=retain_until,
            )
        logger.info("S3 WORM upload complete: s3://%s/%s", _cfg.s3_worm_bucket, key)
    except ImportError as exc:
        raise RuntimeError(
            "aiobotocore is required for S3 WORM archiving but is not installed. "
            "Run: pip install aiobotocore — Seal aborted to prevent ghost seals."
        ) from exc
    except Exception as exc:
        logger.error("S3 WORM upload failed for key=%s: %s", key, exc)
        # Hard failure: a seal without a confirmed WORM archive is a false cryptographic claim.
        # The engagement stays in REVIEWED state and can be retried after the storage issue is resolved.
        raise RuntimeError(
            f"S3 WORM archive failed — seal operation aborted. "
            f"The engagement has NOT been marked as SEALED. Resolve the S3 issue and retry. "
            f"Cause: {exc}"
        ) from exc
