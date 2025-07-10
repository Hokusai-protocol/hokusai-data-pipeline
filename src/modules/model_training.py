"""Module for model training."""

from datetime import datetime
from typing import Any, Optional

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


class ModelTrainer:
    """Handles model training with contributed data."""

    def __init__(
        self,
        random_seed: int = 42,
        mlflow_tracking_uri: Optional[str] = None,
        experiment_name: Optional[str] = None,
    ) -> None:
        self.random_seed = random_seed
        np.random.seed(random_seed)

        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
        if experiment_name:
            mlflow.set_experiment(experiment_name)

    def prepare_training_data(
        self,
        df: pd.DataFrame,
        target_column: str,
        feature_columns: Optional[list] = None,
        test_size: float = 0.2,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """Prepare data for training.

        Args:
            df: Input dataframe
            target_column: Name of target column
            feature_columns: List of feature columns (if None, use all except
                target)
            test_size: Fraction of data to use for testing

        Returns:
            X_train, X_test, y_train, y_test

        """
        if feature_columns is None:
            feature_columns = [col for col in df.columns if col != target_column]

        X = df[feature_columns]
        y = df[target_column]

        return train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=self.random_seed,
            stratify=y if len(np.unique(y)) < 100 else None,
        )

    def train_mock_model(
        self, X_train: pd.DataFrame, y_train: pd.Series, model_type: str = "mock_classifier"
    ) -> dict[str, Any]:
        """Train a mock model for testing.

        Args:
            X_train: Training features
            y_train: Training labels
            model_type: Type of mock model

        Returns:
            Mock trained model

        """
        # Simulate training metrics with some randomness
        base_accuracy = 0.85
        improvement = np.random.uniform(0.02, 0.05)

        return {
            "type": f"mock_{model_type}",
            "version": "2.0.0",
            "algorithm": model_type,
            "training_date": datetime.utcnow().isoformat(),
            "training_samples": len(X_train),
            "feature_count": X_train.shape[1],
            "metrics": {
                "accuracy": base_accuracy + improvement,
                "precision": base_accuracy + improvement - 0.02,
                "recall": base_accuracy + improvement + 0.02,
                "f1_score": base_accuracy + improvement,
                "auroc": min(0.95, base_accuracy + improvement + 0.06),
            },
            "parameters": {
                "random_seed": self.random_seed,
                "training_duration_seconds": np.random.uniform(10, 60),
            },
            "feature_importance": {col: np.random.uniform(0, 1) for col in X_train.columns},
        }

    def train_sklearn_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        model_class: Any,
        model_params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Train a scikit-learn model.

        Args:
            X_train: Training features
            y_train: Training labels
            model_class: Scikit-learn model class
            model_params: Model hyperparameters

        Returns:
            Trained model

        """
        if model_params is None:
            model_params = {}

        # Add random seed if supported
        if "random_state" in model_class.__init__.__code__.co_varnames:
            model_params["random_state"] = self.random_seed

        model = model_class(**model_params)
        model.fit(X_train, y_train)

        return model

    def _log_model_data(
        self, model: Any, model_name: str, params: dict[str, Any], metrics: dict[str, float]
    ):
        """Helper method to log model data to MLflow."""
        # Log parameters
        for key, value in params.items():
            mlflow.log_param(key, value)

        # Log metrics
        for key, value in metrics.items():
            mlflow.log_metric(key, value)

        # Log model
        if isinstance(model, dict) and model.get("type", "").startswith("mock"):
            # For mock models, log as artifact
            import json
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(model, f, indent=2)
                mlflow.log_artifact(f.name, artifact_path="model")
        else:
            # For real models
            mlflow.sklearn.log_model(model, model_name)

    def log_model_to_mlflow(
        self,
        model: Any,
        model_name: str,
        metrics: dict[str, float],
        params: dict[str, Any],
        artifacts: Optional[dict[str, str]] = None,
    ) -> str:
        """Log model to MLflow.

        Args:
            model: Trained model
            model_name: Name for the model
            metrics: Model metrics
            params: Model parameters
            artifacts: Additional artifacts to log

        Returns:
            MLflow run ID

        """
        # Use current active run if available, otherwise start a new one
        active_run = mlflow.active_run()
        if active_run:
            run = active_run
            self._log_model_data(model, model_name, params, metrics)

            # Log additional artifacts
            if artifacts:
                for artifact_name, artifact_path in artifacts.items():
                    mlflow.log_artifact(artifact_path, artifact_name)

            return run.info.run_id
        else:
            with mlflow.start_run() as run:
                self._log_model_data(model, model_name, params, metrics)

                # Log additional artifacts
                if artifacts:
                    for artifact_name, artifact_path in artifacts.items():
                        mlflow.log_artifact(artifact_path, artifact_name)

                return run.info.run_id

    def create_training_report(
        self, model: Any, X_train: pd.DataFrame, y_train: pd.Series, training_time: float
    ) -> dict[str, Any]:
        """Create a training report.

        Args:
            model: Trained model
            X_train: Training features
            y_train: Training labels
            training_time: Time taken to train

        Returns:
            Training report dictionary

        """
        model_type = type(model).__name__ if not isinstance(model, dict) else model.get("type")
        target_dist = y_train.value_counts().to_dict() if hasattr(y_train, "value_counts") else {}

        return {
            "model_type": model_type,
            "training_samples": len(X_train),
            "feature_count": X_train.shape[1],
            "target_distribution": target_dist,
            "training_time_seconds": training_time,
            "timestamp": datetime.utcnow().isoformat(),
            "feature_names": X_train.columns.tolist(),
        }
