#!/usr/bin/env python3
"""Test Redis configuration to debug deployment issue."""

import os
import sys

# Set the environment variables as they are in ECS
os.environ["REDIS_HOST"] = "master.hokusai-redis-development.lenvj6.use1.cache.amazonaws.com"
os.environ["REDIS_PORT"] = "6379"
# No auth token since it was removed temporarily
os.environ.pop("REDIS_AUTH_TOKEN", None)

# Add src to path
sys.path.insert(0, ".")

from src.api.utils.config import Settings

# Test the configuration
settings = Settings()

print("Testing Redis Configuration")
print("=" * 50)
print(f"REDIS_HOST from env: {os.getenv('REDIS_HOST')}")
print(f"REDIS_PORT from env: {os.getenv('REDIS_PORT')}")
print(f"REDIS_AUTH_TOKEN from env: {os.getenv('REDIS_AUTH_TOKEN')}")
print("")
print("Settings Object:")
print(f"  redis_host: {settings.redis_host}")
print(f"  redis_port: {settings.redis_port}")
print(f"  redis_auth_token: {settings.redis_auth_token}")
print(f"  redis_enabled: {settings.redis_enabled}")
print(f"  redis_url: {settings.redis_url}")
print("")

# Test the health check logic
if settings.redis_enabled:
    print("✅ Redis is enabled in settings")
    print(f"Would connect to: {settings.redis_url}")
else:
    print("❌ Redis is NOT enabled in settings")
    print("This is why it's not connecting!")

# Also test the factory
from src.events.publishers.factory import create_publisher

print("\nTesting Publisher Factory:")
try:
    publisher = create_publisher("redis")
    print(f"Publisher created with URL: {publisher.redis_url}")
except Exception as e:
    print(f"Error creating publisher: {e}")