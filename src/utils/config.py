"""Configuration management for Hokusai pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class PipelineConfig:
    """Configuration for the Hokusai evaluation pipeline."""

    # Environment settings
    environment: str = "development"
    log_level: str = "INFO"
    dry_run: bool = False

    # Paths
    data_dir: Path = Path("./data")
    model_dir: Path = Path("./models")

    # MLflow settings
    mlflow_tracking_uri: str = "./mlruns"
    mlflow_experiment_name: str = "hokusai-evaluation"

    # Metaflow settings
    metaflow_datastore_root: str = "./metaflow_data"

    # Pipeline parameters
    random_seed: int = 42
    max_workers: int = 4
    batch_size: int = 1000

    # Model evaluation settings
    evaluation_metrics: list = field(
        default_factory=lambda: ["accuracy", "precision", "recall", "f1", "auroc"]
    )
    confidence_threshold: float = 0.5

    # Data sampling
    sample_size: Optional[int] = None
    stratify_column: Optional[str] = None
    test_size: float = 0.2
    
    # Message queue settings
    message_queue_type: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    message_queue_name: str = "hokusai:model_ready_queue"
    message_retry_max: int = 3
    message_retry_base_delay: float = 1.0

    def __post_init__(self):
        """Load configuration from environment variables and create directories."""
        # Environment settings
        self.environment = os.getenv("PIPELINE_ENV", self.environment)
        self.log_level = os.getenv("PIPELINE_LOG_LEVEL", self.log_level)
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        # Paths
        self.data_dir = Path(os.getenv("PIPELINE_DATA_DIR", str(self.data_dir)))
        self.model_dir = Path(os.getenv("PIPELINE_MODEL_DIR", str(self.model_dir)))
        
        # MLflow settings
        self.mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", self.mlflow_tracking_uri)
        self.mlflow_experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", self.mlflow_experiment_name)
        
        # Metaflow settings
        self.metaflow_datastore_root = os.getenv("METAFLOW_DATASTORE_ROOT", self.metaflow_datastore_root)
        
        # Pipeline parameters
        self.random_seed = int(os.getenv("RANDOM_SEED", str(self.random_seed)))
        self.max_workers = int(os.getenv("MAX_WORKERS", str(self.max_workers)))
        self.batch_size = int(os.getenv("BATCH_SIZE", str(self.batch_size)))
        
        # Model evaluation settings
        self.confidence_threshold = float(os.getenv("CONFIDENCE_THRESHOLD", str(self.confidence_threshold)))
        
        # Message queue settings
        self.message_queue_type = os.getenv("MESSAGE_QUEUE_TYPE", self.message_queue_type)
        self.redis_url = os.getenv("REDIS_URL", self.redis_url)
        self.message_queue_name = os.getenv("MESSAGE_QUEUE_NAME", self.message_queue_name)
        self.message_retry_max = int(os.getenv("MESSAGE_RETRY_MAX", str(self.message_retry_max)))
        self.message_retry_base_delay = float(os.getenv("MESSAGE_RETRY_BASE_DELAY", str(self.message_retry_base_delay)))
        
        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
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
            "message_queue_type": self.message_queue_type,
            "redis_url": self.redis_url,
            "message_queue_name": self.message_queue_name,
            "message_retry_max": self.message_retry_max,
            "message_retry_base_delay": self.message_retry_base_delay,
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
