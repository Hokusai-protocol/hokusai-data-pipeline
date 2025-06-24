# Modular Model Architecture Design

## Overview

This document outlines the design for a modular architecture that supports multiple models, A/B testing, versioning, rollback capabilities, and an inference pipeline with caching for the Hokusai Data Pipeline.

## Architecture Components

### 1. Model Interface Abstraction

#### Base Model Interface
```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import numpy as np

class HokusaiModel(ABC):
    """Abstract base class for all Hokusai models."""
    
    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions on input data."""
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata and configuration."""
        pass
    
    @abstractmethod
    def get_required_features(self) -> List[str]:
        """Return list of required feature names."""
        pass
    
    @abstractmethod
    def validate_input(self, X: np.ndarray) -> bool:
        """Validate input data format and shape."""
        pass
```

#### Model Registry Extension
```python
class EnhancedModelRegistry(HokusaiModelRegistry):
    """Extended model registry with versioning and rollback support."""
    
    def register_model_version(self, model: HokusaiModel, 
                             model_family: str,
                             version_tag: str,
                             metadata: Dict[str, Any]) -> str:
        """Register a new model version with semantic versioning."""
        pass
    
    def get_active_model(self, model_family: str) -> HokusaiModel:
        """Get the currently active model for a family."""
        pass
    
    def rollback_model(self, model_family: str, 
                      target_version: str) -> bool:
        """Rollback to a previous model version."""
        pass
    
    def get_model_by_version(self, model_family: str, 
                           version: str) -> HokusaiModel:
        """Retrieve a specific model version."""
        pass
```

### 2. A/B Testing Framework

#### Traffic Router
```python
class ModelTrafficRouter:
    """Routes traffic between models for A/B testing."""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.routing_rules = {}
    
    def create_ab_test(self, test_config: ABTestConfig) -> str:
        """Create a new A/B test configuration."""
        pass
    
    def route_request(self, request_id: str, 
                     user_id: Optional[str] = None) -> str:
        """Determine which model to use for a request."""
        pass
    
    def update_traffic_split(self, test_id: str, 
                           splits: Dict[str, float]) -> bool:
        """Update traffic distribution between models."""
        pass
```

#### A/B Test Configuration
```python
@dataclass
class ABTestConfig:
    test_id: str
    model_a: str  # Model ID/version
    model_b: str  # Model ID/version
    traffic_split: Dict[str, float]  # {"model_a": 0.5, "model_b": 0.5}
    start_time: datetime
    end_time: Optional[datetime]
    success_metrics: List[str]
    user_segments: Optional[Dict[str, Any]]
```

### 3. Model Versioning System

#### Semantic Versioning
- **Major**: Breaking changes in model architecture or features
- **Minor**: Performance improvements, new features (backward compatible)
- **Patch**: Bug fixes, minor adjustments

#### Version Management
```python
class ModelVersionManager:
    """Manages model versions and transitions."""
    
    def __init__(self, registry: EnhancedModelRegistry):
        self.registry = registry
        self.version_history = {}
    
    def promote_model(self, model_id: str, 
                     environment: str = "production") -> bool:
        """Promote a model version to production."""
        pass
    
    def deprecate_model(self, model_id: str) -> bool:
        """Mark a model version as deprecated."""
        pass
    
    def get_version_history(self, model_family: str) -> List[Dict]:
        """Get complete version history for a model family."""
        pass
```

### 4. Inference Pipeline with Caching

#### Caching Strategy
```python
class InferenceCacheManager:
    """Manages caching for model inference."""
    
    def __init__(self, redis_client: Redis, 
                 cache_ttl: int = 3600):
        self.redis = redis_client
        self.cache_ttl = cache_ttl
    
    def get_cached_prediction(self, model_id: str, 
                            feature_hash: str) -> Optional[np.ndarray]:
        """Retrieve cached prediction if available."""
        pass
    
    def cache_prediction(self, model_id: str, 
                       feature_hash: str, 
                       prediction: np.ndarray) -> bool:
        """Cache a prediction result."""
        pass
    
    def invalidate_model_cache(self, model_id: str) -> bool:
        """Invalidate all cache entries for a model."""
        pass
```

