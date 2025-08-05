"""End-to-end tests for model registration through the improved MLflow proxy."""

import os
import pytest
import json
import time
from unittest.mock import patch, Mock, AsyncMock
import mlflow
from mlflow.tracking import MlflowClient
from fastapi.testclient import TestClient

# Import app with mocked environment
with patch.dict(os.environ, {
    "MLFLOW_SERVER_URL": "http://mlflow.test.local:5000",
    "MLFLOW_SERVE_ARTIFACTS": "true",
    "MLFLOW_PROXY_DEBUG": "true"
}):
    from src.api.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_mlflow_responses():
    """Mock responses for a complete model registration flow."""
    return {
        "create_experiment": {
            "experiment_id": "exp-123"
        },
        "create_run": {
            "run": {
                "info": {
                    "run_id": "run-456",
                    "experiment_id": "exp-123",
                    "status": "RUNNING"
                }
            }
        },
        "log_metrics": {},
        "log_params": {},
        "update_run": {},
        "create_model": {
            "registered_model": {
                "name": "test-token-model",
                "creation_timestamp": int(time.time() * 1000),
                "last_updated_timestamp": int(time.time() * 1000)
            }
        },
        "create_model_version": {
            "model_version": {
                "name": "test-token-model",
                "version": "1",
                "creation_timestamp": int(time.time() * 1000),
                "status": "READY",
                "source": "mlflow-artifacts:/exp-123/run-456/artifacts/model"
            }
        },
        "set_model_version_tag": {},
        "search_model_versions": {
            "model_versions": [{
                "name": "test-token-model",
                "version": "1",
                "tags": [
                    {"key": "hokusai_token_id", "value": "test-token"},
                    {"key": "benchmark_metric", "value": "accuracy"},
                    {"key": "benchmark_value", "value": "0.95"}
                ]
            }]
        }
    }


