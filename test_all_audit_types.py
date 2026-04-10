#!/usr/bin/env python3
"""
Comprehensive Audit Type Testing Script
Tests all supported audit types for error-free execution
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

def test_all_audit_types():
    """Test all supported audit types"""
    token = generate_test_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # All audit types from the UI dropdown
    audit_types = [
        "Financial Audit",
        "Forensic Audit", 
        "Internal Audit",
        "Statutory Audit",
        "Tax Audit",
        "Compliance Audit",
        "ESG Audit",
        "External Audit",
        "Operational Audit",
        "IT Audit",
        "Payroll Audit",
        "Performance Audit",
        "Quality Audit",
        "Environmental Audit"
    ]
    
    print("🔍 Testing All Audit Types for Error-Free Execution")
    print("=" * 60)
    
    results = {}
    
    for audit_type in audit_types:
        print(f"\n📋 Testing: {audit_type}")
        print("-" * 40)
        
        # Test audit execution for each type
        audit_data = {
            "audit_id": f"{audit_type.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
            "client_id": "test-client-123",
            "audit_type": audit_type,
            "parameters": {
                "risk_level": "Medium",
                "jurisdiction": "US",
                "materiality_threshold": 50000,
                "audit_scope": "comprehensive"
            }
        }
        
        try:
            response = requests.post(f"{API_BASE}/api/agents/run-audit", 
                                   json=audit_data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                results[audit_type] = {
                    "status": "SUCCESS",
                    "risk_score": result.get("risk_score", 0),
                    "requires_review": result.get("requires_review", False),
                    "exceptions_count": result.get("exceptions_count", 0),
                    "findings_count": result.get("findings_count", 0)
                }
                print(f"✅ SUCCESS - Risk Score: {result.get('risk_score', 0)}")
            else:
                results[audit_type] = {
                    "status": "FAILED",
                    "error": response.text
                }
                print(f"❌ FAILED - {response.text}")
                
        except Exception as e:
            results[audit_type] = {
                "status": "ERROR",
                "error": str(e)
            }
            print(f"❌ ERROR - {e}")
    
    # Summary Report
    print("\n" + "=" * 60)
    print("📊 COMPREHENSIVE AUDIT TYPE TEST RESULTS")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for audit_type, result in results.items():
        status = result["status"]
        if status == "SUCCESS":
            success_count += 1
            print(f"✅ {audit_type:<25} | Risk: {result.get('risk_score', 0):<5} | Review: {result.get('requires_review', False)}")
        else:
            failed_count += 1
            print(f"❌ {audit_type:<25} | {result.get('error', 'Unknown error')}")
    
    print(f"\n📈 SUMMARY:")
    print(f"✅ Successful: {success_count}/{len(audit_types)} ({success_count/len(audit_types)*100:.1f}%)")
    print(f"❌ Failed: {failed_count}/{len(audit_types)} ({failed_count/len(audit_types)*100:.1f}%)")
    
    if success_count == len(audit_types):
        print("\n🎉 ALL AUDIT TYPES WORK WITHOUT ERRORS!")
    elif success_count >= len(audit_types) * 0.8:
        print("\n✅ MAJORITY OF AUDIT TYPES WORK CORRECTLY")
    else:
        print("\n⚠️ SIGNIFICANT ISSUES DETECTED")
    
    return results

if __name__ == "__main__":
    test_all_audit_types()
