"""Concrete model-serving registry entries."""

from src.api.schemas import MODEL_27_INPUT_FIELDS

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
from .sales_lead_scoring_adapter import (
    MODEL_27_SCHEMA,
    MODEL_27_VERSION,
    call_mlflow_model_27,
    get_model_27_uri,
    is_model_27_cached,
    normalize_model_27_output,
    sales_lead_scoring_inputs_to_features,
    validate_sales_lead_scoring_inputs,
)

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
    "27": ModelRegistryEntry(
        name="Sales Lead Scoring",
        storage_type="mlflow",
        model_type="sales_lead_scoring",
        is_private=False,
        inference_method="mlflow_pyfunc",
        model_uri=get_model_27_uri(),
        model_version=MODEL_27_VERSION,
        schema=MODEL_27_SCHEMA,
        description="MLflow-backed sales lead scoring model.",
        max_batch_size=1,
        supported_inference_methods=("mlflow_pyfunc",),
        registered_model_name="Sales Lead Scoring",
        input_validator=validate_sales_lead_scoring_inputs,
        feature_mapper=sales_lead_scoring_inputs_to_features,
        output_normalizer=normalize_model_27_output,
        model_caller=call_mlflow_model_27,
        cache_checker=is_model_27_cached,
        input_fields=MODEL_27_INPUT_FIELDS,
        readiness_inputs={
            "Customer ID": "CG-12520",
            "first_industry": "Technology",
            "first_segment": "Enterprise",
            "first_region": "North America",
            "first_subregion": "US East",
            "first_country": "United States",
            "first_product": "Analytics Suite",
            "first_sales": 12500.0,
            "first_quantity": 25.0,
            "first_discount": 0.1,
            "total_profit": 3200.0,
        },
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
        readiness_inputs={
            "task": {
                "description": "Readiness check for Technical Task Router",
                "task_type": "health_check",
            }
        },
    ),
}
