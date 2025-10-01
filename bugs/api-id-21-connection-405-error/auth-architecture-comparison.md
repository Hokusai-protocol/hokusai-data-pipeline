# Authentication Architecture Comparison

## Executive Summary

**Recommendation**: **Middleware-Based Authentication (Current APIKeyAuthMiddleware)** is significantly better for scaling, billing integration, and long-term maintainability.

**Key Reasons**:
1. Centralized auth enables usage tracking for billing
2. Redis caching reduces auth service load at scale
3. Consistent auth across all endpoints
4. Built-in rate limiting and scoping
5. Easier to add features (billing tiers, quotas, analytics)

---

## Current State: Dual Authentication (❌ Not Recommended)

### How It Works Now

```
Client Request → ALB → ECS Task
                          ↓
                    APIKeyAuthMiddleware (Layer 1)
                          ├─ Validates with auth service
                          ├─ Caches result in Redis
                          ├─ Sets request.state attributes
                          └─ Passes to endpoint
                          ↓
                    Endpoint Auth Check (Layer 2)
                          ├─ Checks Authorization header again
                          ├─ Validates API key format (starts with "hk_")
                          └─ Proceeds with business logic
```

### Problems with Dual Auth

1. **Redundancy**: Same validation happening twice
2. **Inconsistency**: Two different validation methods
3. **Confusion**: Which layer is responsible for what?
4. **Debugging Nightmare**: Hard to trace auth failures
5. **Billing Tracking**: No clear point to track usage
6. **Performance Overhead**: Double validation cost
7. **Maintenance Burden**: Update auth logic in multiple places

---

## Option 1: Middleware-Based Authentication (✅ RECOMMENDED)

### Architecture

```
┌─────────────┐
│   Client    │
│  (API Key)  │
└──────┬──────┘
       │ POST /api/v1/models/21/predict
       │ Authorization: Bearer hk_live_abc123...
       ↓
┌─────────────────────────────────────────┐
│     Application Load Balancer (ALB)     │
│  - SSL termination                      │
│  - Path-based routing                   │
└──────┬──────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────┐
│         ECS Task (API Service)          │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   APIKeyAuthMiddleware            │ │
│  │                                   │ │
│  │  1. Extract API key               │ │
│  │  2. Check Redis cache             │ │
│  │     ├─ Cache hit? Use cached      │ │
│  │     └─ Cache miss? Validate       │ │
│  │  3. Validate with Auth Service    │ │
│  │     POST /api/v1/keys/validate    │ │
│  │  4. Check scopes/permissions      │ │
│  │  5. Set request.state             │ │
│  │     - user_id                     │ │
│  │     - api_key_id                  │ │
│  │     - scopes                      │ │
│  │     - rate_limit_per_hour         │ │
│  │  6. Log usage (async)             │ │
│  │     POST /api/v1/usage/{key_id}   │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ↓                           │
│  ┌───────────────────────────────────┐ │
│  │   Model Serving Endpoint          │ │
│  │                                   │ │
│  │  @router.post("/{model_id}/predict")│
│  │  async def predict(              │ │
│  │    model_id: str,                │ │
│  │    request: PredictionRequest,   │ │
│  │    auth: dict = Depends(require_auth)│
│  │  ):                              │ │
│  │    # auth already validated      │ │
│  │    # Use auth['user_id'] etc     │ │
│  │    # Focus on business logic     │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
       │
       ↓ (async, non-blocking)
┌─────────────────────────────────────────┐
│       Auth Service (Separate ECS)       │
│  - API key validation                   │
│  - User/key lookup                      │
│  - Scope verification                   │
│  - Usage logging                        │
│  - Billing event generation             │
└─────────────────────────────────────────┘
```

### Implementation

```python
# src/api/endpoints/model_serving.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict
from src.middleware.auth import require_auth

router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])

@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    auth: Dict[str, Any] = Depends(require_auth),  # ← Single auth point
) -> PredictionResponse:
    """Make prediction using a model.

    Auth is handled by APIKeyAuthMiddleware - request will never
    reach this function if authentication fails.
    """
    # Access user context from middleware
    user_id = auth["user_id"]
    api_key_id = auth["api_key_id"]
    scopes = auth["scopes"]

    # Log for billing/analytics
    logger.info(
        f"Prediction request: user={user_id} key={api_key_id} model={model_id}",
        extra={
            "user_id": user_id,
            "api_key_id": api_key_id,
            "model_id": model_id,
            "endpoint": "predict",
        }
    )

    # Business logic only - no auth concerns
    predictions = await serving_service.serve_prediction(
        model_id=model_id,
        inputs=request.inputs,
        options=request.options,
    )

    return PredictionResponse(
        model_id=model_id,
        predictions=predictions,
        metadata={
            "api_version": "1.0",
            "user_id": user_id,  # Can include for tracking
        },
        timestamp=datetime.utcnow().isoformat(),
    )
```

