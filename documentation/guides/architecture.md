---
id: architecture
title: Architecture Overview
sidebar_label: Architecture
sidebar_position: 1
---

# Architecture Overview

Understanding the Hokusai ML Platform architecture and how components work together.

## System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        CLI[CLI Tools]
        SDK[Python SDK]
        API[REST API]
    end
    
    subgraph "Application Layer"
        MS[Model Service]
        DS[Data Service]
        PS[Performance Service]
        RS[Reward Service]
        DSPY[DSPy Engine]
    end
    
    subgraph "Core Platform"
        MR[Model Registry]
        DO[DeltaOne Detector]
        AB[A/B Testing]
        IP[Inference Pipeline]
    end
    
    subgraph "Infrastructure"
        MLF[MLflow Server]
        REDIS[Redis Cache]
        S3[S3 Storage]
        ETH[Ethereum]
    end
    
    CLI --> MS
    SDK --> MS
    API --> MS
    
    MS --> MR
    DS --> MR
    PS --> DO
    RS --> ETH
    DSPY --> IP
    
    MR --> MLF
    IP --> REDIS
    MR --> S3
    DO --> ETH
```

## Core Components

### 1. Model Registry

The Model Registry is the heart of Hokusai, extending MLflow with blockchain awareness:

```python
# Architecture
ModelRegistry
├── MLflowClient (base registry)
├── TokenValidator (blockchain integration)
├── MetadataManager (Hokusai-specific tags)
└── VersionController (version management)
```

**Key Features:**
- Token-aware model registration
- Automatic lineage tracking
- Metadata validation
- Version comparison

### 2. DeltaOne Detection Engine

Monitors model improvements and triggers rewards:

```python
# Detection Flow
DeltaOneDetector
├── VersionComparator
│   ├── Load baseline metrics
│   ├── Load new metrics
│   └── Calculate delta
├── ThresholdChecker
│   └── Verify ≥1pp improvement
└── RewardTrigger
    ├── Webhook notifications
    └── Smart contract calls
```

### 3. Inference Pipeline

Handles production model serving with advanced features:

```python
# Pipeline Components
InferencePipeline
├── ModelLoader
│   ├── Cache management
│   └── Lazy loading
├── RequestRouter
│   ├── A/B test logic
│   └── Traffic management
├── PredictionEngine
│   ├── Batch processing
│   └── Result caching
└── MetricsCollector
    └── Performance tracking
```

### 4. Data Contribution System

Manages the complete data contribution lifecycle:

```python
# Contribution Flow
DataContributionSystem
├── DataValidator
│   ├── Format checking
│   ├── Quality assessment
│   └── PII detection
├── ContributionProcessor
│   ├── Data hashing
│   ├── Storage management
│   └── Metadata extraction
└── ImpactTracker
    ├── Model retraining
    └── Performance comparison
```

## Data Flow

### Model Training Flow

```mermaid
sequenceDiagram
    participant C as Contributor
    participant DS as Data Service
    participant MR as Model Registry
    participant MLF as MLflow
    participant DO as DeltaOne
    participant ETH as Ethereum
    
    C->>DS: Submit data
    DS->>DS: Validate & hash
    DS->>MLF: Trigger training
    MLF->>MLF: Train model
    MLF->>MR: Register model
    MR->>DO: Check improvement
    DO->>ETH: Trigger reward
    ETH->>C: Distribute tokens
```

### Inference Flow

```mermaid
sequenceDiagram
    participant U as User
    participant API as API Gateway
    participant R as Router
    participant C as Cache
    participant M as Model
    
    U->>API: Prediction request
    API->>R: Route request
    R->>C: Check cache
    alt Cache hit
        C-->>API: Return cached
    else Cache miss
        R->>M: Load model
        M->>M: Generate prediction
        M->>C: Store in cache
        M-->>API: Return prediction
    end
    API-->>U: Response
