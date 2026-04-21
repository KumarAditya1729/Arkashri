# 🚀 Arkashri Staging Deployment Guide
## Following ChatGPT's Recommended Architecture

This guide will help you deploy Arkashri to staging in 20-30 minutes using the recommended stack:
- **Frontend**: Vercel
- **Backend**: Railway  
- **Database**: PostgreSQL (Railway)
- **Queue**: Redis (Railway)
- **Storage**: AWS S3

---

## 📋 Prerequisites

### **Required Accounts:**
- ✅ GitHub account (with repos)
- ✅ Railway account
- ✅ Vercel account  
- ✅ AWS account (for S3)

### **Required Files (Already Created):**
- ✅ `arkashri/Dockerfile` - Backend container
- ✅ `arkashri/railway.json` - Railway configuration
- ✅ `arkashri/railway_start.sh` - Startup script
- ✅ `arkashri/requirements.txt` - Python dependencies
- ✅ `frontend/vercel.json` - Vercel configuration
- ✅ `frontend/.env.example` - Frontend env template

---

## 🔧 STEP 1: Deploy Backend to Railway

### **1.1 Push Backend to GitHub**
```bash
# Make sure your backend is in a GitHub repo
cd /Users/adityashrivastava/Desktop/company_1
git add .
git commit -m "Add Railway deployment configuration"
git push origin main
```

### **1.2 Deploy to Railway**
1. Go to [railway.app](https://railway.app)
2. Click **"New Project"** → **"Deploy from GitHub"**
3. Select your `arkashri` repository
4. Railway will detect Python and FastAPI automatically
5. Click **"Deploy"**

### **1.3 Add Database**
1. In Railway project, click **"New"** → **"Database"** → **"PostgreSQL"**
2. Railway will automatically provide `DATABASE_URL`
3. Add this to your Railway environment variables

### **1.4 Add Redis Queue**
1. Click **"New"** → **"Redis"**
2. Railway will provide `REDIS_URL`
3. Add to environment variables

### **1.5 Configure Environment Variables**
Copy variables from `railway_env_template.txt` to Railway:

**Critical Variables:**
```
DATABASE_URL=postgresql://... (provided by Railway)
REDIS_URL=redis://... (provided by Railway)
JWT_SECRET_KEY=<REPLACE_WITH_SECURE_32_CHAR_HEX_STRING>
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=ap-south-1
S3_WORM_BUCKET=arkashri-production-worm-archive
POLKADOT_WS_URL=wss://rpc.polkadot.io
```

### **1.6 Redeploy**
Click **"Redeploy"** in Railway to apply new environment variables.

### **1.7 Get Backend URL**
After deployment, Railway will give you a URL like:
```
https://arkashri-backend.up.railway.app
```

---

## 🎨 STEP 2: Deploy Frontend to Vercel

### **2.1 Push Frontend to GitHub**
```bash
# Make sure frontend is pushed
cd /Users/adityashrivastava/Desktop/company_1/frontend
git add .
git commit -m "Add Vercel deployment configuration"
git push origin main
```

### **2.2 Deploy to Vercel**
1. Go to [vercel.com](https://vercel.com)
2. Click **"New Project"** → **"Import Git Repository"**
3. Select your frontend repository
4. Vercel will detect Next.js automatically
5. Click **"Deploy"**

### **2.3 Configure Environment Variables**
1. In Vercel project, go to **"Settings"** → **"Environment Variables"**
2. Add these variables (from `vercel_env_template.txt`):

```
NEXT_PUBLIC_API_URL=https://arkashri-backend.up.railway.app
NEXT_PUBLIC_WS_URL=wss://arkashri-backend.up.railway.app/ws
```

**Important:** Replace `arkashri-backend` with your actual Railway project name.

### **2.4 Redeploy Frontend**
Vercel will automatically redeploy with new environment variables.

### **2.5 Get Frontend URL**
Vercel will give you a URL like:
```
https://arkashri.vercel.app
```

---

## 🗄️ STEP 3: Configure AWS S3 Evidence Storage

### **3.1 Create S3 Bucket**
1. Go to [AWS S3 Console](https://s3.console.aws.amazon.com)
2. Click **"Create bucket"**
3. Bucket name: `arkashri-production-worm-archive`
4. Region: `ap-south-1`
5. Block all public access: ✅
6. Enable **"Versioning"**
7. Enable **"Object Lock"** (WORM compliance)

### **3.2 Bucket Policy**
Add this bucket policy for security:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DenyPublicAccess",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": "arn:aws:s3:::arkashri-production-worm-archive/*"
        }
    ]
}
```

---

## 🧪 STEP 4: Test Complete System

### **4.1 Health Checks**
```bash
# Test backend health
curl https://arkashri-backend.up.railway.app/

