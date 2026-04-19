#!/usr/bin/env python3
"""
Blockchain Functionality Test Script
Tests blockchain anchoring and evidence verification
"""
import jwt
import datetime
import uuid
import json
import requests
import hashlib

# JWT Configuration
SECRET_KEY = "bafc8aedb2980401f4d3872d6f8307ef14535a77e615e48da577dee6f2268567"
ALGORITHM = "HS256"
API_BASE = "http://127.0.0.1:8003"

def generate_test_token():
    """Generate a test JWT token for authentication"""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "550e8400-e29b-41d4-a716-446655440000",
        "iss": "arkashri", 
        "aud": "arkashri-api",
        "iat": now,
        "exp": now + datetime.timedelta(hours=24),
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "test@example.com",
        "role": "ADMIN",
        "tenant_id": "test-tenant",
        "type": "access",
        "sid": "660e8400-e29b-41d4-a716-446655440000"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def test_blockchain_functionality():
    """Test blockchain anchoring and verification"""
    token = generate_test_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print("🔗 Testing Blockchain Functionality")
    print("=" * 50)
    
    # Test 1: Check Blockchain Status
    print("\n📊 Blockchain Status:")
    try:
        response = requests.get(f"{API_BASE}/api/blockchain/status", headers=headers)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Total Blocks: {status['total_blocks']}")
            print(f"✅ Total Evidence: {status['total_evidence']}")
            print(f"✅ Chain Valid: {status['chain_valid']}")
            print(f"✅ Latest Block Hash: {status['latest_block_hash']}")
        else:
            print(f"❌ Status Check Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Submit Evidence to Blockchain
    print("\n📝 Submitting Evidence to Blockchain:")
    evidence_data = {
        "audit_id": "test-audit-123",
        "evidence_hash": hashlib.sha256(b"test_evidence_data").hexdigest(),
        "evidence_type": "transaction",
        "metadata": {
            "transaction_id": "txn_001",
            "amount": 1000.00,
            "date": "2024-01-01",
            "description": "Test transaction for blockchain"
        }
    }
    
    try:
        response = requests.post(f"{API_BASE}/api/blockchain/evidence/submit", 
                               json=evidence_data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Evidence Submitted: {json.dumps(result, indent=2)}")
            evidence_id = result.get("evidence_id", "test_evidence")
        else:
            print(f"❌ Evidence Submission Failed: {response.text}")
            evidence_id = "test_evidence"
    except Exception as e:
        print(f"❌ Error: {e}")
        evidence_id = "test_evidence"
    
    # Test 3: Mine Block (Anchor Evidence)
    print("\n⛏️ Mining Block (Anchoring Evidence):")
    try:
        response = requests.post(f"{API_BASE}/api/blockchain/evidence/mine-block", 
                               json={"audit_id": "test-audit-123"}, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Block Mined: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ Block Mining Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Verify Evidence
    print("\n🔍 Verifying Evidence on Blockchain:")
    try:
        response = requests.post(f"{API_BASE}/api/blockchain/evidence/verify", 
                               json={"evidence_hash": evidence_data["evidence_hash"]}, 
                               headers=headers)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Evidence Verified: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ Evidence Verification Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 5: Get Audit Trail
    print("\n📋 Getting Audit Trail from Blockchain:")
    try:
        response = requests.get(f"{API_BASE}/api/blockchain/audit/test-audit-123/trail", 
                              headers=headers)
        if response.status_code == 200:
            trail = response.json()
            print(f"✅ Audit Trail: {json.dumps(trail, indent=2)}")
        else:
            print(f"❌ Audit Trail Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 6: Check Blockchain Status Again
    print("\n📊 Final Blockchain Status:")
    try:
        response = requests.get(f"{API_BASE}/api/blockchain/status", headers=headers)
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Total Blocks: {status['total_blocks']}")
            print(f"✅ Total Evidence: {status['total_evidence']}")
            print(f"✅ Chain Valid: {status['chain_valid']}")
            print(f"✅ Pending Evidence: {status['pending_evidence']}")
        else:
            print(f"❌ Final Status Check Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n🎉 Blockchain Functionality Test Complete!")

if __name__ == "__main__":
    test_blockchain_functionality()
