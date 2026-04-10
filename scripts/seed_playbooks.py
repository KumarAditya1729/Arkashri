import asyncio
import json
from pathlib import Path
from sqlalchemy import select

from arkashri.db import AsyncSessionLocal
from arkashri.models import AuditPlaybook, EngagementType

ROOT_DIR = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT_DIR / "workflow_pack"
INDEX_PATH = PACK_DIR / "index.json"

MAPPING = {
    "financial_audit": EngagementType.FINANCIAL_AUDIT,
    "internal_audit": EngagementType.INTERNAL_AUDIT,
    "external_audit": EngagementType.EXTERNAL_AUDIT,
    "statutory_audit": EngagementType.STATUTORY_AUDIT,
    "compliance_audit": EngagementType.COMPLIANCE_AUDIT,
    "operational_audit": EngagementType.OPERATIONAL_AUDIT,
    "tax_audit": EngagementType.TAX_AUDIT,
    "it_audit": EngagementType.IT_AUDIT,
    "forensic_audit": EngagementType.FORENSIC_AUDIT,
    "performance_audit": EngagementType.PERFORMANCE_AUDIT,
    "environmental_audit": EngagementType.ENVIRONMENTAL_AUDIT,
    "payroll_audit": EngagementType.PAYROLL_AUDIT,
    "quality_audit": EngagementType.QUALITY_AUDIT,
    "single_audit": EngagementType.SINGLE_AUDIT,
    "esg_deep_audit": EngagementType.ENVIRONMENTAL_AUDIT,
    "forensic_risk_profile": EngagementType.FORENSIC_AUDIT,
}

async def seed_playbooks():
    print("Reading workflow_pack/index.json...")
    with open(INDEX_PATH, "r") as f:
        index = json.load(f)
    
    async with AsyncSessionLocal() as session:
        for item in index["templates"]:
            audit_type_str = item["audit_type"]
            path = item["path"]
            
            engagement_type = MAPPING.get(audit_type_str)
            if not engagement_type:
                print(f"Skipping unknown type: {audit_type_str}")
                continue
                
            template_path = PACK_DIR / path
            if not template_path.exists():
                print(f"Template file not found: {template_path}")
                continue
                
            with open(template_path, "r") as tf:
                template = json.load(tf)
                
            workflow_id = template.get("workflow_id", audit_type_str)
            objective = template.get("objective", "")
            phases = template.get("phases", [])
            
            # Check if playbook already exists
            existing = await session.scalar(
                select(AuditPlaybook).where(
                    AuditPlaybook.workflow_template_id == workflow_id
                )
            )
            if existing:
                print(f"Playbook for {workflow_id} already exists, skipping.")
                continue
                
            print(f"Adding playbook for {workflow_id} ({engagement_type})...")
            playbook = AuditPlaybook(
                audit_type=engagement_type,
                sector=None,
                playbook_name=workflow_id.replace('_', ' ').title(),
                description=objective[:500] if objective else None,
                workflow_template_id=workflow_id,
                required_phases={"phases": phases},  # Wrap list in dict for Pydantic/JSON compatibility
                is_active=True,
                version=1
            )
            session.add(playbook)
            
        await session.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_playbooks())
