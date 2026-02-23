"""Unit tests for MLFlow configuration with DNS integration."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.utils.mlflow_config import (
    MLFlowConfig,
    get_mlflow_status,
    resolve_tracking_uri,
    resolve_tracking_uri_sync,
)


class TestMLFlowConfigDNSIntegration:
    """Test suite for MLFlowConfig with DNS integration."""

    @patch("src.utils.mlflow_config.resolve_tracking_uri_sync")
    def test_mlflow_config_initialization_with_dns_resolution(self, mock_resolve):
        """Test MLFlowConfig initialization with DNS resolution."""
        mock_resolve.return_value = "http://10.0.1.221:5000"

        with patch.dict(
            "os.environ", {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"}
        ):
            config = MLFlowConfig()

            assert config.tracking_uri_raw == "http://mlflow.hokusai-development.local:5000"
            assert config.tracking_uri == "http://10.0.1.221:5000"
            assert config._resolved_tracking_uri == "http://10.0.1.221:5000"

            mock_resolve.assert_called_once_with("http://mlflow.hokusai-development.local:5000")

    @patch("src.utils.mlflow_config.resolve_tracking_uri_sync")
    def test_mlflow_config_dns_resolution_failure_fallback(self, mock_resolve):
        """Test MLFlowConfig fallback when DNS resolution fails."""
        mock_resolve.side_effect = Exception("DNS resolution failed")

        with patch.dict(
            "os.environ", {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"}
        ):
            config = MLFlowConfig()

            # Should fall back to original URI
            assert config.tracking_uri == "http://mlflow.hokusai-development.local:5000"
            assert config._resolved_tracking_uri is None

    @patch("src.utils.mlflow_config.resolve_tracking_uri_sync")
    def test_mlflow_config_refresh_dns_resolution(self, mock_resolve):
        """Test DNS resolution refresh functionality."""
        mock_resolve.side_effect = [
            "http://10.0.1.221:5000",  # Initial resolution
            "http://10.0.1.222:5000",  # Refresh resolution (new IP)
        ]

        with patch.dict(
            "os.environ", {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"}
        ):
            config = MLFlowConfig()

            # Initial state
            assert config.tracking_uri == "http://10.0.1.221:5000"

            # Refresh DNS resolution
            result = config.refresh_dns_resolution()

            assert result is True
            assert config.tracking_uri == "http://10.0.1.222:5000"
            assert config._resolved_tracking_uri == "http://10.0.1.222:5000"

    @patch("src.utils.mlflow_config.resolve_tracking_uri_sync")
    def test_mlflow_config_refresh_dns_resolution_failure(self, mock_resolve):
        """Test DNS resolution refresh failure handling."""
        mock_resolve.side_effect = [
            "http://10.0.1.221:5000",  # Initial resolution succeeds
            Exception("DNS refresh failed"),  # Refresh fails
        ]

        with patch.dict(
            "os.environ", {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"}
        ):
            config = MLFlowConfig()

            # Initial state
            assert config.tracking_uri == "http://10.0.1.221:5000"

            # Refresh DNS resolution fails
            result = config.refresh_dns_resolution()

            assert result is False
            # Should keep original resolved URI
            assert config.tracking_uri == "http://10.0.1.221:5000"

    def test_mlflow_config_get_dns_info(self):
        """Test DNS information retrieval."""
        with (
            patch("src.utils.mlflow_config.resolve_tracking_uri_sync") as mock_resolve,
            patch("src.utils.dns_resolver.get_dns_resolver") as mock_get_resolver,
        ):
            mock_resolve.return_value = "http://10.0.1.221:5000"

            mock_resolver = Mock()
            mock_resolver.get_metrics.return_value = {
                "resolution_attempts": 5,
                "cache_hits": 3,
                "errors": 1,
            }
            mock_resolver.health_check.return_value = {"status": "healthy", "error_rate": 0.2}
            mock_get_resolver.return_value = mock_resolver

            with patch.dict(
                "os.environ",
                {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"},
            ):
                config = MLFlowConfig()
                dns_info = config.get_dns_info()

                assert (
                    dns_info["raw_tracking_uri"] == "http://mlflow.hokusai-development.local:5000"
                )
                assert dns_info["resolved_tracking_uri"] == "http://10.0.1.221:5000"
                assert dns_info["current_tracking_uri"] == "http://10.0.1.221:5000"
                assert dns_info["dns_metrics"]["resolution_attempts"] == 5
                assert dns_info["dns_health"]["status"] == "healthy"


class TestResolveTrackingURI:
    """Test suite for resolve_tracking_uri functions."""

    @pytest.mark.asyncio
    @patch("src.utils.mlflow_config.get_dns_resolver")
    async def test_resolve_tracking_uri_success(self, mock_get_resolver):
        """Test successful DNS resolution of tracking URI."""
        mock_resolver = AsyncMock()
        mock_resolver.resolve.return_value = "http://10.0.1.221:5000"
        mock_get_resolver.return_value = mock_resolver

        result = await resolve_tracking_uri("http://mlflow.hokusai-development.local:5000")

        assert result == "http://10.0.1.221:5000"
        mock_resolver.resolve.assert_called_once_with(
            "http://mlflow.hokusai-development.local:5000"
        )

    @pytest.mark.asyncio
    @patch("src.utils.mlflow_config.get_dns_resolver")
    async def test_resolve_tracking_uri_no_change(self, mock_get_resolver):
        """Test DNS resolution when URI doesn't change."""
        mock_resolver = AsyncMock()
        mock_resolver.resolve.return_value = "http://10.0.1.221:5000"  # Same as input
        mock_get_resolver.return_value = mock_resolver

        result = await resolve_tracking_uri("http://10.0.1.221:5000")

        assert result == "http://10.0.1.221:5000"

    @pytest.mark.asyncio
    @patch("src.utils.mlflow_config.get_dns_resolver")
    async def test_resolve_tracking_uri_dns_error_with_fallback(self, mock_get_resolver):
        """Test DNS resolution error with fallback."""
        from src.utils.dns_resolver import DNSResolutionError

        mock_resolver = AsyncMock()
        dns_error = DNSResolutionError(
            "DNS failed", "mlflow.hokusai-development.local", fallback_used=True
        )
        mock_resolver.resolve.side_effect = dns_error
        mock_get_resolver.return_value = mock_resolver

        result = await resolve_tracking_uri("http://mlflow.hokusai-development.local:5000")

        # Should return original URI when fallback was used
        assert result == "http://mlflow.hokusai-development.local:5000"

    @pytest.mark.asyncio
    @patch("src.utils.mlflow_config.get_dns_resolver")
    async def test_resolve_tracking_uri_dns_error_no_fallback(self, mock_get_resolver):
        """Test DNS resolution error without fallback."""
        from src.utils.dns_resolver import DNSResolutionError

        mock_resolver = AsyncMock()
        dns_error = DNSResolutionError(
            "DNS failed", "mlflow.hokusai-development.local", fallback_used=False
        )
        mock_resolver.resolve.side_effect = dns_error
        mock_get_resolver.return_value = mock_resolver

        with pytest.raises(DNSResolutionError):
            await resolve_tracking_uri("http://mlflow.hokusai-development.local:5000")

    @pytest.mark.asyncio
    @patch("src.utils.mlflow_config.get_dns_resolver")
    async def test_resolve_tracking_uri_unexpected_error(self, mock_get_resolver):
        """Test unexpected error handling."""
        mock_resolver = AsyncMock()
        mock_resolver.resolve.side_effect = Exception("Unexpected error")
        mock_get_resolver.return_value = mock_resolver

        result = await resolve_tracking_uri("http://mlflow.hokusai-development.local:5000")

        # Should return original URI as fallback
        assert result == "http://mlflow.hokusai-development.local:5000"

    @patch("asyncio.get_event_loop")
    @patch("src.utils.mlflow_config.resolve_tracking_uri")
    def test_resolve_tracking_uri_sync_success(self, mock_async_resolve, mock_get_loop):
        """Test synchronous wrapper for DNS resolution."""
        mock_loop = Mock()
        mock_loop.is_running.return_value = False
        mock_loop.run_until_complete.return_value = "http://10.0.1.221:5000"
        mock_get_loop.return_value = mock_loop

        result = resolve_tracking_uri_sync("http://mlflow.hokusai-development.local:5000")

        assert result == "http://10.0.1.221:5000"
        mock_loop.run_until_complete.assert_called_once()

    @patch("asyncio.get_event_loop")
    def test_resolve_tracking_uri_sync_loop_running(self, mock_get_loop):
        """Test synchronous wrapper when event loop is already running."""
        mock_loop = Mock()
        mock_loop.is_running.return_value = True
        mock_get_loop.return_value = mock_loop

        result = resolve_tracking_uri_sync("http://mlflow.hokusai-development.local:5000")

        # Should return original URI when loop is running
        assert result == "http://mlflow.hokusai-development.local:5000"

    @patch("asyncio.get_event_loop")
    def test_resolve_tracking_uri_sync_no_loop(self, mock_get_loop):
        """Test synchronous wrapper when no event loop exists."""
        mock_get_loop.side_effect = RuntimeError("No event loop")

        with (
            patch("asyncio.new_event_loop") as mock_new_loop,
            patch("asyncio.set_event_loop") as mock_set_loop,
        ):
            mock_loop = Mock()
            mock_loop.run_until_complete.return_value = "http://10.0.1.221:5000"
            mock_new_loop.return_value = mock_loop

            result = resolve_tracking_uri_sync("http://mlflow.hokusai-development.local:5000")

            assert result == "http://10.0.1.221:5000"
            mock_new_loop.assert_called_once()
            mock_set_loop.assert_called_once_with(mock_loop)

    def test_resolve_tracking_uri_sync_error(self):
        """Test synchronous wrapper error handling."""
        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_get_loop.side_effect = Exception("Unexpected error")

            result = resolve_tracking_uri_sync("http://mlflow.hokusai-development.local:5000")

            # Should return original URI on error
            assert result == "http://mlflow.hokusai-development.local:5000"


