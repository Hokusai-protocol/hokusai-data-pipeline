"""Tests for Model Version Management."""
from datetime import datetime
from unittest.mock import Mock

import pytest
from hokusai.core.models import HokusaiModel, ModelType
from hokusai.core.registry import ModelRegistry, ModelRegistryEntry
from hokusai.core.versioning import (
    ModelVersionManager,
    Version,
    VersioningException,
)


class TestVersion:
    """Test cases for Version class."""

    def test_version_parsing(self) -> None:
        """Test parsing version strings."""
        v1 = Version("1.0.0")
        assert v1.major == 1
        assert v1.minor == 0
        assert v1.patch == 0

        v2 = Version("2.3.1")
        assert v2.major == 2
        assert v2.minor == 3
        assert v2.patch == 1

    def test_version_comparison(self) -> None:
        """Test version comparison operations."""
        v1 = Version("1.0.0")
        v2 = Version("1.0.1")
        v3 = Version("1.1.0")
        v4 = Version("2.0.0")

        assert v1 < v2 < v3 < v4
        assert v4 > v3 > v2 > v1
        assert v1 == Version("1.0.0")
        assert v1 != v2

    def test_invalid_version_format(self) -> None:
        """Test that invalid version formats raise errors."""
        with pytest.raises(VersioningException):
            Version("1.0")

        with pytest.raises(VersioningException):
            Version("1.0.0.0")

        with pytest.raises(VersioningException):
            Version("invalid")

    def test_version_string_representation(self) -> None:
        """Test version string representation."""
        v = Version("1.2.3")
        assert str(v) == "1.2.3"
        assert repr(v) == "Version(1.2.3)"


