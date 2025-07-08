"""Model versioning and rollback system for Hokusai platform."""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import redis
from packaging import version
import hashlib

from .model_abstraction import HokusaiModel, ModelStatus
from .model_registry import HokusaiModelRegistry

logger = logging.getLogger(__name__)


class VersionTransitionType(Enum):
    """Types of version transitions."""

    PROMOTE = "promote"
    ROLLBACK = "rollback"
    DEPRECATE = "deprecate"
    ARCHIVE = "archive"


class Environment(Enum):
    """Deployment environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class ModelVersion:
    """Represents a specific model version."""

    model_family: str
    version: str
    model_id: str
    status: ModelStatus
    environment: Environment
    created_at: datetime
    updated_at: datetime
    created_by: str
    metadata: Dict[str, Any]
    performance_metrics: Dict[str, float]
    mlflow_run_id: Optional[str] = None
    parent_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        data["environment"] = self.environment.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelVersion":
        """Create from dictionary."""
        data["status"] = ModelStatus(data["status"])
        data["environment"] = Environment(data["environment"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


@dataclass
class VersionTransition:
    """Records a version transition event."""

    transition_id: str
    model_family: str
    from_version: str
    to_version: str
    transition_type: VersionTransitionType
    environment: Environment
    performed_by: str
    performed_at: datetime
    reason: str
    rollback_available: bool = True
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["transition_type"] = self.transition_type.value
        data["environment"] = self.environment.value
        data["performed_at"] = self.performed_at.isoformat()
        return data


class ModelVersionManager:
    """Manages model versions and transitions."""

    def __init__(self, registry: HokusaiModelRegistry, redis_client: redis.Redis):
        """Initialize the version manager.
        
        Args:
            registry: Model registry instance
            redis_client: Redis client for version tracking

        """
        self.registry = registry
        self.redis = redis_client
        self.version_history = {}

    def register_version(self, model: HokusaiModel,
                        model_family: str,
                        version_tag: str,
                        created_by: str,
                        parent_version: Optional[str] = None) -> ModelVersion:
        """Register a new model version.
        
        Args:
            model: The model instance
            model_family: Model family name
            version_tag: Semantic version tag (e.g., "1.2.0")
            created_by: User or system that created the version
            parent_version: Parent version if this is derived
            
        Returns:
            ModelVersion instance

        """
        # Validate version format
        try:
            version.parse(version_tag)
        except version.InvalidVersion:
            raise ValueError(f"Invalid version format: {version_tag}")

        # Check if version already exists
        if self._version_exists(model_family, version_tag):
            raise ValueError(f"Version {version_tag} already exists for {model_family}")

        # Register with MLFlow
        mlflow_result = self.registry.register_baseline(
            model=model,
            model_type=model.metadata.model_type.value,
            metadata={
                "version": version_tag,
                "model_family": model_family,
                "created_by": created_by,
                "parent_version": parent_version
            }
        )

        # Create version record
        model_version = ModelVersion(
            model_family=model_family,
            version=version_tag,
            model_id=mlflow_result["model_id"],
            status=ModelStatus.STAGING,
            environment=Environment.DEVELOPMENT,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by=created_by,
            metadata=model.metadata.to_dict(),
            performance_metrics=model.metadata.performance_metrics,
            mlflow_run_id=mlflow_result["run_id"],
            parent_version=parent_version
        )

        # Store version
        self._save_version(model_version)

        # Update version index
        self._update_version_index(model_family, version_tag)

        logger.info(f"Registered model version: {model_family}/{version_tag}")
        return model_version

    def promote_model(self, model_family: str,
                     version_tag: str,
                     environment: Environment,
                     promoted_by: str,
                     reason: str) -> bool:
        """Promote a model version to a higher environment.
        
        Args:
            model_family: Model family name
            version_tag: Version to promote
            environment: Target environment
            promoted_by: User performing promotion
            reason: Reason for promotion
            
        Returns:
            True if successful

        """
        # Load version
        model_version = self.get_version(model_family, version_tag)
        if not model_version:
            raise ValueError(f"Version {version_tag} not found for {model_family}")

        # Validate promotion path
        if not self._validate_promotion_path(model_version.environment, environment):
            raise ValueError(
                f"Invalid promotion from {model_version.environment.value} "
                f"to {environment.value}"
            )

        # Get current production version if promoting to production
        previous_version = None
        if environment == Environment.PRODUCTION:
            previous_version = self.get_active_version(model_family, Environment.PRODUCTION)

        # Update version
        old_environment = model_version.environment
        model_version.environment = environment
        model_version.status = ModelStatus.PRODUCTION
        model_version.updated_at = datetime.utcnow()

        # Save updated version
        self._save_version(model_version)

        # Record transition
        transition = VersionTransition(
            transition_id=self._generate_transition_id(),
            model_family=model_family,
            from_version=previous_version.version if previous_version else "none",
            to_version=version_tag,
            transition_type=VersionTransitionType.PROMOTE,
            environment=environment,
            performed_by=promoted_by,
            performed_at=datetime.utcnow(),
            reason=reason,
            metadata={
                "old_environment": old_environment.value,
                "new_environment": environment.value
            }
        )
        self._record_transition(transition)

        # Update active version for environment
        self._set_active_version(model_family, environment, version_tag)

        logger.info(
            f"Promoted {model_family}/{version_tag} to {environment.value}"
        )
        return True

    def rollback_model(self, model_family: str,
                      target_version: str,
                      environment: Environment,
                      performed_by: str,
                      reason: str) -> bool:
        """Rollback to a previous model version.
        
        Args:
            model_family: Model family name
            target_version: Version to rollback to
            environment: Environment to rollback in
            performed_by: User performing rollback
            reason: Reason for rollback
            
        Returns:
            True if successful

        """
        # Validate target version exists
        target_model = self.get_version(model_family, target_version)
        if not target_model:
            raise ValueError(f"Target version {target_version} not found")

        # Get current version
        current_version = self.get_active_version(model_family, environment)
        if not current_version:
            raise ValueError(f"No active version in {environment.value}")

        # Check if rollback is allowed
        if not self._can_rollback(current_version, target_model):
            raise ValueError(f"Cannot rollback from {current_version.version} to {target_version}")

        # Perform rollback
        target_model.environment = environment
        target_model.status = ModelStatus.PRODUCTION
        target_model.updated_at = datetime.utcnow()

        # Save updated version
        self._save_version(target_model)

        # Update current version status
        current_version.status = ModelStatus.DEPRECATED
        self._save_version(current_version)

        # Record transition
        transition = VersionTransition(
            transition_id=self._generate_transition_id(),
            model_family=model_family,
            from_version=current_version.version,
            to_version=target_version,
            transition_type=VersionTransitionType.ROLLBACK,
            environment=environment,
            performed_by=performed_by,
            performed_at=datetime.utcnow(),
            reason=reason
        )
        self._record_transition(transition)

        # Update active version
        self._set_active_version(model_family, environment, target_version)

        logger.info(
            f"Rolled back {model_family} from {current_version.version} "
            f"to {target_version} in {environment.value}"
        )
        return True

    def deprecate_model(self, model_family: str,
                       version_tag: str,
                       deprecated_by: str,
                       reason: str) -> bool:
        """Mark a model version as deprecated.
        
        Args:
            model_family: Model family name
            version_tag: Version to deprecate
            deprecated_by: User deprecating the version
            reason: Reason for deprecation
            
        Returns:
            True if successful

        """
        # Load version
        model_version = self.get_version(model_family, version_tag)
        if not model_version:
            raise ValueError(f"Version {version_tag} not found")

        # Check if version is in production
        if (model_version.status == ModelStatus.PRODUCTION and
            model_version.environment == Environment.PRODUCTION):
            raise ValueError("Cannot deprecate active production version")

        # Update status
        old_status = model_version.status
        model_version.status = ModelStatus.DEPRECATED
        model_version.updated_at = datetime.utcnow()

        # Save updated version
        self._save_version(model_version)

        # Record transition
        transition = VersionTransition(
            transition_id=self._generate_transition_id(),
            model_family=model_family,
            from_version=version_tag,
            to_version=version_tag,
            transition_type=VersionTransitionType.DEPRECATE,
            environment=model_version.environment,
            performed_by=deprecated_by,
            performed_at=datetime.utcnow(),
            reason=reason,
            metadata={"old_status": old_status.value}
        )
        self._record_transition(transition)

        logger.info(f"Deprecated {model_family}/{version_tag}")
        return True

    def get_version(self, model_family: str,
                   version_tag: str) -> Optional[ModelVersion]:
        """Get a specific model version.
        
        Args:
            model_family: Model family name
            version_tag: Version tag
            
        Returns:
            ModelVersion instance or None

        """
        key = f"model_version:{model_family}:{version_tag}"
        data = self.redis.get(key)

        if data:
            return ModelVersion.from_dict(json.loads(data))
        return None

    def get_active_version(self, model_family: str,
                          environment: Environment) -> Optional[ModelVersion]:
        """Get the active version for an environment.
        
        Args:
            model_family: Model family name
            environment: Target environment
            
        Returns:
            Active ModelVersion or None

        """
        key = f"active_version:{model_family}:{environment.value}"
        version_tag = self.redis.get(key)

        if version_tag:
            version_tag = version_tag.decode() if isinstance(version_tag, bytes) else version_tag
            return self.get_version(model_family, version_tag)
        return None

    def get_version_history(self, model_family: str,
                          limit: int = 10) -> List[ModelVersion]:
        """Get version history for a model family.
        
        Args:
            model_family: Model family name
            limit: Maximum number of versions to return
            
        Returns:
            List of ModelVersion instances

        """
        # Get all versions for family
        index_key = f"version_index:{model_family}"
        version_tags = self.redis.zrevrange(index_key, 0, limit - 1)

        versions = []
        for tag in version_tags:
            tag = tag.decode() if isinstance(tag, bytes) else tag
            version_obj = self.get_version(model_family, tag)
            if version_obj:
                versions.append(version_obj)

        return versions

    def get_transition_history(self, model_family: str,
                             limit: int = 20) -> List[VersionTransition]:
        """Get transition history for a model family.
        
        Args:
            model_family: Model family name
            limit: Maximum number of transitions to return
            
        Returns:
            List of VersionTransition instances

        """
        key = f"transitions:{model_family}"
        transitions_data = self.redis.lrange(key, 0, limit - 1)

        transitions = []
        for data in transitions_data:
            transition_dict = json.loads(data)
            transition_dict["transition_type"] = VersionTransitionType(
                transition_dict["transition_type"]
            )
            transition_dict["environment"] = Environment(
                transition_dict["environment"]
            )
            transition_dict["performed_at"] = datetime.fromisoformat(
                transition_dict["performed_at"]
            )
            transitions.append(VersionTransition(**transition_dict))

        return transitions

    def compare_versions(self, model_family: str,
                        version_a: str,
                        version_b: str) -> Dict[str, Any]:
        """Compare two model versions.
        
        Args:
            model_family: Model family name
            version_a: First version
            version_b: Second version
            
        Returns:
            Comparison results

        """
        # Load versions
        model_a = self.get_version(model_family, version_a)
        model_b = self.get_version(model_family, version_b)

        if not model_a or not model_b:
            raise ValueError("One or both versions not found")

        # Compare metrics
        metric_comparison = {}
        for metric in model_a.performance_metrics:
            if metric in model_b.performance_metrics:
                metric_comparison[metric] = {
                    "version_a": model_a.performance_metrics[metric],
                    "version_b": model_b.performance_metrics[metric],
                    "difference": model_b.performance_metrics[metric] -
                                model_a.performance_metrics[metric],
                    "improvement": model_b.performance_metrics[metric] >
                                 model_a.performance_metrics[metric]
                }

        return {
            "model_family": model_family,
            "version_a": version_a,
            "version_b": version_b,
            "metric_comparison": metric_comparison,
            "version_a_status": model_a.status.value,
            "version_b_status": model_b.status.value,
            "version_a_environment": model_a.environment.value,
            "version_b_environment": model_b.environment.value,
            "is_newer": version.parse(version_b) > version.parse(version_a)
        }

    def cleanup_old_versions(self, model_family: str,
                           keep_count: int = 5,
                           dry_run: bool = True) -> List[str]:
        """Clean up old deprecated versions.
        
        Args:
            model_family: Model family name
            keep_count: Number of recent versions to keep
            dry_run: If True, only return what would be deleted
            
        Returns:
            List of versions that were (or would be) deleted

        """
        # Get all versions
        all_versions = self.get_version_history(model_family, limit=100)

        # Sort by version number
        all_versions.sort(key=lambda v: version.parse(v.version), reverse=True)

        # Identify candidates for deletion
        candidates = []
        kept_count = 0

        for v in all_versions:
            # Always keep production versions
            if v.status == ModelStatus.PRODUCTION:
                kept_count += 1
                continue

            # Keep recent versions
            if kept_count < keep_count:
                kept_count += 1
                continue

            # Only delete deprecated or archived versions
            if v.status in [ModelStatus.DEPRECATED, ModelStatus.ARCHIVED]:
                candidates.append(v.version)

        # Perform deletion if not dry run
        if not dry_run:
            for version_tag in candidates:
                self._delete_version(model_family, version_tag)
                logger.info(f"Deleted old version: {model_family}/{version_tag}")

        return candidates

    def _version_exists(self, model_family: str, version_tag: str) -> bool:
        """Check if a version exists."""
        key = f"model_version:{model_family}:{version_tag}"
        return self.redis.exists(key)

    def _save_version(self, model_version: ModelVersion):
        """Save a model version to Redis."""
        key = f"model_version:{model_version.model_family}:{model_version.version}"
        self.redis.set(key, json.dumps(model_version.to_dict()))

    def _update_version_index(self, model_family: str, version_tag: str):
        """Update the version index for a model family."""
        key = f"version_index:{model_family}"
        # Use version number as score for sorting
        score = self._version_to_score(version_tag)
        self.redis.zadd(key, {version_tag: score})

    def _set_active_version(self, model_family: str,
                          environment: Environment,
                          version_tag: str):
        """Set the active version for an environment."""
        key = f"active_version:{model_family}:{environment.value}"
        self.redis.set(key, version_tag)

    def _record_transition(self, transition: VersionTransition):
        """Record a version transition."""
        key = f"transitions:{transition.model_family}"
        self.redis.lpush(key, json.dumps(transition.to_dict()))
        # Keep only last 100 transitions
        self.redis.ltrim(key, 0, 99)

    def _generate_transition_id(self) -> str:
        """Generate a unique transition ID."""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.md5(timestamp.encode()).hexdigest()[:12]

    def _validate_promotion_path(self, from_env: Environment,
                               to_env: Environment) -> bool:
        """Validate if promotion path is allowed."""
        allowed_paths = {
            (Environment.DEVELOPMENT, Environment.STAGING),
            (Environment.DEVELOPMENT, Environment.PRODUCTION),  # Hot fix
            (Environment.STAGING, Environment.PRODUCTION)
        }
        return (from_env, to_env) in allowed_paths

    def _can_rollback(self, current: ModelVersion,
                     target: ModelVersion) -> bool:
        """Check if rollback is allowed."""
        # Can only rollback to older versions
        current_v = version.parse(current.version)
        target_v = version.parse(target.version)

        if target_v >= current_v:
            return False

        # Target must have been in production before
        transitions = self.get_transition_history(current.model_family)
        for transition in transitions:
            if (transition.to_version == target.version and
                transition.environment == Environment.PRODUCTION):
                return True

        return False

    def _version_to_score(self, version_tag: str) -> float:
        """Convert version string to numeric score for sorting."""
        v = version.parse(version_tag)
        # Convert to score: major*10000 + minor*100 + micro
        if hasattr(v, "major") and hasattr(v, "minor") and hasattr(v, "micro"):
            return v.major * 10000 + v.minor * 100 + v.micro
        return 0

    def _delete_version(self, model_family: str, version_tag: str):
        """Delete a version from storage."""
        # Delete version data
        version_key = f"model_version:{model_family}:{version_tag}"
        self.redis.delete(version_key)

        # Remove from index
        index_key = f"version_index:{model_family}"
        self.redis.zrem(index_key, version_tag)