#### Inference Pipeline
```python
class HokusaiInferencePipeline:
    """Main inference pipeline with caching and model routing."""
    
    def __init__(self, 
                 model_registry: EnhancedModelRegistry,
                 traffic_router: ModelTrafficRouter,
                 cache_manager: InferenceCacheManager):
        self.registry = model_registry
        self.router = traffic_router
        self.cache = cache_manager
    
    async def predict(self, 
                     request: InferenceRequest) -> InferenceResponse:
        """Main prediction endpoint with caching and routing."""
        # 1. Determine which model to use (A/B testing)
        model_id = self.router.route_request(
            request.request_id, 
            request.user_id
        )
        
        # 2. Check cache
        feature_hash = self._hash_features(request.features)
        cached = self.cache.get_cached_prediction(model_id, feature_hash)
        if cached is not None:
            return InferenceResponse(
                prediction=cached,
                model_id=model_id,
                cached=True
            )
        
        # 3. Load model and predict
        model = self.registry.get_model_by_version(
            model_id.split("/")[0], 
            model_id.split("/")[1]
        )
        prediction = model.predict(request.features)
        
        # 4. Cache result
        self.cache.cache_prediction(model_id, feature_hash, prediction)
        
        # 5. Log metrics
        await self._log_inference_metrics(model_id, request, prediction)
        
        return InferenceResponse(
            prediction=prediction,
            model_id=model_id,
            cached=False
        )
```

## Implementation Plan

### Phase 1: Model Interface and Registry (Week 1-2)
1. Implement `HokusaiModel` base class
2. Create model adapters for existing models
3. Extend `HokusaiModelRegistry` with versioning support
4. Add model validation and compatibility checks

### Phase 2: A/B Testing Framework (Week 3-4)
1. Implement `ModelTrafficRouter` with Redis backend
2. Create A/B test configuration management
3. Add request routing logic with user segmentation
4. Implement metric collection for A/B tests

### Phase 3: Versioning and Rollback (Week 5)
1. Implement semantic versioning system
2. Add model promotion/demotion workflows
3. Create rollback mechanisms with safety checks
4. Add version history tracking

### Phase 4: Inference Pipeline (Week 6-7)
1. Implement caching layer with Redis
2. Create inference pipeline with async support
3. Add monitoring and metrics collection
4. Implement cache invalidation strategies

### Phase 5: Integration and Testing (Week 8)
1. Integrate with existing Metaflow pipeline
2. Create comprehensive test suite
3. Performance benchmarking
4. Documentation and deployment guides

## Configuration Examples

### Model Registration
```python
# Register a new model version
registry = EnhancedModelRegistry()
model = XGBoostHokusaiModel(model_path="models/xgboost_v2.pkl")

model_id = registry.register_model_version(
    model=model,
    model_family="lead_scoring",
    version_tag="2.1.0",
    metadata={
        "training_date": "2024-01-15",
        "dataset_version": "v3",
        "performance_metrics": {
            "accuracy": 0.92,
            "auroc": 0.95
        }
    }
)
```

### A/B Test Setup
```python
# Create an A/B test
router = ModelTrafficRouter(redis_client)

test_id = router.create_ab_test(
    ABTestConfig(
        test_id="lead_scoring_v2_test",
        model_a="lead_scoring/2.0.0",
        model_b="lead_scoring/2.1.0",
        traffic_split={"model_a": 0.8, "model_b": 0.2},
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(days=7),
        success_metrics=["accuracy", "conversion_rate"],
        user_segments={"region": ["US", "EU"]}
    )
)
```

### Inference with Caching
```python
# Make predictions using the pipeline
pipeline = HokusaiInferencePipeline(
    model_registry=registry,
    traffic_router=router,
    cache_manager=cache_manager
)

response = await pipeline.predict(
    InferenceRequest(
        request_id="req_123",
        user_id="user_456",
        features=np.array([[1.0, 2.0, 3.0]]),
        model_family="lead_scoring"
    )
)
```

## Monitoring and Observability

### Key Metrics
1. **Model Performance**
   - Prediction latency (p50, p95, p99)
   - Cache hit rate
   - Model load time
   - Error rates by model version

2. **A/B Test Metrics**
   - Traffic distribution accuracy
   - Conversion rates by variant
   - Statistical significance
   - User segment performance

3. **System Health**
   - Redis connection pool status
   - Model memory usage
   - Request queue depth
   - Cache memory usage

### Alerting Rules
- Model prediction latency > 100ms (p95)
- Cache hit rate < 80%
- A/B test traffic deviation > 5%
- Model rollback triggered
- Cache memory > 80% capacity

## Security Considerations

1. **Model Access Control**
   - API key authentication for model access
   - Role-based access for model management
   - Audit logging for all model operations

2. **Data Privacy**
   - Feature hashing for cache keys (no PII storage)
   - Encryption for model artifacts at rest
   - Secure model transfer protocols

3. **Version Control**
   - Immutable model versions
   - Cryptographic signatures for models
   - Rollback authorization requirements

## Future Enhancements

1. **Multi-Armed Bandit Testing**
   - Dynamic traffic allocation based on performance
   - Automatic winner selection
   - Exploration vs exploitation strategies

2. **Feature Store Integration**
   - Centralized feature management
   - Feature versioning alongside models
   - Real-time feature engineering

3. **Model Explainability**
   - SHAP/LIME integration
   - Feature importance tracking
   - Prediction explanation API

4. **Edge Deployment**
   - Model quantization for edge devices
   - Federated learning support
   - Offline inference capabilities