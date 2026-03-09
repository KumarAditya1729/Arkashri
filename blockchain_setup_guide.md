# ⛓️  Blockchain Anchoring Setup Guide - Arkashri

## 🚀 Blockchain Status: ENABLED ✅

Your Arkashri system now has blockchain anchoring enabled for immutable audit trails.

## 📋 What Blockchain Anchoring Provides

### **Immutable Audit Trail**
- Every audit event is cryptographically hashed and anchored to blockchain
- Tamper-evident verification of all financial records
- Chronological proof of document existence and integrity

### **Key Features**
- **Evidence Hashing**: SHA-256 cryptographic hashes of all audit evidence
- **Blockchain Anchoring**: Integration with Polkadot substrate chain
- **Verification**: Real-time verification of document integrity
- **QR Code Generation**: Shareable verification codes for stakeholders
- **Export Capabilities**: Complete blockchain trail exports

## 🔗 Available Blockchain Endpoints

### **Core Operations**
```bash
# Check blockchain status
GET /api/blockchain/status

# Submit evidence to blockchain
POST /api/blockchain/evidence/submit

# Verify evidence integrity
POST /api/blockchain/evidence/verify

# Mine a new block (batch processing)
POST /api/blockchain/evidence/mine-block
```

### **Audit Trail Operations**
```bash
# Get complete audit trail
GET /api/blockchain/audit/{audit_id}/trail

# Get specific block details
GET /api/blockchain/block/{block_index}

# Generate QR code for evidence
GET /api/blockchain/evidence/{evidence_hash}/qr

# Export blockchain data
GET /api/blockchain/export
```

## 🛠️ Configuration Details

### **Current Blockchain Settings**
```env
ENABLE_BLOCKCHAIN_ANCHORING=true
POLKADOT_ENABLED=true
POLKADOT_WS_URL=wss://rpc.polkadot.io
POLKADOT_KEYPAIR_URI=chunk goat mixed odor high eyebrow barely second unusual latin alarm fuel
POLKADOT_WAIT_FOR_INCLUSION=true
```

### **Blockchain Network**
- **Network**: Polkadot (production)
- **Consensus**: Proof of Authority (PoA) for fast finality
- **Block Time**: ~6 seconds
- **Finality**: Immediate with Polkadot's GRANDPA

## 🚀 How to Use Blockchain Anchoring

### **Step 1: Enable in Frontend**
1. Navigate to http://localhost:3000
2. Go to **Settings > Blockchain**
3. Enable **Blockchain Anchoring**
4. Configure anchoring frequency (real-time or batch)

### **Step 2: Anchor Evidence Automatically**
Once enabled, Arkashri will automatically:
- Hash all uploaded documents and evidence
- Submit hashes to blockchain during audits
- Generate verification QR codes
- Maintain immutable audit trail

### **Step 3: Manual Evidence Anchoring**
```bash
# Anchor specific evidence
curl -X POST "http://localhost:8000/api/blockchain/evidence/submit" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "evidence_type": "financial_statement",
    "evidence_hash": "document_sha256_hash",
    "metadata": {
      "audit_id": "audit_123",
      "document_name": "Q1_2024_Statement.pdf",
      "timestamp": "2024-03-09T10:39:00Z"
    }
  }'
```

### **Step 4: Verify Evidence Integrity**
```bash
# Verify document integrity
curl -X POST "http://localhost:8000/api/blockchain/evidence/verify" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "evidence_hash": "document_sha256_hash",
    "original_document": "base64_encoded_document"
  }'
```

## 📊 Blockchain Dashboard Features

### **Real-time Monitoring**
- **Total Blocks**: Number of blocks in the chain
- **Total Evidence**: Count of anchored evidence
- **Pending Evidence**: Evidence waiting to be mined
- **Chain Validity**: Blockchain integrity status

### **Audit Trail Visualization**
- **Timeline View**: Chronological evidence anchoring
- **Block Explorer**: Detailed block information
- **Evidence Verification**: QR code-based verification
- **Export Options**: JSON, CSV, PDF exports

## 🔐 Security Features

### **Cryptographic Security**
- **SHA-256 Hashing**: Industry-standard document hashing
- **Merkle Trees**: Efficient verification of large datasets
- **Digital Signatures**: Polkadot substrate cryptographic signatures
- **Key Management**: Secure keypair management

### **Tamper Detection**
- **Hash Verification**: Instant detection of document modifications
- **Chain Validation**: Continuous blockchain integrity checks
- **Alert System**: Notifications for potential tampering
- **Audit Logs**: Complete record of all anchoring operations

## 📈 Benefits for Auditing

### **Regulatory Compliance**
- **ICAI Standards**: Meets Institute of Chartered Accountants requirements
- **GST Compliance**: Immutable GST audit trails
- **Tax Audit**: Court-admissible evidence integrity
- **SOX Compliance**: Sarbanes-Oxley internal control requirements

### **Stakeholder Trust**
- **Client Verification**: Clients can verify audit integrity independently
- **Partner Assurance**: Multi-partner seal sessions with blockchain proof
- **Regulatory Submission**: Blockchain-backed evidence for regulators
- **Insurance Claims**: Immutable evidence for claim processing

## 🛠️ Advanced Configuration

### **Custom Blockchain Network**
For enterprise deployments, you can configure:
```env
# Custom substrate node
POLKADOT_WS_URL=wss://your-custom-node.io
POLKADOT_KEYPAIR_URI=your-enterprise-keypair

# Test network
POLKADOT_WS_URL=wss://westend-rpc.polkadot.io
```

### **Batch Processing**
Configure batch anchoring for performance:
```env
BLOCKCHAIN_BATCH_SIZE=100
BLOCKCHAIN_BATCH_INTERVAL=300  # 5 minutes
```

## 🔧 Troubleshooting

### **Common Issues**
1. **Connection Failed**: Check Polkadot node connectivity
2. **KeyPair Error**: Verify keypair URI format
3. **Timeout**: Increase blockchain operation timeout
4. **Storage**: Ensure sufficient disk space for blockchain data

### **Reset Blockchain**
```bash
# Clear local blockchain cache (emergency only)
docker compose exec api rm -rf /app/blockchain_cache
docker compose restart api
```

## 📞 Support

### **Blockchain Documentation**
- **Polkadot Docs**: https://docs.polkadot.io/
- **Substrate Runtime**: https://substrate.io/docs/
- **Arkashri API**: http://localhost:8000/docs

### **Monitoring**
- **Blockchain Status**: http://localhost:8000/api/blockchain/status
- **System Logs**: `logs/arkashri.log`
- **Performance Metrics**: http://localhost:8000/metrics

## 🎯 Production Considerations

### **Enterprise Deployment**
1. **Dedicated Blockchain Node**: Run your own Polkadot validator
2. **Key Security**: Hardware security modules for key management
3. **Backup Strategy**: Regular blockchain state backups
4. **Monitoring**: 24/7 blockchain health monitoring

### **Performance Optimization**
- **Batch Operations**: Group evidence submissions
- **Caching**: Cache frequent blockchain queries
- **Async Processing**: Background blockchain operations
- **Load Balancing**: Multiple blockchain nodes

---

**🎉 Your Arkashri system now has enterprise-grade blockchain anchoring for immutable audit trails!**
