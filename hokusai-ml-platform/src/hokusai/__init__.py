"""Hokusai ML Platform - Unified MLOps infrastructure for model management and tracking."""

__version__ = "1.0.0"
__author__ = "Hokusai Team"
__email__ = "team@hokus.ai"

# Import key components for easier access
from hokusai.core.registry import ModelRegistry
from hokusai.core.versioning import ModelVersionManager
from hokusai.core.models import HokusaiModel

__all__ = [
    "__version__",
    "ModelRegistry",
    "ModelVersionManager", 
    "HokusaiModel",
]