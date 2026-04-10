# Arkashri Architecture Graphs

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        CF[Web Frontend]
        MB[Mobile App]
        API_CLIENT[API Clients]
    end
    
    subgraph "CDN/Edge"
        CDN[Cloudflare/Vercel CDN]
    end
    
    subgraph "Load Balancer"
        LB[Application Load Balancer]
    end
    
    subgraph "API Gateway"
        GW[API Gateway]
        AUTH[Authentication Service]
        RATE[Rate Limiting]
        SEC[Security Middleware]
    end
    
    subgraph "Application Services"
        API1[API Pod 1]
        API2[API Pod 2]
        API3[API Pod 3]
        WORKER1[Background Worker 1]
        WORKER2[Background Worker 2]
    end
    
    subgraph "Data Layer"
        PG_MASTER[(PostgreSQL Master)]
        PG_REPLICA1[(PostgreSQL Replica 1)]
        PG_REPLICA2[(PostgreSQL Replica 2)]
        REDIS_MASTER[(Redis Master)]
        REDIS_REPLICA[(Redis Replica)]
    end
    
    subgraph "External Services"
        BLOCKCHAIN[Polkadot/Ethereum]
        S3[AWS S3 Storage]
        SMTP[Email Service]
        OPENAI[OpenAI API]
    end
    
    subgraph "Monitoring"
        SENTRY[Sentry Error Tracking]
        PROMETHEUS[Prometheus Metrics]
        CLOUDWATCH[CloudWatch Logs]
    end
    
    CF --> CDN
    MB --> CDN
    API_CLIENT --> CDN
    CDN --> LB
    LB --> GW
    GW --> AUTH
    AUTH --> RATE
    RATE --> SEC
    SEC --> API1
    SEC --> API2
    SEC --> API3
    
    API1 --> PG_MASTER
    API2 --> PG_MASTER
    API3 --> PG_MASTER
    API1 --> PG_REPLICA1
    API2 --> PG_REPLICA2
    API3 --> PG_REPLICA1
    
    API1 --> REDIS_MASTER
    API2 --> REDIS_MASTER
    API3 --> REDIS_MASTER
    
    WORKER1 --> PG_MASTER
    WORKER2 --> PG_MASTER
    WORKER1 --> REDIS_MASTER
    WORKER2 --> REDIS_MASTER
    
    API1 --> BLOCKCHAIN
    API2 --> S3
    API3 --> SMTP
    WORKER1 --> OPENAI
    
    API1 --> SENTRY
    API2 --> PROMETHEUS
    API3 --> CLOUDWATCH
```

## 2. Microservices Architecture Flow

```mermaid
graph LR
    subgraph "Frontend Services"
        WEB[Next.js Frontend]
        WS[WebSocket Client]
    end
    
    subgraph "API Gateway"
        GATEWAY[FastAPI Gateway]
        MIDDLEWARE[Middleware Stack]
    end
    
    subgraph "Core Business Services"
        DECISION[Decision Engine]
        AUDIT[Audit Service]
        APPROVAL[Approval Service]
        RAG[RAG Service]
        BLOCKCHAIN[Blockchain Service]
    end
    
    subgraph "Support Services"
        AUTH[Auth Service]
        USER[User Service]
        NOTIFICATION[Notification Service]
        REPORT[Report Service]
    end
    
    subgraph "Data Services"
        POSTGRES[(PostgreSQL)]
        REDIS[(Redis Cache)]
        S3_STORAGE[(S3 Storage)]
    end
    
    subgraph "External Integrations"
        POLKADOT[Polkadot Network]
        ETHEREUM[Ethereum Network]
        ERP[ERP Systems]
        REGULATORY[Regulatory Feeds]
    end
    
    WEB --> GATEWAY
    WS --> GATEWAY
    GATEWAY --> MIDDLEWARE
    MIDDLEWARE --> DECISION
    MIDDLEWARE --> AUDIT
    MIDDLEWARE --> APPROVAL
    MIDDLEWARE --> RAG
    MIDDLEWARE --> BLOCKCHAIN
    
    DECISION --> AUTH
    AUDIT --> USER
    APPROVAL --> NOTIFICATION
    RAG --> REPORT
    
    DECISION --> POSTGRES
    AUDIT --> POSTGRES
    APPROVAL --> POSTGRES
    RAG --> REDIS
    BLOCKCHAIN --> S3_STORAGE
    
    BLOCKCHAIN --> POLKADOT
    BLOCKCHAIN --> ETHEREUM
    AUDIT --> ERP
    RAG --> REGULATORY
