"""MLflow proxy router to forward requests to MLflow server with improved routing."""

import json
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()

# MLflow server configuration with fallback for local development
MLFLOW_SERVER_URL = os.getenv(
    "MLFLOW_SERVER_URL", "http://mlflow.hokusai-development.local:5000"
)  # Use service discovery DNS
PROXY_TIMEOUT = 30.0  # seconds
ENABLE_DEBUG_LOGGING = os.getenv("MLFLOW_PROXY_DEBUG", "false").lower() == "true"


async def proxy_request(
    request: Request, path: str, mlflow_base_url: str = MLFLOW_SERVER_URL
) -> Response:
    """Proxy requests to MLflow server with improved routing and logging.

    Args:
    ----
        request: The incoming FastAPI request
        path: The path to forward to MLflow
        mlflow_base_url: Base URL of the MLflow server

    Returns:
    -------
        Response from MLflow server

    """
    original_path = path

    # Enhanced logging for debugging
    if ENABLE_DEBUG_LOGGING:
        logger.debug(f"Incoming proxy request: method={request.method}, path={path}")
        logger.debug(f"MLflow base URL: {mlflow_base_url}")

    # Path translation for MLflow API compatibility
    # MLflow expects either 'api/2.0' or 'ajax-api/2.0' depending on the deployment
    if path.startswith("api/2.0/mlflow/"):
        # For internal MLflow server, use standard API path
        if "registry.hokus.ai" in mlflow_base_url:
            # External MLflow uses ajax-api
            path = path.replace("api/2.0/mlflow/", "ajax-api/2.0/mlflow/")
            logger.info(f"Converted path for external MLflow: {original_path} -> {path}")
        else:
            # Internal MLflow uses standard api path
            logger.info(f"Using standard API path for internal MLflow: {path}")

    # Handle artifact endpoints with proper path translation
    if path.startswith("api/2.0/mlflow-artifacts/"):
        logger.info(f"Proxying artifact request: {path}")

        # Apply the same ajax-api conversion for external MLflow
        if "registry.hokus.ai" in mlflow_base_url:
            path = path.replace("api/2.0/mlflow-artifacts/", "ajax-api/2.0/mlflow-artifacts/")
            logger.info(f"Converted artifact path for external MLflow: {original_path} -> {path}")

        # Check if artifact serving is enabled
        if not os.getenv("MLFLOW_SERVE_ARTIFACTS", "true").lower() == "true":
            logger.warning("Artifact storage is disabled by configuration")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "ARTIFACTS_DISABLED",
                    "message": "Artifact storage is not configured. Please contact your administrator.",
                },
            )

    # Construct the target URL
    target_url = f"{mlflow_base_url}/{path}"

    # Log the final target URL for debugging
    logger.info(f"Proxying request: {request.method} {original_path} -> {target_url}")

    # Get the HTTP method
    method = request.method.lower()

    # Prepare headers, keeping track of the authenticated user
    headers = dict(request.headers)

    # Add user context headers for MLflow tracking
    if hasattr(request.state, "user_id"):
        headers["X-Hokusai-User-Id"] = str(request.state.user_id)
        headers["X-Hokusai-API-Key-Id"] = str(request.state.api_key_id)
        logger.info(f"Adding user context: user_id={request.state.user_id}")

    # Remove only headers that shouldn't be forwarded
    # CRITICAL: We MUST forward authentication headers to MLflow
    # MLflow requires authentication to authorize requests
    headers_to_remove = [
        "host",  # We'll use MLflow's host
        "content-length",  # Will be recalculated
        # NOTE: We intentionally keep authorization and x-api-key headers
        # They are required for MLflow authentication
    ]
    for header in headers_to_remove:
        headers.pop(header, None)

    # Get query parameters
    query_params = dict(request.query_params)

    # Get request body if applicable
    body = None
    if method in ["post", "put", "patch"]:
        body = await request.body()
        if ENABLE_DEBUG_LOGGING and body:
            logger.debug(f"Request body size: {len(body)} bytes")

    try:
        # Create async HTTP client with retry capability
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT) as client:
            # Make the request to MLflow
            response = await client.request(
                method=method,
                url=target_url,
                headers=headers,
                params=query_params,
                content=body,
                follow_redirects=False,
            )

            # Log response status
            logger.info(
                f"MLflow response: status={response.status_code}, "
                f"path={original_path}, target={target_url}"
            )

            # Create response headers
            response_headers = dict(response.headers)
            # Remove transfer encoding header as FastAPI handles it
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-encoding", None)

            # Log detailed info for debugging failed requests
            if response.status_code >= 400:
                logger.warning(
                    f"MLflow error response: status={response.status_code}, "
                    f"path={original_path}, response_text={response.text[:500]}"
                )

                # Check if response is HTML error page and convert to JSON
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type and response.status_code == 404:
                    # Convert HTML 404 to JSON response for API consistency
                    json_error = {
                        "error_code": "RESOURCE_NOT_FOUND",
                        "message": f"The requested resource was not found: {original_path}",
                    }
                    return Response(
                        content=json.dumps(json_error),
                        status_code=404,
                        headers={"Content-Type": "application/json"},
                    )

            # Return the response
            return Response(
                content=response.content, status_code=response.status_code, headers=response_headers
            )

    except httpx.TimeoutException:
        logger.error(f"Timeout connecting to MLflow server at {target_url}")
        raise HTTPException(
            status_code=504, detail=f"MLflow server request timeout after {PROXY_TIMEOUT}s"
        )
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to MLflow server at {target_url}: {e}")
        raise HTTPException(
            status_code=502, detail=f"Failed to connect to MLflow server at {mlflow_base_url}"
        )
    except Exception as e:
        logger.error(f"Unexpected error proxying request to MLflow: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Internal server error while proxying to MLflow"
        )


