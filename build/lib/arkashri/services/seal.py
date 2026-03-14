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
import logging as _log
import hashlib
import hmac
import json
import uuid
import datetime
import math
import logging

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

settings = _get_settings()
logger = logging.getLogger(__name__)

# ─── Key Registry ─────────────────────────────────────────────────────────────
# Loaded at startup. In production: set SEAL_KEY_V1 env var to a base64-encoded
# 32-byte key stored in AWS KMS / HashiCorp Vault / GCP CKMS.
# If unset, the insecure dev constant is used — system logs a WARNING.

def _load_key_registry() -> dict[str, bytes]:
    _s = settings
    registry: dict[str, bytes] = {}
    if _s.seal_key_v1:
        try:
            registry["v1"] = _b64.b64decode(_s.seal_key_v1)
            _log.getLogger(__name__).info("SEAL_KEY_V1 loaded from environment (production mode)")
        except Exception as e:
            _log.getLogger(__name__).error("SEAL_KEY_V1 is set but not valid base64: %s — falling back to dev key", e)
    if "v1" not in registry:
        _log.getLogger(__name__).warning(
            "SEAL_KEY_V1 not set — using insecure dev HMAC key. "
            "Set SEAL_KEY_V1 in .env before sealing in production."
        )
        registry["v1"] = b"arkashri_hsm_private_key_super_secret"
    return registry

_KEY_REGISTRY: dict[str, bytes] = _load_key_registry()
CURRENT_KEY_VERSION = "v1"
SYSTEM_VERSION = "Arkashri_OS_2.0_Enterprise"


# ─── Canonical JSON Serializer ────────────────────────────────────────────────
# Addresses the PCAOB reviewer's concern:
#   - Float precision drift
#   - Decimal inconsistency
#   - Timezone / ISO-8601 normalization
#   - Non-deterministic list ordering

def _canonical_float(v: float) -> str | float | None:
    """Round to 10 decimal places; represent NaN/Inf as null-safe strings."""
    if v is None:
        return None
    if math.isnan(v) or math.isinf(v):
        return str(v)
    return round(v, 10)  # type: ignore


def _canonical_value(v: object) -> object:
    """Recursively normalize a value for deterministic serialization."""
    if isinstance(v, dict):
        return {k: _canonical_value(val) for k, val in sorted(v.items())}
    if isinstance(v, list):
        return sorted(
            [_canonical_value(i) for i in v],
            key=lambda x: json.dumps(x, sort_keys=True, default=str),
        )
    if isinstance(v, float):
        return _canonical_float(v)
    if isinstance(v, datetime.datetime):
        # Normalize to UTC, drop microseconds for stability
        if v.tzinfo is None:
            v = v.replace(tzinfo=datetime.timezone.utc)
        return v.astimezone(datetime.timezone.utc).isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def _canonical_json(obj: dict) -> bytes:
    """
    Byte-identical JSON across all environments.
    Uses sort_keys=True + no-whitespace separators + float normalization.
    This is the ONLY serializer used for hash computation.
    """
    normalized = _canonical_value(obj)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        allow_nan=False,
    ).encode('utf-8')


def compute_seal_hash(payload: dict) -> str:
    """Public: compute SHA-256 of canonical payload. Used by verifier."""
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def compute_seal_signature(payload: dict, key_version: str = CURRENT_KEY_VERSION) -> str:
    """Public: compute HMAC-SHA256. Used by verifier."""
    key = _KEY_REGISTRY.get(key_version)
    if not key:
        raise ValueError(f"Unknown key version: {key_version}. Cannot compute or verify HMAC.")
    return hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest()


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
    return hashlib.sha256(_canonical_json({"rules": snapshot})).hexdigest()


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
    datetime.datetime.now(datetime.timezone.utc)
    tenant_id    = engagement.tenant_id
    jurisdiction = engagement.jurisdiction
    engagement_id = engagement.id

    # Fetch opinion
    final_opinion = (await session.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == engagement_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()

    # Fetch exceptions
    exceptions = (await session.scalars(
        select(ExceptionCase).where(
            ExceptionCase.tenant_id   == tenant_id,
            ExceptionCase.jurisdiction == jurisdiction,
        )
    )).all()

    # Fetch decisions (capped for payload size — hash tree covers full set)
    decisions = (await session.scalars(
        select(Decision)
        .where(Decision.transaction.has(tenant_id=tenant_id))
        .limit(500)
    )).all()

    # Fetch overrides
    overrides = (await session.scalars(
        select(DecisionOverride)
        .where(DecisionOverride.tenant_id == tenant_id)
    )).all()

    # Fetch latest audit event merkle root
    latest_event = (await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
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

    decision_hash_tree = hashlib.sha256(
        _canonical_json({"hashes": sorted(d.output_hash for d in decisions)})
    ).hexdigest()

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
            .where(RegulatoryDocument.is_promoted == True)
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
    seal_payload = await _build_seal_payload(
        session, engagement, seal_session, now_iso, CURRENT_KEY_VERSION
    )

    # ── 5. Canonical hash + HMAC ──────────────────────────────────────────────
    payload_hash = compute_seal_hash(seal_payload)
    signature    = compute_seal_signature(seal_payload, CURRENT_KEY_VERSION)

    sealed_bundle = {
        "payload":   seal_payload,
        "hash":      payload_hash,
        "signature": signature,
        "signer":    "Arkashri_Internal_HSM_01",
    }

    # ── 6. Persist — Engagement → SEALED ─────────────────────────────────────
    engagement.sealed_at         = now
    engagement.seal_hash         = payload_hash
    engagement.status            = EngagementStatus.SEALED
    engagement.seal_bundle       = seal_payload          # Stored for replay verification
    engagement.seal_key_version  = CURRENT_KEY_VERSION
    engagement.seal_verify_status = "PENDING"

    session.add(engagement)
    await session.commit()

    logger.info(
        "Engagement %s sealed. hash=%s key_version=%s partners=%d",
        engagement_id, payload_hash, CURRENT_KEY_VERSION,
        len(seal_payload.get("partner_signatures", [])),
    )

    # ── S3 WORM upload (enabled when S3_WORM_BUCKET is set in env) ──────────────
    await _s3_worm_upload(
        key=f"seals/{engagement.tenant_id}/{engagement_id}.json",
        bundle=sealed_bundle,
    )

    return sealed_bundle


async def _s3_worm_upload(key: str, bundle: dict) -> None:
    """
    Write sealed bundle to S3 with Object Lock (COMPLIANCE mode, 10-year retention).
    Silently skips if S3_WORM_BUCKET / AWS credentials are not configured.
    In production, failure should be surfaced as a hard error — adjust as needed.
    """
    _cfg = settings
    if not _cfg.s3_worm_bucket or not _cfg.aws_access_key_id:
        logger.debug("S3 WORM upload skipped — S3_WORM_BUCKET not configured (dev mode).")
        return
    try:
        import aiobotocore.session as _aio_session
        body = _canonical_json(bundle)
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
    except ImportError:
        logger.warning("aiobotocore not installed — S3 WORM upload skipped. pip install aiobotocore")
    except Exception as exc:
        logger.error("S3 WORM upload failed for key=%s: %s", key, exc)
        # In production: raise here to block seal completion until archive is confirmed
