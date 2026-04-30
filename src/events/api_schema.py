"""Utilities for deriving API schema from MLflow model signatures."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MLFLOW_TYPE_MAP: dict[str, dict[str, str]] = {
    "string": {"type": "string"},
    "integer": {"type": "integer"},
    "long": {"type": "integer"},
    "float": {"type": "number"},
    "double": {"type": "number"},
    "boolean": {"type": "boolean"},
    "binary": {"type": "string", "format": "byte"},
    "datetime": {"type": "string", "format": "date-time"},
}


def _mlflow_type_to_jsonschema(mlflow_type: Any) -> Optional[dict[str, Any]]:
    """Map a single MLflow DataType to a JSON Schema type fragment."""
    # DataType.name gives the bare name (e.g. "string"); str() gives "DataType.string"
    type_name = getattr(mlflow_type, "name", str(mlflow_type)).lower()
    return _MLFLOW_TYPE_MAP.get(type_name)


def _schema_to_jsonschema(schema: Any) -> Optional[dict[str, Any]]:
    """Convert an MLflow column-based Schema to a JSON Schema object.

    Returns None for tensor-based schemas or on any error.
    """
    try:
        from mlflow.types import ColSpec

        inputs = schema.inputs
    except Exception:
        return None

    if not inputs:
        return None

    # Only support column-based schemas (ColSpec items have a .name attribute).
    # Tensor specs don't have column names — fall back to None.
    if not isinstance(inputs[0], ColSpec):
        return None

    properties: dict[str, Any] = {}
    required: list = []

    for col in inputs:
        if not isinstance(col, ColSpec) or col.name is None:
            return None  # Inconsistent spec; bail entirely
        type_schema = _mlflow_type_to_jsonschema(col.type)
        if type_schema is None:
            logger.debug("Unknown MLflow type %s for column %s — skipping", col.type, col.name)
            continue
        properties[col.name] = type_schema
        # ColSpec uses required=True (default) to indicate the field is required
        if getattr(col, "required", True):
            required.append(col.name)

    if not properties:
        return None

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def derive_api_schema(signature: Any) -> Optional[dict[str, Any]]:
    """Derive an api_schema dict from an MLflow ModelSignature.

    Returns {"inputSchema": ..., "outputSchema": ...} or None when the
    signature is absent, tensor-based, or conversion fails.
    """
    if signature is None:
        return None

    try:
        input_schema = _schema_to_jsonschema(signature.inputs) if signature.inputs else None
        output_schema = _schema_to_jsonschema(signature.outputs) if signature.outputs else None
    except Exception as exc:
        logger.debug("Failed to convert MLflow signature: %s", exc)
        return None

    if input_schema is None and output_schema is None:
        return None

    result: dict[str, Any] = {}
    if input_schema is not None:
        result["inputSchema"] = input_schema
    if output_schema is not None:
        result["outputSchema"] = output_schema

    return result or None


def derive_api_schema_from_uri(model_uri: Optional[str]) -> Optional[dict[str, Any]]:
    """Fetch MLflow model info and derive api_schema from its signature.

    Never raises — any failure is logged as a warning and None is returned so
    callers can still send the webhook without api_schema.

    MLflow auth is handled by the caller via MLFLOW_TRACKING_TOKEN / tracking URI
    configuration before this function is invoked.
    """
    if not model_uri:
        return None

    try:
        import mlflow.models

        info = mlflow.models.get_model_info(model_uri)
        return derive_api_schema(info.signature)
    except Exception as exc:
        logger.warning("Could not derive api_schema from %s: %s", model_uri, exc)
        return None
