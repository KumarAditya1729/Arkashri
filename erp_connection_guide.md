# 🔗 Complete ERP Integration Guide - Arkashri

## 📋 Overview
This guide helps you connect all three ERP systems (QuickBooks, Zoho Books, and Tally) to Arkashri for comprehensive financial data integration.

## 🚀 QuickBooks Integration

### Step 1: Get QuickBooks API Credentials
1. Go to [QuickBooks Developer Portal](https://developer.intuit.com/app/developer/dashboard)
2. Create a new app or use existing one
3. Note down:
   - Client ID
   - Client Secret
   - Environment (sandbox for testing)

### Step 2: Configure QuickBooks in Arkashri
Update your `.env` file:
```bash
QUICKBOOKS_CLIENT_ID=your_actual_client_id
QUICKBOOKS_CLIENT_SECRET=your_actual_client_secret
QUICKBOOKS_ENVIRONMENT=sandbox
```

### Step 3: Connect QuickBooks
```bash
# 1. Get OAuth URL (requires authentication)
curl -X GET "http://localhost:8000/api/erp/oauth/quickbooks/url" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 2. After authorization, exchange code for token
curl -X POST "http://localhost:8000/api/erp/oauth/quickbooks/token" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "code": "AUTH_CODE_FROM_QUICKBOOKS",
    "realm_id": "REALM_ID"
  }'

# 3. Connect QuickBooks to Arkashri
curl -X POST "http://localhost:8000/api/erp/connect/quickbooks" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "access_token": "QUICKBOOKS_ACCESS_TOKEN",
    "refresh_token": "QUICKBOOKS_REFRESH_TOKEN",
    "realm_id": "REALM_ID"
  }'
```

## 📊 Zoho Books Integration

### Step 1: Get Zoho API Credentials
1. Go to [Zoho Developer Console](https://api-console.zoho.com/)
2. Create a new client
3. Note down:
   - Client ID
   - Client Secret

### Step 2: Configure Zoho in Arkashri
Update your `.env` file:
```bash
ZOHO_CLIENT_ID=your_actual_zoho_client_id
ZOHO_CLIENT_SECRET=your_actual_zoho_client_secret
ZOHO_ENVIRONMENT=development
```

### Step 3: Connect Zoho Books
```bash
# 1. Get OAuth URL
curl -X GET "http://localhost:8000/api/erp/oauth/zoho/url" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 2. After authorization, exchange code for token
curl -X POST "http://localhost:8000/api/erp/oauth/zoho/token" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "code": "AUTH_CODE_FROM_ZOHO"
  }'

# 3. Connect Zoho to Arkashri
curl -X POST "http://localhost:8000/api/erp/connect/zoho" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "access_token": "ZOHO_ACCESS_TOKEN",
    "refresh_token": "ZOHO_REFRESH_TOKEN"
  }'
```

## 📈 Tally Integration

### Step 1: Configure Tally
1. Ensure Tally is running with XML/JSON interface
2. Enable HTTP interface in Tally (F12 > Configure > HTTP/JSON Server)
3. Note down:
   - Tally server IP (usually localhost)
   - Port (usually 9000)
   - Company name

### Step 2: Configure Tally in Arkashri
Update your `.env` file:
```bash
TALLY_HOST=localhost
TALLY_PORT=9000
TALLY_COMPANY_NAME=Your_Actual_Company_Name
TALLY_USERNAME=admin
TALLY_PASSWORD=your_tally_password
```

### Step 3: Connect Tally
```bash
curl -X POST "http://localhost:8000/api/erp/connect/tally" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "host": "localhost",
    "port": 9000,
    "company_name": "Your_Company_Name",
    "username": "admin",
    "password": "your_password"
  }'
```

## 🔄 Testing All Connections

### Check Connection Status
```bash
# List all ERP connections
curl -X GET "http://localhost:8000/api/erp/connections" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Check specific connection status
curl -X GET "http://localhost:8000/api/erp/connection/{connection_id}/status" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Sync Data from All ERPs
```bash
# Sync all connected ERPs
curl -X POST "http://localhost:8000/api/erp/sync" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"sync_type": "full"}'

# Preview data before sync
curl -X POST "http://localhost:8000/api/erp/preview" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"erp_type": "all"}'
```

## 🛠️ Frontend Integration

1. Navigate to http://localhost:3000
2. Login to your account
3. Go to **ERP Integration** section
4. Use the connection wizard for each ERP:
   - QuickBooks: OAuth flow
   - Zoho Books: OAuth flow  
   - Tally: Direct connection

## 📊 Available Data After Connection

Once connected, you can access:
- **Chart of Accounts**
- **Transactions**
- **Invoices and Bills**
- **Customer/Vendor Data**
- **Financial Reports**
- **Trial Balance**
- **Bank Statements**

## 🔧 Troubleshooting

### Common Issues:
1. **403 Forbidden**: Ensure you're authenticated with valid JWT token
2. **422 Validation Error**: Check required parameters in request body
3. **Connection Timeout**: Verify ERP server is accessible
4. **OAuth Errors**: Ensure redirect URIs match in ERP developer console

### Reset Connections:
```bash
# Delete specific connection
curl -X DELETE "http://localhost:8000/api/erp/connection/{connection_id}" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## 🚀 Production Considerations

1. **Use production environment** for real data
2. **Secure API credentials** properly
3. **Set up webhooks** for real-time sync
4. **Monitor connection health** regularly
5. **Implement retry logic** for failed syncs

## 📞 Support

For ERP-specific issues:
- **QuickBooks**: https://developer.intuit.com/app/developer/community
- **Zoho**: https://help.zoho.com/portal
- **Tally**: https://forum.tallysolutions.com/

For Arkashri integration issues, check the logs in `logs/arkashri.log`
