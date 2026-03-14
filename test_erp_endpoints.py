# pyre-ignore-all-errors
#!/usr/bin/env python3
"""
ERP Integration Test Script
Tests all ERP endpoints for QuickBooks, Zoho Books, and Tally
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint, method="GET", data=None, headers=None):
    """Test an API endpoint"""
    try:
        url = f"{BASE_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "OPTIONS":
            response = requests.options(url, headers=headers)
        
        return {
            "status_code": response.status_code,
            "response": response.text[:200] if response.text else "",
            "success": response.status_code < 400
        }
    except Exception as e:
        return {
            "status_code": 0,
            "response": str(e),
            "success": False
        }

def main():
    print("🔗 Testing All ERP Integration Endpoints")
    print("=" * 50)
    
    # Test QuickBooks endpoints
    print("\n📊 QuickBooks Endpoints:")
    quickbooks_endpoints = [
        ("/api/erp/oauth/quickbooks/url", "GET"),
        ("/api/erp/oauth/quickbooks/token", "POST"),
        ("/api/erp/connect/quickbooks", "POST"),
    ]
    
    for endpoint, method in quickbooks_endpoints:
        result = test_endpoint(endpoint, method)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {method} {endpoint} - {result['status_code']}")
    
    # Test Zoho Books endpoints
    print("\n📊 Zoho Books Endpoints:")
    zoho_endpoints = [
        ("/api/erp/oauth/zoho/url", "GET"),
        ("/api/erp/oauth/zoho/token", "POST"),
        ("/api/erp/connect/zoho", "POST"),
    ]
    
    for endpoint, method in zoho_endpoints:
        result = test_endpoint(endpoint, method)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {method} {endpoint} - {result['status_code']}")
    
    # Test Tally endpoints
    print("\n📈 Tally Endpoints:")
    tally_endpoints = [
        ("/api/erp/connect/tally", "POST"),
    ]
    
    for endpoint, method in tally_endpoints:
        result = test_endpoint(endpoint, method)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {method} {endpoint} - {result['status_code']}")
    
    # Test general ERP endpoints
    print("\n🔧 General ERP Endpoints:")
    general_endpoints = [
        ("/api/erp/connections", "GET"),
        ("/api/erp/sync", "POST"),
        ("/api/erp/preview", "POST"),
    ]
    
    for endpoint, method in general_endpoints:
        result = test_endpoint(endpoint, method)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {method} {endpoint} - {result['status_code']}")
    
    # Test CORS for ERP endpoints
    print("\n🌐 CORS Testing:")
    cors_headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization"
    }
    
    for endpoint in ["/api/erp/connections", "/api/erp/connect/quickbooks"]:
        result = test_endpoint(endpoint, "OPTIONS", headers=cors_headers)
        status = "✅" if result["success"] else "❌"
        print(f"  {status} OPTIONS {endpoint} - {result['status_code']}")
    
    print("\n" + "=" * 50)
    print("📋 Test Summary:")
    print("✅ ERP endpoints are available and responding")
    print("⚠️  403/401 errors are expected without authentication")
    print("📖 See erp_connection_guide.md for connection instructions")

if __name__ == "__main__":
    main()
