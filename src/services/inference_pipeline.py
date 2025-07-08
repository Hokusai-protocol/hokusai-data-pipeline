"""Inference pipeline with caching for high-performance model serving."""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd
import redis
from redis.exceptions import RedisError
import hashlib
import pickle
import zlib
from concurrent.futures import ThreadPoolExecutor

from .model_abstraction import HokusaiModel, ModelFactory
from .model_versioning import ModelVersionManager, Environment
from .ab_testing import ModelTrafficRouter
from .model_registry import HokusaiModelRegistry

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """Caching strategies for inference results."""

    LRU = "lru"  # Least Recently Used
    TTL = "ttl"  # Time To Live
    LFU = "lfu"  # Least Frequently Used
    ADAPTIVE = "adaptive"  # Adaptive based on usage patterns


class InferenceStatus(Enum):
    """Status of an inference request."""

    SUCCESS = "success"
    CACHE_HIT = "cache_hit"
    ERROR = "error"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"


@dataclass
class InferenceRequest:
    """Request for model inference."""

    request_id: str
    model_family: str
    features: Union[np.ndarray, pd.DataFrame, Dict[str, Any]]
    user_id: Optional[str] = None
    request_metadata: Optional[Dict[str, Any]] = None
    timeout_ms: int = 1000
    use_cache: bool = True

    def get_cache_key(self, model_id: str) -> str:
        """Generate cache key for this request."""
        # Convert features to consistent format
        if isinstance(self.features, dict):
            feature_str = json.dumps(self.features, sort_keys=True)
        elif isinstance(self.features, pd.DataFrame):
            feature_str = self.features.to_json(orient="records")
        else:
            feature_str = str(self.features.tolist())

        # Create hash
        content = f"{model_id}:{feature_str}"
        return f"inference:{hashlib.sha256(content.encode()).hexdigest()}"


@dataclass
class InferenceResponse:
    """Response from model inference."""

    request_id: str
    prediction: Union[np.ndarray, List[float], float]
    model_id: str
    model_version: str
    status: InferenceStatus
    latency_ms: float
    cached: bool = False
    cache_key: Optional[str] = None
    confidence: Optional[float] = None
    explanation: Optional[Dict[str, Any]] = None
    ab_test_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        if isinstance(data["prediction"], np.ndarray):
            data["prediction"] = data["prediction"].tolist()
        return data


