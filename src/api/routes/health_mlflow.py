"""MLflow health check endpoints accessible at /api/health/mlflow."""

import os
import httpx
from fastapi import APIRouter, HTTPException
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()

# MLflow server configuration
MLFLOW_SERVER_URL = os.getenv("MLFLOW_SERVER_URL", "http://10.0.1.88:5000"  # TEMPORARY: Direct IP until service discovery fixed)
ENABLE_DEBUG_LOGGING = os.getenv("MLFLOW_PROXY_DEBUG", "false").lower() == "true"


@router.get("/mlflow")
async def mlflow_health_check() -> Dict[str, Any]:
    """Check if MLflow server is accessible with detailed diagnostics."""
    health_status = {
        "mlflow_server": MLFLOW_SERVER_URL,
        "checks": {
            "connectivity": {"status": "unknown", "message": ""},
            "experiments_api": {"status": "unknown", "message": ""},
            "artifacts_api": {"status": "unknown", "message": ""}
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check basic connectivity
            try:
                response = await client.get(f"{MLFLOW_SERVER_URL}/health")
                if response.status_code in [200, 404]:  # 404 is OK, means server is up
                    health_status["checks"]["connectivity"] = {
                        "status": "healthy",
                        "message": "MLflow server is reachable"
                    }
                else:
                    health_status["checks"]["connectivity"] = {
                        "status": "unhealthy",
                        "message": f"Unexpected status code: {response.status_code}"
                    }
            except Exception as e:
                health_status["checks"]["connectivity"] = {
                    "status": "unhealthy",
                    "message": str(e)
                }
            
            # Check experiments API
            try:
                # Use appropriate API path based on server type
                api_path = "ajax-api" if "registry.hokus.ai" in MLFLOW_SERVER_URL else "api"
                response = await client.get(
                    f"{MLFLOW_SERVER_URL}/{api_path}/2.0/mlflow/experiments/search?max_results=1"
                )
                if response.status_code == 200:
                    health_status["checks"]["experiments_api"] = {
                        "status": "healthy",
                        "message": "Experiments API is functional"
                    }
                else:
                    health_status["checks"]["experiments_api"] = {
                        "status": "unhealthy",
                        "message": f"API returned status {response.status_code}"
                    }
            except Exception as e:
                health_status["checks"]["experiments_api"] = {
                    "status": "unhealthy",
                    "message": str(e)
                }
            
            # Check if artifact serving is enabled
            if os.getenv("MLFLOW_SERVE_ARTIFACTS", "true").lower() == "true":
                health_status["checks"]["artifacts_api"] = {
                    "status": "enabled",
                    "message": "Artifact serving is configured"
                }
            else:
                health_status["checks"]["artifacts_api"] = {
                    "status": "disabled",
                    "message": "Artifact serving is not configured"
                }
    
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        health_status["error"] = str(e)
    
    # Determine overall status
    all_healthy = all(
        check.get("status") in ["healthy", "enabled", "disabled"] 
        for check in health_status["checks"].values()
    )
    health_status["status"] = "healthy" if all_healthy else "unhealthy"
    
    # Return appropriate status code
    if not all_healthy:
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status


@router.get("/mlflow/detailed")
async def mlflow_detailed_health_check() -> Dict[str, Any]:
    """Perform comprehensive MLflow health checks including all API endpoints."""
    results = {
        "mlflow_server": MLFLOW_SERVER_URL,
        "timestamp": os.popen('date').read().strip(),
        "environment": {
            "MLFLOW_SERVER_URL": MLFLOW_SERVER_URL,
            "MLFLOW_SERVE_ARTIFACTS": os.getenv("MLFLOW_SERVE_ARTIFACTS", "true"),
            "PROXY_DEBUG": ENABLE_DEBUG_LOGGING
        },
        "tests": []
    }
    
    # Test cases for different MLflow endpoints
    test_endpoints = [
        {"name": "experiments_list", "path": "/api/2.0/mlflow/experiments/search", "method": "GET"},
        {"name": "models_list", "path": "/api/2.0/mlflow/registered-models/search", "method": "GET"},
        {"name": "metrics_history", "path": "/api/2.0/mlflow/metrics/get-history", "method": "GET"},
    ]
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for test in test_endpoints:
            try:
                # Adjust path for external vs internal MLflow
                path = test["path"]
                if "registry.hokus.ai" in MLFLOW_SERVER_URL:
                    path = path.replace("/api/2.0/", "/ajax-api/2.0/")
                
                url = f"{MLFLOW_SERVER_URL}{path}"
                response = await client.request(method=test["method"], url=url)
                
                results["tests"].append({
                    "endpoint": test["name"],
                    "url": url,
                    "status_code": response.status_code,
                    "success": response.status_code < 400,
                    "response_time_ms": response.elapsed.total_seconds() * 1000
                })
            except Exception as e:
                results["tests"].append({
                    "endpoint": test["name"],
                    "url": url,
                    "success": False,
                    "error": str(e)
                })
    
    # Overall health determination
    results["overall_health"] = all(test.get("success", False) for test in results["tests"])
    
    return results


@router.get("/mlflow/connectivity")
async def mlflow_connectivity_check() -> Dict[str, Any]:
    """Simple connectivity check for MLflow server."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{MLFLOW_SERVER_URL}/health")
            
            return {
                "status": "connected" if response.status_code in [200, 404] else "error",
                "mlflow_server": MLFLOW_SERVER_URL,
                "response_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
    except httpx.TimeoutException:
        return {
            "status": "timeout",
            "mlflow_server": MLFLOW_SERVER_URL,
            "error": "Connection timeout after 3 seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "mlflow_server": MLFLOW_SERVER_URL,
            "error": str(e)
        }