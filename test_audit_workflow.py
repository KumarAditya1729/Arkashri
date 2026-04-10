#!/usr/bin/env python3
"""
Test script for complete audit workflow
"""
import jwt
import datetime
import uuid
import json
import requests

# JWT Configuration
SECRET_KEY = "bafc8aedb2980401f4d3872d6f8307ef14535a77e615e48da577dee6f2268567"
ALGORITHM = "HS256"
API_BASE = "http://localhost:8000"

def generate_test_token():
    """Generate a test JWT token for authentication"""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "test-user",
        "iss": "arkashri", 
        "aud": "arkashri-api",
        "iat": now,
        "exp": now + datetime.timedelta(hours=24),
        "user_id": str(uuid.uuid4()),
        "email": "test@example.com",
        "role": "ADMIN",
        "tenant_id": "test-tenant"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def test_audit_workflow():
    """Test the complete audit workflow"""
    token = generate_test_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print("🔍 Starting Complete Audit Workflow Test")
    print("=" * 50)
    
    # Phase 1: Create Audit
    print("\n📋 Phase 1: Creating Audit...")
    audit_data = {
        "title": "Financial Audit - Test Corporation 2024",
        "client_name": "Test Corporation",
        "audit_type": "Financial",
        "jurisdiction": "US",
        "risk_level": "Medium",
        "estimated_hours": 200
    }
    
    try:
        response = requests.post(f"{API_BASE}/api/audits/create", 
                               json=audit_data, headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            audit_result = response.json()
            print(f"✅ Audit Created: {json.dumps(audit_result, indent=2)}")
            audit_id = audit_result.get("id", "test-audit-123")
        else:
            print(f"❌ Failed: {response.text}")
            audit_id = "test-audit-123"
    except Exception as e:
        print(f"❌ Error: {e}")
        audit_id = "test-audit-123"
    
    # Phase 2: Run Audit Agents
    print(f"\n🤖 Phase 2: Running Audit Agents for {audit_id}...")
    agent_data = {
        "audit_id": audit_id,
        "client_id": "client-123",
        "audit_type": "Financial",
        "parameters": {
            "risk_level": "Medium",
            "jurisdiction": "US",
            "materiality_threshold": 50000
        }
    }
    
    try:
        response = requests.post(f"{API_BASE}/api/agents/run-audit", 
                               json=agent_data, headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            agent_result = response.json()
            print(f"✅ Agents Executed: {json.dumps(agent_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Phase 3: Evidence Collection
    print(f"\n📄 Phase 3: Evidence Collection...")
    evidence_data = {
        "audit_id": audit_id,
        "source": "erp",
        "document_path": "/documents/financial_statements.pdf",
        "document_type": "Financial Statement"
    }
    try:
        response = requests.post(f"{API_BASE}/api/agents/extract", 
                               json=evidence_data, 
                               headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            extract_result = response.json()
            print(f"✅ Evidence Extracted: {json.dumps(extract_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Phase 4: Fraud Analysis
    print(f"\n🔍 Phase 4: Fraud Analysis...")
    fraud_data = {
        "audit_id": audit_id,
        "data_set": "transactions",
        "transactions": [
            {"id": 1, "amount": 1000, "date": "2024-01-01", "description": "Test Transaction 1"},
            {"id": 2, "amount": 5000, "date": "2024-01-02", "description": "Test Transaction 2"}
        ]
    }
    try:
        response = requests.post(f"{API_BASE}/api/agents/fraud-analysis", 
                               json=fraud_data, 
                               headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            fraud_result = response.json()
            print(f"✅ Fraud Analysis Complete: {json.dumps(fraud_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Phase 5: Compliance Check
    print(f"\n✅ Phase 5: Compliance Check...")
    compliance_data = {
        "audit_id": audit_id,
        "framework": "SOX",
        "transaction": {"amount": 1000, "account": "Revenue", "date": "2024-01-01"},
        "rules": [{"rule_id": "SOX_401", "description": "Internal controls test"}]
    }
    try:
        response = requests.post(f"{API_BASE}/api/agents/compliance-check", 
                               json=compliance_data, 
                               headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            compliance_result = response.json()
            print(f"✅ Compliance Check Complete: {json.dumps(compliance_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Phase 6: Report Generation
    print(f"\n📊 Phase 6: Report Generation...")
    report_data = {
        "audit_id": audit_id,
        "format": "pdf",
        "audit_data": {
            "title": "Financial Audit Report",
            "client": "Test Corporation",
            "findings": [],
            "risk_score": 45
        }
    }
    try:
        response = requests.post(f"{API_BASE}/api/agents/generate-report", 
                               json=report_data, 
                               headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            report_result = response.json()
            print(f"✅ Report Generated: {json.dumps(report_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Phase 7: Get Audit Stats
    print(f"\n📈 Phase 7: Getting Audit Statistics...")
    try:
        response = requests.get(f"{API_BASE}/api/audits/{audit_id}/stats", 
                              headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            stats_result = response.json()
            print(f"✅ Audit Stats: {json.dumps(stats_result, indent=2)}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n🎉 Complete Audit Workflow Test Finished!")
    print("=" * 50)

if __name__ == "__main__":
    test_audit_workflow()
