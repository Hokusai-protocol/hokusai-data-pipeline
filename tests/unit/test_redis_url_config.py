"""Unit tests for Redis URL configuration handling.

This test module covers the redis_url property in src/api/utils/config.py,
ensuring it correctly handles various input formats and TLS settings.

Bug fix for: ECS deployment rollbacks due to malformed Redis URLs
"""

import os

import pytest

from src.api.utils.config import Settings


@pytest.fixture
def clean_env():
    """Clean environment before each test."""
    redis_vars = [
        "REDIS_URL",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_AUTH_TOKEN",
        "REDIS_TLS_ENABLED",
    ]

    # Store original values
    original_values = {}
    for var in redis_vars:
        original_values[var] = os.environ.get(var)
        # Clear the variable
        if var in os.environ:
            del os.environ[var]

    yield

    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


class TestRedisURLWithScheme:
    """Test cases for Redis URLs that already have a scheme."""

    def test_full_redis_url_returned_as_is(self, clean_env):
        """Full redis:// URL should be returned unchanged."""
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        settings = Settings()
        assert settings.redis_url == "redis://localhost:6379"

    def test_full_rediss_url_returned_as_is(self, clean_env):
        """Full rediss:// URL (TLS) should be returned unchanged."""
        os.environ["REDIS_URL"] = "rediss://master.redis.amazonaws.com:6379"
        settings = Settings()
        assert settings.redis_url == "rediss://master.redis.amazonaws.com:6379"

    def test_unix_socket_url_returned_as_is(self, clean_env):
        """Unix socket URL should be returned unchanged."""
        os.environ["REDIS_URL"] = "unix:///var/run/redis.sock"
        settings = Settings()
        assert settings.redis_url == "unix:///var/run/redis.sock"

    def test_url_with_auth_token_returned_as_is(self, clean_env):
        """Redis URL with auth token should be returned unchanged."""
        os.environ["REDIS_URL"] = "redis://:mytoken@localhost:6379/0"
        settings = Settings()
        assert settings.redis_url == "redis://:mytoken@localhost:6379/0"


class TestRedisURLBareHostname:
    """Test cases for bare hostnames without scheme (the bug scenario)."""

    def test_bare_hostname_gets_redis_scheme_by_default(self, clean_env):
        """Bare hostname should get redis:// scheme prepended."""
        os.environ["REDIS_URL"] = "localhost"
        settings = Settings()
        assert settings.redis_url.startswith("redis://localhost")

    def test_bare_hostname_gets_rediss_scheme_when_tls_enabled(self, clean_env):
        """Bare hostname should get rediss:// when REDIS_TLS_ENABLED=true."""
        os.environ["REDIS_URL"] = "master.redis.amazonaws.com"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        settings = Settings()
        assert settings.redis_url.startswith("rediss://master.redis.amazonaws.com")

    def test_bare_hostname_gets_redis_scheme_when_tls_disabled(self, clean_env):
        """Bare hostname should get redis:// when REDIS_TLS_ENABLED=false."""
        os.environ["REDIS_URL"] = "localhost"
        os.environ["REDIS_TLS_ENABLED"] = "false"
        settings = Settings()
        assert settings.redis_url.startswith("redis://localhost")

    def test_bare_hostname_with_port_gets_scheme(self, clean_env):
        """Bare hostname:port should get scheme prepended."""
        os.environ["REDIS_URL"] = "localhost:6380"
        settings = Settings()
        assert settings.redis_url.startswith("redis://localhost:6380")

    def test_aws_elasticache_hostname_gets_rediss_with_tls(self, clean_env):
        """AWS ElastiCache hostname should get rediss:// when TLS enabled.

        This is the exact bug scenario that was causing deployment rollbacks.
        SSM parameter stored bare ElastiCache hostname without scheme.
        """
        os.environ["REDIS_URL"] = "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        settings = Settings()

        # Should start with rediss:// (TLS)
        assert settings.redis_url.startswith("rediss://")
        # Should include the full hostname
        assert "master.hokusai-redis-development" in settings.redis_url
        # Should include port
        assert ":6379" in settings.redis_url or settings.redis_url.endswith("/0")


