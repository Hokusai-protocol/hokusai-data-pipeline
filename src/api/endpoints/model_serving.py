#!/usr/bin/env python3
"""Model serving endpoint for Hokusai API.

This module handles serving models (like Model ID 21) through the API,
integrating with HuggingFace and other storage backends.

Authentication is handled by APIKeyAuthMiddleware - all endpoints
use the require_auth dependency to access validated user context.
"""

import asyncio
import logging
import os
import pickle
import tempfile
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from huggingface_hub import hf_hub_download, snapshot_download
from pydantic import BaseModel, Field, ValidationError

from ...middleware.auth import require_auth
from ...utils.mlflow_health import check_mlflow_registry_sdk
from ..dependencies import get_contributor_logger
from ..middleware.validation_logging import (
    classify_client_ip,
    emit_model_serving_validation_422,
    get_or_generate_request_id,
)
from ..services.contributor_logger import ContributorLogger
from .latency_trace import Model30LatencyTrace
from .model_30_adapter import (
    Model30FailurePhase,
    Model30InferenceError,
    Model30LoadInProgressError,
    log_model_30_failure,
)
from .model_registry import ModelRegistryEntry
from .model_registry_entries import MODEL_CONFIGS

# Setup logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/models", tags=["model-serving"])


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
        self.prediction_timeout_seconds = float(
            os.getenv("MODEL_SERVING_PREDICTION_TIMEOUT_SECONDS", "25")
        )
        self.model_load_timeout_seconds = float(
            os.getenv("MODEL_SERVING_LOAD_TIMEOUT_SECONDS", "25")
        )
        self.model_30_readiness_timeout_seconds = float(
            os.getenv("MODEL_30_READINESS_TIMEOUT_SECONDS", "22")
        )
        model_21_entry = MODEL_CONFIGS.get("21")
        if model_21_entry is not None and model_21_entry.local_predictor is None:
            MODEL_CONFIGS["21"] = replace(
                model_21_entry,
                local_predictor=self._predict_sales_lead_local,
            )

    def get_registry_entry(self, model_id: str) -> ModelRegistryEntry:
        """Resolve a typed registry entry for a model id."""
        entry = MODEL_CONFIGS.get(model_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        return entry

    def get_model_config(self, model_id: str) -> dict[str, Any]:
        """Return the public JSON-safe model configuration."""
        return self.get_registry_entry(model_id).as_public_config()

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
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._load_model_from_huggingface_sync,
                    repository_id,
                    model_type,
                ),
                timeout=self.model_load_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.error(
                "Timed out loading model from HuggingFace",
                extra={
                    "repository_id": repository_id,
                    "model_type": model_type,
                    "timeout_seconds": self.model_load_timeout_seconds,
                },
            )
            raise HTTPException(
                status_code=504,
                detail=(
                    "Timed out loading model artifact. "
                    "Please retry after the model cache has warmed."
                ),
            ) from exc

        except Exception as e:
            logger.error(f"Failed to load model from HuggingFace: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")

    def _load_model_from_huggingface_sync(self, repository_id: str, model_type: str) -> Any:
        with tempfile.TemporaryDirectory() as tmpdir:
            if model_type == "sklearn":
                model_path = hf_hub_download(
                    repo_id=repository_id,
                    filename="model.pkl",
                    token=self.hf_token,
                    cache_dir=tmpdir,
                )
                with open(model_path, "rb") as f:
                    return pickle.load(f)

            if model_type == "pytorch":
                model_path = hf_hub_download(
                    repo_id=repository_id,
                    filename="pytorch_model.bin",
                    token=self.hf_token,
                    cache_dir=tmpdir,
                )
                import torch

                return torch.load(model_path)

            return snapshot_download(repo_id=repository_id, token=self.hf_token, cache_dir=tmpdir)

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
        entry: ModelRegistryEntry,
        model: Any,
        inputs: dict[str, Any],
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run prediction locally with the loaded model.

        This is for models that are downloaded and run locally.
        """
        if entry.local_predictor is None:
            raise NotImplementedError(f"Local prediction not implemented for model {entry.name}")

        return await asyncio.wait_for(
            asyncio.to_thread(entry.local_predictor, model, inputs, options),
            timeout=self.prediction_timeout_seconds,
        )

    @staticmethod
    def _predict_sales_lead_sync(classifier: Any, features: np.ndarray) -> tuple[Any, Any]:
        prediction = classifier.predict(features)[0]
        probabilities = classifier.predict_proba(features)[0]
        return prediction, probabilities

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

    def _predict_sales_lead_local(
        self,
        model: Any,
        inputs: dict[str, Any],
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Predict using the sales lead local sklearn artifact."""
        del options
        features = self._prepare_sales_lead_features(inputs)

        if isinstance(model, dict):
            classifier = model.get("model")
            if classifier is None:
                raise ValueError("Model not found in loaded data")
        else:
            classifier = model

        _prediction, probabilities = self._predict_sales_lead_sync(classifier, features)
        lead_score = int(probabilities[1] * 100)

        if lead_score >= 70:
            recommendation = "Hot"
        elif lead_score >= 40:
            recommendation = "Warm"
        else:
            recommendation = "Cold"

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

    async def serve_prediction(  # noqa: C901
        self,
        model_id: str,
        inputs: dict[str, Any],
        options: dict[str, Any],
        request_id: str = "",
        caller_context: dict | None = None,
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
        entry = self.get_registry_entry(model_id)
        config = entry.as_public_config()

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
                entry,
                cached_model["model"] if cached_model else None,
                inputs,
                options,
            )

        elif inference_method == "mlflow_pyfunc":
            predictions = await self._serve_mlflow_prediction(
                entry=entry,
                model_id=model_id,
                inputs=inputs,
                request_id=request_id,
                caller_context=caller_context,
            )

        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown inference method: {inference_method}"
            )

        return predictions

    def _get_required_mlflow_component(self, entry: ModelRegistryEntry, field_name: str) -> Any:
        value = getattr(entry, field_name)
        if value is None:
            raise HTTPException(
                status_code=500,
                detail=f"MLflow registry entry for {entry.name} is missing {field_name}",
            )
        return value

    async def _serve_mlflow_prediction(
        self,
        entry: ModelRegistryEntry,
        model_id: str,
        inputs: dict[str, Any],
        request_id: str,
        caller_context: dict | None = None,
    ) -> dict[str, Any]:
        model_uri = self._get_required_mlflow_component(entry, "model_uri")
        input_validator = self._get_required_mlflow_component(entry, "input_validator")
        feature_mapper = self._get_required_mlflow_component(entry, "feature_mapper")
        model_caller = self._get_required_mlflow_component(entry, "model_caller")
        output_normalizer = self._get_required_mlflow_component(entry, "output_normalizer")
        cache_checker = self._get_required_mlflow_component(entry, "cache_checker")

        request_started_at = time.perf_counter()
        trace = Model30LatencyTrace(request_id=request_id, model_uri=model_uri)
        trace_emitted = False
        try:
            with trace.phase("model_cache_lookup"):
                is_cached = cache_checker(model_uri)
            trace.set_path_type(is_cached)

            with trace.phase("request_validation"):
                validated_inputs = input_validator(inputs)
            metadata = getattr(validated_inputs, "metadata", None)
            if metadata is not None:
                trace.run_id = getattr(metadata, "run_id", None)

            with trace.phase("preprocessor_setup"):
                pass

            with trace.phase("feature_transformation"):
                features = feature_mapper(validated_inputs)

            mlflow_timings: dict[str, float] = {}
            inference_started_at = time.perf_counter()
            try:
                raw_model_output = await asyncio.wait_for(
                    asyncio.to_thread(model_caller, model_uri, features, mlflow_timings),
                    timeout=self.prediction_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                trace.outcome = "timeout"
                trace.deadline_boundary_ms = (time.perf_counter() - inference_started_at) * 1000
                trace.record_ms("artifact_load", mlflow_timings.get("artifact_load_ms", 0.0))
                trace.emit(logger)
                trace_emitted = True
                log_model_30_failure(
                    logger,
                    request_id=request_id,
                    model_uri=model_uri,
                    model_version=entry.model_version,
                    phase=Model30FailurePhase.TIMEOUT,
                    path_type=getattr(trace, "path_type", "unknown") or "unknown",
                    exc=exc,
                    duration_ms=(time.perf_counter() - request_started_at) * 1000,
                )
                raise HTTPException(
                    status_code=504,
                    detail={
                        "error": (
                            f"{entry.name} inference timed out before the service deadline. "
                            "Please retry after the model cache has warmed."
                        ),
                        "request_id": request_id,
                        "run_id": trace.run_id,
                    },
                ) from exc
            except Model30LoadInProgressError as exc:
                trace.outcome = "load_in_progress"
                trace.deadline_boundary_ms = (time.perf_counter() - inference_started_at) * 1000
                trace.emit(logger)
                trace_emitted = True
                log_model_30_failure(
                    logger,
                    request_id=request_id,
                    model_uri=model_uri,
                    model_version=entry.model_version,
                    phase=Model30FailurePhase.ARTIFACT_LOAD,
                    path_type=getattr(trace, "path_type", "unknown") or "unknown",
                    exc=exc,
                    duration_ms=(time.perf_counter() - request_started_at) * 1000,
                    level=logging.WARNING,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": (
                            f"{entry.name} cold load is already in progress. "
                            "Please retry shortly."
                        ),
                        "request_id": request_id,
                        "run_id": trace.run_id,
                    },
                ) from exc

            trace.deadline_boundary_ms = (time.perf_counter() - inference_started_at) * 1000
            trace.record_ms("artifact_load", mlflow_timings.get("artifact_load_ms", 0.0))
            trace.record_ms(
                "model_inference",
                mlflow_timings.get("inference_only_ms", trace.deadline_boundary_ms),
            )

            with trace.phase("postprocessing_serialization"):
                predictions = output_normalizer(raw_model_output, validated_inputs)
            trace.outcome = "success"
            trace.emit(logger)
            trace_emitted = True
            return predictions
        except ValidationError as exc:
            trace.outcome = "validation_error"
            if not trace_emitted:
                trace.emit(logger)
            emit_model_serving_validation_422(
                logger,
                request_id=request_id,
                model_id=model_id,
                caller_context=caller_context,
                pydantic_errors=exc.errors(),
            )
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        except HTTPException:
            if not trace_emitted:
                trace.outcome = "http_error"
                trace.emit(logger)
            raise
        except Exception as exc:
            trace.outcome = "error"
            if not trace_emitted:
                trace.emit(logger)
            phase = (
                exc.phase
                if isinstance(exc, Model30InferenceError)
                else Model30FailurePhase.PREDICT_CALL
            )
            log_model_30_failure(
                logger,
                request_id=request_id,
                model_uri=model_uri,
                model_version=entry.model_version,
                phase=phase,
                path_type=getattr(trace, "path_type", "unknown") or "unknown",
                exc=exc,
                duration_ms=(time.perf_counter() - request_started_at) * 1000,
            )
            raise HTTPException(
                status_code=503,
                detail=f"{entry.name} MLflow inference failed: {exc}",
            ) from exc

    async def warm_mlflow_model(self, entry: ModelRegistryEntry) -> dict[str, Any]:
        """Load an MLflow model and run a minimal readiness check."""
        validated_inputs = self._get_required_mlflow_component(entry, "input_validator")(
            {
                "task": {
                    "description": "Readiness check for Technical Task Router",
                    "task_type": "health_check",
                }
            }
        )
        features = self._get_required_mlflow_component(entry, "feature_mapper")(validated_inputs)
        timings: dict[str, float] = {}
        model_uri = self._get_required_mlflow_component(entry, "model_uri")
        raw_model_output = await asyncio.wait_for(
            asyncio.to_thread(
                self._get_required_mlflow_component(entry, "model_caller"),
                model_uri,
                features,
                timings,
            ),
            timeout=self.model_30_readiness_timeout_seconds,
        )
        normalized = self._get_required_mlflow_component(entry, "output_normalizer")(
            raw_model_output,
            validated_inputs,
        )
        return {
            "selected_model": normalized["selected_model"],
            "artifact_load_ms": round(timings.get("artifact_load_ms", 0.0), 2),
            "inference_only_ms": round(timings.get("inference_only_ms", 0.0), 2),
        }


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
    if config["storage_type"] == "mlflow":
        response["model_type"] = config["model_type"]
        response["storage_type"] = config["storage_type"]
        response["model_uri"] = config["model_uri"]
    for _key in ("model_version", "schema", "description"):
        if (_val := config.get(_key)) is not None:
            response[_key] = _val
    return response


