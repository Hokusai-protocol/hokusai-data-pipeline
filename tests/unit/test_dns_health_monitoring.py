"""Tests for DNS health monitoring in health endpoints."""

import os
from unittest.mock import Mock, patch

import pytest

from src.utils.dns_resolver import get_dns_resolver, get_dns_health
from src.utils.mlflow_config import get_mlflow_status


class TestDNSHealthMonitoring:
    """Test suite for DNS health monitoring integration."""

    def test_dns_resolver_global_instance(self):
        """Test global DNS resolver instance creation."""
        resolver1 = get_dns_resolver()
        resolver2 = get_dns_resolver()
        
        # Should be the same instance
        assert resolver1 is resolver2
        
        # Should have default configuration
        assert resolver1.cache_ttl == 300
        assert resolver1.timeout == 10.0

    def test_dns_health_function(self):
        """Test global DNS health function."""
        health = get_dns_health()
        
        # Should return health status
        assert 'status' in health
        assert 'error_rate' in health
        assert 'metrics' in health
        assert health['status'] in ['healthy', 'degraded', 'unhealthy']

    def test_dns_resolver_with_environment_config(self):
        """Test DNS resolver configuration from environment."""
        with patch.dict('os.environ', {
            'DNS_CACHE_TTL': '600',
            'DNS_TIMEOUT': '15.0'
        }):
            # Clear global resolver to force recreation
            from src.utils.dns_resolver import reset_dns_resolver
            reset_dns_resolver()
            
            resolver = get_dns_resolver()
            
            assert resolver.cache_ttl == 600
            assert resolver.timeout == 15.0

    def test_mlflow_status_includes_dns_info(self):
        """Test that MLflow status includes DNS resolution information."""
        with patch.dict('os.environ', {
            'MLFLOW_TRACKING_URI': 'http://mlflow.hokusai-development.local:5000'
        }):
            status = get_mlflow_status()
            
            # Should include DNS resolution information
            assert 'dns_resolution' in status
            assert 'raw_uri' in status['dns_resolution']
            assert 'metrics' in status['dns_resolution']
            assert 'health' in status['dns_resolution']
            
            # Raw URI should match environment
            assert status['dns_resolution']['raw_uri'] == 'http://mlflow.hokusai-development.local:5000'

    @pytest.mark.asyncio
    async def test_dns_resolver_hostname_resolution(self):
        """Test DNS resolver with actual hostname resolution."""
        resolver = get_dns_resolver()
        
        # Test with localhost (should resolve to 127.0.0.1)
        result = await resolver.resolve("localhost")
        assert result == "127.0.0.1"
        
        # Verify metrics were updated
        metrics = resolver.get_metrics()
        assert metrics['resolution_attempts'] >= 1

    def test_dns_resolver_ip_passthrough(self):
        """Test DNS resolver with IP address passthrough."""
        import asyncio
        
        resolver = get_dns_resolver()
        
        # Test with IP address (should pass through unchanged)
        result = asyncio.run(resolver.resolve("10.0.1.221"))
        assert result == "10.0.1.221"
        
        # Should not increment resolution attempts for IP addresses
        initial_attempts = resolver.metrics.resolution_attempts
        asyncio.run(resolver.resolve("192.168.1.1"))
        assert resolver.metrics.resolution_attempts == initial_attempts

    def test_dns_cache_functionality(self):
        """Test DNS cache functionality."""
        import asyncio
        import time
        
        resolver = get_dns_resolver()
        resolver.clear_cache()  # Start with clean cache
        
        # Add an entry to cache
        hostname = "test.example.com"
        resolver.cache[hostname] = {
            'ip': '1.2.3.4',
            'hostname': hostname,
            'timestamp': time.time()
        }
        
        # Verify cache info
        cache_info = resolver.get_cache_info()
        assert cache_info['total_entries'] == 1
        assert cache_info['expired_entries'] == 0
        
        # Test cache lookup
        result = asyncio.run(resolver.resolve(hostname))
        assert result == '1.2.3.4'
        assert resolver.metrics.cache_hits >= 1

    def test_dns_cache_cleanup(self):
        """Test DNS cache cleanup of expired entries."""
        import time
        
        resolver = get_dns_resolver()
        resolver.clear_cache()
        
        # Add expired entry - use a much older timestamp to ensure expiration
        hostname = "expired.example.com"
        resolver.cache[hostname] = {
            'ip': '1.2.3.4',
            'hostname': hostname,
            'timestamp': time.time() - (resolver.cache_ttl + 100)  # Definitely expired
        }
        
        # Verify it's expired before cleanup
        cache_info = resolver.get_cache_info()
        assert cache_info['expired_entries'] == 1
        
        # Clean up expired entries
        cleaned = resolver.cleanup_expired_entries()
        assert cleaned == 1
        assert hostname not in resolver.cache

    def test_dns_health_status_calculation(self):
        """Test DNS health status calculation based on metrics."""
        resolver = get_dns_resolver()
        
        # Reset metrics for clean test
        resolver.metrics.reset()
        
        # Test healthy status (no errors)
        resolver.metrics.resolution_attempts = 10
        resolver.metrics.errors = 0
        health = resolver.health_check()
        assert health['status'] == 'healthy'
        assert health['error_rate'] == 0.0
        
        # Test degraded status (some errors)
        resolver.metrics.errors = 3  # 30% error rate
        health = resolver.health_check()
        assert health['status'] == 'degraded'
        assert health['error_rate'] == 0.3
        
        # Test unhealthy status (high error rate)
        resolver.metrics.errors = 8  # 80% error rate
        health = resolver.health_check()
        assert health['status'] == 'unhealthy'
        assert health['error_rate'] == 0.8

    def test_dns_metrics_tracking(self):
        """Test DNS metrics tracking functionality."""
        resolver = get_dns_resolver()
        resolver.metrics.reset()
        
        # Record various metrics
        resolver.metrics.record_resolution_attempt()
        resolver.metrics.record_cache_hit()
        resolver.metrics.record_cache_miss()
        resolver.metrics.record_fallback_use()
        resolver.metrics.record_error()
        
        # Verify metrics
        metrics = resolver.get_metrics()
        assert metrics['resolution_attempts'] == 1
        assert metrics['cache_hits'] == 1
        assert metrics['cache_misses'] == 1
        assert metrics['fallback_uses'] == 1
        assert metrics['errors'] == 1
        assert metrics['cache_hit_rate'] == 0.5  # 1 hit out of 2 total lookups

    @patch('src.utils.mlflow_config.resolve_tracking_uri_sync')
    def test_mlflow_config_dns_integration(self, mock_resolve):
        """Test MLflow configuration DNS integration."""
        from src.utils.mlflow_config import MLFlowConfig
        
        # Mock DNS resolution
        mock_resolve.return_value = "http://10.0.1.221:5000"
        
        with patch.dict('os.environ', {
            'MLFLOW_TRACKING_URI': 'http://mlflow.hokusai-development.local:5000'
        }):
            config = MLFlowConfig()
            
            # Should have raw and resolved URIs
            assert config.tracking_uri_raw == 'http://mlflow.hokusai-development.local:5000'
            assert config.tracking_uri == 'http://10.0.1.221:5000'
            
            # Should have called DNS resolution
            mock_resolve.assert_called_once_with('http://mlflow.hokusai-development.local:5000')

    def test_dns_resolver_environment_fallback(self):
        """Test DNS resolver environment variable fallback."""
        import asyncio
        
        resolver = get_dns_resolver()
        fallback_ip = "10.0.1.240"
        
        with patch.dict('os.environ', {'MLFLOW_FALLBACK_IP': fallback_ip}):
            with patch('socket.getaddrinfo') as mock_getaddrinfo:
                mock_getaddrinfo.side_effect = Exception("DNS failed")
                
                # Should use environment fallback
                result = asyncio.run(resolver.resolve("unknown.hostname.local"))
                assert result == fallback_ip
                assert resolver.metrics.fallback_uses >= 1