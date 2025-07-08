"""Unit tests for model versioning service."""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import redis

from src.services.model_abstraction import ModelStatus
from src.services.model_versioning import (
    Environment,
    ModelVersion,
    ModelVersionManager,
    VersionTransition,
    VersionTransitionType,
)


class TestVersionTransitionType:
    """Test suite for VersionTransitionType enum."""

    def test_transition_types(self):
        """Test version transition type values."""
        assert VersionTransitionType.PROMOTE.value == "promote"
        assert VersionTransitionType.ROLLBACK.value == "rollback"
        assert VersionTransitionType.DEPRECATE.value == "deprecate"
        assert VersionTransitionType.ARCHIVE.value == "archive"


class TestEnvironment:
    """Test suite for Environment enum."""

    def test_environment_values(self):
        """Test environment enumeration values."""
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"


class TestModelVersion:
    """Test suite for ModelVersion dataclass."""

    def setup_method(self):
        """Set up test fixtures."""
        self.version = ModelVersion(
            model_family="lead_scoring",
            version="1.2.0",
            model_id="model_123",
            status=ModelStatus.PRODUCTION,
            environment=Environment.PRODUCTION,
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            updated_at=datetime(2024, 1, 15, 14, 0, 0),
            created_by="user@example.com",
            metadata={"framework": "sklearn", "algorithm": "xgboost"},
            performance_metrics={"accuracy": 0.95, "f1": 0.93},
            mlflow_run_id="run_123",
            parent_version="1.1.0",
        )

    def test_model_version_creation(self):
        """Test creating model version."""
        assert self.version.model_family == "lead_scoring"
        assert self.version.version == "1.2.0"
        assert self.version.model_id == "model_123"
        assert self.version.status == ModelStatus.PRODUCTION
        assert self.version.environment == Environment.PRODUCTION
        assert self.version.parent_version == "1.1.0"

    def test_model_version_to_dict(self):
        """Test converting model version to dictionary."""
        data = self.version.to_dict()

        assert data["model_family"] == "lead_scoring"
        assert data["version"] == "1.2.0"
        assert data["status"] == "production"
        assert data["environment"] == "production"
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)
        assert data["metadata"]["framework"] == "sklearn"

    def test_model_version_from_dict(self):
        """Test creating model version from dictionary."""
        data = self.version.to_dict()
        loaded_version = ModelVersion.from_dict(data)

        assert loaded_version.model_family == self.version.model_family
        assert loaded_version.version == self.version.version
        assert loaded_version.status == self.version.status
        assert loaded_version.environment == self.version.environment
        assert isinstance(loaded_version.created_at, datetime)


class TestVersionTransition:
    """Test suite for VersionTransition dataclass."""

    def test_version_transition_creation(self):
        """Test creating version transition."""
        transition = VersionTransition(
            transition_id="trans_123",
            model_family="lead_scoring",
            from_version="1.1.0",
            to_version="1.2.0",
            transition_type=VersionTransitionType.PROMOTE,
            environment=Environment.PRODUCTION,
            performed_by="admin@example.com",
            performed_at=datetime.now(),
            reason="Performance improvement",
            success=True,
        )

        assert transition.transition_id == "trans_123"
        assert transition.from_version == "1.1.0"
        assert transition.to_version == "1.2.0"
        assert transition.transition_type == VersionTransitionType.PROMOTE
        assert transition.success is True


