"""Tests for Inference Pipeline with caching."""
import asyncio
import json
import time
from unittest.mock import Mock, patch

import pytest
import redis
from hokusai.core.ab_testing import ModelTrafficRouter
from hokusai.core.inference import (
    CacheConfig,
    HokusaiInferencePipeline,
    InferenceRequest,
    InferenceResponse,
)
from hokusai.core.models import HokusaiModel
from hokusai.core.registry import ModelRegistry
from hokusai.core.versioning import ModelVersionManager


class TestInferenceRequest:
    """Test cases for InferenceRequest."""

    def test_request_creation(self) -> None:
        """Test creating inference request."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]},
            user_id="user-123",
            metadata={"source": "api"}
        )

        assert request.request_id == "req-001"
        assert request.model_type == "lead_scoring"
        assert request.data["features"] == [1, 2, 3]
        assert request.user_id == "user-123"

    def test_request_cache_key(self) -> None:
        """Test generating cache key for request."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]},
            model_version="1.0.0"
        )

        cache_key = request.get_cache_key()
        assert "lead_scoring" in cache_key
        assert "1.0.0" in cache_key
        # Data should be hashed consistently
        assert len(cache_key) > 20


class TestHokusaiInferencePipeline:
    """Test cases for HokusaiInferencePipeline."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        registry = Mock(spec=ModelRegistry)
        version_manager = Mock(spec=ModelVersionManager)
        traffic_router = Mock(spec=ModelTrafficRouter)
        redis_client = Mock(spec=redis.Redis)

        return registry, version_manager, traffic_router, redis_client

    @pytest.fixture
    def pipeline(self, mock_dependencies):
        """Create inference pipeline instance."""
        registry, version_manager, traffic_router, redis_client = mock_dependencies

        with patch("redis.Redis", return_value=redis_client):
            pipeline = HokusaiInferencePipeline(
                registry=registry,
                version_manager=version_manager,
                traffic_router=traffic_router,
                cache_config=CacheConfig(enabled=True, ttl_seconds=300)
            )

        return pipeline

    def test_pipeline_initialization(self, mock_dependencies) -> None:
        """Test pipeline initialization with components."""
        registry, version_manager, traffic_router, redis_client = mock_dependencies

        with patch("redis.Redis", return_value=redis_client):
            pipeline = HokusaiInferencePipeline(
                registry=registry,
                version_manager=version_manager,
                traffic_router=traffic_router
            )

        assert pipeline.registry == registry
        assert pipeline.version_manager == version_manager
        assert pipeline.traffic_router == traffic_router
        assert pipeline.cache is not None

    @pytest.mark.asyncio
    async def test_predict_with_cache_hit(self, pipeline) -> None:
        """Test prediction with cache hit."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]}
        )

        cached_result = {"prediction": 0.85, "cached": True}
        pipeline.cache.get.return_value = json.dumps(cached_result).encode()

        response = await pipeline.predict(request)

        assert response.prediction == {"prediction": 0.85, "cached": True}
        assert response.cache_hit is True
        assert response.model_version is not None
        pipeline.cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_with_cache_miss(self, pipeline) -> None:
        """Test prediction with cache miss."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]}
        )

        # Mock cache miss
        pipeline.cache.get.return_value = None

        # Mock model loading and prediction
        mock_model = Mock(spec=HokusaiModel)
        mock_model.predict.return_value = {"prediction": 0.85}
        mock_model.version = "1.0.0"

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-001")
        pipeline._load_model = Mock(return_value=mock_model)

        response = await pipeline.predict(request)

        assert response.prediction == {"prediction": 0.85}
        assert response.cache_hit is False
        assert response.model_version == "1.0.0"

        # Should cache the result
        pipeline.cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_with_ab_test(self, pipeline) -> None:
        """Test prediction with A/B test routing."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]},
            user_id="user-123"
        )

        # Mock A/B test routing
        pipeline.traffic_router.get_active_test.return_value = Mock(test_id="test-001")
        pipeline.traffic_router.route_request.return_value = "model-v2"

        # Mock model
        mock_model = Mock(spec=HokusaiModel)
        mock_model.predict.return_value = {"prediction": 0.90}
        mock_model.version = "2.0.0"
        mock_model.model_id = "model-v2"

        pipeline.registry.get_model_by_id.return_value = Mock(model_id="model-v2")
        pipeline._load_model = Mock(return_value=mock_model)
        pipeline.cache.get.return_value = None

        response = await pipeline.predict(request)

        assert response.prediction == {"prediction": 0.90}
        assert response.model_version == "2.0.0"
        assert response.ab_test_id == "test-001"

        # Should record metric for A/B test
        pipeline.traffic_router.record_metric.assert_called()

    @pytest.mark.asyncio
    async def test_batch_predict(self, pipeline) -> None:
        """Test batch prediction functionality."""
        requests = [
            InferenceRequest(
                request_id=f"req-{i}",
                model_type="lead_scoring",
                data={"features": [i, i+1, i+2]}
            )
            for i in range(5)
        ]

        # Mock model for batch prediction
        mock_model = Mock(spec=HokusaiModel)
        mock_model.batch_predict.return_value = [
            {"prediction": 0.8 + i*0.01} for i in range(5)
        ]
        mock_model.version = "1.0.0"

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-001")
        pipeline._load_model = Mock(return_value=mock_model)
        pipeline.cache.get.return_value = None

        responses = await pipeline.batch_predict(requests)

        assert len(responses) == 5
        assert all(isinstance(r, InferenceResponse) for r in responses)
        assert responses[0].prediction["prediction"] == 0.8
        assert responses[4].prediction["prediction"] == 0.84

        # Should use batch_predict method
        mock_model.batch_predict.assert_called_once()

    def test_model_loading_with_cache(self, pipeline) -> None:
        """Test model loading with in-memory cache."""
        model_id = "model-001"

        # First load
        mock_model = Mock(spec=HokusaiModel)
        with patch.object(pipeline, "_download_and_load_model", return_value=mock_model):
            loaded_model = pipeline._load_model(model_id)
            assert loaded_model == mock_model

        # Second load should use cache
        cached_model = pipeline._load_model(model_id)
        assert cached_model == mock_model

        # Download should only be called once
        pipeline._download_and_load_model.assert_called_once()

    def test_model_eviction_on_memory_pressure(self, pipeline) -> None:
        """Test model eviction when memory limit is reached."""
        # Set small memory limit
        pipeline.max_models_in_memory = 2

        # Load models
        for i in range(3):
            model_id = f"model-{i}"
            mock_model = Mock(spec=HokusaiModel)
            mock_model.get_memory_usage.return_value = 100  # MB

            with patch.object(pipeline, "_download_and_load_model", return_value=mock_model):
                pipeline._load_model(model_id)

        # Should have evicted the first model
        assert len(pipeline.model_cache) == 2
        assert "model-0" not in pipeline.model_cache
        assert "model-1" in pipeline.model_cache
        assert "model-2" in pipeline.model_cache

    @pytest.mark.asyncio
    async def test_predict_with_preprocessing(self, pipeline) -> None:
        """Test prediction with data preprocessing."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"raw_features": {"age": 25, "income": 50000}},
            preprocessing_required=True
        )

        # Mock preprocessing
        pipeline.preprocessor = Mock()
        pipeline.preprocessor.process.return_value = {"features": [25, 50000, 0.5]}

        # Mock model
        mock_model = Mock(spec=HokusaiModel)
        mock_model.predict.return_value = {"prediction": 0.75}
        mock_model.version = "1.0.0"

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-001")
        pipeline._load_model = Mock(return_value=mock_model)
        pipeline.cache.get.return_value = None

        response = await pipeline.predict(request)

        assert response.prediction == {"prediction": 0.75}
        pipeline.preprocessor.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_with_postprocessing(self, pipeline) -> None:
        """Test prediction with result postprocessing."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]},
            postprocessing_required=True
        )

        # Mock model
        mock_model = Mock(spec=HokusaiModel)
        mock_model.predict.return_value = {"raw_score": 0.75}
        mock_model.version = "1.0.0"

        # Mock postprocessing
        pipeline.postprocessor = Mock()
        pipeline.postprocessor.process.return_value = {
            "prediction": "high",
            "confidence": 0.95,
            "score": 0.75
        }

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-001")
        pipeline._load_model = Mock(return_value=mock_model)
        pipeline.cache.get.return_value = None

        response = await pipeline.predict(request)

        assert response.prediction["prediction"] == "high"
        assert response.prediction["confidence"] == 0.95
        pipeline.postprocessor.process.assert_called_once()

    def test_performance_monitoring(self, pipeline) -> None:
        """Test performance monitoring during inference."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]}
        )

        # Mock model with controlled execution time
        mock_model = Mock(spec=HokusaiModel)

        def slow_predict(data):
            time.sleep(0.1)  # 100ms
            return {"prediction": 0.85}

        mock_model.predict.side_effect = slow_predict
        mock_model.version = "1.0.0"

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-001")
        pipeline._load_model = Mock(return_value=mock_model)
        pipeline.cache.get.return_value = None

        # Run async prediction synchronously for testing
        response = asyncio.run(pipeline.predict(request))

        assert response.latency_ms >= 100
        assert response.latency_ms < 200  # Should not be much more than 100ms

    @pytest.mark.asyncio
    async def test_fallback_on_model_failure(self, pipeline) -> None:
        """Test fallback to previous version on model failure."""
        request = InferenceRequest(
            request_id="req-001",
            model_type="lead_scoring",
            data={"features": [1, 2, 3]}
        )

        # Mock failing current model
        failing_model = Mock(spec=HokusaiModel)
        failing_model.predict.side_effect = Exception("Model error")
        failing_model.version = "2.0.0"

        # Mock working fallback model
        fallback_model = Mock(spec=HokusaiModel)
        fallback_model.predict.return_value = {"prediction": 0.80}
        fallback_model.version = "1.0.0"

        pipeline.registry.get_latest_model.return_value = Mock(model_id="model-v2")
        pipeline.version_manager.get_previous_version.return_value = Mock(model_id="model-v1")

        # First call returns failing model, second returns fallback
        pipeline._load_model = Mock(side_effect=[failing_model, fallback_model])
        pipeline.cache.get.return_value = None

        response = await pipeline.predict(request)

        assert response.prediction == {"prediction": 0.80}
        assert response.model_version == "1.0.0"
        assert response.fallback_used is True
