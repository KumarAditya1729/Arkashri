import asyncio
import uuid
from arkashri.db import AsyncSessionLocal
from arkashri.services.orchestrator import create_run_from_template, execute_run
from arkashri.models import User

async def test_run():
    async with AsyncSessionLocal() as session:
        print("Creating run from template...")
        run = await create_run_from_template(
            session=session,
            tenant_id="test_org_id_123",
            jurisdiction="IN",
            audit_type="financial_audit",
            created_by="Validator_Script",
            input_payload={"automation_mode": "deterministic_llm"}
        )
        
        print(f"Run ID: {run.id}. Executing run...")
        
        # In a real environment, arq's Redis queue handles the actual emails from inside check_approvals.
        # But we only want to test the `build_step_output` mappings for Risk, Opinion & GC
        # Let's bypass the execution DB save and directly test `_build_step_output` logic.
        from arkashri.services.orchestrator import _build_step_output
        from arkashri.models import AuditRunStep
        from sqlalchemy import select
        
        steps = await session.scalars(select(AuditRunStep).where(AuditRunStep.run_id == run.id))
        
        print("\n=== TESTING SEMANTIC ENGINE ROUTES ===")
        for s in steps:
            # We want to test SA 570 matching
            out = await _build_step_output(session, run, s)
            mode = out.get("automation_mode", "UNKNOWN")
            action_disp = s.action[:60] + "..." if len(s.action)>60 else s.action
            
            print(f"[{s.step_id}] -> Mode: {mode:25} | Action: {action_disp}")
            
            if mode == "deterministic_math":
                if "gc_analysis" in out:
                    zn = out['gc_analysis'].get('altman_result',{}).get('zone')
                    print(f"    ✅ SUCCESSFULLY CALLED GC ADVANCED. ZONE: {zn}")
                if "critical_flags_count" in out:
                    print(f"    ✅ SUCCESSFULLY CALLED RISK ENGINE COMPUTATION.")

if __name__ == "__main__":
    asyncio.run(test_run())