class TestModelVersionManager:
    """Test suite for ModelVersionManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_redis = Mock(spec=redis.Redis)
        self.mock_registry = Mock()

        with patch(
            "src.services.model_versioning.HokusaiModelRegistry", return_value=self.mock_registry
        ):
            self.manager = ModelVersionManager(self.mock_redis)

    def test_manager_initialization(self):
        """Test version manager initialization."""
        assert self.manager.redis_client == self.mock_redis
        assert self.manager.registry == self.mock_registry

    def test_create_version(self):
        """Test creating a new model version."""
        # Mock model
        mock_model = Mock()

        # Create version
        model_version = self.manager.create_version(
            model_family="lead_scoring",
            version="2.0.0",
            model=mock_model,
            created_by="user@example.com",
            metadata={"algorithm": "xgboost"},
            parent_version="1.5.0",
        )

        assert model_version.model_family == "lead_scoring"
        assert model_version.version == "2.0.0"
        assert model_version.status == ModelStatus.STAGING
        assert model_version.environment == Environment.DEVELOPMENT
        assert model_version.created_by == "user@example.com"
        assert model_version.parent_version == "1.5.0"

        # Check Redis storage
        self.mock_redis.set.assert_called()

    def test_get_version(self):
        """Test getting a model version."""
        # Mock stored version
        stored_data = {
            "model_family": "lead_scoring",
            "version": "1.0.0",
            "model_id": "model_123",
            "status": "production",
            "environment": "production",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "user@example.com",
            "metadata": {},
            "performance_metrics": {},
        }
        self.mock_redis.get.return_value = json.dumps(stored_data)

        # Get version
        version = self.manager.get_version("lead_scoring", "1.0.0")

        assert version is not None
        assert version.model_family == "lead_scoring"
        assert version.version == "1.0.0"

    def test_get_version_not_found(self):
        """Test getting non-existent version."""
        self.mock_redis.get.return_value = None

        version = self.manager.get_version("lead_scoring", "99.0.0")
        assert version is None

    def test_list_versions(self):
        """Test listing model versions."""
        # Mock version keys
        self.mock_redis.keys.return_value = [
            b"model_version:lead_scoring:1.0.0",
            b"model_version:lead_scoring:1.1.0",
            b"model_version:lead_scoring:2.0.0",
        ]

        # Mock version data
        def mock_get(key):
            version_map = {
                "model_version:lead_scoring:1.0.0": {"version": "1.0.0"},
                "model_version:lead_scoring:1.1.0": {"version": "1.1.0"},
                "model_version:lead_scoring:2.0.0": {"version": "2.0.0"},
            }
            key_str = key.decode() if isinstance(key, bytes) else key
            return json.dumps(version_map.get(key_str, {}))

        self.mock_redis.get.side_effect = mock_get

        versions = self.manager.list_versions("lead_scoring")

        assert len(versions) == 3
        # Should be sorted by version
        assert versions[0]["version"] == "2.0.0"
        assert versions[1]["version"] == "1.1.0"
        assert versions[2]["version"] == "1.0.0"

    def test_promote_version(self):
        """Test promoting a model version."""
        # Mock current version
        current_version = ModelVersion(
            model_family="lead_scoring",
            version="1.5.0",
            model_id="model_123",
            status=ModelStatus.STAGING,
            environment=Environment.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user@example.com",
            metadata={},
            performance_metrics={"accuracy": 0.95},
        )

        self.mock_redis.get.return_value = json.dumps(current_version.to_dict())

        # Promote to production
        transition = self.manager.promote_version(
            "lead_scoring", "1.5.0", Environment.PRODUCTION, "admin@example.com", "Passed all tests"
        )

        assert transition.transition_type == VersionTransitionType.PROMOTE
        assert transition.to_version == "1.5.0"
        assert transition.environment == Environment.PRODUCTION
        assert transition.performed_by == "admin@example.com"

        # Check that version was updated
        assert self.mock_redis.set.call_count >= 2  # Version and transition

    def test_rollback_version(self):
        """Test rolling back to a previous version."""
        # Mock versions
        current_prod = ModelVersion(
            model_family="lead_scoring",
            version="2.0.0",
            model_id="model_200",
            status=ModelStatus.PRODUCTION,
            environment=Environment.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user@example.com",
            metadata={},
            performance_metrics={},
        )

        previous_version = ModelVersion(
            model_family="lead_scoring",
            version="1.5.0",
            model_id="model_150",
            status=ModelStatus.DEPRECATED,
            environment=Environment.STAGING,
            created_at=datetime.now() - timedelta(days=7),
            updated_at=datetime.now() - timedelta(days=7),
            created_by="user@example.com",
            metadata={},
            performance_metrics={},
        )

        def mock_get(key):
            if "2.0.0" in str(key):
                return json.dumps(current_prod.to_dict())
            elif "1.5.0" in str(key):
                return json.dumps(previous_version.to_dict())
            return None

        self.mock_redis.get.side_effect = mock_get

        # Perform rollback
        transition = self.manager.rollback_version(
            "lead_scoring",
            "1.5.0",
            Environment.PRODUCTION,
            "admin@example.com",
            "Performance regression detected",
        )

        assert transition.transition_type == VersionTransitionType.ROLLBACK
        assert transition.from_version == "2.0.0"
        assert transition.to_version == "1.5.0"

    def test_get_active_version(self):
        """Test getting active version for an environment."""
        # Mock scan results
        self.mock_redis.scan_iter.return_value = [
            b"model_version:lead_scoring:1.0.0",
            b"model_version:lead_scoring:2.0.0",
        ]

        # Mock version data
        v1 = ModelVersion(
            model_family="lead_scoring",
            version="1.0.0",
            model_id="model_100",
            status=ModelStatus.DEPRECATED,
            environment=Environment.STAGING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user@example.com",
            metadata={},
            performance_metrics={},
        )

        v2 = ModelVersion(
            model_family="lead_scoring",
            version="2.0.0",
            model_id="model_200",
            status=ModelStatus.PRODUCTION,
            environment=Environment.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user@example.com",
            metadata={},
            performance_metrics={},
        )

        def mock_get(key):
            if "1.0.0" in str(key):
                return json.dumps(v1.to_dict())
            elif "2.0.0" in str(key):
                return json.dumps(v2.to_dict())
            return None

        self.mock_redis.get.side_effect = mock_get

        # Get active production version
        active = self.manager.get_active_version("lead_scoring", Environment.PRODUCTION)

        assert active is not None
        assert active.version == "2.0.0"
        assert active.environment == Environment.PRODUCTION

    def test_deprecate_version(self):
        """Test deprecating a model version."""
        # Mock version
        version_data = ModelVersion(
            model_family="lead_scoring",
            version="1.0.0",
            model_id="model_100",
            status=ModelStatus.PRODUCTION,
            environment=Environment.PRODUCTION,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by="user@example.com",
            metadata={},
            performance_metrics={},
        )

        self.mock_redis.get.return_value = json.dumps(version_data.to_dict())

        # Deprecate version
        result = self.manager.deprecate_version(
            "lead_scoring", "1.0.0", "admin@example.com", "Superseded by version 2.0.0"
        )

        assert result is True

        # Check that status was updated
        saved_calls = [call for call in self.mock_redis.set.call_args_list]
        assert len(saved_calls) > 0

    def test_get_version_history(self):
        """Test getting version transition history."""
        # Mock transition keys
        self.mock_redis.keys.return_value = [
            b"version_transition:lead_scoring:trans_1",
            b"version_transition:lead_scoring:trans_2",
        ]

        # Mock transition data
        trans1 = {
            "transition_id": "trans_1",
            "from_version": "1.0.0",
            "to_version": "1.1.0",
            "transition_type": "promote",
            "performed_at": (datetime.now() - timedelta(days=7)).isoformat(),
        }

        trans2 = {
            "transition_id": "trans_2",
            "from_version": "1.1.0",
            "to_version": "2.0.0",
            "transition_type": "promote",
            "performed_at": datetime.now().isoformat(),
        }

        def mock_get(key):
            if "trans_1" in str(key):
                return json.dumps(trans1)
            elif "trans_2" in str(key):
                return json.dumps(trans2)
            return None

        self.mock_redis.get.side_effect = mock_get

        # Get history
        history = self.manager.get_version_history("lead_scoring", limit=10)

        assert len(history) == 2
        # Should be sorted by date (newest first)
        assert history[0]["transition_id"] == "trans_2"
        assert history[1]["transition_id"] == "trans_1"
