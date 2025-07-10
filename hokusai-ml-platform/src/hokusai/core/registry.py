"""Model Registry for centralized model management."""
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import mlflow
from mlflow.tracking import MlflowClient

from .models import HokusaiModel

# Required tags for Hokusai tokenized models
REQUIRED_HOKUSAI_TAGS = {"hokusai_token_id": str, "benchmark_metric": str, "benchmark_value": str}


class RegistryException(Exception):
    """Exception raised by model registry operations."""

    pass


@dataclass
class ModelRegistryEntry:
    """Entry in the model registry."""

    model_id: str
    model_type: str
    version: str
    is_baseline: bool = False
    baseline_id: Optional[str] = None
    metrics: Dict[str, float] = None
    delta_metrics: Optional[Dict[str, float]] = None
    contributor_address: Optional[str] = None
    timestamp: datetime = None
    mlflow_version: Optional[str] = None
    tags: Dict[str, str] = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
        if self.tags is None:
            self.tags = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class ModelLineage:
    """Model lineage information."""

    model_id: str
    entries: List[Dict[str, Any]]
    total_improvement: float = 0.0


class ModelRegistry:
    """Central registry for all models with MLflow backend."""

    def __init__(self, tracking_uri: str = "http://localhost:5000") -> None:
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri)

    def register_baseline(
        self, model: HokusaiModel, model_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ModelRegistryEntry:
        """Register a baseline model."""
        try:
            # Create or get registered model
            try:
                self.client.create_registered_model(
                    name=model_type, description=f"Hokusai model type: {model_type}"
                )
            except Exception:
                # Model already exists
                pass

            # Create model version
            model_version = self.client.create_model_version(
                name=model_type,
                source="mlflow-artifacts:/models",
                description=f"Baseline model {model.model_id}",
            )

            # Create registry entry
            entry = ModelRegistryEntry(
                model_id=model.model_id,
                model_type=model_type,
                version=model.version,
                is_baseline=True,
                metrics=model.get_metrics(),
                mlflow_version=model_version.version,
            )

            # Set tags in MLflow
            tags = {
                "model_id": model.model_id,
                "model_type": model_type,
                "version": model.version,
                "is_baseline": "true",
                "metrics": json.dumps(entry.metrics),
                "timestamp": entry.timestamp.isoformat(),
            }

            if metadata:
                tags["metadata"] = json.dumps(metadata)

            for key, value in tags.items():
                self.client.set_model_version_tag(
                    name=model_type, version=model_version.version, key=key, value=value
                )

            return entry

        except Exception as e:
            raise RegistryException(f"Failed to register baseline model: {str(e)}")

    def register_improved_model(
        self,
        model: HokusaiModel,
        baseline_id: str,
        delta_metrics: Dict[str, float],
        contributor: str,
    ) -> ModelRegistryEntry:
        """Register an improved model with baseline reference."""
        try:
            # Verify baseline exists
            baseline = self.get_model_by_id(baseline_id)
            if not baseline:
                raise RegistryException(f"Baseline model {baseline_id} not found")

            # Create model version
            model_version = self.client.create_model_version(
                name=baseline.model_type,
                source="mlflow-artifacts:/models",
                description=f"Improved model {model.model_id} based on {baseline_id}",
            )

            # Create registry entry
            entry = ModelRegistryEntry(
                model_id=model.model_id,
                model_type=baseline.model_type,
                version=model.version,
                is_baseline=False,
                baseline_id=baseline_id,
                metrics=model.get_metrics(),
                delta_metrics=delta_metrics,
                contributor_address=contributor,
                mlflow_version=model_version.version,
            )

            # Set tags
            tags = {
                "model_id": model.model_id,
                "model_type": baseline.model_type,
                "version": model.version,
                "is_baseline": "false",
                "baseline_id": baseline_id,
                "metrics": json.dumps(entry.metrics),
                "delta_metrics": json.dumps(delta_metrics),
                "contributor_address": contributor,
                "timestamp": entry.timestamp.isoformat(),
            }

            for key, value in tags.items():
                self.client.set_model_version_tag(
                    name=baseline.model_type, version=model_version.version, key=key, value=value
                )

            return entry

        except Exception as e:
            raise RegistryException(f"Failed to register improved model: {str(e)}")

    def get_model_by_id(self, model_id: str) -> Optional[ModelRegistryEntry]:
        """Get model by its ID."""
        try:
            # Search across all registered models
            for rm in self.client.search_registered_models():
                versions = self.client.search_model_versions(f"name='{rm.name}'")
                for version in versions:
                    if version.tags.get("model_id") == model_id:
                        return self._version_to_entry(version)

            raise RegistryException(f"Model not found: {model_id}")

        except Exception as e:
            if "Model not found" in str(e):
                raise
            raise RegistryException(f"Failed to get model: {str(e)}")

    def get_model_lineage(self, model_id: str) -> ModelLineage:
        """Get complete lineage of a model."""
        try:
            lineage_entries = []
            total_improvement = 0.0

            # Start with the requested model
            current_model = self.get_model_by_id(model_id)
            if not current_model:
                raise RegistryException(f"Model {model_id} not found")

            # Trace back through baselines
            while current_model:
                entry_dict = {
                    "model_id": current_model.model_id,
                    "baseline_id": current_model.baseline_id,
                    "version": current_model.version,
                    "metrics": current_model.metrics,
                    "timestamp": current_model.timestamp.isoformat(),
                }

                if current_model.delta_metrics:
                    entry_dict["delta_metrics"] = current_model.delta_metrics
                    # Sum up improvements
                    for metric, delta in current_model.delta_metrics.items():
                        if "improvement" in metric:
                            total_improvement += delta

                if current_model.contributor_address:
                    entry_dict["contributor_address"] = current_model.contributor_address

                lineage_entries.insert(0, entry_dict)  # Insert at beginning to maintain order

                # Move to baseline
                if current_model.baseline_id:
                    current_model = self.get_model_by_id(current_model.baseline_id)
                else:
                    break

            return ModelLineage(
                model_id=model_id, entries=lineage_entries, total_improvement=total_improvement
            )

        except Exception as e:
            raise RegistryException(f"Failed to get model lineage: {str(e)}")

    def list_models_by_type(self, model_type: str) -> List[ModelRegistryEntry]:
        """List all models of a specific type."""
        try:
            entries = []
            versions = self.client.search_model_versions(f"name='{model_type}'")

            for version in versions:
                entry = self._version_to_entry(version)
                if entry:
                    entries.append(entry)

            return entries

        except Exception as e:
            raise RegistryException(f"Failed to list models: {str(e)}")

    def get_latest_model(self, model_type: str) -> Optional[ModelRegistryEntry]:
        """Get the latest model version for a type."""
        try:
            latest_versions = self.client.get_latest_versions(model_type)
            if not latest_versions:
                return None

            # Get the production version if available, otherwise the latest
            for version in latest_versions:
                if version.current_stage == "Production":
                    return self._version_to_entry(version)

            # Return the latest version
            return self._version_to_entry(latest_versions[0])

        except Exception as e:
            raise RegistryException(f"Failed to get latest model: {str(e)}")

    def rollback_model(self, model_type: str, target_model_id: str) -> bool:
        """Rollback to a specific model version."""
        try:
            # Find the target model
            target = self.get_model_by_id(target_model_id)
            if not target or target.model_type != model_type:
                return False

            # Transition current production to archived
            current = self.get_latest_model(model_type)
            if current and current.mlflow_version:
                self.client.transition_model_version_stage(
                    name=model_type, version=current.mlflow_version, stage="Archived"
                )

            # Transition target to production
            if target.mlflow_version:
                self.client.transition_model_version_stage(
                    name=model_type, version=target.mlflow_version, stage="Production"
                )

            return True

        except Exception as e:
            raise RegistryException(f"Failed to rollback model: {str(e)}")

    def register_tokenized_model(
        self,
        model_uri: str,
        model_name: str,
        token_id: str,
        metric_name: str,
        baseline_value: float,
        additional_tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Register a model with Hokusai token metadata.

        Args:
            model_uri: MLflow model URI (e.g., "runs:/abc123/model")
            model_name: Name for the registered model
            token_id: Hokusai token ID (e.g., "msg-ai")
            metric_name: Performance metric name (e.g., "reply_rate")
            baseline_value: Baseline performance value
            additional_tags: Optional additional tags

        Returns:
            Dict with registration details

        Raises:
            ValueError: Invalid parameters
            RegistryException: Registration failed

        """
        # Validate parameters
        if not all([model_uri, model_name, token_id, metric_name]):
            raise ValueError("All parameters are required")

        if not isinstance(baseline_value, (int, float)):
            raise ValueError("baseline_value must be numeric")

        # Validate token ID format
        self.validate_token_id(token_id)

        try:
            # Create or get registered model
            try:
                self.client.create_registered_model(
                    name=model_name, description=f"Hokusai tokenized model: {token_id}"
                )
            except Exception:
                # Model already exists
                pass

            # Create model version
            model_version = self.client.create_model_version(
                name=model_name,
                source=model_uri,
                description=f"Token: {token_id}, Metric: {metric_name}",
            )

            # Set required Hokusai tags
            tags = {
                "hokusai_token_id": token_id,
                "benchmark_metric": metric_name,
                "benchmark_value": str(baseline_value),
            }

            # Add any additional tags
            if additional_tags:
                tags.update(additional_tags)

            # Set all tags
            for key, value in tags.items():
                self.client.set_model_version_tag(
                    name=model_name, version=model_version.version, key=key, value=str(value)
                )

            return {
                "model_name": model_name,
                "version": model_version.version,
                "token_id": token_id,
                "metric_name": metric_name,
                "baseline_value": baseline_value,
                "tags": tags,
            }

        except Exception as e:
            raise RegistryException(f"Failed to register tokenized model: {str(e)}")

    def validate_hokusai_tags(self, tags: Dict[str, str]) -> None:
        """Validate required Hokusai tags.

        Args:
            tags: Dictionary of tags to validate

        Raises:
            RegistryException: Invalid or missing tags

        """
        for tag_name, tag_type in REQUIRED_HOKUSAI_TAGS.items():
            if tag_name not in tags:
                raise RegistryException(f"Missing required tag: {tag_name}")

            if not isinstance(tags[tag_name], tag_type):
                raise RegistryException(f"Tag {tag_name} must be a {tag_type.__name__}")

            # Special validation for benchmark_value
            if tag_name == "benchmark_value":
                try:
                    float(tags[tag_name])
                except ValueError:
                    raise RegistryException("benchmark_value must be convertible to float")

    def get_tokenized_model(self, model_name: str, version: str) -> Dict[str, Any]:
        """Get a tokenized model by name and version.

        Args:
            model_name: Registered model name
            version: Model version

        Returns:
            Dict with model details including token metadata

        """
        try:
            model_version = self.client.get_model_version(name=model_name, version=version)

            tags = model_version.tags
            self.validate_hokusai_tags(tags)

            return {
                "model_name": model_name,
                "version": version,
                "token_id": tags["hokusai_token_id"],
                "metric_name": tags["benchmark_metric"],
                "baseline_value": float(tags["benchmark_value"]),
                "tags": tags,
            }

        except Exception as e:
            raise RegistryException(f"Failed to get tokenized model: {str(e)}")

    def list_models_by_token(self, token_id: str) -> List[Dict[str, Any]]:
        """List all models associated with a token.

        Args:
            token_id: Hokusai token ID

        Returns:
            List of model details

        """
        try:
            models = []

            # Search across all registered models
            for rm in self.client.search_registered_models():
                versions = self.client.search_model_versions(f"name='{rm.name}'")

                for version in versions:
                    if version.tags.get("hokusai_token_id") == token_id:
                        try:
                            model_data = self.get_tokenized_model(rm.name, version.version)
                            models.append(model_data)
                        except RegistryException:
                            # Skip models without valid Hokusai tags
                            continue

            return models

        except Exception as e:
            raise RegistryException(f"Failed to list models by token: {str(e)}")

    def update_model_tags(self, model_name: str, version: str, tags: Dict[str, str]) -> None:
        """Update tags for a model version.

        Args:
            model_name: Registered model name
            version: Model version
            tags: Tags to update

        """
        try:
            for key, value in tags.items():
                self.client.set_model_version_tag(
                    name=model_name, version=version, key=key, value=str(value)
                )
        except Exception as e:
            raise RegistryException(f"Failed to update model tags: {str(e)}")

    def validate_token_id(self, token_id: str) -> None:
        """Validate token ID format.

        Args:
            token_id: Token ID to validate

        Raises:
            ValueError: Invalid token ID format

        """
        import re

        if not token_id:
            raise ValueError("Invalid token ID: cannot be empty")

        if len(token_id) > 64:
            raise ValueError("Invalid token ID: too long (max 64 chars)")

        # Allow lowercase letters, numbers, and hyphens
        if not re.match(r"^[a-z0-9-]+$", token_id):
            raise ValueError(
                "Invalid token ID: must contain only lowercase letters, numbers, and hyphens"
            )

        if token_id.startswith("-") or token_id.endswith("-"):
            raise ValueError("Invalid token ID: cannot start or end with hyphen")

    def delete_model_version(self, model_id: str) -> bool:
        """Delete a specific model version."""
        try:
            model = self.get_model_by_id(model_id)
            if not model or not model.mlflow_version:
                return False

            self.client.delete_model_version(name=model.model_type, version=model.mlflow_version)

            return True

        except Exception as e:
            raise RegistryException(f"Failed to delete model: {str(e)}")

    def _version_to_entry(self, version) -> Optional[ModelRegistryEntry]:
        """Convert MLflow model version to registry entry."""
        try:
            tags = version.tags

            # Parse metrics
            metrics = {}
            if "metrics" in tags:
                metrics = json.loads(tags["metrics"])

            # Parse delta metrics
            delta_metrics = None
            if "delta_metrics" in tags:
                delta_metrics = json.loads(tags["delta_metrics"])

            # Parse timestamp
            timestamp = datetime.utcnow()
            if "timestamp" in tags:
                timestamp = datetime.fromisoformat(tags["timestamp"])

            return ModelRegistryEntry(
                model_id=tags.get("model_id", ""),
                model_type=tags.get("model_type", version.name),
                version=tags.get("version", ""),
                is_baseline=tags.get("is_baseline", "false") == "true",
                baseline_id=tags.get("baseline_id"),
                metrics=metrics,
                delta_metrics=delta_metrics,
                contributor_address=tags.get("contributor_address"),
                timestamp=timestamp,
                mlflow_version=version.version,
                tags=tags,
            )

        except Exception:
            return None

    def _fetch_lineage_data(self, model_id: str) -> List[Dict[str, Any]]:
        """Fetch lineage data (helper method for testing)."""
        # This is a placeholder for the actual implementation
        # In real implementation, this would query the database
        lineage = self.get_model_lineage(model_id)
        return lineage.entries
