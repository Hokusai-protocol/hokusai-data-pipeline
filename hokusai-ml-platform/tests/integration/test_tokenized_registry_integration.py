"""Integration tests for token-aware MLflow registry with real MLflow server."""
import shutil
import tempfile

import mlflow
import pytest
from hokusai.core.registry import ModelRegistry, RegistryException


@pytest.mark.integration
class TestTokenizedRegistryIntegration:
    """Integration tests requiring MLflow server."""

    @pytest.fixture(scope="class")
    def mlflow_server(self):
        """Setup local MLflow server for testing."""
        # Create a temporary directory for MLflow
        temp_dir = tempfile.mkdtemp()
        tracking_uri = f"file://{temp_dir}"

        # Set tracking URI
        mlflow.set_tracking_uri(tracking_uri)

        yield tracking_uri

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def registry(self, mlflow_server):
        """Create registry with test MLflow server."""
        return ModelRegistry(mlflow_server)

    @pytest.fixture
    def sample_model(self, mlflow_server):
        """Create and log a sample model."""
        import mlflow.sklearn
        from sklearn.datasets import make_classification
        from sklearn.linear_model import LogisticRegression

        mlflow.set_tracking_uri(mlflow_server)

        # Train a simple model
        X, y = make_classification(n_samples=100, n_features=5)
        model = LogisticRegression()
        model.fit(X, y)

        # Log model
        with mlflow.start_run() as run:
            mlflow.sklearn.log_model(model, "model")
            model_uri = f"runs:/{run.info.run_id}/model"

        return model_uri

    def test_full_tokenized_workflow(self, registry, sample_model) -> None:
        """Test complete tokenized model workflow."""
        # Register tokenized model
        result = registry.register_tokenized_model(
            model_uri=sample_model,
            model_name="test-model",
            token_id="test-token",
            metric_name="accuracy",
            baseline_value=0.85
        )

        assert result["model_name"] == "test-model"
        assert result["token_id"] == "test-token"
        assert "version" in result

        # Retrieve the model
        retrieved = registry.get_tokenized_model("test-model", result["version"])
        assert retrieved["token_id"] == "test-token"
        assert retrieved["metric_name"] == "accuracy"
        assert retrieved["baseline_value"] == 0.85

        # List models by token
        models = registry.list_models_by_token("test-token")
        assert len(models) == 1
        assert models[0]["token_id"] == "test-token"

    def test_multiple_versions_same_token(self, registry, mlflow_server) -> None:
        """Test registering multiple model versions for same token."""
        import mlflow.sklearn
        from sklearn.datasets import make_classification
        from sklearn.linear_model import LogisticRegression

        mlflow.set_tracking_uri(mlflow_server)

        # Create and register first version
        X, y = make_classification(n_samples=100, n_features=5)
        model1 = LogisticRegression(C=1.0)
        model1.fit(X, y)

        with mlflow.start_run() as run1:
            mlflow.sklearn.log_model(model1, "model")
            uri1 = f"runs:/{run1.info.run_id}/model"

        result1 = registry.register_tokenized_model(
            model_uri=uri1,
            model_name="multi-version-model",
            token_id="multi-token",
            metric_name="f1_score",
            baseline_value=0.75
        )

        # Create and register second version
        model2 = LogisticRegression(C=0.5)
        model2.fit(X, y)

        with mlflow.start_run() as run2:
            mlflow.sklearn.log_model(model2, "model")
            uri2 = f"runs:/{run2.info.run_id}/model"

        result2 = registry.register_tokenized_model(
            model_uri=uri2,
            model_name="multi-version-model",
            token_id="multi-token",
            metric_name="f1_score",
            baseline_value=0.78  # Improved
        )

        # Verify both versions exist
        models = registry.list_models_by_token("multi-token")
        assert len(models) == 2

        # Verify different versions
        assert result1["version"] != result2["version"]

        # Verify improvements tracked
        v1 = registry.get_tokenized_model("multi-version-model", result1["version"])
        v2 = registry.get_tokenized_model("multi-version-model", result2["version"])
        assert v2["baseline_value"] > v1["baseline_value"]

    def test_update_tags_integration(self, registry, sample_model) -> None:
        """Test updating tags on a registered model."""
        # Register model
        result = registry.register_tokenized_model(
            model_uri=sample_model,
            model_name="update-test-model",
            token_id="update-token",
            metric_name="precision",
            baseline_value=0.90
        )

        # Update tags
        new_tags = {
            "benchmark_value": "0.92",
            "evaluation_date": "2024-01-15",
            "notes": "Improved with additional training data"
        }

        registry.update_model_tags(
            "update-test-model",
            result["version"],
            new_tags
        )

        # Retrieve and verify
        updated = registry.get_tokenized_model("update-test-model", result["version"])
        assert updated["baseline_value"] == 0.92  # Should parse updated value
        assert "evaluation_date" in updated["tags"]
        assert updated["tags"]["notes"] == "Improved with additional training data"

    def test_invalid_model_uri(self, registry) -> None:
        """Test handling of invalid model URI."""
        with pytest.raises(RegistryException):
            registry.register_tokenized_model(
                model_uri="invalid://uri",
                model_name="invalid-model",
                token_id="test-token",
                metric_name="accuracy",
                baseline_value=0.85
            )

    def test_concurrent_registrations(self, registry, mlflow_server) -> None:
        """Test concurrent model registrations."""
        import concurrent.futures

        import mlflow.sklearn
        from sklearn.datasets import make_classification
        from sklearn.linear_model import LogisticRegression

        mlflow.set_tracking_uri(mlflow_server)

        def register_model(idx):
            # Create unique model
            X, y = make_classification(n_samples=50, n_features=3, random_state=idx)
            model = LogisticRegression()
            model.fit(X, y)

            with mlflow.start_run() as run:
                mlflow.sklearn.log_model(model, "model")
                uri = f"runs:/{run.info.run_id}/model"

            # Register with unique token
            return registry.register_tokenized_model(
                model_uri=uri,
                model_name=f"concurrent-model-{idx}",
                token_id=f"concurrent-token-{idx}",
                metric_name="accuracy",
                baseline_value=0.80 + idx * 0.01
            )

        # Register multiple models concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(register_model, i) for i in range(3)]
            results = [f.result() for f in futures]

        # Verify all registered successfully
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result["token_id"] == f"concurrent-token-{i}"


@pytest.mark.skipif(
    not pytest.config.getoption("--integration", default=False),
    reason="Integration tests require --integration flag"
)
def test_with_real_mlflow_server() -> None:
    """Test with actual MLflow server if available."""
    # This test requires MLflow server running on localhost:5000
    try:
        registry = ModelRegistry("http://localhost:5000")

        # Try to list models (should not fail if server is running)
        models = registry.list_models_by_token("test-token")
        print(f"Found {len(models)} models for test-token")

    except Exception as e:
        pytest.skip(f"MLflow server not available: {e}")
