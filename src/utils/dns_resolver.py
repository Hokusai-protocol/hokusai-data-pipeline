"""DNS resolution utility with caching, fallback, and metrics for service discovery."""

import asyncio
import logging
import os
import re
import socket
import time
from typing import Dict, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DNSResolutionError(Exception):
    """Raised when DNS resolution fails and no fallback is available."""
    
    def __init__(self, message: str, hostname: str, fallback_used: bool = False):
        super().__init__(message)
        self.hostname = hostname
        self.fallback_used = fallback_used


class DNSMetrics:
    """Metrics tracking for DNS resolution operations."""
    
    def __init__(self):
        self.resolution_attempts = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.fallback_uses = 0
        self.errors = 0
        self.last_resolution_time: Optional[float] = None
    
    def record_resolution_attempt(self):
        """Record a DNS resolution attempt."""
        self.resolution_attempts += 1
        self.last_resolution_time = time.time()
    
    def record_cache_hit(self):
        """Record a cache hit."""
        self.cache_hits += 1
    
    def record_cache_miss(self):
        """Record a cache miss."""
        self.cache_misses += 1
    
    def record_fallback_use(self):
        """Record a fallback use."""
        self.fallback_uses += 1
    
    def record_error(self):
        """Record a DNS resolution error."""
        self.errors += 1
    
    def reset(self):
        """Reset all metrics."""
        self.resolution_attempts = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.fallback_uses = 0
        self.errors = 0
        self.last_resolution_time = None


