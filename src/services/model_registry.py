"""Hokusai Model Registry Service for centralized model management."""

import logging
import re
from datetime import datetime
from typing import Any

import mlflow
import mlflow.pyfunc

logger = logging.getLogger(__name__)


class HokusaiModelRegistry:
    """Centralized model registry for all Hokusai projects.

    This service provides:
    - Unified model registration for baseline and improved models
    - Model lineage tracking across improvements
    - Contributor attribution
    - Cross-project model sharing
    """

    VALID_MODEL_TYPES = ["lead_scoring", "classification", "regression", "ranking"]

    def __init__(self, tracking_uri: str = "http://mlflow.hokusai-development.local:5000") -> None:
        """Initialize the model registry with MLFlow tracking.

        Args:
        ----
            tracking_uri: MLFlow tracking server URI

        """
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        logger.info(f"Initialized HokusaiModelRegistry with tracking URI: {tracking_uri}")

    def register_baseline(
        self, model: Any, model_type: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Register a baseline model for future comparisons.

        Args:
        ----
            model: The model object to register
            model_type: Type of model (lead_scoring, classification, etc.)
            metadata: Additional metadata about the model

        Returns:
        -------
            Dictionary containing model ID, version, and registration details

        """
        if model is None:
            raise ValueError("Model cannot be None")

        if model_type not in self.VALID_MODEL_TYPES:
            raise ValueError(
                f"Invalid model type: {model_type}. Must be one of {self.VALID_MODEL_TYPES}"
            )

        model_name = f"hokusai_{model_type}_baseline"

        try:
            with mlflow.start_run() as run:
                # Log model metadata
                mlflow.log_params(
                    {
                        "model_type": model_type,
                        "is_baseline": True,
                        "registration_time": datetime.utcnow().isoformat(),
                    }
                )

                # Log additional metadata
                for key, value in metadata.items():
                    mlflow.log_param(f"metadata_{key}", value)

                # Log the model
                mlflow.pyfunc.log_model(
                    artifact_path="model", python_model=model, registered_model_name=model_name
                )

                # Register the model version
                model_version = mlflow.register_model(f"runs:/{run.info.run_id}/model", model_name)

                result = {
                    "model_id": f"{model_version.name}/{model_version.version}",
                    "model_name": model_version.name,
                    "version": model_version.version,
                    "model_type": model_type,
                    "is_baseline": True,
                    "run_id": run.info.run_id,
                    "registration_timestamp": datetime.utcnow().isoformat(),
                }

                logger.info(f"Successfully registered baseline model: {result['model_id']}")
                return result

        except Exception as e:
            logger.error(f"Failed to register baseline model: {str(e)}")
            raise

    def register_improved_model(
        self, model: Any, baseline_id: str, delta_metrics: dict[str, float], contributor: str
    ) -> dict[str, Any]:
        """Register an improved model with performance delta.

        Args:
        ----
            model: The improved model object
            baseline_id: ID of the baseline model this improves upon
            delta_metrics: Performance improvements over baseline
            contributor: Ethereum address of the contributor

        Returns:
        -------
            Dictionary containing model ID, version, and improvement details

        """
        if not self._validate_eth_address(contributor):
            raise ValueError(f"Invalid Ethereum address: {contributor}")

        # Extract model name from baseline ID
        baseline_name = baseline_id.split("/")[0]
        improved_name = baseline_name.replace("_baseline", "_improved")

        try:
            with mlflow.start_run() as run:
                # Log improvement metrics
                mlflow.log_metrics(delta_metrics)

                # Log model parameters
                mlflow.log_params(
                    {
                        "baseline_model_id": baseline_id,
                        "contributor_address": contributor,
                        "improvement_count": len(delta_metrics),
                        "registration_time": datetime.utcnow().isoformat(),
                    }
                )

                # Log the improved model
                mlflow.pyfunc.log_model(
                    artifact_path="model", python_model=model, registered_model_name=improved_name
                )

                # Register the model version with tags
                model_version = mlflow.register_model(
                    f"runs:/{run.info.run_id}/model", improved_name
                )

                # Set version tags
                client = mlflow.tracking.MlflowClient()
                client.set_model_version_tag(
                    improved_name, model_version.version, "baseline_model_id", baseline_id
                )
                client.set_model_version_tag(
                    improved_name, model_version.version, "contributor", contributor
                )

                result = {
                    "model_id": f"{model_version.name}/{model_version.version}",
                    "model_name": model_version.name,
                    "version": model_version.version,
                    "baseline_id": baseline_id,
                    "contributor": contributor,
                    "delta_metrics": delta_metrics,
                    "run_id": run.info.run_id,
                    "registration_timestamp": datetime.utcnow().isoformat(),
                }

                logger.info(f"Successfully registered improved model: {result['model_id']}")
                return result

        except Exception as e:
            logger.error(f"Failed to register improved model: {str(e)}")
            raise

    def get_model_lineage(self, model_id: str) -> list[dict[str, Any]]:
        """Track model improvements over time.

        Args:
        ----
            model_id: The model ID to get lineage for

        Returns:
        -------
            List of model versions with their improvement history

        """
        client = mlflow.tracking.MlflowClient()

        try:
            # Search for all versions of the model
            versions = client.search_model_versions(f"name='{model_id}'")

            if not versions:
                raise ValueError(f"Model {model_id} not found")

            lineage = []

            for version in sorted(versions, key=lambda x: int(x.version)):
                version_info = {
                    "version": version.version,
                    "run_id": version.run_id,
                    "created_at": version.creation_timestamp,
                    "is_baseline": False,
                    "metrics": {},
                }

                # Get run details
                run = client.get_run(version.run_id)

                # Check if this is a baseline
                if run.data.params.get("is_baseline") == "True":
                    version_info["is_baseline"] = True
                else:
                    # Get contributor and baseline info
                    version_info["contributor"] = run.data.params.get("contributor_address")
                    version_info["baseline_id"] = run.data.params.get("baseline_model_id")

                # Get metrics
                version_info["metrics"] = dict(run.data.metrics)

                lineage.append(version_info)

            # Calculate cumulative improvements
            if len(lineage) > 1:
                cumulative = self._calculate_cumulative_metrics(lineage)
                lineage[-1]["cumulative_improvement"] = cumulative

            return lineage

        except Exception as e:
            logger.error(f"Failed to get model lineage: {str(e)}")
            raise

    def _validate_eth_address(self, address: str) -> bool:
        """Validate Ethereum address format.

        Args:
        ----
            address: Ethereum address to validate

        Returns:
        -------
            True if valid, False otherwise

        """
        if not address:
            return False

        # Check if it matches Ethereum address pattern
        pattern = r"^0x[a-fA-F0-9]{40}$"
        return bool(re.match(pattern, address))

    def _calculate_cumulative_metrics(self, versions: list[dict[str, Any]]) -> dict[str, float]:
        """Calculate cumulative improvements across versions.

        Args:
        ----
            versions: List of model versions with metrics

        Returns:
        -------
            Dictionary of cumulative metric improvements

        """
        cumulative = {}

        # Find baseline metrics
        baseline_metrics = None
        for version in versions:
            if version["is_baseline"]:
                baseline_metrics = version["metrics"]
                break

        if not baseline_metrics:
            return cumulative

        # Calculate total improvements
        for metric_name in baseline_metrics:
            if metric_name.endswith("_improvement"):
                continue

            total_improvement = 0
            for version in versions[1:]:  # Skip baseline
                if f"{metric_name}_improvement" in version["metrics"]:
                    total_improvement += version["metrics"][f"{metric_name}_improvement"]

            if total_improvement > 0:
                cumulative[metric_name] = total_improvement

        cumulative["total_improvements"] = len([v for v in versions if not v["is_baseline"]])

        return cumulative

    def get_contributor_models(self, contributor_address: str) -> list[dict[str, Any]]:
        """Get all models contributed by a specific address.

        Args:
        ----
            contributor_address: Ethereum address of contributor

        Returns:
        -------
            List of models with contribution details

        """
        try:
            import mlflow

            # Search for runs with this contributor
            runs = mlflow.search_runs(
                filter_string=f"params.contributor_address = '{contributor_address}'",
                order_by=["start_time DESC"],
            )

            models = []
            for _, run in runs.iterrows():
                # Parse model history if it exists
                model_history_str = run.get("tags.mlflow.log-model.history", "[]")
                try:
                    import json

                    model_history = (
                        json.loads(model_history_str)
                        if isinstance(model_history_str, str)
                        else model_history_str
                    )
                    model_name = (
                        model_history[0].get("artifact_path", "unknown")
                        if model_history
                        else "unknown"
                    )
                except (json.JSONDecodeError, IndexError):
                    model_name = "unknown"

                model_info = {
                    "run_id": run["run_id"],
                    "model_name": model_name,
                    "contributor_address": contributor_address,
                    "baseline_id": run.get("params.baseline_model_id"),
                    "metrics": {
                        k.replace("metrics.", ""): v
                        for k, v in run.items()
                        if k.startswith("metrics.")
                    },
                    "created_at": run["start_time"],
                }
                models.append(model_info)

            return models

        except Exception as e:
            logger.error(f"Failed to get contributor models: {str(e)}")
            return []

    def promote_model_to_production(self, model_name: str, version: str) -> dict[str, Any]:
        """Promote a model version to production stage.

        Args:
        ----
            model_name: Name of the model
            version: Version to promote

        Returns:
        -------
            Dictionary with promotion details

        """
        try:
            client = mlflow.tracking.MlflowClient()

            # Transition to production
            client.transition_model_version_stage(
                name=model_name, version=version, stage="Production", archive_existing_versions=True
            )

            result = {
                "model_id": model_name,
                "version": version,
                "stage": "Production",
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(f"Promoted {model_name} v{version} to production")
            return result

        except Exception as e:
            logger.error(f"Failed to promote model: {str(e)}")
            raise

    def get_production_models(self) -> list[dict[str, Any]]:
        """Get all models currently in production.

        Returns
        -------
            List of production models

        """
        try:
            client = mlflow.tracking.MlflowClient()

            # Get all registered models
            models = client.list_registered_models()

            production_models = []
            for model in models:
                # Check for production versions
                for version in model.latest_versions:
                    if version.current_stage == "Production":
                        production_models.append(
                            {
                                "model_name": model.name,
                                "version": version.version,
                                "stage": version.current_stage,
                                "description": model.description,
                                "tags": model.tags if hasattr(model, "tags") else {},
                            }
                        )

            return production_models

        except Exception as e:
            logger.error(f"Failed to get production models: {str(e)}")
            return []
