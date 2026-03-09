# ✅ ERP Setup Checklist - All 3 Systems

## 🚀 Quick Setup Checklist

### 1. QuickBooks Setup
- [ ] Get QuickBooks Developer Account
- [ ] Create OAuth App at https://developer.intuit.com
- [ ] Note Client ID and Client Secret
- [ ] Update `.env` with QuickBooks credentials
- [ ] Restart backend: `docker compose restart api`

### 2. Zoho Books Setup
- [ ] Get Zoho Developer Account
- [ ] Create Client at https://api-console.zoho.com
- [ ] Note Client ID and Client Secret
- [ ] Update `.env` with Zoho credentials
- [ ] Restart backend: `docker compose restart api`

### 3. Tally Setup
- [ ] Enable HTTP/JSON interface in Tally (F12 > Configure)
- [ ] Note Tally server IP and port
- [ ] Update `.env` with Tally details
- [ ] Restart backend: `docker compose restart api`

## 🔗 Connection Process

### Step 1: Authenticate with Arkashri
1. Go to http://localhost:3000
2. Login or register
3. Get JWT token from browser localStorage

### Step 2: Connect Each ERP
Use the API endpoints or frontend wizard:

**QuickBooks:**
```bash
# Get OAuth URL
curl -X GET "http://localhost:8000/api/erp/oauth/quickbooks/url" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Zoho Books:**
```bash
# Get OAuth URL  
curl -X GET "http://localhost:8000/api/erp/oauth/zoho/url" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Tally:**
```bash
# Connect directly
curl -X POST "http://localhost:8000/api/erp/connect/tally" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "host": "localhost",
    "port": 9000,
    "company_name": "Your_Company"
  }'
```

### Step 3: Verify Connections
```bash
# List all connections
curl -X GET "http://localhost:8000/api/erp/connections" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Test sync
curl -X POST "http://localhost:8000/api/erp/sync" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## 📊 Expected Results

After successful connection:
- ✅ QuickBooks: Access to invoices, bills, customers, vendors
- ✅ Zoho Books: Access to accounts, transactions, reports
- ✅ Tally: Access to ledger, vouchers, trial balance
- ✅ Unified dashboard with all financial data
- ✅ Real-time sync capabilities
- ✅ Audit trail across all systems

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 Forbidden | Check JWT token authentication |
| 422 Validation | Verify required parameters |
| Connection Timeout | Check ERP server accessibility |
| OAuth Errors | Verify redirect URIs match |

## 🎯 Production Tips

1. **Use production credentials** for live data
2. **Set up webhooks** for real-time updates
3. **Monitor connection health** regularly
4. **Implement retry logic** for failed syncs
5. **Secure API keys** properly

## 📞 Quick Links

- **QuickBooks Developer**: https://developer.intuit.com
- **Zoho API Console**: https://api-console.zoho.com
- **Tally Help**: https://forum.tallysolutions.com
- **Arkashri Docs**: http://localhost:8000/docs
