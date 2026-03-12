import uuid
import datetime
import io
import zipfile
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from arkashri.models import (
    Engagement, 
    SAChecklistItem, 
    SAChecklistStatus,
    AuditOpinion
)

SA_REQUIREMENTS = [
    {"ref": "SA 200", "req": "Overall Objectives of the Independent Auditor and the Conduct of an Audit in Accordance with Standards on Auditing"},
    {"ref": "SA 210", "req": "Agreeing the Terms of Audit Engagements"},
    {"ref": "SA 220", "req": "Quality Control for an Audit of Financial Statements"},
    {"ref": "SA 230", "req": "Audit Documentation"},
    {"ref": "SA 240", "req": "The Auditor's Responsibilities Relating to Fraud in an Audit of Financial Statements"},
    {"ref": "SA 250", "req": "Consideration of Laws and Regulations in an Audit of Financial Statements"},
    {"ref": "SA 260", "req": "Communication with Those Charged with Governance"},
    {"ref": "SA 265", "req": "Communicating Deficiencies in Internal Control to Those Charged with Governance and Management"},
    {"ref": "SA 300", "req": "Planning an Audit of Financial Statements"},
    {"ref": "SA 315", "req": "Identifying and Assessing the Risks of Material Misstatement through Understanding the Entity and Its Environment"},
    {"ref": "SA 320", "req": "Materiality in Planning and Performing an Audit"},
    {"ref": "SA 330", "req": "The Auditor's Responses to Assessed Risks"},
    {"ref": "SA 402", "req": "Audit Considerations Relating to an Entity Using a Service Organisation"},
    {"ref": "SA 450", "req": "Evaluation of Misstatements Identified during the Audit"},
    {"ref": "SA 500", "req": "Audit Evidence"},
    {"ref": "SA 501", "req": "Audit Evidence—Specific Considerations for Selected Items"},
    {"ref": "SA 505", "req": "External Confirmations"},
    {"ref": "SA 510", "req": "Initial Audit Engagements – Opening Balances"},
    {"ref": "SA 520", "req": "Analytical Procedures"},
    {"ref": "SA 530", "req": "Audit Sampling"},
    {"ref": "SA 540", "req": "Auditing Accounting Estimates, Including Fair Value Accounting Estimates, and Related Disclosures"},
    {"ref": "SA 550", "req": "Related Parties"},
    {"ref": "SA 560", "req": "Subsequent Events"},
    {"ref": "SA 570", "req": "Going Concern"},
    {"ref": "SA 580", "req": "Written Representations"},
    {"ref": "SA 600", "req": "Using the Work of Another Auditor"},
    {"ref": "SA 610", "req": "Using the Work of Internal Auditors"},
    {"ref": "SA 620", "req": "Using the Work of an Auditor's Expert"},
    {"ref": "SA 700", "req": "Forming an Opinion and Reporting on Financial Statements"},
    {"ref": "SA 701", "req": "Communicating Key Audit Matters in the Independent Auditor's Report"},
    {"ref": "SA 705", "req": "Modifications to the Opinion in the Independent Auditor's Report"},
    {"ref": "SA 706", "req": "Emphasis of Matter Paragraphs and Other Matter Paragraphs in the Independent Auditor's Report"},
    {"ref": "SA 710", "req": "Comparative Information—Corresponding Figures and Comparative Financial Statements"},
    {"ref": "SA 720", "req": "The Auditor's Responsibilities Relating to Other Information"}
]

async def generate_sa_checklist(session: AsyncSession, engagement_id: uuid.UUID) -> list[SAChecklistItem]:
    """Generates a comprehensive SA 200-720 checklist for the given engagement."""
    existing = (await session.scalars(select(SAChecklistItem).where(SAChecklistItem.engagement_id == engagement_id))).all()
    if existing:
        return existing
    
    items = []
    for req in SA_REQUIREMENTS:
        item = SAChecklistItem(
            engagement_id=engagement_id,
            standard_ref=req["ref"],
            requirement=req["req"],
            status=SAChecklistStatus.PENDING
        )
        session.add(item)
        items.append(item)
    
    await session.commit()
    for item in items:
        await session.refresh(item)
    return items


async def generate_nfra_package(session: AsyncSession, engagement_id: uuid.UUID) -> bytes:
    """
    Bundles the cryptographic seal, opinion, structured evidence, and the 
    completed SA 200-720 checklist into an NFRA-compliant Zip submission package.
    """
    engagement = await session.scalar(select(Engagement).where(Engagement.id == engagement_id))
    if not engagement:
        raise ValueError("Engagement not found")
        
    checklist = (await session.scalars(select(SAChecklistItem).where(SAChecklistItem.engagement_id == engagement_id))).all()
    opinion = (await session.scalars(select(AuditOpinion).where(AuditOpinion.engagement_id == engagement_id).order_by(AuditOpinion.created_at.desc()))).first()
    
    out = io.BytesIO()
    with zipfile.ZipFile(out, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Engagement Summary Statement
        eng_data = {
            "id": str(engagement.id),
            "client_name": engagement.client_name,
            "status": engagement.status.value,
            "seal_hash": engagement.seal_hash,
            "sealed_at": engagement.sealed_at.isoformat() if engagement.sealed_at else None
        }
        zf.writestr("engagement_summary.json", json.dumps(eng_data, indent=2))
        
        # 2. SA Compliance Checklist
        if checklist:
            chk_data = [{"standard": c.standard_ref, "requirement": c.requirement, "status": c.status.value, "verified_by": c.verified_by, "verified_at": c.verified_at.isoformat() if c.verified_at else None} for c in checklist]
            zf.writestr("sa_compliance_checklist.json", json.dumps(chk_data, indent=2))
            
        # 3. Final Audit Opinion
        if opinion:
            op_data = {
                "type": opinion.opinion_type.value,
                "basis": opinion.basis_for_opinion,
                "is_signed": opinion.is_signed,
                "hash": opinion.opinion_hash
            }
            zf.writestr("audit_opinion.json", json.dumps(op_data, indent=2))
            
        # 4. Cryptographic Seal Bundle (WORM Verification)
        if engagement.seal_bundle:
            zf.writestr("cryptographic_seal.json", json.dumps(engagement.seal_bundle, indent=2))
            
    return out.getvalue()
