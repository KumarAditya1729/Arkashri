# pyre-ignore-all-errors
import os
import uuid
import datetime
import structlog

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import Engagement, AuditOpinion, SealSession
from arkashri.config import get_settings

logger = structlog.get_logger("services.audit_export")

async def generate_regulatory_pdf(
    db: AsyncSession,
    engagement_id: uuid.UUID,
    include_evidence: bool = True
) -> str:
    """
    Generates a professional, regulator-ready PDF report of an engagement.
    Uses WeasyPrint for CSS-driven PDF generation.
    Returns the file path to the generated PDF.
    """
    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    
    # 1. Gather all data
    eng = (await db.scalars(select(Engagement).where(Engagement.id == engagement_id))).first()
    if not eng:
        raise ValueError("Engagement not found")
        
    opinion = (await db.scalars(
        select(AuditOpinion)
        .where(AuditOpinion.engagement_id == engagement_id)
        .order_by(AuditOpinion.created_at.desc())
    )).first()
    
    seal_sess = (await db.scalars(
        select(SealSession).where(SealSession.engagement_id == engagement_id)
    )).first()

    # 2. Build the report HTML payload.
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: sans-serif; color: #333; }}
            .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; }}
            .opinion-box {{ border: 1px solid #ccc; padding: 20px; margin-top: 20px; }}
            .seal-hash {{ font-family: monospace; background: #eee; padding: 5px; }}
            .watermark {{ color: #ccc; font-size: 80px; position: absolute; rotate: -45deg; opacity: 0.1; }}
        </style>
    </head>
    <body>
        <div class="watermark">ARKASHRI REGULATORY</div>
        <div class="header">
            <h1>Independent Auditor's Report</h1>
            <p><strong>Client:</strong> {eng.client_name}</p>
            <p><strong>Engagement ID:</strong> {eng.id}</p>
            <p><strong>Date:</strong> {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
        </div>
        
        <div class="opinion-box">
            <h2>Audit Opinion: {opinion.opinion_type.value if opinion else "PENDING"}</h2>
            <p>{opinion.basis_for_opinion if opinion else "Opinion not yet finalized."}</p>
        </div>

        <h3>Cryptographic Assurance</h3>
        <p>This report is backed by a blockchain-anchored Merkle root. Any tampering with the underlying evidence will invalidate the seal.</p>
        <p><strong>Blockchain Seal Hash:</strong> <span class="seal-hash">{eng.seal_hash or "NOT_YET_SEALED"}</span></p>
        
        <h3>Signatories</h3>
        <ul>
            {"".join([f"<li>{s.partner_email} ({s.role.value}) - {s.signed_at.isoformat()}</li>" for s in (seal_sess.signatures if seal_sess else []) if not s.withdrawn_at])}
        </ul>
    </body>
    </html>
    """

    filename = f"report_{engagement_id}_{int(datetime.datetime.now().timestamp())}.pdf"
    file_path = os.path.join(settings.upload_dir, filename)

    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(file_path)
        logger.info("regulatory_pdf_generated", path=file_path, engagement_id=str(engagement_id))
        return file_path
    except Exception as e:
        logger.error("pdf_generation_failed", error=str(e), engagement_id=str(engagement_id))
        raise RuntimeError("Regulatory PDF generation failed") from e
