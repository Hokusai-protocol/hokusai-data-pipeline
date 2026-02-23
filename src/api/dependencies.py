"""Dependency providers for API routes."""

from __future__ import annotations

from functools import lru_cache

import redis
from fastapi import Depends
from redis import Redis

from src.api.services.evaluation_service import EvaluationService
from src.api.utils.config import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """Return a shared Redis client backed by a connection pool."""
    settings = get_settings()
    pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=pool)


def get_evaluation_service(redis_client: Redis = Depends(get_redis_client)) -> EvaluationService:
    """Return a service instance for evaluation operations."""
    return EvaluationService(redis_client=redis_client)