# Test frontend
curl https://arkashri.vercel.app/

# Test API docs
curl https://arkashri-backend.up.railway.app/docs
```

### **4.2 Complete Workflow Test**
1. **Open Frontend**: https://arkashri.vercel.app
2. **Test Login**: Navigate to sign-in page
3. **Create Audit**: Start a new audit engagement
4. **Upload Evidence**: Test file upload
5. **Run Audit**: Execute audit workflow
6. **Check Results**: Verify audit report generation
7. **Blockchain Anchor**: Verify evidence anchoring

### **4.3 WebSocket Test**
Open browser console and test real-time updates:
```javascript
// Test WebSocket connection
const ws = new WebSocket('wss://arkashri-backend.up.railway.app/ws');
ws.onmessage = (event) => console.log('Received:', event.data);
```

---

## 📊 Expected Costs (Staging)

| Service | Cost/Month |
|---------|------------|
| Railway Backend | $10-20 |
| PostgreSQL | $10 |
| Redis | $5 |
| Vercel Frontend | Free |
| S3 Storage | $2-10 |

**Total: ~$30-45/month**

---

## 🔍 Troubleshooting

### **Common Issues & Solutions**

#### **Backend Fails to Start**
```bash
# Check Railway logs
# In Railway dashboard → View logs

# Common fixes:
# 1. Missing environment variables
# 2. Database connection issues
# 3. Port binding problems
```

#### **Frontend API Connection Errors**
```bash
# Check environment variables in Vercel
# Ensure NEXT_PUBLIC_API_URL is correct
# Test backend URL directly
```

#### **Database Issues**
```bash
# Check Railway database status
# Verify DATABASE_URL format
# Run migrations manually if needed
```

#### **WebSocket Not Working**
```bash
# Ensure Railway supports WebSockets
# Check NEXT_PUBLIC_WS_URL format
# Verify backend WebSocket endpoints
```

---

## 🎯 Success Criteria

Your staging deployment is successful when:

✅ **Backend**: https://arkashri-backend.up.railway.app responds with 200 OK  
✅ **Frontend**: https://arkashri.vercel.app loads and authenticates  
✅ **Database**: PostgreSQL connected and migrations applied  
✅ **Queue**: Redis connected and ARQ workers running  
✅ **Storage**: S3 bucket accepts file uploads  
✅ **Workflow**: Complete audit workflow functions  
✅ **Blockchain**: Evidence anchoring to Polkadot works  

---

## 🚀 Next Steps After Staging

### **1. Load Testing**
```bash
# Use k6 or Locust to test with 100+ concurrent users
# Test large evidence uploads
# Test multiple simultaneous audits
```

### **2. Security Testing**
- Run OWASP ZAP security scan
- Test authentication and authorization
- Verify CORS and security headers

### **3. Performance Monitoring**
- Set up Sentry error tracking
- Monitor API response times
- Check database query performance

### **4. User Acceptance Testing**
- Test with internal users
- Gather feedback on UI/UX
- Fix any discovered issues

---

## 🎉 Deployment Complete!

Once all tests pass, you'll have:

- **Frontend**: https://arkashri.vercel.app
- **Backend**: https://arkashri-backend.up.railway.app  
- **Database**: PostgreSQL on Railway
- **Queue**: Redis on Railway
- **Storage**: S3 WORM bucket
- **Blockchain**: Polkadot anchoring

**Your Arkashri Audit OS is now running in staging!** 🎉

Ready for private beta testing and eventually production deployment.

---

## 📞 Need Help?

If you encounter issues:
1. Check Railway and Vercel logs
2. Verify environment variables
3. Test individual components
4. Review this troubleshooting section

**Good luck with your staging deployment!** 🚀