### Middleware Configuration

```python
# src/middleware/auth.py

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, ...):
        # Paths that don't require auth
        self.excluded_paths = [
            "/health",
            "/docs",
            "/openapi.json",
            # Model serving endpoints ARE authenticated
        ]
```

### Advantages for Scaling & Billing

#### 1. **Centralized Usage Tracking**

Every API call goes through middleware, enabling:

```python
# Middleware automatically logs usage
await self._log_usage_to_auth_service(
    key_id=validation_result.key_id,
    endpoint=request.url.path,
    response_time_ms=response_time_ms,
    status_code=response.status_code,
)
```

Auth service receives:
- Which API key made the call
- Which endpoint was called
- Response time
- Success/failure status

Perfect for billing!

#### 2. **Redis Caching for Scale**

```python
# Cache validation for 5 minutes
cache_key = f"api_key:validation:{api_key}"
self.cache.setex(cache_key, 300, json.dumps(cache_data))
```

**At 10,000 requests/min**:
- Without cache: 10,000 auth service calls/min
- With 5-min cache: ~2,000 auth service calls/min (80% reduction)

**Cost savings**:
- Reduced auth service load
- Lower latency (Redis ~1ms vs HTTP ~50ms)
- Better user experience

#### 3. **Scope-Based Authorization**

```python
validation_result.scopes = ["model:read", "model:write", "billing:manage"]

# Different billing tiers with different scopes
if "premium_tier" in scopes:
    rate_limit = 10000  # requests/hour
elif "standard_tier" in scopes:
    rate_limit = 1000
else:
    rate_limit = 100
```

Enable:
- Free tier: Limited requests, read-only
- Standard tier: More requests, basic features
- Premium tier: Unlimited requests, all features

#### 4. **Built-in Rate Limiting**

```python
# Middleware checks rate limits from auth service
if validation_result.rate_limit_per_hour:
    # Track usage in Redis
    # Return 429 if exceeded
```

Perfect for billing tiers!

#### 5. **Billing Events**

Auth service can emit billing events:

```python
# In auth service
async def log_usage(key_id: str, endpoint: str, ...):
    # Store usage in database
    await db.insert_usage_event(...)

    # Emit to billing system
    await billing_service.record_api_call(
        customer_id=key.customer_id,
        product="model_inference",
        quantity=1,
        metadata={
            "model_id": model_id,
            "endpoint": endpoint,
        }
    )
```

Enables:
- Usage-based billing
- Cost attribution per customer
- Revenue analytics
- Chargeback reporting

#### 6. **Analytics & Observability**

Centralized auth provides single point for:

```python
# Track every API call
await analytics.track_event(
    event="api_call",
    user_id=user_id,
    properties={
        "endpoint": endpoint,
        "model_id": model_id,
        "response_time": response_time_ms,
        "success": status_code == 200,
    }
)
```

Enable dashboards showing:
- API usage per customer
- Popular models
- Error rates
- Cost per customer
- Revenue forecasting

---

## Option 2: Endpoint-Based Authentication (❌ Not Recommended)

### Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ↓
┌─────────────────────────────────────────┐
│         ECS Task (API Service)          │
│                                         │
│  (No middleware - requests pass through)│
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   Model Serving Endpoint          │ │
│  │                                   │ │
│  │  @router.post("/{model_id}/predict")│
│  │  async def predict(              │ │
│  │    authorization: str = Header() │ │
│  │  ):                              │ │
│  │    # Extract API key             │ │
│  │    if not authorization:         │ │
│  │      raise 401                   │ │
│  │    api_key = parse_header()      │ │
│  │    # Validate format             │ │
│  │    if not api_key.startswith("hk_"):│
│  │      raise 401                   │ │
│  │    # Business logic              │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### Implementation

```python
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    authorization: Optional[str] = Header(None),
):
    # Every endpoint must implement auth
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    api_key = authorization.replace("Bearer ", "")

    # Basic format validation only
    if not api_key.startswith("hk_"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # NO validation with auth service
    # NO user context
    # NO usage tracking
    # NO rate limiting
    # NO billing events

    # Just proceed with business logic
    predictions = await serving_service.serve_prediction(...)
    return PredictionResponse(...)
```

### Problems at Scale

#### 1. **No Usage Tracking**
- Can't track which customer made which calls
- Can't implement usage-based billing
- No data for cost attribution
- Can't analyze usage patterns

#### 2. **No Centralized Validation**
- Each endpoint validates independently
- Inconsistent validation logic
- Can't update all endpoints at once
- High risk of security holes

#### 3. **No Caching**
- Every request validates from scratch
- High latency for auth checks
- Can't scale efficiently
- Unnecessary load on validation systems

