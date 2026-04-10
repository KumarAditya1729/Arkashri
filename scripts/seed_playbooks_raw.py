import asyncio
import json
import uuid
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from arkashri.config import get_settings

ROOT_DIR = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT_DIR / "workflow_pack"
INDEX_PATH = PACK_DIR / "index.json"

MAPPING = {
    "financial_audit": "FINANCIAL_AUDIT",
    "internal_audit": "INTERNAL_AUDIT",
    "external_audit": "EXTERNAL_AUDIT",
    "statutory_audit": "STATUTORY_AUDIT",
    "compliance_audit": "COMPLIANCE_AUDIT",
    "operational_audit": "OPERATIONAL_AUDIT",
    "tax_audit": "TAX_AUDIT",
    "it_audit": "IT_AUDIT",
    "forensic_audit": "FORENSIC_AUDIT",
    "performance_audit": "PERFORMANCE_AUDIT",
    "environmental_audit": "ENVIRONMENTAL_AUDIT",
    "payroll_audit": "PAYROLL_AUDIT",
    "quality_audit": "QUALITY_AUDIT",
    "single_audit": "SINGLE_AUDIT",
    "esg_deep_audit": "ENVIRONMENTAL_AUDIT",
    "forensic_risk_profile": "FORENSIC_AUDIT",
}

async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    
    print("Reading workflow_pack/index.json...")
    with open(INDEX_PATH, "r") as f:
        index = json.load(f)
        
    async with engine.connect() as conn:
        # Get existing template IDs to avoid duplicates
        result = await conn.execute(text("SELECT workflow_template_id FROM audit_playbook"))
        existing_ids = {row[0] for row in result.all()}
        
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
            
            if workflow_id in existing_ids:
                print(f"Playbook {workflow_id} already exists, skipping.")
                continue
                
            print(f"Inserting playbook for {workflow_id}...")
            
            # Use raw SQL to bypass SQLAlchemy type mapping issues with poolers
            sql = """
            INSERT INTO audit_playbook (
                id, audit_type, sector, playbook_name, description, 
                workflow_template_id, required_phases, is_active, version,
                created_at, updated_at
            ) VALUES (
                :id, CAST(:audit_type AS engagement_type), :sector, :playbook_name, :description,
                :workflow_template_id, CAST(:required_phases AS json), :is_active, :version,
                NOW(), NOW()
            )
            """
            
            await conn.execute(text(sql), {
                "id": str(uuid.uuid4()),
                "audit_type": engagement_type,
                "sector": None,
                "playbook_name": workflow_id.replace('_', ' ').title(),
                "description": objective[:500] if objective else None,
                "workflow_template_id": workflow_id,
                "required_phases": json.dumps({"phases": phases}),
                "is_active": True,
                "version": 1
            })
            
        await conn.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
