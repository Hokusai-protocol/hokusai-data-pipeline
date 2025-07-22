"""Integration tests for MLflow artifact storage configuration."""

import os
import pytest
import tempfile
import mlflow
from mlflow.tracking import MlflowClient
import numpy as np
import joblib


@pytest.fixture
def mlflow_client():
    """Create MLflow client with configured tracking URI."""
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "https://registry.hokus.ai/api/mlflow")
    client = MlflowClient(tracking_uri=tracking_uri)
    mlflow.set_tracking_uri(tracking_uri)
    return client


@pytest.fixture
def api_key():
    """Get API key from environment."""
    key = os.getenv("HOKUSAI_API_KEY")
    if not key:
        pytest.skip("HOKUSAI_API_KEY not set")
    return key


@pytest.fixture
def temp_model():
    """Create a temporary model file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        # Create a simple model
        model = {"type": "test", "version": "1.0", "data": np.array([1, 2, 3])}
        joblib.dump(model, f.name)
        yield f.name
    # Cleanup
    if os.path.exists(f.name):
        os.unlink(f.name)


class TestMLflowArtifactStorage:
    """Test MLflow artifact storage functionality."""
    
    def test_artifact_upload(self, mlflow_client, api_key, temp_model):
        """Test uploading model artifacts to S3."""
        # Set authentication
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
        
        # Create experiment
        experiment_name = f"test_artifacts_{os.getpid()}"
        try:
            experiment_id = mlflow_client.create_experiment(experiment_name)
        except Exception:
            # Experiment might already exist
            experiment = mlflow_client.get_experiment_by_name(experiment_name)
            experiment_id = experiment.experiment_id
        
        # Start run and log artifact
        with mlflow.start_run(experiment_id=experiment_id) as run:
            # Log the model file as artifact
            mlflow.log_artifact(temp_model, "model")
            
            # Log some metrics
            mlflow.log_metric("test_metric", 0.95)
            mlflow.log_param("test_param", "value")
            
            run_id = run.info.run_id
        
        # Verify artifact was uploaded
        run = mlflow_client.get_run(run_id)
        assert run.info.artifact_uri.startswith("s3://")
        
        # List artifacts
        artifacts = mlflow_client.list_artifacts(run_id, "model")
        assert len(artifacts) > 0
        assert any(a.path.endswith(".pkl") for a in artifacts)
    
    def test_artifact_download(self, mlflow_client, api_key):
        """Test downloading artifacts from S3."""
        # Set authentication
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
        
        # Create and upload a test artifact first
        experiment_name = f"test_download_{os.getpid()}"
        try:
            experiment_id = mlflow_client.create_experiment(experiment_name)
        except Exception:
            experiment = mlflow_client.get_experiment_by_name(experiment_name)
            experiment_id = experiment.experiment_id
        
        with mlflow.start_run(experiment_id=experiment_id) as run:
            # Create and log a test file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("Test artifact content")
                temp_path = f.name
            
            mlflow.log_artifact(temp_path, "test_dir")
            run_id = run.info.run_id
            
            # Clean up temp file
            os.unlink(temp_path)
        
        # Download artifacts
        with tempfile.TemporaryDirectory() as download_dir:
            mlflow_client.download_artifacts(run_id, "test_dir", download_dir)
            
            # Verify downloaded content
            downloaded_files = os.listdir(os.path.join(download_dir, "test_dir"))
            assert len(downloaded_files) > 0
            
            # Read and verify content
            with open(os.path.join(download_dir, "test_dir", downloaded_files[0])) as f:
                content = f.read()
                assert content == "Test artifact content"
    
    def test_artifact_error_handling(self, mlflow_client, api_key):
        """Test error handling for artifact operations."""
        # Test with invalid run ID
        with pytest.raises(Exception) as exc_info:
            mlflow_client.list_artifacts("invalid-run-id")
        
        # The error should indicate the run was not found
        assert "not found" in str(exc_info.value).lower() or "404" in str(exc_info.value)
    
    def test_large_artifact_upload(self, mlflow_client, api_key):
        """Test uploading larger artifacts to ensure S3 multipart works."""
        # Set authentication
        os.environ["MLFLOW_TRACKING_TOKEN"] = api_key
        
        # Create a larger file (10MB)
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            # Write 10MB of random data
            data = np.random.bytes(10 * 1024 * 1024)
            f.write(data)
            large_file = f.name
        
        try:
            experiment_name = f"test_large_{os.getpid()}"
            try:
                experiment_id = mlflow_client.create_experiment(experiment_name)
            except Exception:
                experiment = mlflow_client.get_experiment_by_name(experiment_name)
                experiment_id = experiment.experiment_id
            
            with mlflow.start_run(experiment_id=experiment_id) as run:
                # This should trigger multipart upload if file is large enough
                mlflow.log_artifact(large_file, "large_files")
                run_id = run.info.run_id
            
            # Verify upload succeeded
            artifacts = mlflow_client.list_artifacts(run_id, "large_files")
            assert len(artifacts) > 0
            assert artifacts[0].file_size == 10 * 1024 * 1024
        
        finally:
            # Clean up
            if os.path.exists(large_file):
                os.unlink(large_file)


@pytest.mark.skipif(
    not os.getenv("HOKUSAI_API_KEY"),
    reason="Requires HOKUSAI_API_KEY environment variable"
)
class TestArtifactEndpoints:
    """Test artifact-specific endpoints."""
    
    def test_artifact_proxy_routing(self):
        """Test that artifact endpoints are properly routed."""
        import requests
        
        api_key = os.getenv("HOKUSAI_API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}
        
        # Test artifact endpoint availability
        response = requests.get(
            "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow-artifacts/artifacts",
            headers=headers
        )
        
        # Should not return 404 (endpoint not found)
        # May return 400/403 if no valid path provided, but endpoint should exist
        assert response.status_code != 404, f"Artifact endpoint returned 404: {response.text}"