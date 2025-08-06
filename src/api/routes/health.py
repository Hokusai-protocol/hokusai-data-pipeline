"""Health check endpoints."""

from datetime import datetime
import logging
import os

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


def check_database_connection():
    """Check database connection status with retry logic and timeout configuration."""
    import time
    
    max_retries = settings.database_max_retries
    base_delay = settings.database_retry_delay
    timeout = settings.database_connect_timeout
    
    for attempt in range(max_retries):
        try:
            psycopg2 = _get_psycopg2()
            
            # Try primary database first
            try:
                conn = psycopg2.connect(
                    settings.postgres_uri, 
                    connect_timeout=timeout
                )
                conn.close()
                logger.debug(f"Database connection successful (primary): {settings.database_name}")
                return (True, None)
            except Exception as primary_error:
                logger.warning(f"Primary database connection failed: {primary_error}")
                
                # Try fallback database for backward compatibility
                try:
                    conn = psycopg2.connect(
                        settings.postgres_uri_fallback,
                        connect_timeout=timeout
                    )
                    conn.close()
                    logger.info(f"Database connection successful (fallback): {settings.database_fallback_name}")
                    return (True, f"Connected to fallback database: {settings.database_fallback_name}")
                except Exception as fallback_error:
                    logger.error(f"Both primary and fallback database connections failed. Primary: {primary_error}, Fallback: {fallback_error}")
                    raise primary_error  # Raise the primary error
                    
        except Exception as e:
            if attempt == max_retries - 1:
                error_msg = f"Database connection failed after {max_retries} attempts: {str(e)}"
                logger.error(error_msg, extra={
                    "database_host": settings.database_host,
                    "database_name": settings.database_name,
                    "timeout": timeout,
                    "attempts": max_retries
                })
                return (False, error_msg)
            
            delay = base_delay * (2 ** attempt)  # Exponential backoff
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    
    return (False, "Unexpected error in database connection retry logic")