class InferenceCacheManager:
    """Manages caching for model inference with multiple strategies."""

    def __init__(self, redis_client: redis.Redis,
                 cache_strategy: CacheStrategy = CacheStrategy.TTL,
                 default_ttl: int = 3600,
                 max_cache_size_mb: int = 1024):
        """Initialize cache manager.
        
        Args:
            redis_client: Redis client for cache storage
            cache_strategy: Caching strategy to use
            default_ttl: Default TTL in seconds
            max_cache_size_mb: Maximum cache size in MB

        """
        self.redis = redis_client
        self.cache_strategy = cache_strategy
        self.default_ttl = default_ttl
        self.max_cache_size_mb = max_cache_size_mb
        self._cache_stats = defaultdict(int)

    async def get_cached_prediction(self, cache_key: str) -> Optional[np.ndarray]:
        """Retrieve cached prediction if available.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached prediction or None

        """
        try:
            # Get from cache
            cached_data = self.redis.get(cache_key)
            if not cached_data:
                self._cache_stats["misses"] += 1
                return None

            # Update access statistics
            self._update_access_stats(cache_key)

            # Decompress and deserialize
            decompressed = zlib.decompress(cached_data)
            prediction = pickle.loads(decompressed)

            self._cache_stats["hits"] += 1
            return prediction

        except (RedisError, pickle.PickleError, zlib.error) as e:
            logger.error(f"Cache retrieval error: {str(e)}")
            self._cache_stats["errors"] += 1
            return None

    async def cache_prediction(self, cache_key: str,
                             prediction: np.ndarray,
                             ttl: Optional[int] = None) -> bool:
        """Cache a prediction result.
        
        Args:
            cache_key: Cache key
            prediction: Prediction to cache
            ttl: Optional TTL override
            
        Returns:
            True if successful

        """
        try:
            # Serialize and compress
            serialized = pickle.dumps(prediction)
            compressed = zlib.compress(serialized)

            # Check size
            size_mb = len(compressed) / (1024 * 1024)
            if size_mb > 10:  # Don't cache large predictions
                logger.warning(f"Prediction too large to cache: {size_mb:.2f}MB")
                return False

            # Store with TTL
            ttl = ttl or self.default_ttl
            self.redis.setex(cache_key, ttl, compressed)

            # Update cache size tracking
            self._track_cache_size(cache_key, len(compressed))

            self._cache_stats["writes"] += 1
            return True

        except (RedisError, pickle.PickleError) as e:
            logger.error(f"Cache write error: {str(e)}")
            self._cache_stats["errors"] += 1
            return False

    def invalidate_model_cache(self, model_id: str) -> int:
        """Invalidate all cache entries for a model.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Number of entries invalidated

        """
        pattern = "inference:*"
        invalidated = 0

        # Scan for matching keys
        for key in self.redis.scan_iter(match=pattern):
            # Check if this key is for the specified model
            # This would require storing model_id in cache metadata
            self.redis.delete(key)
            invalidated += 1

        logger.info(f"Invalidated {invalidated} cache entries for model {model_id}")
        return invalidated

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Cache statistics dictionary

        """
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = self._cache_stats["hits"] / total_requests if total_requests > 0 else 0

        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "errors": self._cache_stats["errors"],
            "writes": self._cache_stats["writes"],
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            "cache_size_mb": self._get_total_cache_size_mb()
        }

    def clear_cache(self) -> int:
        """Clear all inference cache entries.
        
        Returns:
            Number of entries cleared

        """
        pattern = "inference:*"
        cleared = 0

        for key in self.redis.scan_iter(match=pattern):
            self.redis.delete(key)
            cleared += 1

        self._cache_stats.clear()
        logger.info(f"Cleared {cleared} cache entries")
        return cleared

    def _update_access_stats(self, cache_key: str):
        """Update access statistics for cache entry."""
        if self.cache_strategy == CacheStrategy.LFU:
            # Increment frequency counter
            freq_key = f"{cache_key}:freq"
            self.redis.incr(freq_key)
        elif self.cache_strategy == CacheStrategy.LRU:
            # Update last access time
            access_key = f"{cache_key}:access"
            self.redis.set(access_key, int(time.time()))

    def _track_cache_size(self, cache_key: str, size_bytes: int):
        """Track cache entry size."""
        size_key = f"{cache_key}:size"
        self.redis.set(size_key, size_bytes)

        # Check if eviction needed
        if self._get_total_cache_size_mb() > self.max_cache_size_mb:
            self._evict_entries()

    def _get_total_cache_size_mb(self) -> float:
        """Get total cache size in MB."""
        total_bytes = 0
        for key in self.redis.scan_iter(match="inference:*:size"):
            size = self.redis.get(key)
            if size:
                total_bytes += int(size)
        return total_bytes / (1024 * 1024)

    def _evict_entries(self):
        """Evict cache entries based on strategy."""
        # Simple implementation - evict oldest entries
        # In production, implement proper LRU/LFU eviction
        pattern = "inference:*"
        entries = []

        for key in self.redis.scan_iter(match=pattern):
            if not key.endswith(b":size") and not key.endswith(b":freq"):
                entries.append(key)

        # Delete 10% of entries
        to_delete = max(1, len(entries) // 10)
        for key in entries[:to_delete]:
            self.redis.delete(key)
            # Also delete metadata keys
            self.redis.delete(f"{key}:size")
            self.redis.delete(f"{key}:freq")
            self.redis.delete(f"{key}:access")


class ModelLoader:
    """Handles model loading and caching in memory."""

    def __init__(self, registry: HokusaiModelRegistry,
                 version_manager: ModelVersionManager,
                 max_models_in_memory: int = 10):
        """Initialize model loader.
        
        Args:
            registry: Model registry
            version_manager: Version manager
            max_models_in_memory: Maximum models to keep in memory

        """
        self.registry = registry
        self.version_manager = version_manager
        self.max_models_in_memory = max_models_in_memory
        self._model_cache = {}
        self._load_times = {}

    async def load_model(self, model_family: str,
                        version: Optional[str] = None,
                        environment: Environment = Environment.PRODUCTION) -> HokusaiModel:
        """Load a model, using cache if available.
        
        Args:
            model_family: Model family name
            version: Specific version or None for active
            environment: Environment to load from
            
        Returns:
            Loaded model

        """
        # Determine version
        if not version:
            active_version = self.version_manager.get_active_version(
                model_family, environment
            )
            if not active_version:
                raise ValueError(f"No active version for {model_family} in {environment.value}")
            version = active_version.version

        model_key = f"{model_family}/{version}"

        # Check memory cache
        if model_key in self._model_cache:
            self._load_times[model_key] = time.time()
            return self._model_cache[model_key]

        # Load model
        start_time = time.time()

        # Get model metadata
        model_version = self.version_manager.get_version(model_family, version)
        if not model_version:
            raise ValueError(f"Model version {model_key} not found")

        # Load from MLFlow
        import mlflow.pyfunc
        mlflow_model = mlflow.pyfunc.load_model(f"models:/{model_version.model_id}")

        # Create HokusaiModel wrapper
        # This is simplified - in practice, detect model type
        model = ModelFactory.create_model(
            model_type="sklearn",  # Would be detected from metadata
            model_instance=mlflow_model,
            metadata=model_version.metadata
        )

        load_time = time.time() - start_time
        logger.info(f"Loaded model {model_key} in {load_time:.2f}s")

        # Cache model
        self._cache_model(model_key, model)

        return model

    def _cache_model(self, model_key: str, model: HokusaiModel):
        """Cache model in memory with eviction."""
        # Check if eviction needed
        if len(self._model_cache) >= self.max_models_in_memory:
            # Evict least recently used
            oldest_key = min(self._load_times, key=self._load_times.get)
            del self._model_cache[oldest_key]
            del self._load_times[oldest_key]
            logger.info(f"Evicted model {oldest_key} from memory")

        self._model_cache[model_key] = model
        self._load_times[model_key] = time.time()


class HokusaiInferencePipeline:
    """Main inference pipeline with caching, routing, and monitoring."""

    def __init__(self, model_registry: HokusaiModelRegistry,
                 version_manager: ModelVersionManager,
                 traffic_router: ModelTrafficRouter,
                 cache_manager: InferenceCacheManager,
                 redis_client: redis.Redis,
                 enable_fallback: bool = True):
        """Initialize inference pipeline.
        
        Args:
            model_registry: Model registry
            version_manager: Version manager
            traffic_router: A/B test traffic router
            cache_manager: Cache manager
            redis_client: Redis client
            enable_fallback: Enable fallback to previous version on error

        """
        self.registry = model_registry
        self.version_manager = version_manager
        self.router = traffic_router
        self.cache = cache_manager
        self.redis = redis_client
        self.enable_fallback = enable_fallback

        # Initialize model loader
        self.model_loader = ModelLoader(self.registry, self.version_manager)

        # Metrics tracking
        self._metrics = defaultdict(int)

        # Thread pool for parallel operations
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def predict(self, request: InferenceRequest) -> InferenceResponse:
        """Main prediction endpoint with caching and routing.
        
        Args:
            request: Inference request
            
        Returns:
            Inference response

        """
        start_time = time.time()

        try:
            # 1. Determine which model to use (A/B testing)
            model_id, ab_test_id = self.router.route_request(
                request.request_id,
                request.model_family,
                request.user_id,
                request.request_metadata
            )

            # Parse model ID to get family and version
            model_family, model_version = self._parse_model_id(model_id)

            # 2. Check cache if enabled
            cache_key = None
            if request.use_cache:
                cache_key = request.get_cache_key(model_id)
                cached_prediction = await self.cache.get_cached_prediction(cache_key)

                if cached_prediction is not None:
                    latency_ms = (time.time() - start_time) * 1000

                    # Record metrics
                    if ab_test_id:
                        self.router.record_prediction_result(
                            ab_test_id,
                            self._get_ab_variant(model_id, ab_test_id),
                            latency_ms,
                            True,
                            True
                        )

                    return InferenceResponse(
                        request_id=request.request_id,
                        prediction=cached_prediction,
                        model_id=model_id,
                        model_version=model_version,
                        status=InferenceStatus.CACHE_HIT,
                        latency_ms=latency_ms,
                        cached=True,
                        cache_key=cache_key,
                        ab_test_id=ab_test_id
                    )

            # 3. Load model
            model = await self.model_loader.load_model(
                model_family,
                model_version
            )

            # 4. Make prediction
            prediction = await self._predict_with_timeout(
                model,
                request.features,
                request.timeout_ms
            )

            # 5. Cache result if enabled
            if request.use_cache and cache_key:
                await self.cache.cache_prediction(cache_key, prediction)

            # 6. Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # 7. Record metrics
            self._record_metrics(model_id, latency_ms, InferenceStatus.SUCCESS)

            if ab_test_id:
                self.router.record_prediction_result(
                    ab_test_id,
                    self._get_ab_variant(model_id, ab_test_id),
                    latency_ms,
                    True,
                    False
                )

            # 8. Get confidence if available
            confidence = None
            if hasattr(model, "predict_proba"):
                try:
                    proba = model.predict_proba(request.features)
                    confidence = float(np.max(proba))
                except Exception:
                    pass

            return InferenceResponse(
                request_id=request.request_id,
                prediction=prediction,
                model_id=model_id,
                model_version=model_version,
                status=InferenceStatus.SUCCESS,
                latency_ms=latency_ms,
                cached=False,
                cache_key=cache_key,
                confidence=confidence,
                ab_test_id=ab_test_id
            )

        except asyncio.TimeoutError:
            return await self._handle_timeout(request, model_id, start_time)
        except Exception as e:
            return await self._handle_error(request, model_id, start_time, e)

    async def predict_batch(self, requests: List[InferenceRequest]) -> List[InferenceResponse]:
        """Batch prediction with parallel processing.
        
        Args:
            requests: List of inference requests
            
        Returns:
            List of inference responses

        """
        # Process in parallel
        tasks = [self.predict(req) for req in requests]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        results = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                results.append(
                    InferenceResponse(
                        request_id=requests[i].request_id,
                        prediction=np.array([]),
                        model_id="unknown",
                        model_version="unknown",
                        status=InferenceStatus.ERROR,
                        latency_ms=0,
                        cached=False
                    )
                )
            else:
                results.append(response)

        return results

    async def warm_cache(self, model_family: str,
                        sample_features: List[Union[np.ndarray, pd.DataFrame]],
                        version: Optional[str] = None) -> int:
        """Warm the cache with sample predictions.
        
        Args:
            model_family: Model family to warm
            sample_features: Sample features to predict
            version: Specific version or None for active
            
        Returns:
            Number of entries cached

        """
        # Load model (ensures model is loaded into cache)
        await self.model_loader.load_model(model_family, version)
        model_id = f"{model_family}/{version or 'active'}"

        cached = 0
        for features in sample_features:
            try:
                # Create request
                request = InferenceRequest(
                    request_id=f"warmup_{cached}",
                    model_family=model_family,
                    features=features,
                    use_cache=True
                )

                # Make prediction (will cache)
                await self.predict(request)
                cached += 1

            except Exception as e:
                logger.error(f"Cache warming error: {str(e)}")

        logger.info(f"Warmed cache with {cached} entries for {model_id}")
        return cached

    def get_pipeline_metrics(self) -> Dict[str, Any]:
        """Get pipeline performance metrics.
        
        Returns:
            Metrics dictionary

        """
        total_requests = sum(self._metrics.values())

        return {
            "total_requests": total_requests,
            "success_rate": self._metrics[InferenceStatus.SUCCESS] / total_requests if total_requests > 0 else 0,
            "cache_hit_rate": self._metrics[InferenceStatus.CACHE_HIT] / total_requests if total_requests > 0 else 0,
            "error_rate": self._metrics[InferenceStatus.ERROR] / total_requests if total_requests > 0 else 0,
            "timeout_rate": self._metrics[InferenceStatus.TIMEOUT] / total_requests if total_requests > 0 else 0,
            "fallback_rate": self._metrics[InferenceStatus.FALLBACK] / total_requests if total_requests > 0 else 0,
            "cache_stats": self.cache.get_cache_stats(),
            "models_in_memory": len(self.model_loader._model_cache)
        }

    async def _predict_with_timeout(self, model: HokusaiModel,
                                  features: Union[np.ndarray, pd.DataFrame],
                                  timeout_ms: int) -> np.ndarray:
        """Make prediction with timeout."""
        loop = asyncio.get_event_loop()

        # Run prediction in thread pool
        future = loop.run_in_executor(
            self._executor,
            model.predict,
            features
        )

        # Wait with timeout
        timeout_seconds = timeout_ms / 1000.0
        return await asyncio.wait_for(future, timeout=timeout_seconds)

    async def _handle_timeout(self, request: InferenceRequest,
                            model_id: str,
                            start_time: float) -> InferenceResponse:
        """Handle prediction timeout."""
        latency_ms = (time.time() - start_time) * 1000
        self._record_metrics(model_id, latency_ms, InferenceStatus.TIMEOUT)

        # Try fallback if enabled
        if self.enable_fallback:
            return await self._try_fallback(request, model_id, start_time)

        return InferenceResponse(
            request_id=request.request_id,
            prediction=np.array([]),
            model_id=model_id,
            model_version="unknown",
            status=InferenceStatus.TIMEOUT,
            latency_ms=latency_ms,
            cached=False
        )

    async def _handle_error(self, request: InferenceRequest,
                          model_id: str,
                          start_time: float,
                          error: Exception) -> InferenceResponse:
        """Handle prediction error."""
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"Prediction error for {model_id}: {str(error)}")
        self._record_metrics(model_id, latency_ms, InferenceStatus.ERROR)

        # Try fallback if enabled
        if self.enable_fallback:
            return await self._try_fallback(request, model_id, start_time)

        return InferenceResponse(
            request_id=request.request_id,
            prediction=np.array([]),
            model_id=model_id,
            model_version="unknown",
            status=InferenceStatus.ERROR,
            latency_ms=latency_ms,
            cached=False
        )

    async def _try_fallback(self, request: InferenceRequest,
                          failed_model_id: str,
                          start_time: float) -> InferenceResponse:
        """Try fallback to previous model version."""
        try:
            # Get previous version
            model_family, _ = self._parse_model_id(failed_model_id)
            versions = self.version_manager.get_version_history(model_family, limit=2)

            if len(versions) < 2:
                raise ValueError("No fallback version available")

            fallback_version = versions[1]  # Previous version

            # Load fallback model
            fallback_model = await self.model_loader.load_model(
                model_family,
                fallback_version.version
            )

            # Make prediction
            prediction = await self._predict_with_timeout(
                fallback_model,
                request.features,
                request.timeout_ms
            )

            latency_ms = (time.time() - start_time) * 1000
            self._record_metrics(failed_model_id, latency_ms, InferenceStatus.FALLBACK)

            return InferenceResponse(
                request_id=request.request_id,
                prediction=prediction,
                model_id=f"{model_family}/{fallback_version.version}",
                model_version=fallback_version.version,
                status=InferenceStatus.FALLBACK,
                latency_ms=latency_ms,
                cached=False
            )

        except Exception as e:
            logger.error(f"Fallback failed: {str(e)}")
            latency_ms = (time.time() - start_time) * 1000
            return InferenceResponse(
                request_id=request.request_id,
                prediction=np.array([]),
                model_id=failed_model_id,
                model_version="unknown",
                status=InferenceStatus.ERROR,
                latency_ms=latency_ms,
                cached=False
            )

    def _parse_model_id(self, model_id: str) -> Tuple[str, str]:
        """Parse model ID into family and version."""
        parts = model_id.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid model ID format: {model_id}")
        return parts[0], parts[1]

    def _get_ab_variant(self, model_id: str, ab_test_id: str) -> str:
        """Determine A/B test variant from model ID."""
        # This is simplified - would need to check test configuration
        return "model_a"  # or "model_b"

    def _record_metrics(self, model_id: str, latency_ms: float, status: InferenceStatus):
        """Record inference metrics."""
        self._metrics[status] += 1

        # Store detailed metrics in Redis
        metric_key = f"inference_metrics:{model_id}:{datetime.utcnow().strftime('%Y%m%d%H')}"
        self.redis.hincrby(metric_key, f"{status.value}_count", 1)
        self.redis.hincrbyfloat(metric_key, "total_latency_ms", latency_ms)
        self.redis.expire(metric_key, 86400 * 7)  # 7 days TTL
