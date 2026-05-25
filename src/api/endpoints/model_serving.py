#!/usr/bin/env python3
"""Model serving endpoint for Hokusai API.

This module handles serving models (like Model ID 21) through the API,
integrating with HuggingFace and other storage backends.

Authentication is handled by APIKeyAuthMiddleware - all endpoints
use the require_auth dependency to access validated user context.
"""

import logging
import os
import pickle
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from huggingface_hub import hf_hub_download, snapshot_download
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...middleware.auth import require_auth
from ..dependencies import get_contributor_logger
from ..services.contributor_logger import ContributorLogger

# Setup logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "21": {
        "name": "Sales Lead Scoring Model",
        "repository_id": "timogilvie/hokusai-model-21-sales-lead-scorer",
        "storage_type": "huggingface_private",
        "model_type": "sklearn",
        "is_private": True,
        "inference_method": "local",
        "cache_duration": 3600,
        "max_batch_size": 100,
        "supported_inference_methods": ["api", "local"],
    },
    "30": {
        "name": "Technical Task Router",
        "storage_type": "in_process",
        "model_type": "technical_task_router",
        "is_private": False,
        "inference_method": "local",
        "model_version": "v1",
        "schema": "technical_task_router_inputs/v1",
        "description": "Deterministic local router for nested technical task inputs.",
        "max_batch_size": 1,
        "supported_inference_methods": ["local"],
    },
}

TECHNICAL_TASK_ROUTER_BASE_COSTS_USD: dict[str, float] = {
    "fast-coder-v1": 0.25,
    "deep-coder-v2": 0.42,
    "test-runner-v1": 0.12,
    "db-specialist-v1": 0.37,
}

TECHNICAL_TASK_ROUTER_COMPLEXITY_MULTIPLIERS: dict[str, float] = {
    "low": 0.8,
    "medium": 1.0,
    "high": 3.2,
}

TECHNICAL_TASK_ROUTER_TASK_TYPE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "performance_tuning": {
        "db-specialist-v1": 0.7,
        "fast-coder-v1": 1.8,
    }
}


class PredictionRequest(BaseModel):
    """Request schema for model predictions."""

    inputs: dict[str, Any] = Field(..., description="Input data for prediction")
    options: Optional[dict[str, Any]] = Field(
        default_factory=dict, description="Additional options"
    )


class PredictionResponse(BaseModel):
    """Response schema for model predictions."""

    model_config = {"protected_namespaces": ()}  # Allow model_id field

    model_id: str
    predictions: dict[str, Any]
    metadata: dict[str, Any]
    timestamp: str
    inference_log_id: Optional[str] = None


class TechnicalTaskGroup(BaseModel):
    """Required task description for model 30 routing."""

    model_config = ConfigDict(extra="forbid")

    description: str
    task_type: str
    language: str | None = None
    framework: str | None = None
    repo_type: str | None = None


class TechnicalTaskRoutingGroup(BaseModel):
    """Optional routing constraints and preferences."""

    model_config = ConfigDict(extra="forbid")

    available_models: list[str] | None = Field(default=None, min_length=1)
    preferred_models: list[str] | None = Field(default=None, min_length=1)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_latency_seconds: float | None = Field(default=None, gt=0)
    prioritize_quality: bool | None = None
    prioritize_speed: bool | None = None


class TechnicalTaskContextGroup(BaseModel):
    """Optional task context that can improve routing quality."""

    model_config = ConfigDict(extra="forbid")

    domain: str | None = None
    repo_size_bucket: str | None = None
    requires_tests: bool | None = None
    risk_level: str | None = None
    file_count: int | None = Field(default=None, ge=0)
    estimated_complexity: str | None = None
    security_sensitive: bool | None = None


class TechnicalTaskWorkflowGroup(BaseModel):
    """Optional workflow and execution-surface metadata."""

    model_config = ConfigDict(extra="forbid")

    surface: str | None = None
    stages: list[str] | None = Field(default=None, min_length=1)
    execution_environment: str | None = None
    human_review_required: bool | None = None


