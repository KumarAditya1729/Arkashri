# Custom Domain Setup Guide for Arkashri on Railway

## Issue Fixed
The deployment failure was caused by a port mismatch:
- **Problem**: Dockerfile exposed port 8000, but Railway expects port 8080
- **Solution**: Updated all configurations to use port 8080 consistently

## Changes Made
1. **Dockerfile**: Changed EXPOSE from 8000 to 8080
2. **Dockerfile**: Updated CMD to bind to 0.0.0.0:8080
3. **docker-compose.yml**: Updated port mapping and health checks to use 8080

## Custom Domain Setup Steps

### Step 1: Redeploy the Application
First, redeploy your application with the port fixes:
```bash
git add .
git commit -m "Fix port configuration for Railway deployment"
git push origin main
```

### Step 2: Add Custom Domain in Railway
1. Go to your Railway project dashboard
2. Click on the "Arkashri" service
3. Navigate to the "Networking" tab
4. Click "Custom Domain" button
5. Enter your desired domain (e.g., `arkashri.com` or `app.arkashri.com`)

### Step 3: Configure DNS
After adding the custom domain in Railway, you'll need to configure your DNS:

#### Option A: Using Railway's DNS (Recommended)
1. Railway will provide you with nameservers
2. Update your domain's nameservers at your registrar
3. Wait for DNS propagation (usually 24-48 hours)

#### Option B: Using CNAME Record
1. Add a CNAME record in your DNS settings:
   ```
   Type: CNAME
   Name: @ (or your subdomain like 'app')
   Value: arkashri-production.up.railway.app
   TTL: 300 (or as low as your provider allows)
   ```

### Step 4: SSL Certificate
- Railway automatically provisions SSL certificates for custom domains
- This may take a few minutes after DNS propagation

### Step 5: Verify the Setup
1. Check that your domain resolves correctly
2. Test HTTPS access
3. Verify all application functionality works

## Environment Variables for Production
Ensure these are set in Railway:
- `APP_ENV=production`
- `AUTH_ENFORCED=true`
- All database and service URLs
- Proper CORS origins for your custom domain

## Troubleshooting
- **Application not responding**: Check Railway logs for deployment errors
- **Domain not resolving**: Verify DNS configuration and propagation
- **SSL issues**: Wait longer for certificate provisioning or check DNS CAA records

## Next Steps
1. Deploy the changes
2. Add your custom domain in Railway dashboard
3. Configure DNS as shown above
4. Test the application on your custom domain