@router.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def mlflow_proxy(request: Request, path: str):
    """Proxy all requests to MLflow server.

    This endpoint forwards all requests under /mlflow/* or /api/mlflow/* to the MLflow
    tracking server, stripping authentication headers and handling responses appropriately.
    """
    # Log all incoming requests for debugging
    if ENABLE_DEBUG_LOGGING:
        logger.debug(f"MLflow proxy endpoint called: path={path}")

    # Special handling for MLflow UI assets
    if path == "" or path == "/":
        # Redirect to MLflow UI
        return await proxy_request(request, "", MLFLOW_SERVER_URL)

    # Handle all paths - MLflow will route internally
    return await proxy_request(request, path, MLFLOW_SERVER_URL)


# Enhanced health check endpoints
@router.get("/health/mlflow")
async def mlflow_health_check():
    """Check if MLflow server is accessible with detailed diagnostics."""
    health_status = {
        "mlflow_server": MLFLOW_SERVER_URL,
        "checks": {
            "connectivity": {"status": "unknown", "message": ""},
            "experiments_api": {"status": "unknown", "message": ""},
            "artifacts_api": {"status": "unknown", "message": ""},
        },
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check basic connectivity
            try:
                response = await client.get(f"{MLFLOW_SERVER_URL}/health")
                if response.status_code in [200, 404]:  # 404 is OK, means server is up
                    health_status["checks"]["connectivity"] = {
                        "status": "healthy",
                        "message": "MLflow server is reachable",
                    }
                else:
                    health_status["checks"]["connectivity"] = {
                        "status": "unhealthy",
                        "message": f"Unexpected status code: {response.status_code}",
                    }
            except Exception as e:
                health_status["checks"]["connectivity"] = {"status": "unhealthy", "message": str(e)}

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
                        "message": "Experiments API is functional",
                    }
                else:
                    health_status["checks"]["experiments_api"] = {
                        "status": "unhealthy",
                        "message": f"API returned status {response.status_code}",
                    }
            except Exception as e:
                health_status["checks"]["experiments_api"] = {
                    "status": "unhealthy",
                    "message": str(e),
                }

            # Check artifact API endpoint
            if os.getenv("MLFLOW_SERVE_ARTIFACTS", "true").lower() == "true":
                try:
                    # Use appropriate API path based on server type
                    artifact_path = (
                        "ajax-api" if "registry.hokus.ai" in MLFLOW_SERVER_URL else "api"
                    )
                    response = await client.get(
                        f"{MLFLOW_SERVER_URL}/{artifact_path}/2.0/mlflow-artifacts/artifacts"
                    )
                    # A 200 with empty response or 404 for non-existent artifact is OK
                    if response.status_code in [200, 404]:
                        health_status["checks"]["artifacts_api"] = {
                            "status": "healthy",
                            "message": "Artifact API is accessible",
                        }
                    else:
                        health_status["checks"]["artifacts_api"] = {
                            "status": "unhealthy",
                            "message": f"Artifact API returned status {response.status_code}",
                        }
                except Exception as e:
                    health_status["checks"]["artifacts_api"] = {
                        "status": "unhealthy",
                        "message": f"Artifact API error: {str(e)}",
                    }
            else:
                health_status["checks"]["artifacts_api"] = {
                    "status": "disabled",
                    "message": "Artifact serving is not configured",
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

    return health_status


@router.get("/health/mlflow/detailed")
async def mlflow_detailed_health_check():
    """Perform comprehensive MLflow health checks including all API endpoints."""
    results = {
        "mlflow_server": MLFLOW_SERVER_URL,
        "timestamp": os.popen("date").read().strip(),
        "environment": {
            "MLFLOW_SERVER_URL": MLFLOW_SERVER_URL,
            "MLFLOW_SERVE_ARTIFACTS": os.getenv("MLFLOW_SERVE_ARTIFACTS", "true"),
            "PROXY_DEBUG": ENABLE_DEBUG_LOGGING,
        },
        "tests": [],
    }

    # Test cases for different MLflow endpoints
    test_endpoints = [
        {"name": "experiments_list", "path": "/api/2.0/mlflow/experiments/search", "method": "GET"},
        {
            "name": "models_list",
            "path": "/api/2.0/mlflow/registered-models/search",
            "method": "GET",
        },
        {"name": "metrics_history", "path": "/api/2.0/mlflow/metrics/get-history", "method": "GET"},
        {"name": "artifacts_api", "path": "/api/2.0/mlflow-artifacts/artifacts", "method": "GET"},
    ]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for test in test_endpoints:
            try:
                # Adjust path for external vs internal MLflow
                path = test["path"]
                if "registry.hokus.ai" in MLFLOW_SERVER_URL:
                    # Convert both regular API and artifact paths
                    path = path.replace("/api/2.0/mlflow/", "/ajax-api/2.0/mlflow/")
                    path = path.replace(
                        "/api/2.0/mlflow-artifacts/", "/ajax-api/2.0/mlflow-artifacts/"
                    )

                url = f"{MLFLOW_SERVER_URL}{path}"
                response = await client.request(method=test["method"], url=url)

                results["tests"].append(
                    {
                        "endpoint": test["name"],
                        "url": url,
                        "status_code": response.status_code,
                        "success": response.status_code < 400,
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                    }
                )
            except Exception as e:
                results["tests"].append(
                    {"endpoint": test["name"], "url": url, "success": False, "error": str(e)}
                )

    # Overall health determination
    results["overall_health"] = all(test.get("success", False) for test in results["tests"])

    return results
