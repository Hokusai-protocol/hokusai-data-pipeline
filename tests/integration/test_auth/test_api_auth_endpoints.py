"""Integration tests for API key management endpoints."""

import datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.api_key_service import APIKey


class TestAPIAuthEndpoints:
    """Test cases for API authentication endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_api_key_service(self):
        """Mock API key service."""
        with patch('src.api.auth.api_key_service') as mock_service:
            yield mock_service

    @pytest.fixture
    def authenticated_client(self, client, mock_api_key_service):
        """Create authenticated test client."""
        # Mock authentication middleware
        with patch('src.middleware.auth.APIKeyAuthMiddleware.dispatch') as mock_dispatch:
            # Make middleware always pass
            async def pass_through(request, call_next):
                request.state.user_id = "test_user_123"
                request.state.api_key_id = "test_key_123"
                response = await call_next(request)
                return response
            
            mock_dispatch.side_effect = pass_through
            yield client

    def test_create_api_key_success(self, authenticated_client, mock_api_key_service):
        """Test successful API key creation."""
        # Arrange
        mock_key = APIKey(
            key="hk_live_new_test_key_123",
            key_id="key123",
            user_id="test_user_123",
            name="Production API Key",
            is_active=True,
            created_at=datetime.datetime.utcnow(),
            rate_limit_per_hour=1000
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        response = authenticated_client.post(
            "/api/v1/auth/keys",
            json={
                "name": "Production API Key",
                "environment": "production",
                "rate_limit_per_hour": 1000
            }
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["key"].startswith("hk_live_")
        assert data["key_id"] == "key123"
        assert data["name"] == "Production API Key"
        assert "created_at" in data
        assert data["message"] == "Save this key securely. It will not be shown again."

    def test_create_api_key_with_expiration(self, authenticated_client, mock_api_key_service):
        """Test creating API key with expiration date."""
        # Arrange
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        mock_key = APIKey(
            key="hk_live_temp_key_123",
            key_id="key123",
            user_id="test_user_123",
            name="Temporary Key",
            is_active=True,
            created_at=datetime.datetime.utcnow(),
            expires_at=expires_at
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        response = authenticated_client.post(
            "/api/v1/auth/keys",
            json={
                "name": "Temporary Key",
                "expires_in_days": 30
            }
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "expires_at" in data

    def test_create_api_key_with_ip_restriction(self, authenticated_client, mock_api_key_service):
        """Test creating API key with IP restrictions."""
        # Arrange
        allowed_ips = ["192.168.1.1", "10.0.0.1"]
        mock_key = APIKey(
            key="hk_live_restricted_key_123",
            key_id="key123",
            user_id="test_user_123",
            name="IP Restricted Key",
            is_active=True,
            created_at=datetime.datetime.utcnow(),
            allowed_ips=allowed_ips
        )
        mock_api_key_service.generate_api_key.return_value = mock_key
        
        # Act
        response = authenticated_client.post(
            "/api/v1/auth/keys",
            json={
                "name": "IP Restricted Key",
                "allowed_ips": allowed_ips
            }
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["allowed_ips"] == allowed_ips

    def test_create_api_key_validation_error(self, authenticated_client):
        """Test API key creation with validation errors."""
        # Act
        response = authenticated_client.post(
            "/api/v1/auth/keys",
            json={
                "name": "",  # Empty name
                "rate_limit_per_hour": -1  # Invalid rate limit
            }
        )
        
        # Assert
        assert response.status_code == 422
        assert "validation error" in response.json()["detail"][0]["msg"].lower()

    def test_list_api_keys_success(self, authenticated_client, mock_api_key_service):
        """Test listing user's API keys."""
        # Arrange
        mock_keys = [
            Mock(
                key_id="key1",
                name="Production Key",
                key_prefix="hk_live_abc***",
                created_at=datetime.datetime.utcnow(),
                last_used_at=datetime.datetime.utcnow(),
                is_active=True,
                expires_at=None
            ),
            Mock(
                key_id="key2",
                name="Test Key",
                key_prefix="hk_test_def***",
                created_at=datetime.datetime.utcnow(),
                last_used_at=None,
                is_active=True,
                expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=7)
            )
        ]
        mock_api_key_service.list_api_keys.return_value = mock_keys
        
        # Act
        response = authenticated_client.get("/api/v1/auth/keys")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["keys"]) == 2
        assert data["keys"][0]["key_id"] == "key1"
        assert data["keys"][0]["name"] == "Production Key"
        assert data["keys"][0]["key_prefix"] == "hk_live_abc***"
        assert data["keys"][1]["key_id"] == "key2"
        assert data["total"] == 2

    def test_list_api_keys_empty(self, authenticated_client, mock_api_key_service):
        """Test listing API keys when user has none."""
        # Arrange
        mock_api_key_service.list_api_keys.return_value = []
        
        # Act
        response = authenticated_client.get("/api/v1/auth/keys")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["keys"]) == 0
        assert data["total"] == 0

    def test_revoke_api_key_success(self, authenticated_client, mock_api_key_service):
        """Test successful API key revocation."""
        # Arrange
        key_id = "key123"
        mock_api_key_service.revoke_api_key.return_value = True
        
        # Act
        response = authenticated_client.delete(f"/api/v1/auth/keys/{key_id}")
        
        # Assert
        assert response.status_code == 200
        assert response.json()["message"] == "API key revoked successfully"
        mock_api_key_service.revoke_api_key.assert_called_once_with("test_user_123", key_id)

    def test_revoke_api_key_not_found(self, authenticated_client, mock_api_key_service):
        """Test revoking non-existent API key."""
        # Arrange
        key_id = "nonexistent_key"
        mock_api_key_service.revoke_api_key.side_effect = APIKeyNotFoundError("Key not found")
        
        # Act
        response = authenticated_client.delete(f"/api/v1/auth/keys/{key_id}")
        
        # Assert
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"

    def test_revoke_api_key_wrong_user(self, authenticated_client, mock_api_key_service):
        """Test revoking API key belonging to another user."""
        # Arrange
        key_id = "other_user_key"
        mock_api_key_service.revoke_api_key.side_effect = APIKeyValidationError("Unauthorized")
        
        # Act
        response = authenticated_client.delete(f"/api/v1/auth/keys/{key_id}")
        
        # Assert
        assert response.status_code == 403
        assert response.json()["detail"] == "Not authorized to revoke this key"

    def test_rotate_api_key_success(self, authenticated_client, mock_api_key_service):
        """Test successful API key rotation."""
        # Arrange
        key_id = "key123"
        mock_new_key = APIKey(
            key="hk_live_rotated_key_456",
            key_id="key456",
            user_id="test_user_123",
            name="Production API Key",
            is_active=True,
            created_at=datetime.datetime.utcnow(),
            rate_limit_per_hour=1000
        )
        mock_api_key_service.rotate_api_key.return_value = mock_new_key
        
        # Act
        response = authenticated_client.post(f"/api/v1/auth/keys/{key_id}/rotate")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["key"].startswith("hk_live_")
        assert data["key_id"] == "key456"
        assert data["message"] == "Key rotated successfully. Save the new key securely."

    def test_rotate_api_key_not_found(self, authenticated_client, mock_api_key_service):
        """Test rotating non-existent API key."""
        # Arrange
        key_id = "nonexistent_key"
        mock_api_key_service.rotate_api_key.side_effect = APIKeyNotFoundError("Key not found")
        
        # Act
        response = authenticated_client.post(f"/api/v1/auth/keys/{key_id}/rotate")
        
        # Assert
        assert response.status_code == 404
        assert response.json()["detail"] == "API key not found"

    def test_get_api_key_usage_stats(self, authenticated_client, mock_api_key_service):
        """Test getting API key usage statistics."""
        # Arrange
        key_id = "key123"
        mock_stats = {
            "key_id": key_id,
            "total_requests": 1500,
            "requests_today": 250,
            "requests_this_hour": 45,
            "average_response_time_ms": 123,
            "error_rate": 0.02,
            "top_endpoints": [
                {"endpoint": "/api/v1/models", "count": 500},
                {"endpoint": "/api/v1/evaluate", "count": 300}
            ]
        }
        mock_api_key_service.get_usage_stats.return_value = mock_stats
        
        # Act
        response = authenticated_client.get(f"/api/v1/auth/keys/{key_id}/usage")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["key_id"] == key_id
        assert data["total_requests"] == 1500
        assert data["requests_today"] == 250
        assert len(data["top_endpoints"]) == 2

    def test_unauthenticated_request_blocked(self, client):
        """Test that unauthenticated requests are blocked."""
        # Act
        response = client.post(
            "/api/v1/auth/keys",
            json={"name": "Test Key"}
        )
        
        # Assert
        assert response.status_code == 401
        assert response.json()["detail"] == "API key required"


class TestAPIKeyValidation:
    """Test cases for API key validation in requests."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_api_key_in_header(self, client, mock_api_key_service):
        """Test API key validation from Authorization header."""
        # Arrange
        api_key = "hk_live_test_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123"
        )
        
        # Act
        response = client.get(
            "/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        # Assert
        assert response.status_code != 401  # Not unauthorized

    def test_api_key_in_query_param(self, client, mock_api_key_service):
        """Test API key validation from query parameter."""
        # Arrange
        api_key = "hk_live_test_key_123"
        mock_api_key_service.validate_api_key.return_value = Mock(
            is_valid=True,
            key_id="key123",
            user_id="user123"
        )
        
        # Act
        response = client.get(f"/api/v1/models?api_key={api_key}")
        
        # Assert
        assert response.status_code != 401  # Not unauthorized

    def test_invalid_api_key_format(self, client):
        """Test rejection of invalid API key format."""
        # Act
        response = client.get(
            "/api/v1/models",
            headers={"Authorization": "Bearer invalid_key_format"}
        )
        
        # Assert
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()