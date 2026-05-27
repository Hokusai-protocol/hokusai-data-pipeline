"""Concrete model-serving registry entries."""

from .model_30_adapter import (
    MODEL_30_SCHEMA,
    MODEL_30_VERSION,
    call_mlflow_model_30,
    get_model_30_uri,
    is_model_30_cached,
    model_30_inputs_to_features,
    normalize_model_30_output,
    validate_nested_model_30_inputs,
)
from .model_registry import ModelRegistryEntry

MODEL_CONFIGS: dict[str, ModelRegistryEntry] = {
    "21": ModelRegistryEntry(
        name="Sales Lead Scoring Model",
        repository_id="timogilvie/hokusai-model-21-sales-lead-scorer",
        storage_type="huggingface_private",
        model_type="sklearn",
        is_private=True,
        inference_method="local",
        cache_duration=3600,
        max_batch_size=100,
        supported_inference_methods=("api", "local"),
    ),
    "30": ModelRegistryEntry(
        name="Technical Task Router",
        storage_type="mlflow",
        model_type="technical_task_router",
        is_private=False,
        inference_method="mlflow_pyfunc",
        model_uri=get_model_30_uri(),
        model_version=MODEL_30_VERSION,
        schema=MODEL_30_SCHEMA,
        description="MLflow-backed router for nested technical task inputs.",
        max_batch_size=1,
        supported_inference_methods=("mlflow_pyfunc",),
        input_validator=validate_nested_model_30_inputs,
        feature_mapper=model_30_inputs_to_features,
        output_normalizer=normalize_model_30_output,
        model_caller=call_mlflow_model_30,
        cache_checker=is_model_30_cached,
    ),
}
