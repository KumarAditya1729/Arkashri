# Arkashri OS: AWS Production Setup Guide

To run Arkashri OS securely in production, we need to set up two services on Amazon Web Services (AWS):
1. **Amazon S3 (Simple Storage Service):** For WORM (Write Once, Read Many) immutable archival of audit evidence and reports.
2. **Amazon SES (Simple Email Service):** For sending automated audit notifications to clients and partners.

Follow this guide step-by-step to generate the keys needed for your `.env` file.

---

## Part 1: Initial AWS Setup (If you don't have an account)
1. Go to [aws.amazon.com](https://aws.amazon.com/) and click **"Create an AWS Account"**.
2. Fill in your details and add a billing credit card (don't worry, the Free Tier covers what we need right now).
3. Once logged into the **AWS Management Console**, look at the top right corner (next to your name) and select your timezone/region. For example, select **Asia Pacific (Mumbai) ap-south-1**.
   - *Note your region code (e.g., `ap-south-1`). We need this for the `.env` file!*

---

## Part 2: Setting up Amazon S3 (WORM Archive)
We need to create a bucket that acts as a digital vault. Once Arkashri puts an audit zip file in here, it can *never* be altered or deleted.

1. In the top search bar, type **"S3"** and click on it.
2. Click the orange **"Create bucket"** button.
3. **Bucket name:** Enter a globally unique name, like `arkashri-worm-archive-yourname`.
4. **AWS Region:** Select the region you chose earlier (e.g., `ap-south-1`).
5. **Object Ownership:** Leave as "ACLs disabled".
6. **Block Public Access:** Ensure "Block all public access" is **CHECKED**. We don't want the internet reading your confidential audits.
7. **Bucket Versioning:** Select **Enable**. (Required for object lock).
8. Scroll to the bottom and click **Advanced settings**.
9. **Object Lock:** Select **Enable**. Check the box acknowledging that this will protect objects from being deleted or overwritten.
10. Click **Create bucket**.

*In your `.env` file, update:*
`S3_WORM_BUCKET=arkashri-worm-archive-yourname`

---

## Part 3: Setting up Amazon SES (Email Notifications)
We need to authorize AWS to send emails on behalf of your domain (e.g., `audit@yourstartup.com`).

1. In the top search bar, type **"SES"** and click **Amazon Simple Email Service**.
2. On the left menu, click **Identities**.
3. Click the orange **Create identity** button.
4. Select **Email address** (or Domain if you have one set up).
5. Enter your email address (e.g., your student email or personal email) and click **Create identity**.
6. Check your email inbox. AWS will send you a verification link. Click it to prove you own the email.
7. *Note: By default, AWS puts you in a "Sandbox" where you can only send emails TO verified addresses. For production, you will later click "Request production access" on the SES dashboard.*

*In your `.env` file, update:*
`EMAIL_PROVIDER=aws_ses`
`EMAIL_FROM=your_verified_email@example.com`

---

## Part 4: Generating the Security Keys (IAM)
Arkashri needs a secure "username and password" to talk to AWS. We will create an IAM User.

1. In the top search bar, type **"IAM"** and click it.
2. On the left menu, click **Users**, then click the orange **Create user** button.
3. **User name:** Enter `arkashri-api-worker`. Click **Next**.
4. **Permissions options:** Select **Attach policies directly**.
5. In the search box below, search for and check these two policies:
   - `AmazonS3FullAccess`
   - `AmazonSESFullAccess`
6. Click **Next**, then click **Create user**.
7. You will be taken back to the Users list. Click on your new `arkashri-api-worker` user.
8. Click the **Security credentials** tab.
9. Scroll down to **Access keys** and click **Create access key**.
10. Select **Application running outside AWS** and click **Next**, then **Create access key**.
11. You will now see an **Access key ID** and a **Secret access key**. 
    - *WARNING: This is the ONLY time AWS will show you the Secret Key. Copy it immediately.*

---

## Part 5: Finalizing your .env
Take the keys you just generated and paste them into your `.env` file:

```ini
# ── S3 WORM Archive
S3_WORM_BUCKET=arkashri-worm-archive-yourname # From Part 2
AWS_ACCESS_KEY_ID=AKIA...                      # From Part 4
AWS_SECRET_ACCESS_KEY=wJalrX...                # From Part 4
AWS_REGION=ap-south-1

# ── Email (AWS SES)
EMAIL_PROVIDER=aws_ses
EMAIL_FROM=your_verified_email@example.com     # From Part 3
AWS_SES_ACCESS_KEY_ID=AKIA...                  # Same as above
AWS_SES_SECRET_ACCESS_KEY=wJalrX...            # Same as above
AWS_SES_REGION=ap-south-1
```

**You are done!** Arkashri OS can now permanently archive audits to S3 and dispatch emails to clients!