class TechnicalTaskPredictionGroup(BaseModel):
    """Optional caller-side expectations."""

    model_config = ConfigDict(extra="forbid")

    expected_duration_seconds: float | None = Field(default=None, ge=0)
    expected_cost_usd: float | None = Field(default=None, ge=0)
    expected_success_probability: float | None = Field(default=None, ge=0, le=1)


class TechnicalTaskOutcomeGroup(BaseModel):
    """Optional post-execution outcome metadata."""

    model_config = ConfigDict(extra="forbid")

    completed_successfully: bool | None = None
    actual_cost_usd: float | None = Field(default=None, ge=0)
    actual_time_seconds: float | None = Field(default=None, ge=0)
    retry_count: int | None = Field(default=None, ge=0)
    intervention_required: bool | None = None
    selected_model: str | None = None


class TechnicalTaskRubricGroup(BaseModel):
    """Optional evaluation metadata."""

    model_config = ConfigDict(extra="forbid")

    quality_score: float | None = None
    correctness_score: float | None = None
    human_rating: str | None = None
    benchmark_passed: bool | None = None


class TechnicalTaskMetadataGroup(BaseModel):
    """Optional integration metadata."""

    model_config = ConfigDict(extra="forbid")

    external_task_id: str | None = None
    run_id: str | None = None
    integration_version: str | None = None
    idempotency_key: str | None = None


class TechnicalTaskRouterInputs(BaseModel):
    """Validated model-30 payload matching technical_task_router_inputs/v1."""

    model_config = ConfigDict(extra="forbid")

    task: TechnicalTaskGroup
    routing: TechnicalTaskRoutingGroup | None = None
    context: TechnicalTaskContextGroup | None = None
    workflow: TechnicalTaskWorkflowGroup | None = None
    prediction: TechnicalTaskPredictionGroup | None = None
    outcome: TechnicalTaskOutcomeGroup | None = None
    rubric: TechnicalTaskRubricGroup | None = None
    metadata: TechnicalTaskMetadataGroup | None = None