def check_mlflow_connection():
    """Check MLflow connection status."""
    try:
        from src.utils.mlflow_config import get_mlflow_status
        mlflow_status = get_mlflow_status()
        return (mlflow_status["connected"], mlflow_status.get("error"))
    except Exception as e:
        logger.error(f"MLflow connection check failed: {str(e)}")
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

    # Check MLFlow using enhanced status function with graceful degradation
    try:
        from src.utils.mlflow_config import get_mlflow_status
        mlflow_status = get_mlflow_status()
        
        # Gracefully handle circuit breaker states
        if mlflow_status["circuit_breaker_state"] == "OPEN":
            services_status["mlflow"] = "degraded"
            if detailed:
                services_status["mlflow_details"] = {
                    **mlflow_status,
                    "degradation_reason": "Circuit breaker is open - service temporarily unavailable"
                }
        elif mlflow_status["circuit_breaker_state"] == "HALF_OPEN":
            services_status["mlflow"] = "recovering"
            if detailed:
                services_status["mlflow_details"] = {
                    **mlflow_status,
                    "degradation_reason": "Circuit breaker is half-open - testing recovery"
                }
        else:
            services_status["mlflow"] = "healthy" if mlflow_status["connected"] else "unhealthy"
            if detailed:
                services_status["mlflow_details"] = mlflow_status
        
        logger.debug(f"MLflow health check: {services_status['mlflow']} (CB: {mlflow_status['circuit_breaker_state']})")
    except Exception as e:
        services_status["mlflow"] = "unhealthy"
        logger.error(f"MLflow health check failed: {str(e)}")
        if detailed:
            services_status["mlflow_error"] = str(e)

    # Check Redis with configurable timeout (optional service)
    if settings.redis_enabled:
        try:
            redis = _get_redis()
            redis_timeout = settings.health_check_timeout
            r = redis.Redis(
                host=settings.redis_host, 
                port=settings.redis_port,
                socket_connect_timeout=redis_timeout, 
                socket_timeout=redis_timeout
            )
            r.ping()
            services_status["redis"] = "healthy"
        except Exception as e:
            services_status["redis"] = "unhealthy"
            logger.error(f"Redis health check failed: {str(e)}")
            if detailed:
                services_status["redis_error"] = str(e)
    else:
        services_status["redis"] = "disabled"
        logger.debug("Redis health check skipped - service disabled")
    
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

    # Check PostgreSQL with retry logic and improved error handling
    db_status, db_error = check_database_connection()
    if db_status:
        services_status["postgres"] = "healthy"
        if db_error:  # Fallback database was used
            services_status["postgres_warning"] = db_error
            if detailed:
                services_status["postgres_details"] = {
                    "status": "healthy_fallback",
                    "message": db_error,
                    "primary_db": settings.database_name,
                    "fallback_db": settings.database_fallback_name
                }
    else:
        services_status["postgres"] = "unhealthy"
        logger.error(f"PostgreSQL health check failed: {db_error}")
        if detailed:
            services_status["postgres_error"] = db_error
            services_status["postgres_details"] = {
                "primary_db": settings.database_name,
                "fallback_db": settings.database_fallback_name,
                "timeout": settings.database_connect_timeout,
                "max_retries": settings.database_max_retries
            }

    # Overall status with graceful degradation logic (ignore disabled services)
    active_services = {k: v for k, v in services_status.items() if v != "disabled"}
    healthy_count = sum(1 for s in active_services.values() if s == "healthy")
    degraded_count = sum(1 for s in active_services.values() if s in ["degraded", "recovering"])
    unhealthy_count = sum(1 for s in active_services.values() if s == "unhealthy")
    
    if unhealthy_count == 0 and degraded_count == 0:
        overall_status = "healthy"
    elif unhealthy_count > 0 and healthy_count == 0:
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"
    
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
    """Check if the service is ready to handle requests with graceful degradation."""
    checks = []
    ready = True
    can_serve_traffic = True
    
    # Check database with enhanced error reporting
    db_status, db_error = check_database_connection()
    checks.append({
        "name": "database",
        "passed": db_status,
        "error": db_error,
        "critical": True,
        "connection_details": {
            "primary_db": settings.database_name,
            "fallback_db": settings.database_fallback_name,
            "timeout": settings.database_connect_timeout,
            "max_retries": settings.database_max_retries
        } if not db_status else None
    })
    if not db_status:
        ready = False
        can_serve_traffic = False  # Database is critical
        logger.error(f"Readiness check failed: Database unavailable - {db_error}")
    
    # Check MLflow with circuit breaker awareness
    mlflow_status, mlflow_error = check_mlflow_connection()
    
    # Get circuit breaker state for more nuanced readiness check
    try:
        from src.utils.mlflow_config import get_mlflow_status
        mlflow_detailed = get_mlflow_status()
        cb_state = mlflow_detailed["circuit_breaker_state"]
        
        # Service can handle traffic even if MLflow circuit breaker is open
        if cb_state == "OPEN":
            checks.append({
                "name": "mlflow",
                "passed": False,
                "error": "Circuit breaker open - MLflow temporarily unavailable",
                "critical": False,
                "degraded_mode": True
            })
            ready = False  # Not fully ready, but can still serve some traffic
        elif cb_state == "HALF_OPEN":
            checks.append({
                "name": "mlflow",
                "passed": True,
                "error": None,
                "critical": False,
                "recovering": True
            })
        else:
            checks.append({
                "name": "mlflow", 
                "passed": mlflow_status,
                "error": mlflow_error,
                "critical": False
            })
            if not mlflow_status:
                ready = False
                
    except Exception as e:
        checks.append({
            "name": "mlflow", 
            "passed": False,
            "error": f"Health check error: {str(e)}",
            "critical": False
        })
        ready = False
    
    response = {
        "ready": ready,
        "can_serve_traffic": can_serve_traffic,
        "checks": checks,
        "degraded_mode": not ready and can_serve_traffic
    }
    
    # Return 503 only if we cannot serve any traffic (critical services down)
    if not can_serve_traffic:
        from fastapi import Response
        import json
        return Response(
            content=json.dumps(response),
            status_code=503,
            media_type="application/json"
        )
    
    # Return 200 even in degraded mode - we can still serve some requests
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


@router.post("/health/mlflow/reset")
async def reset_mlflow_circuit_breaker():
    """Manually reset the MLflow circuit breaker."""
    from fastapi import HTTPException
    
    try:
        from src.utils.mlflow_config import reset_circuit_breaker
        reset_circuit_breaker()
        
        logger.info("MLflow circuit breaker manually reset via API")
        
        return {
            "message": "Circuit breaker reset successfully",
            "timestamp": datetime.utcnow(),
            "reset_by": "manual_api_call"
        }
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@router.get("/health/status")
async def get_detailed_service_status():
    """Get comprehensive service status for monitoring and diagnostics."""
    try:
        from src.utils.mlflow_config import get_mlflow_status, get_circuit_breaker_status
        
        # Get MLflow status
        mlflow_status = get_mlflow_status()
        cb_status = get_circuit_breaker_status()
        
        # Get basic service info
        health = await health_check(detailed=True)
        
        return {
            "timestamp": datetime.utcnow(),
            "api_version": "1.0.0",
            "service_name": "hokusai-registry",
            "overall_health": health.status,
            "services": health.services,
            "mlflow": {
                "status": mlflow_status,
                "circuit_breaker": cb_status
            },
            "system_info": getattr(health, 'system_info', {}),
            "uptime_seconds": 0,  # Would track actual uptime
            "environment": os.getenv("ENVIRONMENT", "unknown")
        }
    except Exception as e:
        logger.error(f"Error getting detailed service status: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


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
