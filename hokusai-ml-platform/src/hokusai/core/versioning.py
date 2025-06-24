"""Model version management system"""
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

from .registry import ModelRegistry, ModelRegistryEntry
from .models import HokusaiModel


class VersioningException(Exception):
    """Exception raised by versioning operations"""
    pass


class Version:
    """Semantic version representation"""
    
    VERSION_PATTERN = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
    
    def __init__(self, version_string: str):
        match = self.VERSION_PATTERN.match(version_string)
        if not match:
            raise VersioningException(
                f"Invalid version format: {version_string}. Expected format: X.Y.Z"
            )
        
        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3))
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __repr__(self) -> str:
        return f"Version({self})"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Version):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __lt__(self, other) -> bool:
        if not isinstance(other, Version):
            raise TypeError(f"Cannot compare Version with {type(other)}")
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other) -> bool:
        return self < other or self == other
    
    def __gt__(self, other) -> bool:
        return not self <= other
    
    def __ge__(self, other) -> bool:
        return not self < other
    
    def __ne__(self, other) -> bool:
        return not self == other
    
    def increment(self, level: Literal["major", "minor", "patch"]) -> "Version":
        """Create a new incremented version"""
        if level == "major":
            return Version(f"{self.major + 1}.0.0")
        elif level == "minor":
            return Version(f"{self.major}.{self.minor + 1}.0")
        elif level == "patch":
            return Version(f"{self.major}.{self.minor}.{self.patch + 1}")
        else:
            raise ValueError(f"Invalid increment level: {level}")


@dataclass
class VersionComparisonResult:
    """Result of comparing two model versions"""
    version1: str
    version2: str
    metrics_delta: Dict[str, float]
    is_improvement: bool
    comparison_timestamp: datetime = None
    
    def __post_init__(self):
        if self.comparison_timestamp is None:
            self.comparison_timestamp = datetime.utcnow()


class ModelVersionManager:
    """Manages model versions and versioning operations"""
    
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
    
    def register_version(
        self,
        model: HokusaiModel,
        model_type: str,
        version: Optional[str] = None,
        auto_increment: Optional[Literal["major", "minor", "patch"]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ModelRegistryEntry:
        """Register a new model version"""
        
        # Determine version
        if version and auto_increment:
            raise VersioningException(
                "Cannot specify both explicit version and auto_increment"
            )
        
        if auto_increment:
            # Get latest version and increment
            latest_version = self._get_latest_version_string(model_type)
            if latest_version:
                current = Version(latest_version)
                version = str(current.increment(auto_increment))
            else:
                # First version
                version = "1.0.0"
        elif not version:
            raise VersioningException(
                "Must specify either version or auto_increment"
            )
        
        # Validate version format
        Version(version)  # This will raise if invalid
        
        # Update model version
        model.version = version
        
        # Register in registry
        return self.registry.register_baseline(
            model=model,
            model_type=model_type,
            metadata=metadata
        )
    
    def get_version_history(self, model_type: str) -> List[ModelRegistryEntry]:
        """Get version history for a model type"""
        entries = self.registry.list_models_by_type(model_type)
        
        # Sort by version
        return sorted(
            entries,
            key=lambda e: Version(e.version)
        )
    
    def rollback_to_version(self, model_type: str, target_version: str) -> bool:
        """Rollback to a specific version"""
        # Validate version format
        Version(target_version)
        
        # Find model with target version
        entries = self.registry.list_models_by_type(model_type)
        target_entry = None
        
        for entry in entries:
            if entry.version == target_version:
                target_entry = entry
                break
        
        if not target_entry:
            raise VersioningException(
                f"Version {target_version} not found for model type {model_type}"
            )
        
        # Perform rollback
        return self.registry.rollback_model(model_type, target_entry.model_id)
    
    def compare_versions(
        self,
        model_type: str,
        version1: str,
        version2: str
    ) -> VersionComparisonResult:
        """Compare metrics between two versions"""
        # Validate versions
        Version(version1)
        Version(version2)
        
        # Get models
        entries = self.registry.list_models_by_type(model_type)
        model1 = None
        model2 = None
        
        for entry in entries:
            if entry.version == version1:
                model1 = entry
            elif entry.version == version2:
                model2 = entry
        
        if not model1 or not model2:
            raise VersioningException("One or both versions not found")
        
        # Calculate metrics delta
        metrics_delta = {}
        for metric in set(model1.metrics.keys()) | set(model2.metrics.keys()):
            val1 = model1.metrics.get(metric, 0.0)
            val2 = model2.metrics.get(metric, 0.0)
            metrics_delta[metric] = val2 - val1
        
        # Determine if v2 is an improvement
        # Simple heuristic: positive delta in accuracy-like metrics
        improvement_metrics = ["accuracy", "precision", "recall", "f1_score", "auc"]
        is_improvement = any(
            metric in metrics_delta and metrics_delta[metric] > 0
            for metric in improvement_metrics
        )
        
        return VersionComparisonResult(
            version1=version1,
            version2=version2,
            metrics_delta=metrics_delta,
            is_improvement=is_improvement
        )
    
    def get_latest_stable_version(self, model_type: str) -> Optional[ModelRegistryEntry]:
        """Get the latest stable version"""
        entries = self.registry.list_models_by_type(model_type)
        
        # Filter stable versions (tagged as stable)
        stable_entries = [
            e for e in entries
            if e.tags.get("stable") == "true"
        ]
        
        if not stable_entries:
            return None
        
        # Sort by version and return latest
        return max(stable_entries, key=lambda e: Version(e.version))
    
    def deprecate_version(self, model_type: str, version: str) -> bool:
        """Mark a version as deprecated"""
        # Find the model
        entries = self.registry.list_models_by_type(model_type)
        target = None
        
        for entry in entries:
            if entry.version == version:
                target = entry
                break
        
        if not target:
            return False
        
        # Set deprecated tag
        try:
            self.registry.client.set_model_version_tag(
                name=model_type,
                version=target.mlflow_version,
                key="deprecated",
                value="true"
            )
            self.registry.client.set_model_version_tag(
                name=model_type,
                version=target.mlflow_version,
                key="deprecated_at",
                value=datetime.utcnow().isoformat()
            )
            return True
        except Exception:
            return False
    
    def get_previous_version(self, model_type: str, current_version: str) -> Optional[ModelRegistryEntry]:
        """Get the previous version before the current one"""
        history = self.get_version_history(model_type)
        current = Version(current_version)
        
        # Find the highest version less than current
        previous = None
        for entry in history:
            if Version(entry.version) < current:
                if previous is None or Version(entry.version) > Version(previous.version):
                    previous = entry
        
        return previous
    
    def _get_latest_version_string(self, model_type: str) -> Optional[str]:
        """Get the latest version string for a model type"""
        entries = self.registry.list_models_by_type(model_type)
        if not entries:
            return None
        
        # Find highest version
        return max(entries, key=lambda e: Version(e.version)).version