```

## 3. Database Schema Architecture

```mermaid
erDiagram
    %% Core Registry Tables
    RULE_REGISTRY {
        int id PK
        string rule_key
        int version
        string name
        text description
        json expression
        float signal_value
        float severity_floor
        boolean is_active
        timestamp created_at
    }
    
    FORMULA_REGISTRY {
        int id PK
        int version UK
        text formula_text
        string formula_hash
        json variables
        boolean is_active
        timestamp created_at
    }
    
    WEIGHT_REGISTRY {
        int id PK
        string weight_key
        int version
        json weight_matrix
        float default_weight
        boolean is_active
        timestamp created_at
    }
    
    MODEL_REGISTRY {
        int id PK
        string model_key
        int version
        string model_type
        json model_config
        string status
        float accuracy
        timestamp created_at
    }
    
    %% Decision Engine Tables
    DECISIONS {
        string id PK
        string tenant_id
        string jurisdiction
        json input_data
        json risk_scores
        string final_decision
        string decision_hash
        json explanation
        timestamp created_at
    }
    
    AUDIT_EVENTS {
        string id PK
        string tenant_id
        string jurisdiction
        string event_type
        json event_data
        string previous_hash
        string current_hash
        timestamp created_at
    }
    
    %% Engagement & Workflow Tables
    ENGAGEMENTS {
        string id PK
        string tenant_id
        string engagement_type
        string status
        json metadata
        string created_by
        timestamp created_at
        timestamp updated_at
    }
    
    APPROVAL_REQUESTS {
        string id PK
        string engagement_id FK
        string requester_id
        string approver_id
        string status
        json request_data
        timestamp created_at
        timestamp resolved_at
    }
    
    %% User Management Tables
    USERS {
        string id PK
        string email UK
        string name
        string role
        boolean is_active
        timestamp created_at
        timestamp last_login
    }
    
    API_CLIENTS {
        string id PK
        string client_name
        string api_key_hash
        json permissions
        boolean is_active
        timestamp created_at
        timestamp last_used
    }
    
    %% Knowledge & RAG Tables
    REGULATORY_SOURCES {
        string id PK
        string source_key
        string jurisdiction
        string source_type
        json config
        boolean is_active
        timestamp created_at
    }
    
    DOCUMENTS {
        string id PK
        string source_id FK
        string document_id
        string title
        text content
        string document_hash
        string status
        timestamp created_at
    }
    
    RAG_EMBEDDINGS {
        string id PK
        string document_id FK
        int chunk_index
        vector embedding
        text chunk_text
        timestamp created_at
    }
    
    %% Blockchain Tables
    BLOCKCHAIN_ANCHORS {
        string id PK
        string tenant_id
        string jurisdiction
        string merkle_root
        string transaction_hash
        string network
        timestamp anchored_at
        timestamp created_at
    }
    
    ATTESTATION_RECORDS {
        string id PK
        string anchor_id FK
        string attester_id
        string signature
        json attestation_data
        timestamp created_at
    }
    
    %% Relationships
    RULE_REGISTRY ||--o{ DECISIONS : "generates"
    FORMULA_REGISTRY ||--o{ DECISIONS : "calculates"
    WEIGHT_REGISTRY ||--o{ DECISIONS : "weights"
    MODEL_REGISTRY ||--o{ DECISIONS : "predicts"
    
    DECISIONS ||--o{ AUDIT_EVENTS : "logs"
    AUDIT_EVENTS ||--o{ BLOCKCHAIN_ANCHORS : "anchors"
    BLOCKCHAIN_ANCHORS ||--o{ ATTESTATION_RECORDS : "attests"
    
    ENGAGEMENTS ||--o{ APPROVAL_REQUESTS : "requires"
    USERS ||--o{ APPROVAL_REQUESTS : "approves"
    USERS ||--o{ ENGAGEMENTS : "creates"
    
    REGULATORY_SOURCES ||--o{ DOCUMENTS : "contains"
    DOCUMENTS ||--o{ RAG_EMBEDDINGS : "indexes"
```

## 4. Service Communication Flow

```mermaid
sequenceDiagram
    participant Client as Frontend Client
    participant Gateway as API Gateway
    participant Auth as Auth Service
    participant Decision as Decision Engine
    participant DB as PostgreSQL
    participant Cache as Redis
    participant Blockchain as Blockchain Service
    participant Audit as Audit Service
    
    Client->>Gateway: POST /decisions/score
    Gateway->>Auth: Validate JWT/API Key
    Auth-->>Gateway: Token Valid
    Gateway->>Decision: Process Decision Request
    
    Decision->>Cache: Check Cached Rules
    alt Cache Hit
        Cache-->>Decision: Return Cached Rules
    else Cache Miss
        Decision->>DB: Fetch Rules/Formulas
        DB-->>Decision: Return Rules
        Decision->>Cache: Cache Rules
    end
    
    Decision->>Decision: Calculate Risk Scores
    Decision->>Decision: Generate Decision Hash
    Decision->>Audit: Log Audit Event
    Audit->>DB: Store Audit Trail
    Audit->>Blockchain: Anchor to Blockchain
    
    Decision-->>Gateway: Decision Result
    Gateway-->>Client: Response with Decision
```

## 5. Deployment Architecture

```mermaid
graph TB
    subgraph "Development Environment"
        DEV_DOCKER[Docker Compose]
        DEV_DB[(PostgreSQL)]
        DEV_REDIS[(Redis)]
        DEV_API[API Service]
        DEV_WEB[Frontend Dev]
        DEV_WORKER[Background Worker]
        
        DEV_DOCKER --> DEV_DB
        DEV_DOCKER --> DEV_REDIS
        DEV_DOCKER --> DEV_API
        DEV_DOCKER --> DEV_WEB
        DEV_DOCKER --> DEV_WORKER
    end
    
    subgraph "Staging Environment"
        STAGING_K8S[Kubernetes Cluster]
        STAGING_RDS[(RDS PostgreSQL)]
        STAGING_ELASTICACHE[(ElastiCache)]
        STAGING_PODS[API Pods]
        STAGING_FRONTEND[Staging Frontend]
        
        STAGING_K8S --> STAGING_RDS
        STAGING_K8S --> STAGING_ELASTICACHE
        STAGING_K8S --> STAGING_PODS
        STAGING_K8S --> STAGING_FRONTEND
    end
    
    subgraph "Production Environment"
        PROD_EKS[AWS EKS]
        PROD_RDS[(RDS with Read Replicas)]
        PROD_REDIS[(ElastiCache Cluster)]
        PROD_API[Production API Pods]
        PROD_WORKER[Worker Pods]
        PROD_FRONTEND[Vercel Frontend]
        PROD_S3[S3 Storage]
        PROD_CLOUDFRONT[CloudFront CDN]
        
        PROD_EKS --> PROD_RDS
        PROD_EKS --> PROD_REDIS
        PROD_EKS --> PROD_API
        PROD_EKS --> PROD_WORKER
        PROD_EKS --> PROD_S3
        PROD_FRONTEND --> PROD_CLOUDFRONT
    end
    
    subgraph "CI/CD Pipeline"
        GITHUB[GitHub Actions]
        ECR[Amazon ECR]
        PIPELINE[Deploy Pipeline]
        
        GITHUB --> ECR
        ECR --> PIPELINE
        PIPELINE --> STAGING_K8S
        PIPELINE --> PROD_EKS
    end
```

## 6. Security Architecture

```mermaid
graph TD
    subgraph "Authentication Layer"
        OAUTH[OAuth2/OIDC]
        MFA[Multi-Factor Auth]
        JWT[JWT Tokens]
        API_KEYS[API Key Management]
    end
    
    subgraph "Authorization Layer"
        RBAC[Role-Based Access Control]
        PERMISSIONS[Permission System]
        SCOPES[OAuth Scopes]
    end
    
    subgraph "Security Middleware"
        RATE_LIMIT[Rate Limiting]
        THROTTLE[Request Throttling]
        VALIDATION[Input Validation]
        SANITIZATION[Data Sanitization]
    end
    
    subgraph "Data Protection"
        ENCRYPTION[AES-256 Encryption]
        HASHING[SHA-256 Hashing]
        MASKING[PII Masking]
        BACKUP[Encrypted Backups]
    end
    
    subgraph "Network Security"
        TLS[TLS 1.3]
        FIREWALL[Web Application Firewall]
        CORS[CORS Policies]
        CSP[Content Security Policy]
    end
    
    subgraph "Monitoring & Audit"
        AUDIT_LOG[Immutable Audit Trail]
        SECURITY_LOG[Security Event Logging]
        ALERTING[Threat Detection]
        COMPLIANCE[Compliance Reporting]
    end
    
    OAUTH --> RBAC
    MFA --> PERMISSIONS
    JWT --> SCOPES
    API_KEYS --> RATE_LIMIT
    
    RBAC --> VALIDATION
    PERMISSIONS --> SANITIZATION
    SCOPES --> ENCRYPTION
    
    VALIDATION --> TLS
    SANITIZATION --> FIREWALL
    ENCRYPTION --> AUDIT_LOG
    HASHING --> SECURITY_LOG
    
    TLS --> ALERTING
    FIREWALL --> COMPLIANCE
    AUDIT_LOG --> BACKUP
```

## 7. Data Flow Architecture

```mermaid
graph LR
    subgraph "Input Sources"
        USER_INPUT[User Input]
        API_REQUEST[API Requests]
        WEBHOOK[Webhooks]
        FILE_UPLOAD[File Uploads]
        ERP_DATA[ERP Systems]
    end
    
    subgraph "Processing Layer"
        VALIDATION[Input Validation]
        ENRICHMENT[Data Enrichment]
        TRANSFORMATION[Data Transformation]
        ENCRYPTION[Data Encryption]
    end
    
    subgraph "Business Logic"
        DECISION_ENGINE[Decision Engine]
        RISK_ASSESSMENT[Risk Assessment]
        COMPLIANCE_CHECK[Compliance Check]
        AUDIT_TRAIL[Audit Trail]
    end
    
    subgraph "Storage Layer"
        TRANSACTIONAL_DB[(Transactional DB)]
        ANALYTICAL_DB[(Analytical DB)]
        CACHE_LAYER[(Cache Layer)]
        BLOB_STORAGE[(Blob Storage)]
        BLOCKCHAIN[Blockchain]
    end
    
    subgraph "Output Destinations"
        API_RESPONSE[API Response]
        DASHBOARD[Dashboard]
        REPORTS[Reports]
        NOTIFICATIONS[Notifications]
        EXPORTS[Data Exports]
    end
    
    USER_INPUT --> VALIDATION
    API_REQUEST --> VALIDATION
    WEBHOOK --> ENRICHMENT
    FILE_UPLOAD --> TRANSFORMATION
    ERP_DATA --> ENCRYPTION
    
    VALIDATION --> DECISION_ENGINE
    ENRICHMENT --> RISK_ASSESSMENT
    TRANSFORMATION --> COMPLIANCE_CHECK
    ENCRYPTION --> AUDIT_TRAIL
    
    DECISION_ENGINE --> TRANSACTIONAL_DB
    RISK_ASSESSMENT --> ANALYTICAL_DB
    COMPLIANCE_CHECK --> CACHE_LAYER
    AUDIT_TRAIL --> BLOCKCHAIN
    
    TRANSACTIONAL_DB --> API_RESPONSE
    ANALYTICAL_DB --> DASHBOARD
    CACHE_LAYER --> REPORTS
    BLOB_STORAGE --> NOTIFICATIONS
    BLOCKCHAIN --> EXPORTS
```

## 8. Component Dependency Graph

```mermaid
graph TD
    subgraph "Frontend Components"
        LAYOUT[Layout.tsx]
        AUTH_GUARD[AuthGuard]
        WS_PROVIDER[WebSocketProvider]
        DASHBOARD[Dashboard]
        AUDIT_SHELL[AuditShell]
    end
    
    subgraph "Backend Core"
        MAIN_APP[main.py]
        CONFIG[config.py]
        DATABASE[db.py]
        MIDDLEWARE[middleware/]
        ROUTERS[routers/]
    end
    
    subgraph "Services Layer"
        DECISION_SVC[Decision Service]
        AUDIT_SVC[Audit Service]
        AUTH_SVC[Auth Service]
        BLOCKCHAIN_SVC[Blockchain Service]
        RAG_SVC[RAG Service]
    end
    
    subgraph "Data Access Layer"
        REPOSITORIES[Repositories]
        MODELS[Models]
        MIGRATIONS[Alembic Migrations]
        CONNECTIONS[Connection Pools]
    end
    
    subgraph "Infrastructure"
        DOCKER[Docker]
        K8S[Kubernetes]
        AWS[AWS Services]
        MONITORING[Monitoring Stack]
    end
    
    LAYOUT --> AUTH_GUARD
    AUTH_GUARD --> WS_PROVIDER
    WS_PROVIDER --> DASHBOARD
    DASHBOARD --> AUDIT_SHELL
    
    MAIN_APP --> CONFIG
    MAIN_APP --> DATABASE
    MAIN_APP --> MIDDLEWARE
    MAIN_APP --> ROUTERS
    
    ROUTERS --> DECISION_SVC
    ROUTERS --> AUDIT_SVC
    ROUTERS --> AUTH_SVC
    ROUTERS --> BLOCKCHAIN_SVC
    ROUTERS --> RAG_SVC
    
    SERVICES --> REPOSITORIES
    REPOSITORIES --> MODELS
    MODELS --> MIGRATIONS
    REPOSITORIES --> CONNECTIONS
    
    MAIN_APP --> DOCKER
    DOCKER --> K8S
    K8S --> AWS
    AWS --> MONITORING
```

## 9. Performance & Scaling Architecture

```mermaid
graph TB
    subgraph "Load Distribution"
        LB[Load Balancer]
        CDN[CDN]
        EDGE[Edge Computing]
    end
    
    subgraph "Application Scaling"
        HORIZONTAL[Horizontal Scaling]
        VERTICAL[Vertical Scaling]
        AUTOSCALING[Auto Scaling Groups]
    end
    
    subgraph "Database Scaling"
        READ_REPLICAS[Read Replicas]
        SHARDING[Database Sharding]
        PARTITIONING[Table Partitioning]
        CONNECTION_POOL[Connection Pooling]
    end
    
    subgraph "Caching Strategy"
        L1_CACHE[Application Cache]
        L2_CACHE[Redis Cache]
        L3_CACHE[CDN Cache]
        PERSISTENT_CACHE[Persistent Cache]
    end
    
    subgraph "Background Processing"
        QUEUE[Message Queue]
        WORKERS[Background Workers]
        SCHEDULED_TASKS[Scheduled Tasks]
        BATCH_PROCESSING[Batch Processing]
    end
    
    subgraph "Performance Monitoring"
        METRICS[Metrics Collection]
        TRACING[Distributed Tracing]
        PROFILING[Performance Profiling]
        ALERTS[Performance Alerts]
    end
    
    LB --> HORIZONTAL
    CDN --> VERTICAL
    EDGE --> AUTOSCALING
    
    HORIZONTAL --> READ_REPLICAS
    VERTICAL --> SHARDING
    AUTOSCALING --> PARTITIONING
    
    READ_REPLICAS --> L1_CACHE
    SHARDING --> L2_CACHE
    PARTITIONING --> L3_CACHE
    CONNECTION_POOL --> PERSISTENT_CACHE
    
    L1_CACHE --> QUEUE
    L2_CACHE --> WORKERS
    L3_CACHE --> SCHEDULED_TASKS
    PERSISTENT_CACHE --> BATCH_PROCESSING
    
    QUEUE --> METRICS
    WORKERS --> TRACING
    SCHEDULED_TASKS --> PROFILING
    BATCH_PROCESSING --> ALERTS
```

## 10. Technology Stack Graph

```mermaid
graph TB
    subgraph "Frontend Stack"
        NEXTJS[Next.js 16]
        REACT[React 19.2]
        TYPESCRIPT[TypeScript]
        TAILWIND[Tailwind CSS 4]
        ZUSTAND[Zustand]
        REACT_QUERY[React Query]
    end
    
    subgraph "Backend Stack"
        FASTAPI[FastAPI 2.0]
        PYTHON[Python 3.11]
        SQLALCHEMY[SQLAlchemy 2.0]
        ALEMBIC[Alembic]
        PYDANTIC[Pydantic]
        ARQ[ARQ]
    end
    
    subgraph "Database Stack"
        POSTGRES[PostgreSQL 16]
        REDIS[Redis 7]
        ASYNCPG[AsyncPG]
        PSYCOPG[Psycopg3]
    end
    
    subgraph "Infrastructure Stack"
        DOCKER[Docker]
        KUBERNETES[Kubernetes]
        AWS[AWS]
        RAILWAY[Railway]
        VERCEL[Vercel]
    end
    
    subgraph "Monitoring Stack"
        SENTRY[Sentry]
        PROMETHEUS[Prometheus]
        GRAFANA[Grafana]
        STRUCTLOG[Structlog]
        OPENTELEMETRY[OpenTelemetry]
    end
    
    subgraph "Blockchain Stack"
        POLKADOT[Polkadot.py]
        ETHERS[Ethers.js]
        WEB3[Web3.py]
        SOLIDITY[Solidity]
    end
    
    NEXTJS --> FASTAPI
    REACT --> PYTHON
    TYPESCRIPT --> SQLALCHEMY
    TAILWIND --> ALEMBIC
    
    FASTAPI --> POSTGRES
    PYTHON --> REDIS
    SQLALCHEMY --> ASYNCPG
    ALEMBIC --> PSYCOPG
    
    POSTGRES --> DOCKER
    REDIS --> KUBERNETES
    ASYNCPG --> AWS
    PSYCOPG --> RAILWAY
    
    DOCKER --> SENTRY
    KUBERNETES --> PROMETHEUS
    AWS --> GRAFANA
    RAILWAY --> STRUCTLOG
    
    SENTRY --> POLKADOT
    PROMETHEUS --> ETHERS
    GRAFANA --> WEB3
    STRUCTLOG --> SOLIDITY
```

These graphs provide a comprehensive visual representation of the Arkashri architecture, covering all major aspects from high-level system design to detailed component relationships and technology stack choices.