class TestGetMLFlowStatusDNSIntegration:
    """Test suite for get_mlflow_status with DNS integration."""

    def test_get_mlflow_status_with_dns_resolution(self):
        """Test get_mlflow_status with DNS resolution."""
        with (
            patch("src.utils.mlflow_config._circuit_breaker") as mock_cb,
            patch("src.utils.dns_resolver.get_dns_resolver") as mock_get_resolver,
            patch("src.utils.mlflow_config.resolve_tracking_uri_sync") as mock_resolve,
            patch("mlflow.set_tracking_uri") as mock_set_uri,
            patch("mlflow.get_experiment_by_name") as mock_get_exp,
            patch("src.utils.mlflow_config.exponential_backoff_retry") as mock_retry,
        ):
            # Mock circuit breaker
            mock_cb.is_open.return_value = False
            mock_cb.get_status.return_value = {"state": "CLOSED", "time_until_retry": 0}
            mock_cb.record_success.return_value = None

            # Mock DNS resolver
            mock_resolver = Mock()
            mock_resolver.get_metrics.return_value = {
                "resolution_attempts": 3,
                "cache_hits": 2,
                "errors": 0,
            }
            mock_resolver.health_check.return_value = {"status": "healthy", "error_rate": 0.0}
            mock_get_resolver.return_value = mock_resolver

            # Mock DNS resolution
            mock_resolve.return_value = "http://10.0.1.221:5000"

            # Mock MLflow calls
            mock_get_exp.return_value = Mock()
            mock_retry.return_value = Mock()

            with patch.dict(
                "os.environ",
                {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"},
            ):
                status = get_mlflow_status()

                assert status["connected"] is True
                assert status["tracking_uri"] == "http://mlflow.hokusai-development.local:5000"
                assert (
                    status["dns_resolution"]["raw_uri"]
                    == "http://mlflow.hokusai-development.local:5000"
                )
                assert status["dns_resolution"]["resolved_uri"] == "http://10.0.1.221:5000"
                assert status["dns_resolution"]["metrics"]["resolution_attempts"] == 3
                assert status["dns_resolution"]["health"]["status"] == "healthy"

                # Verify MLflow was called with resolved URI
                mock_set_uri.assert_called_with("http://10.0.1.221:5000")

    def test_get_mlflow_status_dns_resolution_failure(self):
        """Test get_mlflow_status when DNS resolution fails."""
        with (
            patch("src.utils.mlflow_config._circuit_breaker") as mock_cb,
            patch("src.utils.dns_resolver.get_dns_resolver") as mock_get_resolver,
            patch("src.utils.mlflow_config.resolve_tracking_uri_sync") as mock_resolve,
        ):
            # Mock circuit breaker
            mock_cb.is_open.return_value = False
            mock_cb.get_status.return_value = {"state": "CLOSED", "time_until_retry": 0}

            # Mock DNS resolver with high error rate
            mock_resolver = Mock()
            mock_resolver.get_metrics.return_value = {"resolution_attempts": 1, "errors": 1}
            mock_resolver.health_check.return_value = {"status": "degraded", "error_rate": 1.0}
            mock_get_resolver.return_value = mock_resolver

            # Mock DNS resolution failure
            mock_resolve.side_effect = Exception("DNS resolution failed")

            with patch.dict(
                "os.environ",
                {"MLFLOW_TRACKING_URI": "http://mlflow.hokusai-development.local:5000"},
            ):
                status = get_mlflow_status()

                assert (
                    status["dns_resolution"]["raw_uri"]
                    == "http://mlflow.hokusai-development.local:5000"
                )
                assert "resolution_error" in status["dns_resolution"]
                assert status["dns_resolution"]["health"]["status"] == "degraded"

    @patch("src.utils.dns_resolver.get_dns_resolver")
    @patch("src.utils.mlflow_config._circuit_breaker")
    def test_get_mlflow_status_circuit_breaker_open(self, mock_cb, mock_get_resolver):
        """Test get_mlflow_status when circuit breaker is open."""
        # Mock circuit breaker as open
        mock_cb.is_open.return_value = True
        mock_cb.get_status.return_value = {"state": "OPEN", "time_until_retry": 30.0}

        # Mock DNS resolver
        mock_resolver = Mock()
        mock_resolver.get_metrics.return_value = {}
        mock_resolver.health_check.return_value = {"status": "healthy"}
        mock_get_resolver.return_value = mock_resolver

        status = get_mlflow_status()

        assert status["connected"] is False
        assert "Circuit breaker is OPEN" in status["error"]
        assert status["can_retry_in_seconds"] == 30.0
        assert "dns_resolution" in status  # DNS info should still be included