#### 4. **No Rate Limiting**
- Can't enforce per-customer limits
- Can't implement billing tiers
- Vulnerable to abuse
- Hard to prevent DoS

#### 5. **No Scope Management**
- Can't differentiate free vs paid users
- Can't enable/disable features per tier
- Can't offer different SLAs
- Limited monetization options

#### 6. **Maintenance Nightmare**
- Update auth logic in every endpoint
- Test every endpoint separately
- High chance of bugs
- Slow to add features

---

## Billing Integration Comparison

### Scenario: Usage-Based Billing

**Goal**: Charge $0.01 per 1,000 API calls + $0.10 per 1,000 compute units

### With Middleware Auth (✅ Easy)

```python
# Middleware automatically tracks
async def dispatch(self, request: Request, call_next):
    start_time = time.time()

    # Validate auth
    validation_result = await self.validate_with_auth_service(api_key)

    # Process request
    response = await call_next(request)

    # Calculate cost
    response_time_ms = (time.time() - start_time) * 1000
    compute_units = estimate_compute_units(
        endpoint=request.url.path,
        response_time=response_time_ms,
        payload_size=len(await request.body()),
    )

    # Log to billing service (async, non-blocking)
    asyncio.create_task(
        billing_service.record_usage(
            customer_id=validation_result.customer_id,
            timestamp=datetime.utcnow(),
            events=[
                {"type": "api_call", "quantity": 1, "rate": 0.00001},
                {"type": "compute_units", "quantity": compute_units, "rate": 0.0001},
            ],
            metadata={
                "endpoint": request.url.path,
                "model_id": parse_model_id(request.url.path),
                "response_time_ms": response_time_ms,
            }
        )
    )

    return response
```

**Result**: Every API call automatically billed, zero changes to endpoints

### With Endpoint Auth (❌ Very Hard)

```python
# EVERY endpoint must implement billing
@router.post("/{model_id}/predict")
async def predict(model_id: str, ...):
    # Extract customer from API key somehow?
    # No customer_id available!

    # Would need to:
    # 1. Query database to map API key → customer
    # 2. Track usage manually
    # 3. Calculate costs manually
    # 4. Send to billing service manually
    # 5. Repeat for EVERY endpoint

    # Lots of code duplication
    # High chance of billing bugs
    # Inconsistent billing across endpoints
```

---

## Feature Comparison Matrix

| Feature | Middleware Auth | Endpoint Auth |
|---------|----------------|---------------|
| **Centralized validation** | ✅ Yes | ❌ No - Each endpoint |
| **Usage tracking** | ✅ Automatic | ❌ Manual per endpoint |
| **Redis caching** | ✅ Built-in | ❌ Must implement per endpoint |
| **Rate limiting** | ✅ Centralized | ❌ Must implement per endpoint |
| **Scope management** | ✅ Built-in | ❌ Must implement per endpoint |
| **Billing integration** | ✅ Easy - single point | ❌ Hard - duplicate code |
| **Cost attribution** | ✅ Automatic | ❌ Manual tracking |
| **Billing tiers** | ✅ Scope-based | ❌ Hard to implement |
| **Analytics** | ✅ Centralized logging | ❌ Must aggregate |
| **Performance at scale** | ✅ Redis cache (80% faster) | ❌ No caching |
| **Auth updates** | ✅ Update once | ❌ Update every endpoint |
| **Security consistency** | ✅ Guaranteed | ❌ Prone to errors |
| **Debugging** | ✅ Single point | ❌ Multiple locations |
| **Testing** | ✅ Test once | ❌ Test every endpoint |
| **Code maintainability** | ✅ DRY principle | ❌ Lots of duplication |

---

## Migration Strategy: Endpoint Auth → Middleware Auth

If you had existing endpoint auth and wanted to migrate:

### Phase 1: Add Middleware (Non-Breaking)

```python
# Add middleware with all paths excluded initially
app.add_middleware(
    APIKeyAuthMiddleware,
    excluded_paths=[
        "/health",
        "/api/v1/models",  # Exclude all model endpoints initially
    ]
)
```

No behavior change yet - endpoints still handle own auth.

### Phase 2: Update Endpoints One by One

```python
# Before
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    authorization: str = Header(),
):
    if not authorization.startswith("Bearer "):
        raise 401
    # ...

# After
@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    auth: dict = Depends(require_auth),
):
    # Middleware handles auth
    user_id = auth["user_id"]
    # ...
```

### Phase 3: Remove from Exclusions

```python
# Remove model endpoints from excluded paths
app.add_middleware(
    APIKeyAuthMiddleware,
    excluded_paths=[
        "/health",
        # "/api/v1/models" ← removed
    ]
)
```

### Phase 4: Deploy with Feature Flag

```python
# Add feature flag for gradual rollout
if settings.use_middleware_auth:
    # Use middleware auth
else:
    # Use endpoint auth (old behavior)
```

