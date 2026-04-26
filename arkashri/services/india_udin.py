from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, ReportJob
from arkashri.services.canonical import hash_object
from arkashri.services.seal_verify import verify_audit_seal


class UDINError(ValueError):
    pass


def _build_assisted_udin(report_hash: str, generated_at: datetime) -> str:
    return f"UDIN-ASSISTED-{generated_at.strftime('%Y%m')}-{report_hash[:12].upper()}"


async def generate_report_udin(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    tenant_id: str,
    generated_by: str,
    member_id: str | None = None,
) -> ReportJob:
    report = await session.scalar(
        select(ReportJob).where(
            ReportJob.id == report_id,
            ReportJob.tenant_id == tenant_id,
        )
    )
    if report is None:
        raise UDINError("Report not found.")

    payload = copy.deepcopy(report.report_payload or {})
    if payload.get("report_type") != "INDIA_STATUTORY_AUDIT":
        raise UDINError("UDIN can only be generated for India statutory audit reports.")
    if payload.get("is_draft"):
        raise UDINError("UDIN cannot be generated for a draft report.")

    existing_udin = payload.get("udin")
    if isinstance(existing_udin, dict) and existing_udin.get("number"):
        return report

    engagement_id = payload.get("engagement_id")
    if not engagement_id:
        raise UDINError("Report payload is missing engagement context.")

    engagement = await session.scalar(select(Engagement).where(Engagement.id == uuid.UUID(str(engagement_id))))
    if engagement is None:
        raise UDINError("Linked engagement not found.")

    now = datetime.now(timezone.utc)
    udin_number = _build_assisted_udin(report.report_hash, now)
    verification_hash = hash_object(
        {
            "report_id": str(report.id),
            "report_hash": report.report_hash,
            "engagement_id": str(engagement.id),
            "udin_number": udin_number,
        }
    )

    payload["udin"] = {
        "number": udin_number,
        "status": "GENERATED",
        "mode": "ASSISTED",
        "generated_at": now.isoformat(),
        "generated_by": generated_by,
        "member_id": member_id,
        "verification_hash": verification_hash,
    }
    report.report_payload = payload
    report.report_hash = hash_object(payload)
    session.add(report)

    engagement_metadata = copy.deepcopy(engagement.state_metadata or {})
    engagement_metadata.setdefault("history", [])
    engagement_metadata.setdefault("udin_requests", {})
    engagement_metadata["udin_requests"][str(report.id)] = payload["udin"]
    engagement_metadata["history"].append(
        {
            "timestamp": now.isoformat(),
            "actor": generated_by,
            "action": "UDIN_GENERATED",
            "report_id": str(report.id),
            "udin_number": udin_number,
        }
    )
    engagement.state_metadata = engagement_metadata
    session.add(engagement)
    await session.commit()
    await session.refresh(report)
    return report


async def get_report_udin(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    tenant_id: str,
) -> dict[str, Any]:
    report = await session.scalar(
        select(ReportJob).where(
            ReportJob.id == report_id,
            ReportJob.tenant_id == tenant_id,
        )
    )
    if report is None:
        raise UDINError("Report not found.")
    payload = report.report_payload or {}
    return copy.deepcopy(payload.get("udin") or {})


async def verify_public_report(
    session: AsyncSession,
    *,
    report_hash: str,
) -> dict[str, Any]:
    report = await session.scalar(select(ReportJob).where(ReportJob.report_hash == report_hash))
    if report is None:
        raise UDINError("Report not found.")

    payload = copy.deepcopy(report.report_payload or {})
    recomputed_hash = hash_object(payload)
    report_integrity = recomputed_hash == report.report_hash

    engagement_id = payload.get("engagement_id")
    engagement = None
    seal_result: dict[str, Any] | None = None
    if engagement_id:
        engagement = await session.scalar(select(Engagement).where(Engagement.id == uuid.UUID(str(engagement_id))))
        if engagement is not None:
            seal_verification = await verify_audit_seal(session, engagement.id)
            seal_result = seal_verification.to_dict()

    return {
        "report_id": str(report.id),
        "report_type": payload.get("report_type"),
        "client_name": payload.get("client_name"),
        "engagement_id": engagement_id,
        "generated_at": payload.get("generated_at"),
        "report_hash": report.report_hash,
        "report_integrity": {
            "stored_hash": report.report_hash,
            "computed_hash": recomputed_hash,
            "match": report_integrity,
        },
        "udin": payload.get("udin") or {"status": "NOT_GENERATED"},
        "seal": seal_result
        or {
            "status": "NOT_SEALED",
            "engagement_id": engagement_id,
            "stored_hash": engagement.seal_hash if engagement else None,
            "computed_hash": None,
            "hash_match": False,
            "hmac_match": False,
            "partner_sig_checks": [],
            "merkle_match": None,
            "mismatch_details": ["Engagement has not been sealed yet."],
            "key_version": engagement.seal_key_version if engagement else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        },
    }
