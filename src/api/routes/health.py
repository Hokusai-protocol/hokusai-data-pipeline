"""Health check endpoints."""

from datetime import datetime

import mlflow
import psycopg2
import redis
from fastapi import APIRouter

from src.api.models import HealthCheckResponse
from src.api.utils.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Check health status of the API and dependent services."""
    services_status = {}

    # Check MLFlow
    try:
        mlflow.get_tracking_uri()
        services_status["mlflow"] = "healthy"
    except Exception:
        services_status["mlflow"] = "unhealthy"

    # Check Redis
    try:
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port)
        r.ping()
        services_status["redis"] = "healthy"
    except Exception:
        services_status["redis"] = "unhealthy"

    # Check PostgreSQL
    try:
        conn = psycopg2.connect(settings.postgres_uri)
        conn.close()
        services_status["postgres"] = "healthy"
    except Exception:
        services_status["postgres"] = "unhealthy"

    # Overall status
    overall_status = (
        "healthy" if all(s == "healthy" for s in services_status.values()) else "degraded"
    )

    return HealthCheckResponse(
        status=overall_status,
        version="1.0.0",
        services=services_status,
        timestamp=datetime.utcnow(),
    )
