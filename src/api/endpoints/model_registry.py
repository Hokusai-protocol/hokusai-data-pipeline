"""Typed model-serving registry contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

InputValidator = Callable[[dict[str, Any]], Any]
FeatureMapper = Callable[[Any], Any]
OutputNormalizer = Callable[[Any, Any], dict[str, Any]]
ModelCaller = Callable[[str, object, dict[str, float] | None], Any]
CacheChecker = Callable[[str], bool]
LocalPredictor = Callable[[Any, dict[str, Any], dict[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True)
class ModelRegistryEntry:
    """Immutable model-serving registry entry."""

    name: str
    storage_type: Literal["huggingface_private", "huggingface", "mlflow"]
    model_type: str
    is_private: bool
    inference_method: str
    max_batch_size: int
    supported_inference_methods: tuple[str, ...] = ()
    description: str | None = None
    model_uri: str | None = None
    model_version: str | None = None
    schema: str | None = None
    registered_model_name: str | None = None
    input_validator: InputValidator | None = None
    feature_mapper: FeatureMapper | None = None
    output_normalizer: OutputNormalizer | None = None
    model_caller: ModelCaller | None = None
    cache_checker: CacheChecker | None = None
    input_fields: tuple[str, ...] = ()
    readiness_inputs: dict[str, Any] | None = None
    repository_id: str | None = None
    cache_duration: int | None = None
    local_predictor: LocalPredictor | None = None

    def as_public_config(self: ModelRegistryEntry) -> dict[str, Any]:
        """Return the JSON-safe config shape exposed by API endpoints."""
        config: dict[str, Any] = {
            "name": self.name,
            "storage_type": self.storage_type,
            "model_type": self.model_type,
            "is_private": self.is_private,
            "inference_method": self.inference_method,
            "max_batch_size": self.max_batch_size,
            "supported_inference_methods": list(self.supported_inference_methods),
        }
        for key in (
            "description",
            "model_uri",
            "model_version",
            "schema",
            "registered_model_name",
            "input_fields",
            "repository_id",
            "cache_duration",
        ):
            value = getattr(self, key)
            if value is not None:
                config[key] = value
        return config
