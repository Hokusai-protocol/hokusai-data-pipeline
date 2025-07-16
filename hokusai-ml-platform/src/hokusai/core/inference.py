"""Inference pipeline with caching and performance optimization."""
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import redis

from .ab_testing import ModelTrafficRouter
from .models import HokusaiModel
from .registry import ModelRegistry
from .versioning import ModelVersionManager


class InferenceException(Exception):
    """Exception raised by inference operations."""

    pass


@dataclass
class CacheConfig:
    """Configuration for inference caching."""

    enabled: bool = True
    ttl_seconds: int = 300  # 5 minutes default
    max_cache_size_mb: int = 1024  # 1GB default
    eviction_policy: str = "lru"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0


@dataclass
class InferenceRequest:
    """Request for model inference."""

    request_id: str
    model_type: str
    data: Any
    user_id: Optional[str] = None
    model_version: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    preprocessing_required: bool = False
    postprocessing_required: bool = False

    def get_cache_key(self) -> str:
        """Generate cache key for this request."""
        # Create deterministic key from request data
        key_parts = [
            self.model_type,
            self.model_version or "latest",
            json.dumps(self.data, sort_keys=True)
        ]

        key_string = ":".join(key_parts)
        return f"inference:{hashlib.sha256(key_string.encode()).hexdigest()}"


@dataclass
class InferenceResponse:
    """Response from model inference."""

    request_id: str
    prediction: Any
    model_version: str
    model_id: str
    latency_ms: float
    cache_hit: bool = False
    ab_test_id: Optional[str] = None
    fallback_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class BatchProcessor:
    """Handles batch inference operations."""

    async def process_batch(
        self,
        requests: List[InferenceRequest],
        model: HokusaiModel
    ) -> List[Dict[str, Any]]:
        """Process a batch of requests."""
        # Extract data from requests
        batch_data = [req.data for req in requests]

        # Run batch prediction
        if hasattr(model, "batch_predict"):
            predictions = model.batch_predict(batch_data)
        else:
            # Fallback to individual predictions
            predictions = [model.predict(data) for data in batch_data]

        return predictions


