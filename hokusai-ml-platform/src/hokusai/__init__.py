"""Hokusai ML Platform - Unified MLOps infrastructure for model management and tracking."""

__version__ = "1.0.0"
__author__ = "Hokusai Team"
__email__ = "team@hokus.ai"

# Import key components for easier access
from hokusai.core.models import HokusaiModel
from hokusai.core.registry import ModelRegistry
from hokusai.core.versioning import ModelVersionManager
from hokusai.core.inference import HokusaiInferencePipeline
from hokusai.tracking.experiments import ExperimentManager
from hokusai.tracking.performance import PerformanceTracker
from hokusai.auth import HokusaiAuth
from hokusai.auth.client import configure, setup
from hokusai.config import setup_mlflow_auth
from hokusai.exceptions import (
    HokusaiException,
    MLflowConnectionError,
    MLflowAuthenticationError,
    ModelNotFoundError,
    ConfigurationError
)

__all__ = [
    "__version__",
    "ModelRegistry",
    "ModelVersionManager",
    "HokusaiModel",
    "HokusaiInferencePipeline",
    "ExperimentManager",
    "PerformanceTracker",
    "HokusaiAuth",
    "configure",
    "setup",
    "setup_mlflow_auth",
    "HokusaiException",
    "MLflowConnectionError",
    "MLflowAuthenticationError",
    "ModelNotFoundError",
    "ConfigurationError",
]