Deploy and monitor, gradually increase percentage.

---

## Recommended Architecture for Production Scale

```
┌──────────────────────────────────────────────────────────────┐
│                     Client Applications                       │
│  (Web, Mobile, Third-party integrations)                     │
└───────────────────────────┬──────────────────────────────────┘
                            │ API Key: hk_live_...
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                   CloudFront (CDN)                            │
│  - Global edge locations                                     │
│  - DDoS protection                                           │
│  - Rate limiting (Layer 7)                                   │
└───────────────────────────┬──────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│            Application Load Balancer (ALB)                    │
│  - SSL/TLS termination                                       │
│  - Path-based routing                                        │
│  - Health checks                                             │
└───────────────────────────┬──────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                 ECS Fargate (Auto-scaling)                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         APIKeyAuthMiddleware (Layer 1)                 │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │ 1. Extract API key from request                  │ │ │
│  │  │ 2. Check ElastiCache Redis (sub-ms latency)     │ │ │
│  │  │ 3. If cache miss: Validate with Auth Service    │ │ │
│  │  │ 4. Apply rate limits based on tier              │ │ │
│  │  │ 5. Check scopes/permissions                     │ │ │
│  │  │ 6. Set request context (user_id, key_id, etc)   │ │ │
│  │  │ 7. Emit usage metric to CloudWatch              │ │ │
│  │  │ 8. Log to Kinesis Data Stream (async)           │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └─────────────────────┬────────────────────────────────────┘│
│                        ↓                                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Application Endpoints (Layer 2)              │ │
│  │  - Focus on business logic only                       │ │
│  │  - No auth concerns (handled by middleware)           │ │
│  │  - Access user context from request.state             │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
         │                     │                    │
         ↓                     ↓                    ↓
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ ElastiCache     │  │  Auth Service    │  │  Kinesis Data    │
│ Redis           │  │  (ECS)           │  │  Stream          │
│ - Auth cache    │  │  - Validation    │  │  - Usage events  │
│ - 5-min TTL     │  │  - User lookup   │  │  - Billing data  │
│ - 99.9% uptime  │  │  - Scope check   │  │  - Analytics     │
└─────────────────┘  └─────────────────���┘  └──────────────────┘
                              │                     │
                              ↓                     ↓
                     ┌──────────────────┐  ┌──────────────────┐
                     │   RDS PostgreSQL │  │  Lambda Functions│
                     │   - Users        │  │  - Process usage │
                     │   - API Keys     │  │  - Aggregate     │
                     │   - Permissions  │  │  - Send to billing│
                     └──────────────────┘  └──────────────────┘
                                                   │
                                                   ↓
                                          ┌──────────────────┐
                                          │ Billing Service  │
                                          │ (Stripe, etc)    │
                                          │ - Invoice gen    │
                                          │ - Payment        │
                                          │ - Subscription   │
                                          └──────────────────┘
```

### Data Flow for Billing

1. **API Call** → Middleware validates → Sets context
2. **Middleware** → Emits metric to CloudWatch
3. **Middleware** → Logs event to Kinesis (async, non-blocking)
4. **Kinesis** → Triggers Lambda every 1 minute
5. **Lambda** → Aggregates usage events
6. **Lambda** → Sends to billing service API
7. **Billing Service** → Creates invoice line items
8. **Billing Service** → Charges customer monthly

### Cost at 1M requests/month

**With Middleware Auth + Caching**:
- ElastiCache Redis: $15/month (t3.micro)
- Auth service calls: 200K/month (80% cache hit)
- Auth service ECS: $10/month (Fargate Spot)
- **Total: ~$25/month**

**Without Caching (endpoint auth)**:
- Auth service calls: 1M/month
- Auth service ECS: $50/month (need larger instance)
- Database load: 5x higher
- **Total: ~$75/month**

**Savings: $50/month = $600/year**

At 100M requests/month: **$5,000/year savings**

---

## Final Recommendation

### Use Middleware-Based Authentication

**Why?**

1. **Billing Ready**: Built-in usage tracking, perfect for usage-based billing
2. **Scales Efficiently**: Redis caching handles high volume with low latency
3. **Cost Effective**: 80% reduction in auth service calls
4. **Maintainable**: Single point to update auth logic
5. **Secure**: Consistent auth across all endpoints
6. **Observable**: Centralized logging and metrics
7. **Flexible**: Easy to add billing tiers, rate limits, scopes
8. **Future-Proof**: Can add features without touching endpoints

**Migration Path**:
- ✅ You already have APIKeyAuthMiddleware implemented
- ✅ It's already working with auth service integration
- ✅ Redis caching is already configured
- ✅ Just need to remove redundant endpoint auth

**Next Step**: Implement the fix from `fix-tasks.md` to remove endpoint-specific auth and use middleware exclusively.

