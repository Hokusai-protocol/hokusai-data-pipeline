"""Integration tests for MLFlow configuration with DNS resolver."""

import os
import asyncio
from unittest.mock import AsyncMock, Mock, patch, call

import pytest

from src.utils.dns_resolver import DNSResolver, DNSResolutionError
from src.utils.mlflow_config import MLFlowConfig


class TestMLFlowDNSIntegration:
    """Test suite for MLFlow configuration integration with DNS resolver."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dns_resolver = DNSResolver(cache_ttl=300, timeout=5.0)

    def test_mlflow_config_initialization_with_hostname(self):
        """Test MLFlow config with hostname-based tracking URI."""
        with patch.dict('os.environ', {
            'MLFLOW_TRACKING_URI': 'http://mlflow.hokusai-development.local:5000'
        }):
            config = MLFlowConfig()
            
            assert config.tracking_uri == 'http://mlflow.hokusai-development.local:5000'

    @pytest.mark.asyncio
    async def test_dns_resolver_for_mlflow_hostname(self):
        """Test DNS resolution for MLFlow hostname."""
        hostname = "mlflow.hokusai-development.local"
        expected_ip = "10.0.1.221"
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, '', (expected_ip, 5000))
            ]
            
            result = await self.dns_resolver.resolve(hostname)
            
            assert result == expected_ip
            mock_getaddrinfo.assert_called_once()

    @pytest.mark.asyncio
    async def test_dns_resolver_for_mlflow_url(self):
        """Test DNS resolution for MLFlow URL."""
        url = "http://mlflow.hokusai-development.local:5000"
        expected_ip = "10.0.1.221"
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, '', (expected_ip, 5000))
            ]
            
            result = await self.dns_resolver.resolve(url)
            
            assert result == f"http://{expected_ip}:5000"
            mock_getaddrinfo.assert_called_once()
            args = mock_getaddrinfo.call_args[0]
            assert args[0] == "mlflow.hokusai-development.local"

    @pytest.mark.asyncio
    async def test_dns_resolver_fallback_for_mlflow(self):
        """Test DNS resolver fallback for MLFlow service."""
        hostname = "mlflow.hokusai-development.local"
        fallback_ip = "10.0.1.222"
        
        # Pre-populate cache with expired entry
        self.dns_resolver.cache[hostname] = {
            'ip': fallback_ip,
            'hostname': hostname,
            'timestamp': 0  # Very old timestamp
        }
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = Exception("DNS failed")
            
            result = await self.dns_resolver.resolve(hostname)
            
            assert result == fallback_ip
            assert self.dns_resolver.metrics.fallback_uses == 1

    @pytest.mark.asyncio
    async def test_dns_resolver_env_fallback_for_mlflow(self):
        """Test DNS resolver environment fallback for MLFlow service."""
        hostname = "mlflow.hokusai-development.local"
        fallback_ip = "10.0.1.223"
        
        with patch.dict('os.environ', {'MLFLOW_FALLBACK_IP': fallback_ip}):
            with patch('socket.getaddrinfo') as mock_getaddrinfo:
                mock_getaddrinfo.side_effect = Exception("DNS failed")
                
                result = await self.dns_resolver.resolve(hostname)
                
                assert result == fallback_ip
                assert self.dns_resolver.metrics.fallback_uses == 1

    def test_dns_resolver_health_monitoring(self):
        """Test DNS resolver health monitoring for MLFlow integration."""
        # Simulate some resolution attempts and errors
        self.dns_resolver.metrics.resolution_attempts = 10
        self.dns_resolver.metrics.errors = 1
        self.dns_resolver.metrics.cache_hits = 5
        self.dns_resolver.metrics.cache_misses = 4
        
        health = self.dns_resolver.health_check()
        
        assert health['status'] == 'healthy'  # 10% error rate
        assert health['error_rate'] == 0.1
        
        metrics = self.dns_resolver.get_metrics()
        assert metrics['cache_hit_rate'] == 5 / 9  # ~55.6%

    @pytest.mark.asyncio
    async def test_dns_caching_behavior_for_mlflow(self):
        """Test DNS caching behavior for repeated MLFlow requests."""
        hostname = "mlflow.hokusai-development.local"
        expected_ip = "10.0.1.221"
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, '', (expected_ip, 5000))
            ]
            
            # First resolution - should hit DNS
            result1 = await self.dns_resolver.resolve(hostname)
            assert result1 == expected_ip
            assert self.dns_resolver.metrics.cache_misses == 1
            assert self.dns_resolver.metrics.resolution_attempts == 1
            
            # Second resolution - should hit cache
            result2 = await self.dns_resolver.resolve(hostname)
            assert result2 == expected_ip
            assert self.dns_resolver.metrics.cache_hits == 1
            assert self.dns_resolver.metrics.resolution_attempts == 1  # No additional attempt
            
            # Verify only one DNS call was made
            mock_getaddrinfo.assert_called_once()

    @pytest.mark.asyncio
    async def test_dns_resolver_concurrent_mlflow_requests(self):
        """Test concurrent DNS resolution for MLFlow requests."""
        hostname = "mlflow.hokusai-development.local"
        expected_ip = "10.0.1.221"
        
        def slow_resolve(*args, **kwargs):
            import time
            time.sleep(0.1)
            return [(2, 1, 6, '', (expected_ip, 5000))]
        
        with patch('socket.getaddrinfo', side_effect=slow_resolve):
            # Simulate multiple MLFlow connections at once
            tasks = [
                self.dns_resolver.resolve(hostname),
                self.dns_resolver.resolve(hostname),
                self.dns_resolver.resolve(hostname)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # All should get the same IP
            assert all(result == expected_ip for result in results)
            
            # Should only make one DNS resolution attempt
            assert self.dns_resolver.metrics.resolution_attempts == 1

    def test_dns_resolver_cache_cleanup(self):
        """Test DNS cache cleanup for MLFlow entries."""
        hostname1 = "mlflow.hokusai-development.local"
        hostname2 = "api.hokusai-development.local"
        
        # Add fresh and expired entries
        import time
        current_time = time.time()
        
        self.dns_resolver.cache[hostname1] = {
            'ip': '10.0.1.221',
            'hostname': hostname1,
            'timestamp': current_time  # Fresh
        }
        self.dns_resolver.cache[hostname2] = {
            'ip': '10.0.1.222',
            'hostname': hostname2,
            'timestamp': current_time - 400  # Expired (TTL = 300)
        }
        
        cleaned = self.dns_resolver.cleanup_expired_entries()
        
        assert cleaned == 1
        assert hostname1 in self.dns_resolver.cache
        assert hostname2 not in self.dns_resolver.cache

    def test_dns_resolver_cache_info(self):
        """Test DNS cache information retrieval."""
        hostname = "mlflow.hokusai-development.local"
        
        import time
        self.dns_resolver.cache[hostname] = {
            'ip': '10.0.1.221',
            'hostname': hostname,
            'timestamp': time.time()
        }
        
        cache_info = self.dns_resolver.get_cache_info()
        
        assert cache_info['total_entries'] == 1
        assert cache_info['expired_entries'] == 0
        assert cache_info['cache_ttl'] == 300
        assert len(cache_info['entries']) == 1
        
        entry = cache_info['entries'][0]
        assert entry['hostname'] == hostname
        assert entry['ip'] == '10.0.1.221'
        assert not entry['expired']

    @pytest.mark.asyncio
    async def test_dns_resolver_error_handling(self):
        """Test DNS resolver error handling for MLFlow."""
        hostname = "nonexistent.hokusai-development.local"
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = Exception("Host not found")
            
            with pytest.raises(DNSResolutionError, match="Unexpected error resolving"):
                await self.dns_resolver.resolve(hostname)
            
            assert self.dns_resolver.metrics.errors == 1


class TestMLFlowDNSIntegrationScenarios:
    """Integration scenarios testing DNS resolver with MLFlow patterns."""

    @pytest.mark.asyncio
    async def test_mlflow_service_discovery_pattern(self):
        """Test typical MLFlow service discovery pattern."""
        resolver = DNSResolver(cache_ttl=300)
        
        # Simulate various MLFlow service discovery scenarios
        services = [
            "mlflow.hokusai-development.local",
            "mlflow.hokusai-development.local:5000",
            "http://mlflow.hokusai-development.local:5000",
            "http://mlflow.hokusai-development.local:5000/api/2.0/mlflow",
        ]
        
        expected_ip = "10.0.1.221"
        
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, '', (expected_ip, 5000))
            ]
            
            results = []
            for service in services:
                result = await resolver.resolve(service)
                results.append(result)
            
            # Verify expected transformations
            assert results[0] == expected_ip  # plain hostname
            assert results[1] == f"{expected_ip}:5000"  # hostname:port
            assert results[2] == f"http://{expected_ip}:5000"  # http URL
            assert results[3] == f"http://{expected_ip}:5000/api/2.0/mlflow"  # full API URL
            
            # Should only make one DNS resolution (others hit cache)
            assert resolver.metrics.resolution_attempts == 1
            assert resolver.metrics.cache_hits == 3

    @pytest.mark.asyncio
    async def test_mlflow_failover_scenario(self):
        """Test MLFlow failover scenario with DNS fallback."""
        resolver = DNSResolver(cache_ttl=300)
        hostname = "mlflow.hokusai-development.local"
        
        # First, establish a cache entry
        primary_ip = "10.0.1.221"
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, '', (primary_ip, 5000))
            ]
            
            result = await resolver.resolve(hostname)
            assert result == primary_ip
        
        # Simulate DNS failure - should fall back to cached IP
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = Exception("DNS server unavailable")
            
            # Manually expire the cache entry
            resolver.cache[hostname]['timestamp'] = 0
            
            result = await resolver.resolve(hostname)
            assert result == primary_ip  # Should still get cached IP
            assert resolver.metrics.fallback_uses == 1

    @pytest.mark.asyncio
    async def test_mlflow_environment_fallback_scenario(self):
        """Test MLFlow environment variable fallback scenario."""
        resolver = DNSResolver(cache_ttl=300)
        hostname = "mlflow.hokusai-development.local"
        emergency_ip = "10.0.1.240"  # Emergency fallback IP
        
        with patch.dict('os.environ', {'MLFLOW_FALLBACK_IP': emergency_ip}):
            with patch('socket.getaddrinfo') as mock_getaddrinfo:
                mock_getaddrinfo.side_effect = Exception("Complete DNS failure")
                
                result = await resolver.resolve(hostname)
                assert result == emergency_ip
                assert resolver.metrics.fallback_uses == 1

    def test_dns_health_monitoring_for_mlflow_ops(self):
        """Test DNS health monitoring during MLFlow operations."""
        resolver = DNSResolver(cache_ttl=300)
        
        # Simulate a series of operations with varying success
        resolver.metrics.resolution_attempts = 20
        resolver.metrics.errors = 2  # 10% error rate
        resolver.metrics.cache_hits = 15
        resolver.metrics.cache_misses = 10
        resolver.metrics.fallback_uses = 2
        
        health = resolver.health_check()
        metrics = resolver.get_metrics()
        
        # Should be healthy with low error rate
        assert health['status'] == 'healthy'
        assert health['error_rate'] == 0.1
        
        # Verify metrics calculations
        assert metrics['cache_hit_rate'] == 15 / 25  # 60%
        assert metrics['resolution_attempts'] == 20
        assert metrics['fallback_uses'] == 2

    def test_dns_resolver_configuration_from_environment(self):
        """Test DNS resolver configuration from environment variables."""
        with patch.dict('os.environ', {
            'DNS_CACHE_TTL': '600',  # 10 minutes
            'DNS_TIMEOUT': '15.0'    # 15 seconds
        }):
            resolver = DNSResolver()
            
            assert resolver.cache_ttl == 600
            assert resolver.timeout == 15.0

    def test_global_dns_resolver_usage(self):
        """Test global DNS resolver instance usage."""
        from src.utils.dns_resolver import get_dns_resolver, reset_dns_resolver
        
        # Reset to ensure clean state
        reset_dns_resolver()
        
        # Get global resolver
        resolver1 = get_dns_resolver()
        resolver2 = get_dns_resolver()
        
        # Should be the same instance
        assert resolver1 is resolver2
        
        # Reset and get new instance
        reset_dns_resolver()
        resolver3 = get_dns_resolver()
        
        # Should be a different instance
        assert resolver1 is not resolver3