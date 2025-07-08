"""Configuration management for Hokusai pipeline."""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class PipelineConfig:
    """Configuration for the Hokusai evaluation pipeline."""

    # Environment settings
    environment: str = os.getenv("PIPELINE_ENV", "development")
    log_level: str = os.getenv("PIPELINE_LOG_LEVEL", "INFO")
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"

    # Paths
    data_dir: Path = Path(os.getenv("PIPELINE_DATA_DIR", "./data"))
    model_dir: Path = Path(os.getenv("PIPELINE_MODEL_DIR", "./models"))

    # MLflow settings
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "./mlruns")
    mlflow_experiment_name: str = os.getenv("MLFLOW_EXPERIMENT_NAME", "hokusai-evaluation")

    # Metaflow settings
    metaflow_datastore_root: str = os.getenv("METAFLOW_DATASTORE_ROOT", "./metaflow_data")

    # Pipeline parameters
    random_seed: int = int(os.getenv("RANDOM_SEED", "42"))
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "1000"))

    # Model evaluation settings
    evaluation_metrics: list = field(default_factory=lambda: ["accuracy", "precision", "recall", "f1", "auroc"])
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))

    # Data sampling
    sample_size: Optional[int] = None
    stratify_column: Optional[str] = None
    test_size: float = 0.2

    def __post_init__(self):
        """Create directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "environment": self.environment,
            "log_level": self.log_level,
            "dry_run": self.dry_run,
            "data_dir": str(self.data_dir),
            "model_dir": str(self.model_dir),
            "mlflow_tracking_uri": self.mlflow_tracking_uri,
            "mlflow_experiment_name": self.mlflow_experiment_name,
            "metaflow_datastore_root": self.metaflow_datastore_root,
            "random_seed": self.random_seed,
            "max_workers": self.max_workers,
            "batch_size": self.batch_size,
            "evaluation_metrics": self.evaluation_metrics,
            "confidence_threshold": self.confidence_threshold,
            "sample_size": self.sample_size,
            "stratify_column": self.stratify_column,
            "test_size": self.test_size,
        }


def get_config() -> PipelineConfig:
    """Get pipeline configuration."""
    return PipelineConfig()


def get_test_config() -> PipelineConfig:
    """Get configuration for testing."""
    config = PipelineConfig()
    config.dry_run = True
    config.data_dir = Path("./data/test_fixtures")
    config.environment = "test"
    return config