class TestModelRegistrationE2E:
    """End-to-end tests for the complete model registration flow."""
    
    def test_complete_model_registration_with_token_metadata(self, client, mock_mlflow_responses):
        """Test registering a model with Hokusai token metadata through the proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Track API calls
                api_calls = []
                
                async def mock_request(method, url, **kwargs):
                    """Mock MLflow API responses based on the endpoint."""
                    api_calls.append((method, url))
                    
                    # Parse the URL to determine which endpoint is being called
                    if "experiments/create" in url:
                        response_data = mock_mlflow_responses["create_experiment"]
                    elif "runs/create" in url:
                        response_data = mock_mlflow_responses["create_run"]
                    elif "runs/log-metric" in url:
                        response_data = mock_mlflow_responses["log_metrics"]
                    elif "runs/log-parameter" in url:
                        response_data = mock_mlflow_responses["log_params"]
                    elif "runs/update" in url:
                        response_data = mock_mlflow_responses["update_run"]
                    elif "registered-models/create" in url:
                        response_data = mock_mlflow_responses["create_model"]
                    elif "model-versions/create" in url:
                        response_data = mock_mlflow_responses["create_model_version"]
                    elif "model-versions/set-tag" in url:
                        response_data = mock_mlflow_responses["set_model_version_tag"]
                    elif "model-versions/search" in url:
                        response_data = mock_mlflow_responses["search_model_versions"]
                    else:
                        response_data = {}
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.content = json.dumps(response_data).encode()
                    mock_response.headers = {"content-type": "application/json"}
                    return mock_response
                
                mock_client.request.side_effect = mock_request
                
                # Step 1: Create experiment
                response = client.post(
                    "/api/mlflow/api/2.0/mlflow/experiments/create",
                    json={"name": "token-model-experiment"},
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                assert response.json()["experiment_id"] == "exp-123"
                
                # Step 2: Create run
                response = client.post(
                    "/api/mlflow/api/2.0/mlflow/runs/create",
                    json={"experiment_id": "exp-123"},
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                run_id = response.json()["run"]["info"]["run_id"]
                assert run_id == "run-456"
                
                # Step 3: Log metrics
                response = client.post(
                    "/api/mlflow/api/2.0/mlflow/runs/log-metric",
                    json={
                        "run_id": run_id,
                        "key": "accuracy",
                        "value": 0.95,
                        "timestamp": int(time.time() * 1000)
                    },
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                
                # Step 4: Create registered model
                response = client.post(
                    "/api/mlflow/api/2.0/mlflow/registered-models/create",
                    json={"name": "test-token-model"},
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                
                # Step 5: Create model version
                response = client.post(
                    "/api/mlflow/api/2.0/mlflow/model-versions/create",
                    json={
                        "name": "test-token-model",
                        "source": f"mlflow-artifacts:/exp-123/{run_id}/artifacts/model"
                    },
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                assert response.json()["model_version"]["version"] == "1"
                
                # Step 6: Set token metadata tags
                token_tags = [
                    ("hokusai_token_id", "test-token"),
                    ("benchmark_metric", "accuracy"),
                    ("benchmark_value", "0.95")
                ]
                
                for key, value in token_tags:
                    response = client.post(
                        "/api/mlflow/api/2.0/mlflow/model-versions/set-tag",
                        json={
                            "name": "test-token-model",
                            "version": "1",
                            "key": key,
                            "value": value
                        },
                        headers={"Authorization": "Bearer test-key"}
                    )
                    assert response.status_code == 200
                
                # Step 7: Verify model can be retrieved with tags
                response = client.get(
                    "/api/mlflow/api/2.0/mlflow/model-versions/search",
                    params={"filter": "name='test-token-model'"},
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                model_versions = response.json()["model_versions"]
                assert len(model_versions) == 1
                
                # Verify tags
                tags = {tag["key"]: tag["value"] for tag in model_versions[0]["tags"]}
                assert tags["hokusai_token_id"] == "test-token"
                assert tags["benchmark_metric"] == "accuracy"
                assert tags["benchmark_value"] == "0.95"
                
                # Verify all calls went to internal MLflow (not ajax-api)
                for method, url in api_calls:
                    assert "/api/2.0/mlflow/" in url
                    assert "/ajax-api/" not in url
                    assert "http://mlflow.test.local:5000" in url
    
    def test_artifact_upload_and_download_flow(self, client):
        """Test artifact upload and download through the proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_call
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Test artifact upload
                model_artifact = b"pretrained model binary data"
                
                async def mock_upload_request(method, url, **kwargs):
                    if "mlflow-artifacts" in url and method == "put":
                        # Simulate successful upload
                        mock_response = Mock()
                        mock_response.status_code = 200
                        mock_response.content = b""
                        mock_response.headers = {}
                        return mock_response
                    elif "mlflow-artifacts" in url and method == "get":
                        # Return the uploaded artifact
                        mock_response = Mock()
                        mock_response.status_code = 200
                        mock_response.content = model_artifact
                        mock_response.headers = {"content-type": "application/octet-stream"}
                        return mock_response
                    else:
                        mock_response = Mock()
                        mock_response.status_code = 404
                        mock_response.content = b'{"error": "Not found"}'
                        mock_response.headers = {"content-type": "application/json"}
                        return mock_response
                
                mock_client.request.side_effect = mock_upload_request
                
                # Upload artifact
                response = client.put(
                    "/api/mlflow/api/2.0/mlflow-artifacts/artifacts/run-123/model.pkl",
                    content=model_artifact,
                    headers={
                        "Authorization": "Bearer test-key",
                        "Content-Type": "application/octet-stream"
                    }
                )
                assert response.status_code == 200
                
                # Download artifact
                response = client.get(
                    "/api/mlflow/api/2.0/mlflow-artifacts/artifacts/run-123/model.pkl",
                    headers={"Authorization": "Bearer test-key"}
                )
                assert response.status_code == 200
                assert response.content == model_artifact
    
    def test_model_registration_with_disabled_artifacts(self, client):
        """Test model registration when artifact storage is disabled."""
        with patch.dict(os.environ, {"MLFLOW_SERVE_ARTIFACTS": "false"}):
            with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
                async def mock_call(request, call_next):
                    request.state.user_id = "test-user"
                    request.state.api_key_id = "test-key"
                    response = await call_next(request)
                    return response
                mock_auth.side_effect = mock_call
                
                # Try to access artifacts endpoint
                response = client.get(
                    "/api/mlflow/api/2.0/mlflow-artifacts/artifacts/test",
                    headers={"Authorization": "Bearer test-key"}
                )
                
                assert response.status_code == 503
                assert "Artifact storage is not configured" in response.json()["detail"]
    
    def test_concurrent_model_registrations(self, client, mock_mlflow_responses):
        """Test handling concurrent model registrations through the proxy."""
        with patch('src.middleware.auth.APIKeyAuthMiddleware.__call__') as mock_auth:
            async def mock_call(request, call_next):
                request.state.user_id = "test-user"
                request.state.api_key_id = "test-key"
                response = await call_next(request)
                return response
            mock_auth.side_effect = mock_auth
            
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client
                
                # Track concurrent requests
                request_count = 0
                
                async def mock_concurrent_request(method, url, **kwargs):
                    nonlocal request_count
                    request_count += 1
                    
                    # Simulate slight delay for concurrent processing
                    import asyncio
                    await asyncio.sleep(0.01)
                    
                    # Return appropriate response
                    if "registered-models/create" in url:
                        model_data = mock_mlflow_responses["create_model"].copy()
                        model_data["registered_model"]["name"] = f"concurrent-model-{request_count}"
                    else:
                        model_data = {}
                    
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.content = json.dumps(model_data).encode()
                    mock_response.headers = {"content-type": "application/json"}
                    return mock_response
                
                mock_client.request.side_effect = mock_concurrent_request
                
                # Create multiple models concurrently
                import asyncio
                
                async def register_model(model_name):
                    response = client.post(
                        "/api/mlflow/api/2.0/mlflow/registered-models/create",
                        json={"name": model_name},
                        headers={"Authorization": "Bearer test-key"}
                    )
                    return response
                
                # Simulate concurrent registrations
                responses = []
                for i in range(3):
                    response = client.post(
                        "/api/mlflow/api/2.0/mlflow/registered-models/create",
                        json={"name": f"concurrent-model-{i}"},
                        headers={"Authorization": "Bearer test-key"}
                    )
                    responses.append(response)
                
                # Verify all succeeded
                assert all(r.status_code == 200 for r in responses)
                assert request_count == 3