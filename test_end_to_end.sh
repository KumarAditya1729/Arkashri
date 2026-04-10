#!/bin/bash
set -e
BASE="http://localhost:8000/v1"

echo "=== STAGE 1: SYSTEM SETUP ==="
BOOT=$(curl -s -X POST "$BASE/system/bootstrap/minimal" -H "Content-Type: application/json")
API_KEY=$(echo $BOOT | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('admin_api_key', ''))")

if [ -z "$API_KEY" ]; then
    echo "Bootstrap failed or already bootstrapped. Trying to get an API key..."
    # Create an API key by just querying the DB
    API_KEY=$(.venv/bin/python -c "import sqlite3; c=sqlite3.connect('arkashri.db'); c.execute('SELECT api_key FROM tenant LIMIT 1'); print(c.fetchone()[0])" 2>/dev/null || echo "ark_live_test123")
fi
echo "API Key check: $API_KEY"

echo -e "\n=== STAGE 2: WORKFLOW CREATION ==="
ENG=$(curl -s -X POST "$BASE/engagements" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"client_name":"Master Test Co","engagement_type":"FINANCIAL_AUDIT","reporting_period_start":"2024-04-01","reporting_period_end":"2025-03-31","jurisdiction":"IN","workflow_template_id":"financial_audit_v1"}')
ENG_ID=$(echo $ENG | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")
echo "Engagement ID: $ENG_ID"

echo -e "\n=== STAGE 3: ERP DATA ==="
curl -s -X POST "$BASE/erp/ingest" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"engagement_id":"'"$ENG_ID"'","erp_system":"sap","records":[{"BELNR":"SAP001","BUDAT":"2024-05-01","DMBTR":500000,"HKONT":"4001","SHKZG":"S"}]}' | head -n 3

echo -e "\n=== STAGE 4: RISK SUMMARY ==="
curl -s -X POST "$BASE/engagements/$ENG_ID/risk/compute" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" -d '{}' | head -n 5

echo -e "\n=== STAGE 5: ORCHESTRATION ==="
RUN_CREATE=$(curl -s -X POST "$BASE/orchestration/runs" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"engagement_id":"'"$ENG_ID"'","workflow_template_id":"financial_audit_v1"}')
RUN_ID=$(echo $RUN_CREATE | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")
echo "Run ID: $RUN_ID"
curl -s -X POST "$BASE/orchestration/runs/$RUN_ID/execute" -H "X-API-Key: $API_KEY" | head -n 3

echo -e "\n=== STAGE 6: GOING CONCERN FULL ==="
curl -s -X POST "$BASE/v1/going-concern/$ENG_ID/full-analysis" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"total_assets":50000,"total_liabilities":18000,"current_assets":22000,"current_liabilities":8000,"revenue":60000,"ebit":80,"net_income":5500,"operating_cash_flow":7200,"industry_sector":"IT Services","auto_flag_judgment":false}' | head -n 12

echo -e "\n=== STAGE 7: DRAFT OPINION ==="
curl -s -X POST "$BASE/engagements/$ENG_ID/opinion" \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"jurisdiction":"IN","reporting_framework":"IND_AS"}' | head -n 5

echo -e "\n=== STAGE 8: AUDIT SEAL ==="
curl -s -X POST "$BASE/engagements/$ENG_ID/seal" -H "X-API-Key: $API_KEY" | head -n 5