```

## Technology Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| API Framework | FastAPI | High-performance async API |
| ML Platform | MLflow | Experiment tracking & model registry |
| Cache | Redis | Model caching & session management |
| Storage | S3/MinIO | Model artifacts & data storage |
| Database | PostgreSQL | Metadata & configuration |
| Container | Docker | Deployment & isolation |
| Orchestration | Kubernetes | Scaling & management |

### Language & Frameworks

- **Python 3.8+**: Core platform language
- **TypeScript**: Frontend & tooling
- **Solidity**: Smart contracts
- **Go**: High-performance services

## Deployment Architecture

### Local Development

```yaml
# docker-compose.yml structure
services:
  api:
    build: .
    ports: ["8000:8000"]
    
  mlflow:
    image: mlflow/mlflow
    ports: ["5000:5000"]
    
  redis:
    image: redis:alpine
    ports: ["6379:6379"]
    
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: hokusai
```

### Production Deployment

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[AWS ALB]
    end
    
    subgraph "API Layer"
        API1[API Server 1]
        API2[API Server 2]
        API3[API Server 3]
    end
    
    subgraph "Services"
        MS[Model Service]
        DS[Data Service]
        PS[Performance Service]
    end
    
    subgraph "Data Layer"
        RDS[(RDS PostgreSQL)]
        REDIS[(ElastiCache)]
        S3[(S3 Buckets)]
    end
    
    LB --> API1
    LB --> API2
    LB --> API3
    
    API1 --> MS
    API2 --> DS
    API3 --> PS
    
    MS --> RDS
    MS --> REDIS
    MS --> S3
```

## Security Architecture

### Authentication & Authorization

```python
# Security Layers
SecurityArchitecture
├── Authentication
│   ├── API Key validation
│   ├── JWT tokens
│   └── ETH signature verification
├── Authorization
│   ├── Role-based access (RBAC)
│   ├── Resource permissions
│   └── Rate limiting
└── Encryption
    ├── TLS for transport
    ├── Encrypted storage
    └── Key management (KMS)
```

### Data Security

- **At Rest**: AES-256 encryption for stored data
- **In Transit**: TLS 1.3 for all communications
- **Access Control**: IAM roles and policies
- **Audit**: Complete audit trail of all operations

## Scaling Considerations

### Horizontal Scaling

```python
# Scalable Components
- API Servers: Stateless, behind load balancer
- Model Servers: Auto-scaling based on load
- Cache Layer: Redis Cluster for distribution
- Storage: S3 with CloudFront CDN
```

### Performance Optimization

1. **Model Caching**
   - Redis for hot models
   - Local memory for frequently used
   - Lazy loading for cold models

2. **Batch Processing**
   - Queue-based job processing
   - Parallel inference pipelines
   - Async request handling

3. **Database Optimization**
   - Read replicas for queries
   - Connection pooling
   - Query optimization

## Integration Points

### External Systems

```mermaid
graph LR
    H[Hokusai Platform]
    
    H --> HF[HuggingFace]
    H --> AWS[AWS Services]
    H --> ETH[Ethereum]
    H --> IPFS[IPFS Storage]
    H --> GH[GitHub]
    
    HF --> H
    AWS --> H
    ETH --> H
```

### Webhook System

```python
# Webhook Events
WebhookEvents
├── model.registered
├── deltaone.achieved
├── contribution.processed
├── reward.distributed
└── test.completed
```

## Monitoring & Observability

### Metrics Collection

```python
# Monitoring Stack
Observability
├── Metrics (Prometheus)
│   ├── API latency
│   ├── Model performance
│   └── Resource usage
├── Logging (ELK Stack)
│   ├── Application logs
│   ├── Audit trails
│   └── Error tracking
└── Tracing (Jaeger)
    ├── Request flow
    └── Performance bottlenecks
```

### Health Checks

```json
{
  "status": "healthy",
  "components": {
    "api": "up",
    "mlflow": "up",
    "redis": "up",
    "database": "up"
  },
  "version": "1.2.3",
  "uptime": "5d 12h 30m"
}
```

## Best Practices

### 1. Service Isolation

Each service should:
- Have a single responsibility
- Communicate via well-defined APIs
- Handle failures gracefully
- Be independently deployable

### 2. Data Consistency

- Use transactions for critical operations
- Implement idempotent APIs
- Handle eventual consistency
- Maintain audit trails

### 3. Performance

- Cache aggressively but invalidate properly
- Use connection pooling
- Implement circuit breakers
- Monitor and alert on anomalies

### 4. Security

- Principle of least privilege
- Defense in depth
- Regular security audits
- Automated vulnerability scanning

## Future Architecture

### Planned Enhancements

1. **Multi-Region Deployment**
   - Global model distribution
   - Regional data compliance
   - Reduced latency

2. **Edge Computing**
   - Model inference at edge
   - Offline capabilities
   - Real-time processing

3. **Federated Learning**
   - Privacy-preserving training
   - Distributed contributions
   - Cross-organizational models

## Related Documentation

- [Deployment Guide](./deployment.md)
- [Security Best Practices](./security.md)
- [Performance Optimization](./performance-optimization.md)
- [API Reference](../api-reference/index.md)