class HokusaiInferencePipeline:
    """Main inference pipeline with caching and optimization."""

    def __init__(
        self,
        registry: ModelRegistry,
        version_manager: ModelVersionManager,
        traffic_router: ModelTrafficRouter,
        cache_config: Optional[CacheConfig] = None,
        max_models_in_memory: int = 10
    ) -> None:
        self.registry = registry
        self.version_manager = version_manager
        self.traffic_router = traffic_router
        self.cache_config = cache_config or CacheConfig()
        self.max_models_in_memory = max_models_in_memory

        # Initialize cache
        if self.cache_config.enabled:
            self.cache = redis.Redis(
                host=self.cache_config.redis_host,
                port=self.cache_config.redis_port,
                db=self.cache_config.redis_db,
                decode_responses=False
            )
        else:
            self.cache = None

        # In-memory model cache (LRU)
        self.model_cache: OrderedDict[str, HokusaiModel] = OrderedDict()

        # Batch processor
        self.batch_processor = BatchProcessor()

        # Optional processors (set externally if needed)
        self.preprocessor = None
        self.postprocessor = None

    async def predict(self, request: InferenceRequest) -> InferenceResponse:
        """Run inference for a single request."""
        start_time = time.time()

        try:
            # Check cache first
            cache_key = request.get_cache_key()
            cached_result = self._get_from_cache(cache_key)

            if cached_result:
                latency_ms = (time.time() - start_time) * 1000
                return InferenceResponse(
                    request_id=request.request_id,
                    prediction=cached_result,
                    model_version=cached_result.get("model_version", "unknown"),
                    model_id=cached_result.get("model_id", "unknown"),
                    latency_ms=latency_ms,
                    cache_hit=True
                )

            # Determine which model to use
            model_id, ab_test_id = self._select_model(request)

            # Load model
            model = self._load_model(model_id)

            # Preprocessing if required
            data = request.data
            if request.preprocessing_required and self.preprocessor:
                data = self.preprocessor.process(data)

            # Run prediction
            try:
                prediction = model.predict(data)
            except Exception as e:
                # Try fallback to previous version
                if not request.model_version:  # Only fallback if not specific version requested
                    fallback_model_id = self._get_fallback_model(model.model_type, model.version)
                    if fallback_model_id:
                        model = self._load_model(fallback_model_id)
                        prediction = model.predict(data)
                        fallback_used = True
                    else:
                        raise
                else:
                    raise
            else:
                fallback_used = False

            # Postprocessing if required
            if request.postprocessing_required and self.postprocessor:
                prediction = self.postprocessor.process(prediction)

            # Cache the result
            if self.cache:
                cache_data = {
                    "prediction": prediction,
                    "model_version": model.version,
                    "model_id": model.model_id
                }
                self._save_to_cache(cache_key, cache_data)

            # Record metrics for A/B test
            if ab_test_id:
                latency = (time.time() - start_time) * 1000
                self.traffic_router.record_metric(
                    ab_test_id, model.model_id, "latency", latency
                )
                # Record other metrics if available
                if hasattr(prediction, "get") and "confidence" in prediction:
                    self.traffic_router.record_metric(
                        ab_test_id, model.model_id, "confidence", prediction["confidence"]
                    )

            latency_ms = (time.time() - start_time) * 1000

            return InferenceResponse(
                request_id=request.request_id,
                prediction=prediction,
                model_version=model.version,
                model_id=model.model_id,
                latency_ms=latency_ms,
                cache_hit=False,
                ab_test_id=ab_test_id,
                fallback_used=fallback_used
            )

        except Exception as e:
            raise InferenceException(f"Inference failed: {str(e)}")

    def predict_batch(
        self,
        data: Any,
        model_name: str,
        model_version: Optional[str] = None
    ) -> List[Any]:
        """Run batch prediction with simplified interface.
        
        Args:
            data: Batch of input data (list or array)
            model_name: Name of the model to use
            model_version: Specific version to use (optional)
            
        Returns:
            List of predictions
        """
        # Convert to internal request format
        import uuid
        requests = []
        
        if not isinstance(data, list):
            data = [data]
            
        for item in data:
            req = InferenceRequest(
                request_id=str(uuid.uuid4()),
                model_type=model_name,
                data=item,
                model_version=model_version
            )
            requests.append(req)
        
        # Run batch prediction (synchronous wrapper)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            responses = loop.run_until_complete(self.batch_predict(requests))
            return [resp.prediction for resp in responses]
        finally:
            loop.close()

    async def batch_predict(
        self,
        requests: List[InferenceRequest]
    ) -> List[InferenceResponse]:
        """Run inference for a batch of requests (async version)."""
        if not requests:
            return []

        # Group requests by model type and version
        request_groups = {}
        for req in requests:
            key = (req.model_type, req.model_version or "latest")
            if key not in request_groups:
                request_groups[key] = []
            request_groups[key].append(req)

        # Process each group
        all_responses = []

        for (model_type, version), group_requests in request_groups.items():
            # Check cache for each request
            cached_responses = []
            uncached_requests = []

            for req in group_requests:
                cache_key = req.get_cache_key()
                cached_result = self._get_from_cache(cache_key)

                if cached_result:
                    cached_responses.append(InferenceResponse(
                        request_id=req.request_id,
                        prediction=cached_result,
                        model_version=cached_result.get("model_version", "unknown"),
                        model_id=cached_result.get("model_id", "unknown"),
                        latency_ms=0.0,  # Near zero for cache hits
                        cache_hit=True
                    ))
                else:
                    uncached_requests.append(req)

            # Process uncached requests
            if uncached_requests:
                # Load model once for the group
                if version == "latest":
                    model_entry = self.registry.get_latest_model(model_type)
                else:
                    entries = self.registry.list_models_by_type(model_type)
                    model_entry = next((e for e in entries if e.version == version), None)

                if not model_entry:
                    raise InferenceException(f"Model not found: {model_type} v{version}")

                model = self._load_model(model_entry.model_id)

                # Run batch prediction
                start_time = time.time()
                predictions = await self.batch_processor.process_batch(uncached_requests, model)
                batch_latency = (time.time() - start_time) * 1000

                # Create responses and cache results
                for req, pred in zip(uncached_requests, predictions):
                    # Cache the result
                    if self.cache:
                        cache_data = {
                            "prediction": pred,
                            "model_version": model.version,
                            "model_id": model.model_id
                        }
                        self._save_to_cache(req.get_cache_key(), cache_data)

                    cached_responses.append(InferenceResponse(
                        request_id=req.request_id,
                        prediction=pred,
                        model_version=model.version,
                        model_id=model.model_id,
                        latency_ms=batch_latency / len(uncached_requests),
                        cache_hit=False
                    ))

            all_responses.extend(cached_responses)

        return all_responses

    def _select_model(self, request: InferenceRequest) -> tuple[str, Optional[str]]:
        """Select which model to use for inference."""
        # Check if there's an active A/B test
        ab_test_id = None
        active_tests = self.traffic_router.list_active_tests()

        for test_id in active_tests:
            test = self.traffic_router.get_active_test(test_id)
            if test and request.user_id:
                # Check if this test applies to this model type
                # This is simplified - in production, you'd have more sophisticated matching
                model_id = self.traffic_router.route_request(test_id, request.user_id)
                ab_test_id = test_id
                return model_id, ab_test_id

        # No A/B test - use specified version or latest
        if request.model_version:
            entries = self.registry.list_models_by_type(request.model_type)
            for entry in entries:
                if entry.version == request.model_version:
                    return entry.model_id, None
            raise InferenceException(f"Version {request.model_version} not found")
        else:
            latest = self.registry.get_latest_model(request.model_type)
            if not latest:
                raise InferenceException(f"No models found for type {request.model_type}")
            return latest.model_id, None

    def _load_model(self, model_id: str) -> HokusaiModel:
        """Load model with caching."""
        # Check in-memory cache
        if model_id in self.model_cache:
            # Move to end (LRU)
            self.model_cache.move_to_end(model_id)
            return self.model_cache[model_id]

        # Load model
        model = self._download_and_load_model(model_id)

        # Add to cache with eviction
        self.model_cache[model_id] = model
        if len(self.model_cache) > self.max_models_in_memory:
            # Evict least recently used
            self.model_cache.popitem(last=False)

        return model

    def _download_and_load_model(self, model_id: str) -> HokusaiModel:
        """Download and load model from storage."""
        # This is a placeholder - actual implementation would:
        # 1. Get model location from registry
        # 2. Download from S3/storage
        # 3. Load model artifacts
        # 4. Create appropriate model instance

        # For now, create a mock model
        entry = self.registry.get_model_by_id(model_id)

        # Import here to avoid circular dependency
        from .models import ModelFactory

        return ModelFactory.create_model(
            model_type=entry.model_type,
            model_id=model_id,
            version=entry.version,
            metrics=entry.metrics
        )

    def _get_fallback_model(self, model_type: str, current_version: str) -> Optional[str]:
        """Get fallback model ID."""
        previous = self.version_manager.get_previous_version(model_type, current_version)
        return previous.model_id if previous else None

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get result from cache."""
        if not self.cache:
            return None

        try:
            cached = self.cache.get(cache_key)
            if cached:
                return json.loads(cached.decode())
        except Exception:
            pass

        return None

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Save result to cache."""
        if not self.cache:
            return

        try:
            self.cache.setex(
                cache_key,
                self.cache_config.ttl_seconds,
                json.dumps(data).encode()
            )
        except Exception:
            pass  # Silently ignore cache errors
