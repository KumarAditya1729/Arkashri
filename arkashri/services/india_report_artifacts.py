from __future__ import annotations

import base64
import copy
import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jinja2
import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.models import Engagement, ReportJob
from arkashri.config import get_settings
from arkashri.services.india_udin import verify_public_report
from arkashri.services.object_storage import object_storage_service

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
REPORT_TEMPLATE = "india_statutory_report.html"


class IndiaReportArtifactError(ValueError):
    pass


@dataclass
class IndiaReportArtifact:
    filename: str
    content_type: str
    body: str | bytes
    verification_url: str
    qr_code_data_url: str
    render_context: dict[str, Any]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "report"


def _build_qr_data_url(value: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def _build_filename(payload: dict[str, Any], extension: str) -> str:
    client_name = str(payload.get("client_name") or "client")
    period_end = str(payload.get("reporting_period_end") or payload.get("generated_at") or "")
    period_label = re.sub(r"[^0-9]", "", period_end)[:8] or "final"
    return f"{_slugify(client_name)}-india-statutory-audit-{period_label}.{extension}"


def _build_gst_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    highlights = payload.get("report_sections", {}).get("gst_highlights") or {}
    sections: list[dict[str, Any]] = []
    for recon_key, recon in highlights.items():
        sections.append(
            {
                "key": recon_key,
                "title": recon_key.replace("_", " ").upper(),
                "summary": copy.deepcopy(recon.get("summary") or {}),
                "mismatches": copy.deepcopy(recon.get("mismatches") or []),
            }
        )
    return sections


def _build_tally_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tally_summary = payload.get("report_sections", {}).get("tally_import_summary") or {}
    sections: list[dict[str, Any]] = []
    for key, value in tally_summary.items():
        sections.append(
            {
                "key": key,
                "title": key.replace("_", " ").title(),
                "details": copy.deepcopy(value if isinstance(value, dict) else {"value": value}),
            }
        )
    return sections


def _build_context(
    payload: dict[str, Any],
    *,
    report_id: str,
    report_hash: str,
    verification_url: str,
    qr_code_data_url: str,
    seal_summary: dict[str, Any],
) -> dict[str, Any]:
    report_sections = payload.get("report_sections") or {}
    readiness = payload.get("workspace_readiness") or {}
    return {
        "report_id": report_id,
        "report_hash": report_hash,
        "report_type": payload.get("report_type"),
        "client_name": payload.get("client_name"),
        "engagement_id": payload.get("engagement_id"),
        "engagement_type": payload.get("engagement_type"),
        "jurisdiction": payload.get("jurisdiction"),
        "generated_at": payload.get("generated_at"),
        "is_draft": bool(payload.get("is_draft")),
        "mca_company_master": copy.deepcopy(payload.get("mca_company_master") or {}),
        "opinions": {
            "opinion": report_sections.get("opinion") or {},
            "basis_for_opinion": report_sections.get("basis_for_opinion") or {},
            "other_information": report_sections.get("other_information") or {},
            "management_responsibility": report_sections.get("management_responsibility") or {},
            "auditor_responsibility": report_sections.get("auditor_responsibility") or {},
        },
        "key_audit_matters": copy.deepcopy(report_sections.get("key_audit_matters") or []),
        "caro_annexure": copy.deepcopy(report_sections.get("caro_annexure") or []),
        "gst_sections": _build_gst_sections(payload),
        "tally_sections": _build_tally_sections(payload),
        "reporting_pack": copy.deepcopy(payload.get("reporting_pack") or {}),
        "readiness": readiness,
        "readiness_blockers": copy.deepcopy(readiness.get("blockers") or []),
        "udin": copy.deepcopy(payload.get("udin") or {"status": "NOT_GENERATED"}),
        "verification_url": verification_url,
        "qr_code_data_url": qr_code_data_url,
        "seal_summary": seal_summary,
    }


def _render_html(context: dict[str, Any]) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(REPORT_TEMPLATE)
    return template.render(**context)


def _render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise IndiaReportArtifactError(
            "PDF rendering is unavailable because native WeasyPrint dependencies are not installed."
        ) from exc
    return HTML(string=html).write_pdf()


async def render_india_report_artifact(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    tenant_id: str,
    format: Literal["html", "pdf"],
    verification_base_url: str,
) -> IndiaReportArtifact:
    report = await session.scalar(
        select(ReportJob).where(
            ReportJob.id == report_id,
            ReportJob.tenant_id == tenant_id,
        )
    )
    if report is None:
        raise IndiaReportArtifactError("Report not found.")

    payload = copy.deepcopy(report.report_payload or {})
    if payload.get("report_type") != "INDIA_STATUTORY_AUDIT":
        raise IndiaReportArtifactError("Rendered artifacts are only supported for India statutory audit reports.")

    verification_url = f"{verification_base_url.rstrip('/')}/{report.report_hash}"
    qr_code_data_url = _build_qr_data_url(verification_url)
    verification = await verify_public_report(session, report_hash=report.report_hash)
    seal_summary = copy.deepcopy(verification.get("seal") or {})
    context = _build_context(
        payload,
        report_id=str(report.id),
        report_hash=report.report_hash,
        verification_url=verification_url,
        qr_code_data_url=qr_code_data_url,
        seal_summary=seal_summary,
    )
    html = _render_html(context)

    if format == "html":
        return IndiaReportArtifact(
            filename=_build_filename(payload, "html"),
            content_type="text/html; charset=utf-8",
            body=html,
            verification_url=verification_url,
            qr_code_data_url=qr_code_data_url,
            render_context=context,
        )

    pdf_bytes = _render_pdf(html)
    return IndiaReportArtifact(
        filename=_build_filename(payload, "pdf"),
        content_type="application/pdf",
        body=pdf_bytes,
        verification_url=verification_url,
        qr_code_data_url=qr_code_data_url,
        render_context=context,
    )


async def persist_india_report_artifact(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    tenant_id: str,
    format: Literal["html", "pdf"],
    verification_base_url: str,
    actor_id: str,
) -> dict[str, Any]:
    artifact = await render_india_report_artifact(
        session,
        report_id=report_id,
        tenant_id=tenant_id,
        format=format,
        verification_base_url=verification_base_url,
    )
    body = artifact.body.encode("utf-8") if isinstance(artifact.body, str) else artifact.body
    settings = get_settings()
    stored = await object_storage_service.save_bytes(
        tenant_id=tenant_id,
        category="report-artifacts",
        filename=artifact.filename,
        content=body,
        content_type=artifact.content_type,
        bucket=settings.report_artifact_s3_bucket or settings.evidence_s3_bucket,
    )

    report = await session.scalar(
        select(ReportJob).where(
            ReportJob.id == report_id,
            ReportJob.tenant_id == tenant_id,
        )
    )
    if report is None:
        raise IndiaReportArtifactError("Report not found.")

    payload = report.report_payload or {}
    engagement_id = payload.get("engagement_id")
    if not engagement_id:
        raise IndiaReportArtifactError("Report payload is missing engagement context.")

    engagement = await session.scalar(
        select(Engagement).where(
            Engagement.id == uuid.UUID(str(engagement_id)),
            Engagement.tenant_id == tenant_id,
        )
    )
    if engagement is None:
        raise IndiaReportArtifactError("Linked engagement not found.")

    artifact_record = {
        "filename": artifact.filename,
        "content_type": artifact.content_type,
        "uri": stored.uri,
        "provider": stored.provider,
        "bucket": stored.bucket,
        "key": stored.key,
        "persisted_by": actor_id,
        "report_hash": report.report_hash,
    }
    metadata = copy.deepcopy(engagement.state_metadata or {})
    metadata.setdefault("report_artifacts", {})
    metadata["report_artifacts"].setdefault(str(report.id), {})
    metadata["report_artifacts"][str(report.id)][format] = artifact_record
    engagement.state_metadata = metadata
    session.add(engagement)
    await session.commit()
    return copy.deepcopy(artifact_record)
