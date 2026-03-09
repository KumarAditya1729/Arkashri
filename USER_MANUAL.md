# Arkashri OS: Comprehensive Universal Audit Manual

Welcome to the **Arkashri OS V2.0 User Manual**. Arkashri is an Infrastructure-Grade Financial Intelligence Engine capable of supporting **16 distinct audit playbooks** simultaneously with up to 90% AI-driven automation. 

This manual details how to initiate, manage, and complete every type of audit available on your platform.

---

## Table of Contents
1. [Core Concepts & The 7-Day Turnaround](#core-concepts--the-7-day-turnaround)
2. [How to Start Any Audit](#how-to-start-any-audit)
3. [The 16 Supported Audit Types (Detailed Breakdown)](#the-16-supported-audit-types-detailed-breakdown)
4. [Monitoring AI Execution (Live WebSockets)](#monitoring-ai-execution-live-websockets)
5. [Human Governance (Overrides & Approvals)](#human-governance-overrides--approvals)
6. [Report Generation & Blockchain Anchoring](#report-generation--blockchain-anchoring)

---

## 1. Core Concepts & The 7-Day Turnaround

Traditional audits take 3-6 months. Arkashri is built to execute an audit in **7 days** through Mass Parallelization. 

* **The Orchestrator:** Instead of sending an Excel file back and forth, you upload the raw data (or sync via Tally/Zoho ERP). The Arkashri Orchestrator instantly spawns hundreds of independent "Checks" (e.g., matching invoice 124 to bank transaction 932).
* **The AI Fabric (GPT-4o):** For checks that require "judgment" (like reading a complex lease agreement), the engine securely passes the document securely to the AI Fabric. The AI acts as your "Junior Staff," doing the reading and flagging anomalies. 
* **The Ledger:** Every single action the AI or a Human takes is cryptographically signed and stored in an immutable ledger. 

---

## 2. How to Start Any Audit

Whether it's a Financial Audit or an IT Audit, the workflow to start is identical in the Next.js Frontend.

1. **Log In:** Access your dashboard using an `OPERATOR` or `ADMIN` account.
2. **Create Engagement:** Click "New Engagement".
3. **Select Tenant:** Choose the client company you are auditing.
4. **Select Jurisdiction:** e.g., `IN` for India, `US` for United States. This tells the system which regulatory RAG database to read from.
5. **Select Audit Type:** Pick one of the 16 playbooks from the dropdown (detailed below).
6. **Upload Evidence:** Drag and drop Bank Statements, PDFs, Ledgers, or click "Sync ERP". 
7. **Launch:** Click "Start Pipeline". The system will immediately begin processing.

---

## 3. The 16 Supported Audit Types (Detailed Breakdown)

Arkashri OS dynamically loads JSON logic templates. Here is exactly what each template does and how you use them:

### 1. Financial Audit (`financial_audit.json`)
* **Purpose:** The classic external financial statement audit. Ensures balance sheets and P&L are truthful and fair.
* **How to use it:** Upload the Trial Balance, General Ledger, and Bank Statements. The AI will automatically perform 3-way matching between invoices, ledgers, and bank feeds.
* **Automation Level:** 90%. AI handles all reconciliation. Humans only review the flagged "high risk" discrepancies.

### 2. Statutory Audit (`statutory_audit.json`)
* **Purpose:** Mandated by law (like the Companies Act in India). Checks legal compliance alongside financial truth.
* **How to use it:** Similar to Financial, but you must also upload Board Minutes and Statutory Registers. The AI uses the RAG module to read the minutes and ensure they comply with local corporate laws.

### 3. Tax Audit (`tax_audit.json`)
* **Purpose:** Verifies that tax filings (GST, Income Tax) match the raw financial data.
* **How to use it:** Upload previous tax returns and current year ledgers. The engine will explicitly search for non-deductible expenses (like personal travel lumped into business expenses) and flag them.

### 4. Internal Audit (`internal_audit.json`)
* **Purpose:** A health check initiated by the company itself to find inefficiencies or internal control failures.
* **How to use it:** Upload process manuals and sample transaction strings. The AI evaluates if employees are actually following the documented rules (e.g., verifying if POs over $10,000 actually got 2 signatures).

### 5. Compliance Audit (`compliance_audit.json`)
* **Purpose:** Checks adherence to external regulations (like HIPAA, GDPR, or RBI guidelines).
* **How to use it:** The AI will query the specific regulatory texts via the native RAG engine and cross-reference them against the client's uploaded policy documents.

### 6. External Audit (`external_audit.json`)
* **Purpose:** A broader scope audit typically done by third parties for shareholders or investors. 
* **How to use it:** Acts as a superset of the Financial Audit with added layers of independence checks and conflict-of-interest scanning.

### 7. Forensic Audit (`forensic_audit.json`)
* **Purpose:** Deep-dive investigation looking specifically for fraud, embezzlement, or legal disputes.
* **How to use it:** The Risk Engine is dialed to maximum sensitivity. The AI ignores material thresholds (meaning it will flag a suspicious $5 transaction just as heavily as a $50,000 one). Upload email chains, expense reports, and chat logs.

### 8. Forensic Risk Profile V1 (`forensic_risk_profile_v1.json`)
* **Purpose:** Not a full audit, but a rapid 24-hour scan to assign a "Fraud Heatmap" score to a new client before accepting them.
* **How to use it:** Only requires high-level ledger dumps and metadata. Excellent for preliminary client risk scoring.

### 9. IT Audit (`it_audit.json`)
* **Purpose:** Evaluates the security and integrity of the client's software infrastructure.
* **How to use it:** Upload access logs, SOC2 reports, and server configurations. The AI will parse access logs to find unauthorized admin logins or improper data segregation.

### 10. Environmental Audit (`environmental_audit.json`)
* **Purpose:** Checks literal compliance with pollution control board laws or waste disposal regulations.
* **How to use it:** Upload factory emission logs, waste disposal receipts, and electricity bills. The AI calculates expected vs. actual footprint.

### 11. ESG Deep Audit V1 (`esg_deep_audit_v1.json`)
* **Purpose:** Environmental, Social, and Governance scoring. Crucial for modern public companies.
* **How to use it:** Upload HR diversity reports, supply chain sourcing documents, and carbon footprint analyses. The AI will generate a standardized ESG rating scorecard.

### 12. Operational Audit (`operational_audit.json`)
* **Purpose:** Looks at business efficiency rather than financial exactness. Goal is to find wasted money or time.
* **How to use it:** Upload supply chain timelines and manufacturing cost breakdowns.

### 13. Payroll Audit (`payroll_audit.json`)
* **Purpose:** Strictly ensures employees are paid correctly and ghost-employees do not exist.
* **How to use it:** Give the engine the master HR roster and the bank payout files. It will match names, IDs, and tax bracket deductions perfectly across thousands of rows in seconds.

### 14. Performance Audit (`performance_audit.json`)
* **Purpose:** Often used for government/public sector entities to evaluate if program targets were met efficiently.

### 15. Quality Audit (`quality_audit.json`)
* **Purpose:** Ensures the company’s internal Quality Management System (like ISO 9001) is functioning.

### 16. Single Audit (`single_audit.json`)
* **Purpose:** Specifically for US entities that expend $750k+ in federal awards. Strict compliance checks on grant money usage.

---

## 4. Monitoring AI Execution (Live WebSockets)

Because Arkashri uses background ARQ workers and the OpenAI API, an audit handling 10,000 invoices might take 45 minutes of pure computational crunching.
* **The Live Feed:** You do not need to refresh your browser. The system uses the `ConnectionManager` we built to stream a live WebSocket feed to your UI.
* **What you will see:** A live ticker showing "Invoice 842 - Verified", "Lease Agreement 3 - Flagged: Missing Signature", etc.

---

## 5. Human Governance (Overrides & Approvals)

Arkashri OS is deterministic 90% automation. But what about the final 10%?

If the AI flags something it cannot confidently resolve (e.g., an invoice looks mostly fine but has a weird address), the step state changes to `PENDING_HUMAN`.
1. **The Reviewer Inbox:** A manager logs in and looks at the flagged item.
2. **Professional Skepticism (Overrides):** The human can click "Accept AI Conclusion" or "Override AI". 
3. **Audit Trail:** If the human overrides the AI, they *must* type a justification. This justification is permanently glued to that transaction in the database so regulators know exactly *why* a human overruled the machine.

---

## 6. Report Generation & Blockchain Anchoring

The 7-Day turnaround completes here.

1. **PDF Generation:** Once all auto-checks and human-checks hit `COMPLETED`, click "Generate Report". The system compiles a highly technical, legally compliant PDF Summary Report.
2. **The WORM Archive:** The entire history of the audit (all raw files, all AI logic trails, all human overrides) is zipped and dumped into an immutable Amazon S3 bucket.
3. **Polkadot Anchoring (Optional):** If enabled, the cryptographic SHA-256 hash of that final ZIP file is pushed to the public Polkadot Blockchain. 

**Why Blockchain?** If a regulator sues you 5 years from now claiming you forged the audit report, you can verify the Blockchain transaction hash against your S3 file. Math will prove your audit hasn't been tampered with since the exact second it was completed.

---
*End of Arkashri OS Universal Audit Manual*