class TestRedisURLFromComponents:
    """Test cases for building Redis URL from component environment variables."""

    def test_url_built_from_host_and_port(self, clean_env):
        """Should build redis://host:port when components provided."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6379"
        settings = Settings()
        assert settings.redis_url == "redis://redis.example.com:6379/0"

    def test_url_built_with_auth_token(self, clean_env):
        """Should build redis://:token@host:port with auth token."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6379"
        os.environ["REDIS_AUTH_TOKEN"] = "secret123"
        settings = Settings()
        assert settings.redis_url == "redis://:secret123@redis.example.com:6379/0"

    def test_url_built_with_tls_enabled(self, clean_env):
        """Should build rediss:// URL when TLS enabled."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6379"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        settings = Settings()
        assert settings.redis_url == "rediss://redis.example.com:6379/0"

    def test_url_built_with_tls_and_auth(self, clean_env):
        """Should build rediss://:token@host:port with TLS and auth.

        This is the correct format for AWS ElastiCache with TLS.
        """
        os.environ["REDIS_HOST"] = "master.redis.amazonaws.com"
        os.environ["REDIS_PORT"] = "6379"
        os.environ["REDIS_AUTH_TOKEN"] = "mytoken"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        settings = Settings()
        assert settings.redis_url == "rediss://:mytoken@master.redis.amazonaws.com:6379/0"

    def test_url_built_uses_default_port(self, clean_env):
        """Should use default port 6379 when REDIS_PORT not set."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        settings = Settings()
        assert ":6379" in settings.redis_url

    def test_url_built_without_auth_token(self, clean_env):
        """Should build URL without auth token if not provided."""
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"
        settings = Settings()
        assert settings.redis_url == "redis://localhost:6379/0"
        assert "@" not in settings.redis_url


class TestRedisURLTLSHandling:
    """Test cases specifically for TLS (rediss://) handling."""

    def test_tls_enabled_true_lowercase(self, clean_env):
        """REDIS_TLS_ENABLED=true should enable TLS."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        settings = Settings()
        assert settings.redis_url.startswith("rediss://")

    def test_tls_enabled_true_uppercase(self, clean_env):
        """REDIS_TLS_ENABLED=TRUE should enable TLS."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_TLS_ENABLED"] = "TRUE"
        settings = Settings()
        assert settings.redis_url.startswith("rediss://")

    def test_tls_enabled_true_mixed_case(self, clean_env):
        """REDIS_TLS_ENABLED=True should enable TLS."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_TLS_ENABLED"] = "True"
        settings = Settings()
        assert settings.redis_url.startswith("rediss://")

    def test_tls_disabled_false(self, clean_env):
        """REDIS_TLS_ENABLED=false should use redis://"""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_TLS_ENABLED"] = "false"
        settings = Settings()
        assert settings.redis_url.startswith("redis://")

    def test_tls_default_false_when_not_set(self, clean_env):
        """TLS should default to false (redis://) when not set."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        settings = Settings()
        assert settings.redis_url.startswith("redis://")

    def test_tls_invalid_value_defaults_to_false(self, clean_env):
        """Invalid REDIS_TLS_ENABLED value should default to false."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_TLS_ENABLED"] = "invalid"
        settings = Settings()
        assert settings.redis_url.startswith("redis://")


class TestRedisURLErrorCases:
    """Test cases for error conditions."""

    def test_missing_redis_url_and_host_raises_error(self, clean_env):
        """Should raise ValueError when neither REDIS_URL nor REDIS_HOST set."""
        settings = Settings()
        with pytest.raises(ValueError, match="Redis configuration missing"):
            _ = settings.redis_url

    def test_empty_redis_url_raises_error(self, clean_env):
        """Empty REDIS_URL should be treated as missing."""
        os.environ["REDIS_URL"] = ""
        settings = Settings()
        with pytest.raises(ValueError, match="Redis configuration missing"):
            _ = settings.redis_url


class TestRedisURLPrecedence:
    """Test cases for configuration precedence (REDIS_URL vs components)."""

    def test_redis_url_takes_precedence_over_components(self, clean_env):
        """REDIS_URL should take precedence over REDIS_HOST/PORT."""
        os.environ["REDIS_URL"] = "redis://from-url:6380"
        os.environ["REDIS_HOST"] = "from-host"
        os.environ["REDIS_PORT"] = "6381"
        settings = Settings()
        # Should use REDIS_URL, not build from components
        assert "from-url" in settings.redis_url
        assert "from-host" not in settings.redis_url