class DNSResolver:
    """DNS resolver with caching, fallback capabilities, and comprehensive monitoring.
    
    Features:
    - DNS resolution with configurable cache TTL (default 5 minutes)
    - Fallback to cached IP on DNS failure
    - Environment variable fallback (MLFLOW_FALLBACK_IP)
    - Comprehensive metrics and health monitoring
    - Concurrent resolution request handling
    - Support for hostnames, IPs, and full URLs
    """
    
    def __init__(self, cache_ttl: int = None, timeout: float = None):
        """Initialize DNS resolver.
        
        Args:
            cache_ttl: Cache TTL in seconds (default: 300 = 5 minutes)
            timeout: DNS resolution timeout in seconds (default: 10.0)
        """
        self.cache_ttl = cache_ttl or int(os.getenv('DNS_CACHE_TTL', '300'))
        self.timeout = timeout or float(os.getenv('DNS_TIMEOUT', '10.0'))
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.metrics = DNSMetrics()
        self._resolution_locks: Dict[str, asyncio.Lock] = {}
        
        logger.info(f"DNS resolver initialized with cache_ttl={self.cache_ttl}s, timeout={self.timeout}s")
    
    def _is_ip_address(self, hostname: str) -> bool:
        """Check if a string is an IP address."""
        try:
            socket.inet_aton(hostname.split(':')[0])  # Handle hostname:port format
            return True
        except socket.error:
            return False
    
    def _extract_hostname_from_url(self, url: str) -> tuple[str, str]:
        """Extract hostname from URL and return (hostname, original_format).
        
        Args:
            url: URL, hostname, or hostname:port
            
        Returns:
            Tuple of (hostname, original_format) where original_format preserves
            the original structure for reconstruction
        """
        # Handle URLs with schemes
        if '://' in url:
            parsed = urlparse(url)
            hostname = parsed.hostname
            return hostname, url
        
        # Handle hostname:port format
        if ':' in url and not self._is_ip_address(url):
            hostname = url.split(':')[0]
            return hostname, url
        
        # Plain hostname or IP
        return url, url
    
    def _reconstruct_original_format(self, original_format: str, resolved_ip: str) -> str:
        """Reconstruct the original format with resolved IP.
        
        Args:
            original_format: Original input format
            resolved_ip: Resolved IP address
            
        Returns:
            Original format with hostname replaced by IP
        """
        # Handle URLs with schemes
        if '://' in original_format:
            parsed = urlparse(original_format)
            return original_format.replace(parsed.hostname, resolved_ip)
        
        # Handle hostname:port format
        if ':' in original_format and not self._is_ip_address(original_format):
            hostname, port = original_format.split(':', 1)
            return f"{resolved_ip}:{port}"
        
        # Plain hostname
        return resolved_ip
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        if not cache_entry:
            return False
        
        timestamp = cache_entry.get('timestamp', 0)
        return (time.time() - timestamp) < self.cache_ttl
    
    def _get_fallback_ip(self, hostname: str) -> Optional[str]:
        """Get fallback IP for hostname.
        
        Priority:
        1. Cached IP (even if expired)
        2. Environment variable MLFLOW_FALLBACK_IP
        
        Args:
            hostname: Hostname to get fallback for
            
        Returns:
            Fallback IP address or None
        """
        # Try cached IP first (even if expired)
        if hostname in self.cache:
            cached_ip = self.cache[hostname].get('ip')
            if cached_ip:
                logger.info(f"Using cached fallback IP for {hostname}: {cached_ip}")
                return cached_ip
        
        # Try environment variable fallback
        fallback_ip = os.getenv('MLFLOW_FALLBACK_IP')
        if fallback_ip:
            logger.info(f"Using environment fallback IP for {hostname}: {fallback_ip}")
            return fallback_ip
        
        return None
    
    async def _resolve_hostname(self, hostname: str) -> str:
        """Perform actual DNS resolution for hostname.
        
        Args:
            hostname: Hostname to resolve
            
        Returns:
            Resolved IP address
            
        Raises:
            DNSResolutionError: If resolution fails
        """
        self.metrics.record_resolution_attempt()
        
        try:
            logger.debug(f"Resolving hostname: {hostname}")
            
            # Use asyncio to wrap the blocking socket.getaddrinfo call
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
                ),
                timeout=self.timeout
            )
            
            if not result:
                raise DNSResolutionError(f"No address found for {hostname}", hostname)
            
            # Get the first IPv4 address
            ip_address = result[0][4][0]
            logger.info(f"DNS resolution successful: {hostname} -> {ip_address}")
            
            # Update cache
            self.cache[hostname] = {
                'ip': ip_address,
                'hostname': hostname,
                'timestamp': time.time()
            }
            
            return ip_address
            
        except asyncio.TimeoutError:
            self.metrics.record_error()
            raise DNSResolutionError(f"DNS resolution timed out for {hostname}", hostname)
        except socket.gaierror as e:
            self.metrics.record_error()
            raise DNSResolutionError(f"DNS resolution failed for {hostname}: {e}", hostname)
        except socket.timeout as e:
            self.metrics.record_error()
            raise DNSResolutionError(f"DNS resolution timed out for {hostname}: {e}", hostname)
        except Exception as e:
            self.metrics.record_error()
            raise DNSResolutionError(f"Unexpected error resolving {hostname}: {e}", hostname)
    
    async def resolve(self, hostname_or_url: str) -> str:
        """Resolve hostname to IP address with caching and fallback.
        
        Args:
            hostname_or_url: Hostname, IP address, hostname:port, or full URL
            
        Returns:
            Resolved IP address in the same format as input
            
        Raises:
            DNSResolutionError: If resolution fails and no fallback is available
        """
        # Extract hostname from various input formats
        hostname, original_format = self._extract_hostname_from_url(hostname_or_url)
        
        # If it's already an IP address, return as-is
        if self._is_ip_address(hostname):
            return hostname_or_url
        
        # Check cache first
        if hostname in self.cache and self._is_cache_valid(self.cache[hostname]):
            self.metrics.record_cache_hit()
            cached_ip = self.cache[hostname]['ip']
            logger.debug(f"Cache hit for {hostname}: {cached_ip}")
            return self._reconstruct_original_format(original_format, cached_ip)
        
        self.metrics.record_cache_miss()
        
        # Handle concurrent resolution requests for the same hostname
        if hostname not in self._resolution_locks:
            self._resolution_locks[hostname] = asyncio.Lock()
        
        async with self._resolution_locks[hostname]:
            # Double-check cache after acquiring lock (another coroutine might have resolved it)
            if hostname in self.cache and self._is_cache_valid(self.cache[hostname]):
                self.metrics.record_cache_hit()
                cached_ip = self.cache[hostname]['ip']
                logger.debug(f"Cache hit after lock for {hostname}: {cached_ip}")
                return self._reconstruct_original_format(original_format, cached_ip)
            
            # Try DNS resolution
            try:
                resolved_ip = await self._resolve_hostname(hostname)
                return self._reconstruct_original_format(original_format, resolved_ip)
            except DNSResolutionError:
                # DNS resolution failed, try fallback
                fallback_ip = self._get_fallback_ip(hostname)
                if fallback_ip:
                    self.metrics.record_fallback_use()
                    logger.warning(f"DNS resolution failed for {hostname}, using fallback: {fallback_ip}")
                    return self._reconstruct_original_format(original_format, fallback_ip)
                else:
                    # No fallback available
                    logger.error(f"DNS resolution failed for {hostname} and no fallback available")
                    raise
    
    def clear_cache(self):
        """Clear the DNS cache."""
        self.cache.clear()
        logger.info("DNS cache cleared")
    
    def cleanup_expired_entries(self) -> int:
        """Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if (current_time - entry.get('timestamp', 0)) >= self.cache_ttl
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired DNS cache entries")
        
        return len(expired_keys)
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache state.
        
        Returns:
            Dictionary with cache information
        """
        current_time = time.time()
        expired_count = sum(
            1 for entry in self.cache.values()
            if (current_time - entry.get('timestamp', 0)) >= self.cache_ttl
        )
        
        return {
            'total_entries': len(self.cache),
            'expired_entries': expired_count,
            'cache_ttl': self.cache_ttl,
            'entries': [
                {
                    'hostname': entry['hostname'],
                    'ip': entry['ip'],
                    'age_seconds': current_time - entry['timestamp'],
                    'expired': (current_time - entry['timestamp']) >= self.cache_ttl
                }
                for entry in self.cache.values()
            ]
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get DNS resolution metrics.
        
        Returns:
            Dictionary with comprehensive metrics
        """
        total_lookups = self.metrics.cache_hits + self.metrics.cache_misses
        cache_hit_rate = self.metrics.cache_hits / total_lookups if total_lookups > 0 else 0.0
        
        return {
            'resolution_attempts': self.metrics.resolution_attempts,
            'cache_hits': self.metrics.cache_hits,
            'cache_misses': self.metrics.cache_misses,
            'fallback_uses': self.metrics.fallback_uses,
            'errors': self.metrics.errors,
            'cache_hit_rate': cache_hit_rate,
            'cache_size': len(self.cache),
            'last_resolution_time': self.metrics.last_resolution_time
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on DNS resolver.
        
        Returns:
            Health check status with details
        """
        metrics = self.get_metrics()
        
        # Calculate error rate
        total_attempts = self.metrics.resolution_attempts
        error_rate = self.metrics.errors / total_attempts if total_attempts > 0 else 0.0
        
        # Determine health status based on error rate
        if total_attempts == 0 or error_rate <= 0.1:  # No attempts or <=10% error rate
            status = 'healthy'
        elif error_rate <= 0.7:  # Up to 70% error rate considered degraded  
            status = 'degraded'
        else:  # Over 70% error rate considered unhealthy
            status = 'unhealthy'
        
        health_info = {
            'status': status,
            'error_rate': error_rate,
            'cache_size': len(self.cache),
            'metrics': metrics
        }
        
        # Add time since last resolution if available
        if self.metrics.last_resolution_time:
            health_info['last_resolution_seconds_ago'] = time.time() - self.metrics.last_resolution_time
        
        return health_info


# Global DNS resolver instance
_dns_resolver: Optional[DNSResolver] = None


def get_dns_resolver() -> DNSResolver:
    """Get the global DNS resolver instance.
    
    Returns:
        Global DNSResolver instance
    """
    global _dns_resolver
    if _dns_resolver is None:
        _dns_resolver = DNSResolver()
    return _dns_resolver


def reset_dns_resolver():
    """Reset the global DNS resolver instance."""
    global _dns_resolver
    _dns_resolver = None


async def resolve_hostname(hostname_or_url: str) -> str:
    """Convenience function to resolve hostname using global resolver.
    
    Args:
        hostname_or_url: Hostname, IP address, hostname:port, or full URL
        
    Returns:
        Resolved IP address in the same format as input
        
    Raises:
        DNSResolutionError: If resolution fails and no fallback is available
    """
    resolver = get_dns_resolver()
    return await resolver.resolve(hostname_or_url)


def get_dns_metrics() -> Dict[str, Any]:
    """Get DNS resolution metrics from global resolver.
    
    Returns:
        Dictionary with comprehensive metrics
    """
    resolver = get_dns_resolver()
    return resolver.get_metrics()


def get_dns_health() -> Dict[str, Any]:
    """Get DNS resolver health status from global resolver.
    
    Returns:
        Health check status with details
    """
    resolver = get_dns_resolver()
    return resolver.health_check()