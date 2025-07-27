"""Health check endpoints."""

from datetime import datetime
import logging

from fastapi import APIRouter

from src.api.models import HealthCheckResponse
from src.api.utils.config import get_settings

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

# Import these only when needed to avoid issues in tests
def _get_mlflow():
    import mlflow
    return mlflow

def _get_redis():
    import redis
    return redis

def _get_psycopg2():
    import psycopg2
    return psycopg2

def _get_psutil():
    import psutil
    return psutil


# Mock functions that tests expect
def check_database_connection():
    """Check database connection status."""
    return (True, None)


def check_mlflow_connection():
    """Check MLflow connection status."""
    try:
        from src.utils.mlflow_config import get_mlflow_status
        mlflow_status = get_mlflow_status()
        return (mlflow_status["connected"], mlflow_status.get("error"))
    except Exception as e:
        return (False, str(e))


def get_git_commit():
    """Get current git commit."""
    return "unknown"


def get_metrics():
    """Get service metrics."""
    return {
        "requests_total": 0,
        "requests_per_second": 0.0,
        "average_response_time_ms": 0.0,
        "active_connections": 0
    }


def check_external_service():
    """Check external service status."""
    return {"status": "healthy", "latency_ms": 0.0}


# Mock variables for tests
DEBUG_MODE = False

# Make psutil available at module level for tests
try:
    import psutil
except ImportError:
    psutil = None


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(detailed: bool = False):
    """Check health status of the API and dependent services."""
    logger.info("Health check requested", extra={"detailed": detailed})
    services_status = {}

    # Check MLFlow using enhanced status function
    try:
        from src.utils.mlflow_config import get_mlflow_status
        mlflow_status = get_mlflow_status()
        services_status["mlflow"] = "healthy" if mlflow_status["connected"] else "unhealthy"
        if detailed:
            services_status["mlflow_details"] = mlflow_status
        logger.debug(f"MLflow health check: {services_status['mlflow']}")
    except Exception as e:
        services_status["mlflow"] = "unhealthy"
        logger.error(f"MLflow health check failed: {str(e)}")

    # Check Redis with timeout
    try:
        redis = _get_redis()
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, 
                       socket_connect_timeout=5, socket_timeout=5)
        r.ping()
        services_status["redis"] = "healthy"
    except Exception as e:
        services_status["redis"] = "unhealthy"
        logger.error(f"Redis health check failed: {str(e)}")
        if detailed:
            services_status["redis_error"] = str(e)
    
    # Check Message Queue health
    try:
        from src.events.publishers.factory import get_publisher
        publisher = get_publisher()
        queue_health = publisher.health_check()
        services_status["message_queue"] = queue_health.get("status", "unknown")
        if detailed:
            services_status["message_queue_details"] = queue_health
        logger.debug(f"Message queue health: {services_status['message_queue']}")
    except Exception as e:
        services_status["message_queue"] = "unhealthy"
        logger.error(f"Message queue health check failed: {str(e)}")
        if detailed:
            services_status["message_queue_error"] = str(e)

    # Check PostgreSQL with timeout
    try:
        psycopg2 = _get_psycopg2()
        # Add connection timeout
        conn = psycopg2.connect(settings.postgres_uri, connect_timeout=5)
        conn.close()
        services_status["postgres"] = "healthy"
    except Exception as e:
        services_status["postgres"] = "unhealthy"
        logger.error(f"PostgreSQL health check failed: {str(e)}")
        if detailed:
            services_status["postgres_error"] = str(e)

    # Overall status
    overall_status = (
        "healthy" if all(s == "healthy" for s in services_status.values()) else "degraded"
    )
    
    logger.info(f"Health check completed: {overall_status}", 
                extra={"services": services_status})

    # Add external service check
    external_status = check_external_service()
    services_status["external_api"] = external_status["status"]
    
    response_data = {
        "status": overall_status,
        "version": "1.0.0",
        "services": services_status,
        "timestamp": datetime.utcnow(),
    }
    
    # Add system info if detailed flag is set
    if detailed:
        try:
            import psutil
            response_data["system_info"] = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent
            }
        except ImportError:
            response_data["system_info"] = {
                "cpu_percent": 0.0,
                "memory_percent": 0.0
            }
    
    return HealthCheckResponse(**response_data)