@router.post("/{model_id}/predict")
async def predict(
    model_id: str,
    payload: PredictionRequest,
    http_request: Request,
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
        payload: Prediction request containing inputs and options
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

    request_id = get_or_generate_request_id(http_request)

    try:
        started_at = time.perf_counter()
        model_config = serving_service.get_model_config(model_id)
        inference_method = payload.options.get("inference_method", model_config["inference_method"])
        inference_log_id = contributor_logger.new_inference_log_id()
        request_id = str(inference_log_id)
        caller_context = {
            "caller_fingerprint": {
                "user_id": user_id,
                "api_key_id": str(api_key_id) if api_key_id else None,
                "user_agent": (http_request.headers.get("user-agent") or "")[:200] or None,
                "client_ip_class": classify_client_ip(
                    http_request.client.host if http_request.client else None
                ),
            }
        }
        http_request.state.request_id = request_id

        # Run prediction
        predictions = await serving_service.serve_prediction(
            model_id=model_id,
            inputs=payload.inputs,
            options=payload.options,
            request_id=request_id,
            caller_context=caller_context,
        )
        inference_latency_ms = int((time.perf_counter() - started_at) * 1000)
        model_version = str(
            payload.options.get("model_version", model_config.get("model_version", "unknown"))
        )

        # Build response
        metadata = {
            "api_version": "1.0",
            "inference_method": inference_method,
            "user_id": user_id,
            "api_key_id": api_key_id,
        }
        if model_config["storage_type"] == "mlflow":
            metadata.update(
                {
                    "model_uri": model_config["model_uri"],
                    "model_version": model_config["model_version"],
                    "schema": model_config["schema"],
                    "request_id": request_id,
                }
            )
        response = PredictionResponse(
            model_id=model_id,
            predictions=predictions,
            metadata=metadata,
            timestamp=datetime.utcnow().isoformat(),
            inference_log_id=request_id,
        )

        # Persist inference log in the background so hot-path latency remains low.
        background_tasks.add_task(
            contributor_logger.log_inference,
            api_token_id=str(api_key_id or "unknown"),
            model_name=model_config.get("name", model_id),
            model_version=model_version,
            input_payload=payload.inputs,
            output_payload=predictions,
            trace_metadata={
                "latency_ms": inference_latency_ms,
                "inference_method": inference_method,
                "model_id": model_id,
                "request_id": request_id,
            },
            inference_log_id=inference_log_id,
        )

        return response

    except HTTPException as exc:
        if exc.status_code == 422:
            return JSONResponse(
                status_code=422,
                content={"detail": exc.detail},
                headers={"X-Request-ID": request_id},
            )
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
    warmup: bool = Query(
        default=False,
        description="For model 30, load the MLflow artifact and run a minimal prediction.",
    ),
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
        entry = serving_service.get_registry_entry(model_id)
        config = entry.as_public_config()

        # Check if model is cached
        cache_key = f"model_{model_id}"
        is_cached = cache_key in serving_service.model_cache
        inference_ready = True
        readiness: dict[str, Any] | None = None
        mlflow_sdk: dict[str, Any] | None = None
        if config["storage_type"] == "mlflow":
            cache_checker = serving_service._get_required_mlflow_component(entry, "cache_checker")
            model_uri = serving_service._get_required_mlflow_component(entry, "model_uri")
            is_cached = cache_checker(model_uri)
            inference_ready = is_cached
            readiness = {
                "checked": False,
                "model_uri": model_uri,
                "status": "cached" if is_cached else "not_cached",
            }
            if warmup:
                readiness["checked"] = True
                try:
                    readiness.update(await serving_service.warm_mlflow_model(entry))
                    is_cached = cache_checker(model_uri)
                    inference_ready = is_cached
                    readiness["status"] = "ready" if is_cached else "not_cached"
                except Model30LoadInProgressError:
                    readiness["status"] = "warming"
                    readiness["error"] = f"{entry.name} cold load is already in progress"
                except asyncio.TimeoutError:
                    readiness["status"] = "timeout"
                    readiness["error"] = (
                        f"{entry.name} readiness check timed out before the service deadline"
                    )
                except Exception as exc:  # noqa: BLE001 - health should report readiness errors
                    readiness["status"] = "error"
                    readiness["error"] = str(exc)

            sdk_result = (await check_mlflow_registry_sdk()).to_dict()
            mlflow_sdk = {
                "reachable": sdk_result["status"] == "ok",
                "tracking_uri": sdk_result["tracking_uri"],
                "latency_ms": sdk_result["latency_ms"],
                "sample_model": sdk_result.get("sample_model"),
            }
            if sdk_result["status"] != "ok":
                mlflow_sdk["error_type"] = sdk_result.get("error_type")
                mlflow_sdk["error"] = sdk_result.get("error")

        response = {
            "model_id": model_id,
            "status": "healthy",
            "is_cached": is_cached,
            "storage_type": config["storage_type"],
            "inference_ready": inference_ready,
        }
        if readiness is not None:
            response["readiness"] = readiness
        if mlflow_sdk is not None:
            response["mlflow_sdk"] = mlflow_sdk
        return response

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