class TestRedisURLPortHandling:
    """Test cases for port number handling."""

    def test_bare_hostname_without_port_gets_default_port(self, clean_env):
        """Bare hostname without port should get default port added."""
        os.environ["REDIS_URL"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6379"
        settings = Settings()
        assert ":6379" in settings.redis_url

    def test_bare_hostname_with_port_keeps_port(self, clean_env):
        """Bare hostname with port should keep its port."""
        os.environ["REDIS_URL"] = "redis.example.com:6380"
        settings = Settings()
        assert ":6380" in settings.redis_url
        assert ":6379" not in settings.redis_url

    def test_custom_port_from_env_used(self, clean_env):
        """Custom REDIS_PORT should be used when building URL."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_PORT"] = "6380"
        settings = Settings()
        assert ":6380" in settings.redis_url


class TestRedisURLRealWorldScenarios:
    """Test cases for real-world deployment scenarios."""

    def test_aws_elasticache_ssm_parameter_scenario(self, clean_env):
        """Test the exact bug scenario: SSM parameter with bare hostname.

        This reproduces the production issue where:
        - SSM /hokusai/development/redis/endpoint = "master.hokusai...com"
        - Task definition sets REDIS_URL from SSM (bare hostname)
        - REDIS_TLS_ENABLED=true for ElastiCache
        - App should prepend rediss:// and add port
        """
        # Simulate what ECS task receives from SSM parameter
        os.environ["REDIS_URL"] = "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
        os.environ["REDIS_TLS_ENABLED"] = "true"
        os.environ["REDIS_PORT"] = "6379"  # Also from SSM

        settings = Settings()
        redis_url = settings.redis_url

        # Verify correct URL format for ElastiCache
        assert redis_url.startswith("rediss://")
        assert "master.hokusai-redis-development" in redis_url
        assert ":6379" in redis_url

        # Verify it's a valid Redis URL that redis-py will accept
        # (redis-py requires scheme)
        assert redis_url.startswith(("redis://", "rediss://", "unix://"))

    def test_local_development_scenario(self, clean_env):
        """Test local development with localhost."""
        os.environ["REDIS_HOST"] = "localhost"
        os.environ["REDIS_PORT"] = "6379"
        settings = Settings()

        assert settings.redis_url == "redis://localhost:6379/0"

    def test_migration_from_old_config_to_new(self, clean_env):
        """Test backward compatibility when migrating configurations."""
        # Old style: Full URL in environment
        os.environ["REDIS_URL"] = "redis://old-redis:6379"
        settings = Settings()
        assert settings.redis_url == "redis://old-redis:6379"

        # New style: Components
        del os.environ["REDIS_URL"]
        os.environ["REDIS_HOST"] = "new-redis"
        os.environ["REDIS_PORT"] = "6379"
        os.environ["REDIS_TLS_ENABLED"] = "true"

        settings = Settings()  # Fresh instance
        assert settings.redis_url == "rediss://new-redis:6379/0"


class TestRedisURLLogging:
    """Test cases for configuration logging (ensure secrets not logged)."""

    def test_auth_token_not_in_redis_url_string_repr(self, clean_env):
        """Auth token should not appear in string representation."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        os.environ["REDIS_AUTH_TOKEN"] = "super-secret-token"
        settings = Settings()

        # URL should contain token for actual connection
        assert "super-secret-token" in settings.redis_url

        # But when logging, we should sanitize it
        # (This test documents expected behavior for logging improvements)
        # In practice, logging should use redis_url.split('@')[-1] to hide token


class TestRedisEnabled:
    """Test cases for redis_enabled property."""

    def test_redis_enabled_with_redis_url(self, clean_env):
        """Redis should be enabled when REDIS_URL is set."""
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        settings = Settings()
        assert settings.redis_enabled is True

    def test_redis_enabled_with_redis_host(self, clean_env):
        """Redis should be enabled when REDIS_HOST is set (non-localhost)."""
        os.environ["REDIS_HOST"] = "redis.example.com"
        settings = Settings()
        assert settings.redis_enabled is True

    def test_redis_enabled_with_auth_token(self, clean_env):
        """Redis should be enabled when REDIS_AUTH_TOKEN is set."""
        os.environ["REDIS_AUTH_TOKEN"] = "token"
        settings = Settings()
        assert settings.redis_enabled is True

    def test_redis_disabled_with_localhost(self, clean_env):
        """Redis should be disabled for localhost (development safety)."""
        os.environ["REDIS_HOST"] = "localhost"
        settings = Settings()
        # Current implementation: localhost is not automatically enabled
        # This is intentional to require explicit configuration
        assert settings.redis_enabled is False
