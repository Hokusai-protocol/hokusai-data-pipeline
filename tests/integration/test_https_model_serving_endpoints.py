"""Integration tests for HTTPS model serving endpoints.

These tests verify that the model serving endpoints are accessible via HTTPS
and that the ALB routing rules are correctly configured.

This test suite was created to prevent regression of the 404 bug where
HTTPS listener rules were missing from the ALB configuration.
"""

import os

import pytest
import requests

# Test configuration
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.hokus.ai")
API_KEY = os.getenv("HOKUSAI_API_KEY")  # Must be set for tests to run

# Skip all tests if no API key is provided
pytestmark = pytest.mark.skipif(not API_KEY, reason="HOKUSAI_API_KEY environment variable not set")


class TestHTTPSModelServingEndpoints:
    """Test HTTPS access to model serving endpoints.

    These tests ensure that:
    1. HTTPS requests don't return 404
    2. Proper authentication is enforced
    3. Routes are accessible via the correct paths
    """

    def get_headers(self, include_auth: bool = True) -> dict:
        """Get request headers with optional authentication."""
        headers = {"Content-Type": "application/json"}
        if include_auth and API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"
        return headers

    def test_https_connection_works(self):
        """Verify HTTPS connection to API base URL works."""
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)

        # Should not return 404
        assert (
            response.status_code != 404
        ), f"Got 404 on /health endpoint. Response: {response.text}"

        # Should return valid JSON, not plain text
        assert response.headers.get("content-type", "").startswith(
            "application/json"
        ), f"Expected JSON response, got: {response.headers.get('content-type')}"

    def test_model_info_endpoint_https(self):
        """Test GET /api/v1/models/{model_id}/info via HTTPS."""
        model_id = "21"  # Sales Lead Scoring Model
        url = f"{API_BASE_URL}/api/v1/models/{model_id}/info"

        response = requests.get(url, headers=self.get_headers(), timeout=10)

        # Should NOT return 404 (the bug we're fixing)
        assert response.status_code != 404, (
            f"Got 404 on model info endpoint. "
            f"This suggests HTTPS listener rules are missing. "
            f"Response: {response.text}"
        )

        # Should be either 200 (success) or 401 (auth required)
        assert response.status_code in [
            200,
            401,
            403,
        ], f"Expected 200, 401, or 403, got {response.status_code}. Response: {response.text}"

        # Should return JSON, not plain text
        content_type = response.headers.get("content-type", "")
        assert (
            "application/json" in content_type or "json" in content_type.lower()
        ), f"Expected JSON response, got content-type: {content_type}, body: {response.text[:200]}"

    def test_model_predict_endpoint_https(self):
        """Test POST /api/v1/models/{model_id}/predict via HTTPS."""
        model_id = "21"
        url = f"{API_BASE_URL}/api/v1/models/{model_id}/predict"

        # Sample prediction request
        payload = {
            "inputs": {"company_size": 500, "industry": "Technology", "engagement_score": 75}
        }

        response = requests.post(url, json=payload, headers=self.get_headers(), timeout=30)

        # Should NOT return 404
        assert (
            response.status_code != 404
        ), f"Got 404 on predict endpoint. Response: {response.text}"

        # Should be either 200 (success), 401 (auth), or 400/422 (validation error)
        assert response.status_code in [200, 400, 401, 403, 422], (
            f"Expected 200, 400, 401, 403, or 422, "
            f"got {response.status_code}. Response: {response.text}"
        )

    def test_model_health_endpoint_https(self):
        """Test GET /api/v1/models/{model_id}/health via HTTPS."""
        model_id = "21"
        url = f"{API_BASE_URL}/api/v1/models/{model_id}/health"

        response = requests.get(url, headers=self.get_headers(), timeout=10)

        # Should NOT return 404
        assert (
            response.status_code != 404
        ), f"Got 404 on model health endpoint. Response: {response.text}"

        # Should return valid status code
        assert response.status_code in [
            200,
            401,
            403,
        ], f"Expected 200, 401, or 403, got {response.status_code}. Response: {response.text}"

    def test_authentication_required(self):
        """Verify that endpoints require authentication."""
        model_id = "21"
        url = f"{API_BASE_URL}/api/v1/models/{model_id}/info"

        # Request WITHOUT API key
        response = requests.get(url, headers=self.get_headers(include_auth=False), timeout=10)

        # Should NOT return 404 (even without auth)
        assert (
            response.status_code != 404
        ), "Got 404 when testing authentication. This suggests routing issue, not auth issue."

        # Should return 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in [401, 403], (
            f"Expected 401 or 403 without API key, "
            f"got {response.status_code}. Response: {response.text}"
        )

    def test_https_not_plain_text_404(self):
        """Verify we don't get the plain text '404 Not Found' from ALB default action."""
        model_id = "21"
        url = f"{API_BASE_URL}/api/v1/models/{model_id}/info"

        response = requests.get(url, headers=self.get_headers(), timeout=10)

        # Check response is NOT plain text "Not Found"
        if response.status_code == 404:
            content_type = response.headers.get("content-type", "")
            assert "text/plain" not in content_type, (
                f"Got plain text 404! This means ALB default action is being hit. "
                f"HTTPS listener rules are missing! Response: {response.text}"
            )

    def test_api_v1_health_endpoint_https(self):
        """Test /api/health endpoint via HTTPS."""
        url = f"{API_BASE_URL}/api/health"

        response = requests.get(url, timeout=10)

        # Should NOT return 404
        assert response.status_code != 404, f"Got 404 on /api/health. Response: {response.text}"

        # Should return valid response
        assert (
            response.status_code == 200
        ), f"Expected 200 on health endpoint, got {response.status_code}"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/models/21/info",
            "/api/v1/models/21/health",
            "/api/health",
        ],
    )
    def test_critical_paths_not_404(self, path: str):
        """Test that critical API paths don't return 404.

        This is a regression test for the bug where HTTPS listener rules
        were missing, causing all HTTPS requests to return 404.
        """
        url = f"{API_BASE_URL}{path}"

        # Use GET for all paths in this test
        response = requests.get(url, headers=self.get_headers(), timeout=10)

        # The key assertion: should NEVER be 404
        assert (
            response.status_code != 404
        ), f"Path {path} returned 404! Check ALB HTTPS listener rules. Response: {response.text}"


class TestHTTPSVsHTTP:
    """Test that both HTTP and HTTPS work (after fix)."""

    def test_http_redirect_or_works(self):
        """Verify HTTP either redirects to HTTPS or works directly."""
        http_url = API_BASE_URL.replace("https://", "http://")
        url = f"{http_url}/health"

        response = requests.get(url, allow_redirects=False, timeout=10)

        # Should be either 200 (works), 301 (redirect), or 302 (redirect)
        assert response.status_code in [
            200,
            301,
            302,
        ], f"Expected HTTP to work or redirect, got {response.status_code}"

    def test_https_works_after_fix(self):
        """Verify HTTPS works (this is the fix for the bug)."""
        url = f"{API_BASE_URL}/health"

        response = requests.get(url, timeout=10)

        # Should work (200), not 404
        assert response.status_code == 200, f"HTTPS health check failed with {response.status_code}"

        # Should return JSON
        assert "application/json" in response.headers.get("content-type", "")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
