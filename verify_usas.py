# pyre-ignore-all-errors
import os
import asyncio
from httpx import AsyncClient, ASGITransport
from arkashri.main import app

async def test_usas_phase1():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a regulatory framework
        print("Creating Regulatory Framework...")
        fw_payload = {
            "jurisdiction": "US",
            "framework_type": "US_GAAP",
            "name": "US Generally Accepted Accounting Principles",
            "description": "Standard US accounting rules.",
            "authority": "FASB",
            "is_active": True
        }
        res_fw = await client.post("/api/v1/jurisdiction/frameworks", json=fw_payload)
        if res_fw.status_code != 201:
            print("Failed to create framework:", res_fw.text)
            return
        fw_data = res_fw.json()
        print(f"Framework Created: {fw_data['id']}")

        # Retrieve the framework
        print("Retrieving frameworks for 'US'...")
        res_fw_get = await client.get("/api/v1/jurisdiction/frameworks/US")
        print(f"Frameworks found: {len(res_fw_get.json())}")

        # Create an Audit Playbook
        print("Creating Audit Playbook...")
        pb_payload = {
            "audit_type": "STATUTORY_AUDIT",
            "sector": "TECHNOLOGY",
            "playbook_name": "Tech Statutory Audit Playbook v1",
            "description": "Base playbook for tech sector audits.",
            "workflow_template_id": "tpl_tech_stat_01",
            "required_phases": {"planning": True, "fieldwork": True, "reporting": True},
            "is_active": True,
            "version": 1
        }
        res_pb = await client.post("/api/v1/playbooks", json=pb_payload)
        if res_pb.status_code != 201:
            print("Failed to create playbook:", res_pb.text)
            return
        pb_data = res_pb.json()
        print(f"Playbook Created: {pb_data['id']}")

        # Generate a playbook for given parameters
        print("Generating Playbook template for STATUTORY_AUDIT in TECHNOLOGY...")
        res_pb_gen = await client.get("/api/v1/playbooks/generate?audit_type=STATUTORY_AUDIT&sector=TECHNOLOGY")
        if res_pb_gen.status_code != 200:
            print("Failed to generate playbook:", res_pb_gen.text)
            return
        pb_gen_data = res_pb_gen.json()
        print(f"Generated Playbook Response: {pb_gen_data}")
        if isinstance(pb_gen_data, list):
            pb_gen_data = pb_gen_data[0]
        print(f"Generated Playbook Name: {pb_gen_data['playbook_name']}")

if __name__ == "__main__":
    os.environ["AUTH_ENFORCED"] = "false"
    asyncio.run(test_usas_phase1())