class TestModelVersionManager:
    """Test cases for ModelVersionManager."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry."""
        return Mock(spec=ModelRegistry)

    @pytest.fixture
    def version_manager(self, mock_registry):
        """Create ModelVersionManager instance."""
        return ModelVersionManager(registry=mock_registry)

    def test_register_new_version(self, version_manager, mock_registry) -> None:
        """Test registering a new model version."""
        mock_model = Mock(spec=HokusaiModel)
        mock_model.model_id = "model-001"
        mock_model.model_type = ModelType.CLASSIFICATION

        # Mock registry to return existing versions
        mock_registry.list_models_by_type.return_value = [
            ModelRegistryEntry(
                model_id="old-model-001",
                model_type="lead_scoring",
                version="1.0.0"
            ),
            ModelRegistryEntry(
                model_id="old-model-002",
                model_type="lead_scoring",
                version="1.1.0"
            )
        ]

        mock_registry.register_baseline.return_value = ModelRegistryEntry(
            model_id="model-001",
            model_type="lead_scoring",
            version="2.0.0"
        )

        entry = version_manager.register_version(
            model=mock_model,
            model_type="lead_scoring",
            version="2.0.0",
            metadata={"test": "data"}
        )

        assert entry.version == "2.0.0"
        mock_registry.register_baseline.assert_called_once()

    def test_auto_increment_version(self, version_manager, mock_registry) -> None:
        """Test automatic version incrementing."""
        mock_model = Mock(spec=HokusaiModel)

        mock_registry.list_models_by_type.return_value = [
            ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="1.2.3"
            )
        ]

        mock_registry.register_baseline.return_value = ModelRegistryEntry(
            model_id="model-002",
            model_type="lead_scoring",
            version="1.2.4"
        )

        # Test patch increment
        entry = version_manager.register_version(
            model=mock_model,
            model_type="lead_scoring",
            auto_increment="patch"
        )
        assert entry.version == "1.2.4"

        # Test minor increment
        mock_registry.register_baseline.return_value.version = "1.3.0"
        entry = version_manager.register_version(
            model=mock_model,
            model_type="lead_scoring",
            auto_increment="minor"
        )
        assert entry.version == "1.3.0"

        # Test major increment
        mock_registry.register_baseline.return_value.version = "2.0.0"
        entry = version_manager.register_version(
            model=mock_model,
            model_type="lead_scoring",
            auto_increment="major"
        )
        assert entry.version == "2.0.0"

    def test_get_version_history(self, version_manager, mock_registry) -> None:
        """Test retrieving version history for a model type."""
        mock_entries = [
            ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="1.0.0",
                timestamp=datetime(2023, 1, 1)
            ),
            ModelRegistryEntry(
                model_id="model-002",
                model_type="lead_scoring",
                version="1.1.0",
                timestamp=datetime(2023, 2, 1)
            ),
            ModelRegistryEntry(
                model_id="model-003",
                model_type="lead_scoring",
                version="2.0.0",
                timestamp=datetime(2023, 3, 1)
            )
        ]

        mock_registry.list_models_by_type.return_value = mock_entries

        history = version_manager.get_version_history("lead_scoring")

        assert len(history) == 3
        assert history[0].version == "1.0.0"
        assert history[-1].version == "2.0.0"
        # Should be sorted by version
        assert all(Version(history[i].version) < Version(history[i+1].version)
                  for i in range(len(history)-1))

    def test_rollback_to_version(self, version_manager, mock_registry) -> None:
        """Test rolling back to a specific version."""
        target_entry = ModelRegistryEntry(
            model_id="model-002",
            model_type="lead_scoring",
            version="1.1.0"
        )

        mock_registry.list_models_by_type.return_value = [target_entry]
        mock_registry.rollback_model.return_value = True

        success = version_manager.rollback_to_version("lead_scoring", "1.1.0")

        assert success is True
        mock_registry.rollback_model.assert_called_once_with("lead_scoring", "model-002")

    def test_rollback_to_nonexistent_version(self, version_manager, mock_registry) -> None:
        """Test rollback to non-existent version raises error."""
        mock_registry.list_models_by_type.return_value = []

        with pytest.raises(VersioningException, match="Version 9.9.9 not found"):
            version_manager.rollback_to_version("lead_scoring", "9.9.9")

    def test_compare_versions(self, version_manager, mock_registry) -> None:
        """Test comparing two model versions."""
        model_v1 = ModelRegistryEntry(
            model_id="model-001",
            model_type="lead_scoring",
            version="1.0.0",
            metrics={"accuracy": 0.85, "f1_score": 0.80}
        )

        model_v2 = ModelRegistryEntry(
            model_id="model-002",
            model_type="lead_scoring",
            version="2.0.0",
            metrics={"accuracy": 0.90, "f1_score": 0.88}
        )

        def mock_list_models(model_type):
            return [model_v1, model_v2]

        mock_registry.list_models_by_type.side_effect = mock_list_models

        comparison = version_manager.compare_versions(
            model_type="lead_scoring",
            version1="1.0.0",
            version2="2.0.0"
        )

        assert comparison.version1 == "1.0.0"
        assert comparison.version2 == "2.0.0"
        assert comparison.metrics_delta["accuracy"] == 0.05
        assert comparison.metrics_delta["f1_score"] == 0.08
        assert comparison.is_improvement is True

    def test_get_latest_stable_version(self, version_manager, mock_registry) -> None:
        """Test getting the latest stable version."""
        mock_entries = [
            ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="1.0.0",
                tags={"stable": "true"}
            ),
            ModelRegistryEntry(
                model_id="model-002",
                model_type="lead_scoring",
                version="2.0.0-beta",
                tags={"stable": "false"}
            ),
            ModelRegistryEntry(
                model_id="model-003",
                model_type="lead_scoring",
                version="1.5.0",
                tags={"stable": "true"}
            )
        ]

        mock_registry.list_models_by_type.return_value = mock_entries

        latest_stable = version_manager.get_latest_stable_version("lead_scoring")

        assert latest_stable.version == "1.5.0"
        assert latest_stable.tags["stable"] == "true"

    def test_deprecate_version(self, version_manager, mock_registry) -> None:
        """Test deprecating a model version."""
        mock_registry.list_models_by_type.return_value = [
            ModelRegistryEntry(
                model_id="model-001",
                model_type="lead_scoring",
                version="1.0.0"
            )
        ]

        mock_registry.client = Mock()
        mock_registry.client.set_model_version_tag.return_value = None

        success = version_manager.deprecate_version("lead_scoring", "1.0.0")

        assert success is True
        mock_registry.client.set_model_version_tag.assert_called()
