"""Test for ExperimentManager constructor API compatibility fix."""

import pytest
from unittest.mock import MagicMock, patch
import os

# Set mock mode to avoid MLflow connection issues during testing
os.environ["HOKUSAI_MOCK_MODE"] = "true"

from hokusai.tracking.experiments import ExperimentManager


class TestExperimentManagerConstructorFix:
    """Test that ExperimentManager constructor works with both patterns."""

    def test_registry_as_first_positional_argument(self):
        """Test that ExperimentManager(registry) works as expected."""
        # Create a mock registry
        registry = MagicMock()
        registry.tracking_uri = "http://test.mlflow.com"
        
        # This should work without error
        manager = ExperimentManager(registry)
        
        # Should use registry's tracking_uri
        assert manager.tracking_uri == "http://test.mlflow.com"
        assert manager.registry == registry
        # Should use default experiment name
        assert manager.experiment_name == "hokusai_model_improvements"

    def test_experiment_name_as_first_positional_argument(self):
        """Test that ExperimentManager(experiment_name) still works."""
        # This should work without error
        manager = ExperimentManager("my_experiment")
        
        # Should use provided experiment name
        assert manager.experiment_name == "my_experiment"
        assert manager.registry is None
        # Should use default tracking URI
        assert manager.tracking_uri == "http://registry.hokus.ai/mlflow"

    def test_registry_as_named_parameter(self):
        """Test that ExperimentManager(registry=registry) works."""
        registry = MagicMock()
        registry.tracking_uri = "http://test.mlflow.com"
        
        manager = ExperimentManager(registry=registry)
        
        assert manager.registry == registry
        assert manager.tracking_uri == "http://test.mlflow.com"
        assert manager.experiment_name == "hokusai_model_improvements"

    def test_experiment_name_as_named_parameter(self):
        """Test that ExperimentManager(experiment_name=name) works."""
        manager = ExperimentManager(experiment_name="my_experiment")
        
        assert manager.experiment_name == "my_experiment"
        assert manager.registry is None
        assert manager.tracking_uri == "http://registry.hokus.ai/mlflow"

    def test_both_parameters_named(self):
        """Test that ExperimentManager(experiment_name=name, registry=registry) works."""
        registry = MagicMock()
        registry.tracking_uri = "http://test.mlflow.com"
        
        manager = ExperimentManager(experiment_name="my_experiment", registry=registry)
        
        assert manager.experiment_name == "my_experiment"
        assert manager.registry == registry
        assert manager.tracking_uri == "http://test.mlflow.com"

    def test_both_parameters_positional(self):
        """Test that ExperimentManager(experiment_name, registry) works."""
        registry = MagicMock()
        registry.tracking_uri = "http://test.mlflow.com"
        
        manager = ExperimentManager("my_experiment", registry=registry)
        
        assert manager.experiment_name == "my_experiment"
        assert manager.registry == registry
        assert manager.tracking_uri == "http://test.mlflow.com"

    def test_invalid_first_parameter_type(self):
        """Test that invalid first parameter type raises appropriate error."""
        # Pass something that's not a string or registry
        with pytest.raises(ValueError, match="First parameter must be"):
            ExperimentManager(123)

    def test_registry_without_tracking_uri(self):
        """Test registry without tracking_uri attribute."""
        registry = MagicMock()
        # Remove tracking_uri attribute
        delattr(registry, 'tracking_uri')
        
        manager = ExperimentManager(registry)
        
        # Should fall back to default tracking URI
        assert manager.tracking_uri == "http://registry.hokus.ai/mlflow"
        assert manager.registry == registry

    def test_mlflow_tracking_uri_parameter(self):
        """Test that mlflow_tracking_uri parameter works."""
        manager = ExperimentManager(mlflow_tracking_uri="http://custom.mlflow.com")
        
        assert manager.tracking_uri == "http://custom.mlflow.com"

    def test_parameter_precedence(self):
        """Test parameter precedence: mlflow_tracking_uri > registry.tracking_uri > env var > default."""
        registry = MagicMock()
        registry.tracking_uri = "http://registry.mlflow.com"
        
        # mlflow_tracking_uri should take precedence
        manager = ExperimentManager(
            registry=registry,
            mlflow_tracking_uri="http://explicit.mlflow.com"
        )
        
        assert manager.tracking_uri == "http://explicit.mlflow.com"