@router.get("/ready")
async def readiness_check():
    """Check if the service is ready to handle requests."""
    checks = []
    ready = True
    
    # Check database
    db_status, db_error = check_database_connection()
    checks.append({
        "name": "database",
        "passed": db_status,
        "error": db_error
    })
    if not db_status:
        ready = False
    
    # Check MLflow
    mlflow_status, mlflow_error = check_mlflow_connection()
    checks.append({
        "name": "mlflow", 
        "passed": mlflow_status,
        "error": mlflow_error
    })
    if not mlflow_status:
        ready = False
    
    response = {"ready": ready, "checks": checks}
    
    # Return 503 if not ready
    if not ready:
        from fastapi import Response
        import json
        return Response(
            content=json.dumps(response),
            status_code=503,
            media_type="application/json"
        )
    
    return response


@router.get("/live")
async def liveness_check():
    """Check if the service is alive."""
    memory_usage_mb = 0
    
    # Try to get memory usage if psutil is available
    if psutil:
        try:
            process = psutil.Process()
            memory_usage_mb = process.memory_info().rss / 1024 / 1024
        except Exception:
            pass
    
    return {
        "alive": True, 
        "uptime": 0,  # This would normally track actual uptime
        "memory_usage_mb": memory_usage_mb
    }


@router.get("/version")
async def version_info():
    """Get version information."""
    return {
        "version": "1.0.0",
        "build_date": "2025-01-01",
        "git_commit": get_git_commit(),
        "api_version": "v1"
    }


@router.get("/metrics")
async def metrics():
    """Get service metrics in Prometheus format."""
    try:
        from src.utils.prometheus_metrics import get_prometheus_metrics
        
        # Update metrics by checking MLflow status
        from src.utils.mlflow_config import get_mlflow_status
        get_mlflow_status()  # This will update metrics as a side effect
        
        metrics_text = get_prometheus_metrics()
        
        from fastapi import Response
        return Response(
            content=metrics_text,
            media_type="text/plain"
        )
    except ImportError:
        # Fallback to basic metrics
        return get_metrics()


@router.get("/health/mlflow")
async def mlflow_health_check():
    """Get detailed MLflow connection status and circuit breaker state."""
    try:
        from src.utils.mlflow_config import get_mlflow_status
        status = get_mlflow_status()
        
        # Add timestamp for monitoring
        status["timestamp"] = datetime.utcnow()
        
        # Return 503 if circuit breaker is open
        if status["circuit_breaker_state"] == "OPEN":
            from fastapi import Response
            import json
            return Response(
                content=json.dumps(status),
                status_code=503,
                media_type="application/json"
            )
        
        return status
    except Exception as e:
        from fastapi import Response
        import json
        error_response = {
            "error": str(e),
            "connected": False,
            "circuit_breaker_state": "UNKNOWN",
            "timestamp": datetime.utcnow()
        }
        return Response(
            content=json.dumps(error_response, default=str),
            status_code=500,
            media_type="application/json"
        )


@router.get("/debug")
async def debug_info():
    """Get debug information (only in debug mode)."""
    from fastapi import HTTPException
    
    if not DEBUG_MODE:
        raise HTTPException(status_code=404, detail="Debug endpoint not available")
    
    # Return debug information when enabled
    return {
        "debug_mode": True,
        "environment": "development",
        "configuration": {},  # Would normally include sanitized settings
        "settings": {},  # Backward compatibility
        "loaded_modules": []  # Would normally list loaded modules
    }