class ModelServingService:
    """Service for serving models through the Hokusai API.

    This service handles:
    1. Loading models from HuggingFace (or other storage)
    2. Running inference
    3. Caching models for performance
    4. Access control and logging
    """

    def __init__(self):
        self.model_cache = {}
        self.hf_token = os.getenv("HUGGINGFACE_API_KEY")
        self.inference_api_url = "https://api-inference.huggingface.co/models"

    def get_model_config(self, model_id: str) -> dict[str, Any]:
        """Get model configuration from database.

        In production, this would query the database.
        For now, we'll return config for Model ID 21.
        """
        config = MODEL_CONFIGS.get(model_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        return dict(config)

    async def load_model_from_huggingface(self, repository_id: str, model_type: str) -> Any:
        """Load a model from HuggingFace Hub.

        Args:
        ----
            repository_id: HuggingFace repository ID
            model_type: Type of model (sklearn, pytorch, etc.)

        Returns:
        -------
            Loaded model object

        """
        if not self.hf_token:
            raise HTTPException(status_code=500, detail="HuggingFace token not configured")

        try:
            # Download model file from HuggingFace
            with tempfile.TemporaryDirectory() as tmpdir:
                if model_type == "sklearn":
                    # Download pickle file
                    model_path = hf_hub_download(
                        repo_id=repository_id,
                        filename="model.pkl",
                        token=self.hf_token,
                        cache_dir=tmpdir,
                    )

                    # Load the model
                    with open(model_path, "rb") as f:
                        model_data = pickle.load(f)

                    return model_data

                elif model_type == "pytorch":
                    # Download PyTorch model
                    model_path = hf_hub_download(
                        repo_id=repository_id,
                        filename="pytorch_model.bin",
                        token=self.hf_token,
                        cache_dir=tmpdir,
                    )

                    # Load PyTorch model (simplified)
                    import torch

                    model = torch.load(model_path)
                    return model

                else:
                    # For other types, download entire repository
                    snapshot_path = snapshot_download(
                        repo_id=repository_id, token=self.hf_token, cache_dir=tmpdir
                    )
                    return snapshot_path

        except Exception as e:
            logger.error(f"Failed to load model from HuggingFace: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

    async def predict_with_inference_api(
        self, repository_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Use HuggingFace Inference API for prediction.

        This method calls the HuggingFace Inference API directly,
        which is good for testing but has rate limits.
        """
        if not self.hf_token:
            raise HTTPException(status_code=500, detail="HuggingFace token not configured")

        url = f"{self.inference_api_url}/{repository_id}"
        headers = {"Authorization": f"Bearer {self.hf_token}", "Content-Type": "application/json"}

        try:
            response = requests.post(url, headers=headers, json={"inputs": inputs}, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 503:
                # Model is loading
                raise HTTPException(
                    status_code=503, detail="Model is loading. Please try again in a few seconds."
                )
            else:
                raise HTTPException(
                    status_code=response.status_code, detail=f"Inference API error: {response.text}"
                )

        except requests.exceptions.RequestException as e:
            logger.error(f"Inference API request failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to call inference API: {str(e)}")

    async def predict_local(
        self,
        model_id: str,
        model: Any,
        inputs: dict[str, Any],
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run prediction locally with the loaded model.

        This is for models that are downloaded and run locally,
        like Model ID 21 (Sales Lead Scoring).
        """
        # Model ID 21 specific logic
        if model_id == "21":
            # Prepare features for sklearn model
            features = self._prepare_sales_lead_features(inputs)

            # Get model components
            if isinstance(model, dict):
                classifier = model.get("model")
                if classifier is None:
                    raise ValueError("Model not found in loaded data")
            else:
                classifier = model

            # Make prediction
            prediction = classifier.predict(features)[0]
            probabilities = classifier.predict_proba(features)[0]

            # Calculate lead score
            lead_score = int(probabilities[1] * 100)

            # Determine recommendation
            if lead_score >= 70:
                recommendation = "Hot"
            elif lead_score >= 40:
                recommendation = "Warm"
            else:
                recommendation = "Cold"

            # Identify factors
            factors = []
            if inputs.get("demo_requested"):
                factors.append("Demo requested")
            if inputs.get("budget_confirmed"):
                factors.append("Budget confirmed")
            if inputs.get("engagement_score", 0) > 70:
                factors.append("High engagement")

            return {
                "lead_score": lead_score,
                "conversion_probability": float(probabilities[1]),
                "recommendation": recommendation,
                "factors": factors,
                "confidence": float(max(probabilities)),
            }

        elif model_id == "30":
            return self._predict_technical_task_router(inputs, options or {})

        # Generic prediction logic for other models
        raise NotImplementedError(f"Local prediction not implemented for model {model_id}")

    def _predict_technical_task_router(
        self, inputs: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Deterministically route a technical task to an allowed model within budget."""
        try:
            validated_inputs = TechnicalTaskRouterInputs.model_validate(inputs)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

        available_models = (
            validated_inputs.routing.available_models
            if validated_inputs.routing and validated_inputs.routing.available_models is not None
            else list(TECHNICAL_TASK_ROUTER_BASE_COSTS_USD)
        )
        preferred_models = (
            validated_inputs.routing.preferred_models
            if validated_inputs.routing and validated_inputs.routing.preferred_models is not None
            else None
        )
        max_cost_usd = (
            validated_inputs.routing.max_cost_usd
            if validated_inputs.routing and validated_inputs.routing.max_cost_usd is not None
            else 1.0
        )
        estimated_complexity = (
            validated_inputs.context.estimated_complexity
            if validated_inputs.context and validated_inputs.context.estimated_complexity
            else "medium"
        )

        cost_overrides = self._extract_router_cost_overrides(options)
        chosen_model, estimated_cost = self._select_router_model(
            available_models=available_models,
            preferred_models=preferred_models,
            max_cost_usd=max_cost_usd,
            task_type=validated_inputs.task.task_type,
            estimated_complexity=estimated_complexity,
            cost_overrides=cost_overrides,
        )

        if chosen_model is None or estimated_cost is None:
            return {
                "status": "over_budget",
                "selected_models": [],
                "estimated_cost_usd": None,
                "actual_cost_usd": 0.0,
                "max_cost_usd": max_cost_usd,
                "task": validated_inputs.task.model_dump(mode="json", exclude_none=True),
                "completed_successfully": False,
                "rationale": "No allowed model could satisfy the budget constraint.",
            }

        return {
            "status": "success",
            "selected_models": [chosen_model],
            "estimated_cost_usd": estimated_cost,
            "actual_cost_usd": estimated_cost,
            "max_cost_usd": max_cost_usd,
            "task": validated_inputs.task.model_dump(mode="json", exclude_none=True),
            "completed_successfully": True,
            "rationale": f"Selected cheapest allowed model within budget: {chosen_model}.",
        }

    def _extract_router_cost_overrides(self, options: dict[str, Any]) -> dict[str, float]:
        """Collect caller-provided cost hints from request options when present."""
        candidates = [
            options.get("candidate_costs_usd"),
            options.get("metadata", {}).get("candidate_costs_usd")
            if isinstance(options.get("metadata"), dict)
            else None,
        ]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            overrides: dict[str, float] = {}
            for model_name, cost in candidate.items():
                try:
                    overrides[str(model_name)] = float(cost)
                except (TypeError, ValueError):
                    continue
            if overrides:
                return overrides
        return {}

    def _estimate_router_cost(
        self,
        model_name: str,
        task_type: str,
        estimated_complexity: str,
        cost_overrides: dict[str, float],
    ) -> float:
        """Estimate router cost for a single candidate model."""
        if model_name in cost_overrides:
            return cost_overrides[model_name]

        base_cost = TECHNICAL_TASK_ROUTER_BASE_COSTS_USD.get(model_name, 1.0)
        complexity_multiplier = TECHNICAL_TASK_ROUTER_COMPLEXITY_MULTIPLIERS.get(
            estimated_complexity, 1.0
        )
        task_multiplier = TECHNICAL_TASK_ROUTER_TASK_TYPE_MULTIPLIERS.get(task_type, {}).get(
            model_name, 1.0
        )
        return round(base_cost * complexity_multiplier * task_multiplier, 4)

    def _select_router_model(
        self,
        *,
        available_models: list[str],
        preferred_models: list[str] | None,
        max_cost_usd: float,
        task_type: str,
        estimated_complexity: str,
        cost_overrides: dict[str, float],
    ) -> tuple[str | None, float | None]:
        """Pick the cheapest allowed model that satisfies the budget."""
        ranked_candidates: list[tuple[float, str]] = []
        for model_name in available_models:
            estimated_cost = self._estimate_router_cost(
                model_name, task_type, estimated_complexity, cost_overrides
            )
            if estimated_cost <= max_cost_usd:
                ranked_candidates.append((estimated_cost, model_name))

        if not ranked_candidates:
            return None, None

        preferred_rank = {
            model_name: index for index, model_name in enumerate(preferred_models or [])
        }
        if preferred_rank:
            preferred_candidates = [item for item in ranked_candidates if item[1] in preferred_rank]
            if preferred_candidates:
                ranked_candidates = preferred_candidates

        estimated_cost, selected_model = min(
            ranked_candidates,
            key=lambda item: (item[0], preferred_rank.get(item[1], float("inf")), item[1]),
        )
        return selected_model, estimated_cost

    def _prepare_sales_lead_features(self, data: dict[str, Any]) -> np.ndarray:
        """Prepare features for Sales Lead Scoring Model (ID 21).

        This matches the feature preparation in the training script.
        """
        features = []

        # Numerical features
        features.append(data.get("company_size", 0))
        features.append(data.get("engagement_score", 0))
        features.append(data.get("website_visits", 0))
        features.append(data.get("email_opens", 0))
        features.append(data.get("content_downloads", 0))

        # Boolean features
        features.append(1 if data.get("demo_requested", False) else 0)
        features.append(1 if data.get("budget_confirmed", False) else 0)

        # Categorical features (simplified encoding)
        industry_score = {
            "Technology": 3,
            "Finance": 3,
            "Healthcare": 2,
            "Retail": 1,
            "Other": 1,
        }.get(data.get("industry", "Other"), 1)
        features.append(industry_score)

        timeline_score = {
            "Q1 2025": 3,
            "Q2 2025": 2,
            "Q3 2025": 1,
            "Q4 2025": 1,
            "Not specified": 0,
        }.get(data.get("decision_timeline", "Not specified"), 0)
        features.append(timeline_score)

        # Title feature
        title = data.get("title", "").lower()
        title_score = 0
        if "vp" in title or "vice president" in title:
            title_score = 3
        elif "director" in title:
            title_score = 2
        elif "manager" in title:
            title_score = 1
        features.append(title_score)

        return np.array(features).reshape(1, -1)

    async def serve_prediction(
        self, model_id: str, inputs: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Main method to serve predictions for a model.

        Args:
        ----
            model_id: Model ID (e.g., "21")
            inputs: Input data for prediction
            options: Additional options

        Returns:
        -------
            Prediction results

        """
        # Get model configuration
        config = self.get_model_config(model_id)

        logger.info(f"Serving prediction for model {model_id}")

        # Check cache
        cache_key = f"model_{model_id}"
        cached_model = self.model_cache.get(cache_key)

        predictions = None

        # Determine inference method
        inference_method = options.get("inference_method", config["inference_method"])

        if inference_method == "api":
            # Use HuggingFace Inference API (rate limited but no download needed)
            predictions = await self.predict_with_inference_api(config["repository_id"], inputs)

        elif inference_method == "local":
            # Load and run model locally
            if cached_model is None:
                # Load model from HuggingFace
                logger.info(f"Loading model {model_id} from HuggingFace...")
                repository_id = config.get("repository_id")
                if repository_id:
                    model = await self.load_model_from_huggingface(
                        repository_id, config["model_type"]
                    )
                    # Cache the model
                    self.model_cache[cache_key] = {
                        "model": model,
                        "loaded_at": datetime.utcnow(),
                        "config": config,
                    }
                    cached_model = self.model_cache[cache_key]

            # Run local prediction
            predictions = await self.predict_local(
                model_id,
                cached_model["model"] if cached_model else None,
                inputs,
                options,
            )

        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown inference method: {inference_method}"
            )

        return predictions


# Initialize service
serving_service = ModelServingService()


# API Endpoints


@router.get("/{model_id}/info")
async def get_model_info(
    model_id: str,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Get information about a model.

    This endpoint returns metadata about the model without running inference.
    Authentication is handled by APIKeyAuthMiddleware.

    Args:
    ----
        model_id: The ID of the model to get information about
        auth: User authentication context from middleware

    Returns:
    -------
        Model information including name, type, storage, and capabilities

    """
    # Log the request
    logger.info(
        f"Model info request for model {model_id}",
        extra={
            "user_id": auth.get("user_id"),
            "api_key_id": auth.get("api_key_id"),
            "model_id": model_id,
            "endpoint": "info",
        },
    )

    config = serving_service.get_model_config(model_id)

    response: dict[str, Any] = {
        "model_id": model_id,
        "name": config["name"],
        "type": config["model_type"],
        "storage": config["storage_type"],
        "is_available": True,
        "inference_methods": config.get(
            "supported_inference_methods",
            ["api", "local"] if config["is_private"] else ["api"],
        ),
        "max_batch_size": config.get("max_batch_size", 1),
    }
    for _key in ("model_version", "schema", "description"):
        if (_val := config.get(_key)) is not None:
            response[_key] = _val
    return response


@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    request: PredictionRequest,
    background_tasks: BackgroundTasks,
    auth: Dict[str, Any] = Depends(require_auth),
    contributor_logger: ContributorLogger = Depends(get_contributor_logger),
):
    """Run prediction for a model.

    This is the main endpoint that clients call with their Hokusai API key.
    Authentication is handled by APIKeyAuthMiddleware.

    Args:
    ----
        model_id: The ID of the model to use for prediction (e.g., "21")
        request: Prediction request containing inputs and options
        auth: User authentication context from middleware

    Returns:
    -------
        PredictionResponse with predictions and metadata

    """
    # Extract user context from middleware
    user_id = auth.get("user_id")
    api_key_id = auth.get("api_key_id")
    scopes = auth.get("scopes", [])

    # Log the request for audit and billing
    logger.info(
        f"Prediction request for model {model_id}",
        extra={
            "user_id": user_id,
            "api_key_id": api_key_id,
            "model_id": model_id,
            "endpoint": "predict",
            "scopes": scopes,
        },
    )

    try:
        started_at = time.perf_counter()
        # Run prediction
        predictions = await serving_service.serve_prediction(
            model_id=model_id, inputs=request.inputs, options=request.options
        )
        inference_latency_ms = int((time.perf_counter() - started_at) * 1000)
        model_config = serving_service.get_model_config(model_id)
        model_version = str(
            request.options.get("model_version", model_config.get("model_version", "unknown"))
        )
        inference_log_id = contributor_logger.new_inference_log_id()

        # Build response
        response = PredictionResponse(
            model_id=model_id,
            predictions=predictions,
            metadata={
                "api_version": "1.0",
                "inference_method": request.options.get("inference_method", "local"),
                "user_id": user_id,
                "api_key_id": api_key_id,
            },
            timestamp=datetime.utcnow().isoformat(),
            inference_log_id=str(inference_log_id),
        )

        # Persist inference log in the background so hot-path latency remains low.
        background_tasks.add_task(
            contributor_logger.log_inference,
            api_token_id=str(api_key_id or "unknown"),
            model_name=model_config.get("name", model_id),
            model_version=model_version,
            input_payload=request.inputs,
            output_payload=predictions,
            trace_metadata={
                "latency_ms": inference_latency_ms,
                "inference_method": request.options.get("inference_method", "local"),
                "model_id": model_id,
            },
            inference_log_id=inference_log_id,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Prediction failed for model {model_id}: {str(e)}",
            extra={"user_id": user_id, "api_key_id": api_key_id, "model_id": model_id},
        )
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/{model_id}/health")
async def check_model_health(
    model_id: str,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Check if a model is healthy and ready to serve.

    Authentication is handled by APIKeyAuthMiddleware.

    Args:
    ----
        model_id: The ID of the model to check
        auth: User authentication context from middleware

    Returns:
    -------
        Model health status including cache status and readiness

    """
    logger.info(
        f"Health check request for model {model_id}",
        extra={
            "user_id": auth.get("user_id"),
            "api_key_id": auth.get("api_key_id"),
            "model_id": model_id,
            "endpoint": "health",
        },
    )

    try:
        config = serving_service.get_model_config(model_id)

        # Check if model is cached
        cache_key = f"model_{model_id}"
        is_cached = cache_key in serving_service.model_cache

        return {
            "model_id": model_id,
            "status": "healthy",
            "is_cached": is_cached,
            "storage_type": config["storage_type"],
            "inference_ready": True,
        }

    except Exception as e:
        logger.warning(
            f"Health check failed for model {model_id}: {str(e)}",
            extra={
                "user_id": auth.get("user_id"),
                "model_id": model_id,
                "error": str(e),
            },
        )
        return {"model_id": model_id, "status": "unhealthy", "error": str(e)}


# Example usage for testing
if __name__ == "__main__":
    import asyncio

    async def test_model_21():
        """Test Model ID 21 serving."""
        print("🧪 Testing Model 21 (Sales Lead Scoring) serving...")

        # Test data
        test_input = {
            "company_size": 1000,
            "industry": "Technology",
            "engagement_score": 75,
            "website_visits": 10,
            "email_opens": 5,
            "content_downloads": 3,
            "demo_requested": True,
            "budget_confirmed": False,
            "decision_timeline": "Q2 2025",
            "title": "VP of Sales",
        }

        # Simulate serving
        service = ModelServingService()

        try:
            # Get model info
            config = service.get_model_config("21")
            print(f"✅ Model config loaded: {config['name']}")

            # Simulate prediction (would need actual model)
            print(f"📊 Test input: {test_input}")
            print("🔄 Would run prediction through Hokusai API...")
            print("✅ Prediction complete (simulated)")

        except Exception as e:
            print(f"❌ Error: {str(e)}")

    # Run test
    asyncio.run(test_model_21())
