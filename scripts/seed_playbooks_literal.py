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

def escape(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # String or json
    safe_str = str(val).replace("'", "''")
    return f"'{safe_str}'"

async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    
    print("Reading workflow_pack/index.json...")
    with open(INDEX_PATH, "r") as f:
        index = json.load(f)
        
    async with engine.connect() as conn:
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
            
            # Use raw SQL with literals to bypass prepared statement OID caching issues
            playbook_name = workflow_id.replace('_', ' ').title()
            description = objective[:500] if objective else None
            required_phases = json.dumps({"phases": phases})
            
            sql = f"""
            INSERT INTO audit_playbook (
                id, audit_type, sector, playbook_name, description, 
                workflow_template_id, required_phases, is_active, version,
                created_at, updated_at
            ) VALUES (
                '{uuid.uuid4()}', CAST('{engagement_type}' AS engagement_type), NULL, {escape(playbook_name)}, {escape(description)},
                {escape(workflow_id)}, CAST({escape(required_phases)} AS json), TRUE, 1,
                NOW(), NOW()
            )
            """
            
            await conn.execute(text(sql))
            
        await conn.commit()
        print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
