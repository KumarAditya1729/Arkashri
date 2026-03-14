# pyre-ignore-all-errors
import asyncio
import httpx  # pyre-ignore
from colorama import Fore, Style, init  # pyre-ignore

init(autoreset=True)

import os
from httpx import AsyncClient, ASGITransport  # pyre-ignore
from arkashri.main import app  # pyre-ignore

init(autoreset=True)

BASE_URL = "http://test/api/v1"

async def test_usas_phases_2_3_4():
    os.environ["AUTH_ENFORCED"] = "false"
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        print(f"\n{Fore.CYAN}--- Testing USAS Phases 2, 3, & 4 ---{Style.RESET_ALL}\n")

        # Setup: Create a real engagement first
        tenant_id = "test_tenant_123"
        jurisdiction = "US"
        engagement_payload = {
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "client_name": "Test Client Inc",
            "engagement_type": "STATUTORY_AUDIT"
        }
        res_eng = await client.post("/engagements/engagements", json=engagement_payload, headers={"X-API-Key": "test-admin-key"})
        if res_eng.status_code != 201:
            print(f"{Fore.RED}✗ Failed to create initial Engagement: {res_eng.text}{Style.RESET_ALL}")
            return
        engagement_id = res_eng.json()["id"]
        print(f"{Fore.GREEN}✓ Setup: Created Engagement {engagement_id}{Style.RESET_ALL}")


        # --- Phase 2: Resilience ---
        print(f"{Fore.YELLOW}Testing Phase 2 (Resilience - Crisis Mode)...{Style.RESET_ALL}")
        crisis_payload = {
            "engagement_id": engagement_id,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "trigger_type": "FRAUD_DETECTED",
            "escalated_by": "john_doe"
        }
        res = await client.post("/usas/crisis", json=crisis_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ Crisis Event Triggered: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to trigger Crisis Event: {res.text}{Style.RESET_ALL}")

        print(f"\n{Fore.YELLOW}Testing Phase 2 (Resilience - Continuous Audit)...{Style.RESET_ALL}")
        ca_payload = {
            "engagement_id": engagement_id,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "rule_name": "High Value Transactions",
            "data_source_type": "ERP_LEDGER",
            "threshold_value": 500000.0,
            "action_on_breach": "INCREASE_SAMPLE"
        }
        res = await client.post("/usas/continuous-audit/rules", json=ca_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ Continuous Audit Rule Created: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to create CA Rule: {res.text}{Style.RESET_ALL}")


        # --- Phase 3: Deep Intelligence ---
        print(f"\n{Fore.YELLOW}Testing Phase 3 (Intelligence - Forensic Investigation)...{Style.RESET_ALL}")
        forensic_payload = {
            "engagement_id": engagement_id,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "target_entity": "Shell Corp Alpha",
            "investigation_type": "RELATED_PARTY",
            "risk_score": 85.5
        }
        res = await client.post("/usas/forensic-investigations", json=forensic_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ Forensic Investigation Opened: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to open investigation: {res.text}{Style.RESET_ALL}")

        print(f"\n{Fore.YELLOW}Testing Phase 3 (Intelligence - ESG Metrics)...{Style.RESET_ALL}")
        esg_payload = {
            "engagement_id": engagement_id,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "metric_category": "ENVIRONMENTAL",
            "metric_name": "Carbon Footprint Scope 1",
            "value": 1500.5,
            "unit": "tons_co2"
        }
        res = await client.post("/usas/esg-metrics", json=esg_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ ESG Metric Logged: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to log ESG metric: {res.text}{Style.RESET_ALL}")


        # --- Phase 4: Sovereign Governance ---
        print(f"\n{Fore.YELLOW}Testing Phase 4 (Governance - AI Explainability Log)...{Style.RESET_ALL}")
        ai_payload = {
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "decision_id": "dec_948123",
            "model_used": "arkashri-risk-v2",
            "decision_rationale": "High variance detected in Q3 revenue recognition.",
            "human_override": False
        }
        res = await client.post("/usas/ai-governance-logs", json=ai_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ AI Governance Log Recorded: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to record AI log: {res.text}{Style.RESET_ALL}")

        print(f"\n{Fore.YELLOW}Testing Phase 4 (Governance - Sovereign Archival)...{Style.RESET_ALL}")
        archive_payload = {
            "engagement_id": engagement_id,
            "tenant_id": tenant_id,
            "jurisdiction": jurisdiction,
            "archive_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "archive_location": "s3://arkashri-worm-us-east/eng_123.zip",
            "retention_period_years": 10
        }
        res = await client.post("/usas/sovereign-archives", json=archive_payload, headers={"X-API-Key": "test-admin-key"})
        if res.status_code == 201:
            print(f"{Fore.GREEN}✓ Sovereign Archive Sealed: {res.json()['id']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Failed to seal archive: {res.text}{Style.RESET_ALL}")


if __name__ == "__main__":
    asyncio.run(test_usas_phases_2_3_4())
