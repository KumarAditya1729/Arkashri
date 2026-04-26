from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, ReportJob, ReportStatus
from arkashri.services.canonical import hash_object
from arkashri.services.gst_reconciliation import get_gst_reconciliations
from arkashri.services.india_audit_workspace import compute_workspace_readiness, get_india_workspace


class IndiaReportError(ValueError):
    pass


def _latest_tally_summary(engagement: Engagement) -> dict[str, Any]:
    metadata = engagement.state_metadata or {}
    return dict(metadata.get("tally_imports") or {})


def _build_key_audit_matters(workspace: dict[str, Any], readiness: dict[str, Any]) -> list[dict[str, Any]]:
    matters: list[dict[str, Any]] = []
    for paper in workspace["working_papers"]:
        if paper["status"] in {"PREPARED", "REVIEWED", "FINAL"}:
            matters.append(
                {
                    "title": paper["title"],
                    "audit_area": paper["audit_area"],
                    "status": paper["status"],
                    "linked_checklist_codes": paper.get("linked_checklist_codes", []),
                }
            )
    if not matters:
        matters.append(
            {
                "title": "Audit execution still in progress",
                "audit_area": "Planning",
                "status": "DRAFT",
                "linked_checklist_codes": [blocker["code"] for blocker in readiness["blockers"]],
            }
        )
    return matters


def _build_caro_annexure(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    caro_items: list[dict[str, Any]] = []
    for section in workspace["checklist_sections"]:
        if section["section_code"] != "CARO2020":
            continue
        for item in section["items"]:
            caro_items.append(
                {
                    "clause_ref": item["clause_ref"],
                    "title": item["title"],
                    "status": item["status"],
                    "response": item["response"],
                    "notes": item["notes"],
                }
            )
    return caro_items


def _build_basis_for_opinion(readiness: dict[str, Any], draft_mode: bool) -> str:
    if readiness["is_report_ready"]:
        return (
            "The engagement file evidences completion of required SA/CARO procedures, "
            "working papers, and review gates needed for report issuance."
        )
    blocker_codes = ", ".join(blocker["code"] for blocker in readiness["blockers"])
    status_label = "draft" if draft_mode else "blocked"
    return (
        f"This {status_label} report was generated before final report readiness. "
        f"Outstanding blockers: {blocker_codes}."
    )


async def generate_india_statutory_report(
    session: AsyncSession,
    *,
    engagement_id: uuid.UUID,
    tenant_id: str,
    allow_draft: bool,
) -> ReportJob:
    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == engagement_id,
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise IndiaReportError("Engagement not found.")

    try:
        workspace = get_india_workspace(engagement)
    except ValueError as exc:
        raise IndiaReportError(str(exc)) from exc

    readiness = compute_workspace_readiness(engagement)
    if not readiness["is_report_ready"] and not allow_draft:
        blocker_codes = ", ".join(blocker["code"] for blocker in readiness["blockers"])
        raise IndiaReportError(
            "Statutory report is not ready for final generation. "
            f"Outstanding blockers: {blocker_codes}."
        )

    gst_reconciliations = await get_gst_reconciliations(
        session,
        engagement_id=engagement_id,
        tenant_id=tenant_id,
    )
    tally_imports = _latest_tally_summary(engagement)
    now = datetime.now(timezone.utc)

    report_payload = {
        "report_type": "INDIA_STATUTORY_AUDIT",
        "engagement_id": str(engagement.id),
        "client_name": engagement.client_name,
        "jurisdiction": engagement.jurisdiction,
        "engagement_type": engagement.engagement_type.value,
        "generated_at": now.isoformat(),
        "is_draft": not readiness["is_report_ready"],
        "workspace_readiness": readiness,
        "report_sections": {
            "opinion": {
                "title": "Opinion",
                "text": (
                    "In our opinion, the accompanying financial statements give the information "
                    "required by the Companies Act and present a true and fair view in conformity "
                    "with the applicable accounting principles generally accepted in India."
                    if readiness["is_report_ready"]
                    else "Draft opinion withheld pending completion of mandatory audit procedures."
                ),
            },
            "basis_for_opinion": {
                "title": "Basis for Opinion",
                "text": _build_basis_for_opinion(readiness, allow_draft),
            },
            "key_audit_matters": _build_key_audit_matters(workspace, readiness),
            "other_information": {
                "title": "Other Information",
                "text": "Management is responsible for the other information included in the annual report and related records.",
            },
            "management_responsibility": {
                "title": "Management Responsibility",
                "text": "Management is responsible for the preparation of the financial statements and maintenance of adequate accounting records.",
            },
            "auditor_responsibility": {
                "title": "Auditor Responsibility",
                "text": "Our responsibility is to express an opinion based on our audit conducted in accordance with Standards on Auditing issued by ICAI.",
            },
            "caro_annexure": _build_caro_annexure(workspace),
            "gst_highlights": gst_reconciliations,
            "tally_import_summary": tally_imports,
        },
        "reporting_pack": workspace.get("reporting_pack", {}),
        "source_traces": {
            "working_papers": workspace["working_papers"],
            "checklist_sections": workspace["checklist_sections"],
        },
    }

    report = ReportJob(
        tenant_id=tenant_id,
        jurisdiction=engagement.jurisdiction,
        period_start=engagement.period_start or now,
        period_end=engagement.period_end or now,
        status=ReportStatus.GENERATED,
        report_hash=hash_object(report_payload),
        report_payload=report_payload,
        created_at=now,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report
