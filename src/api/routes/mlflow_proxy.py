"""MLflow proxy router to forward requests to MLflow server."""

import os
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# MLflow server configuration
MLFLOW_SERVER_URL = os.getenv("MLFLOW_SERVER_URL", "http://localhost:5000")
PROXY_TIMEOUT = 30.0  # seconds


async def proxy_request(
    request: Request,
    path: str,
    mlflow_base_url: str = MLFLOW_SERVER_URL
) -> Response:
    """
    Proxy requests to MLflow server.
    
    Args:
        request: The incoming FastAPI request
        path: The path to forward to MLflow
        mlflow_base_url: Base URL of the MLflow server
        
    Returns:
        Response from MLflow server
    """
    # Construct the target URL
    target_url = f"{mlflow_base_url}/{path}"
    
    # Get the HTTP method
    method = request.method.lower()
    
    # Prepare headers, removing authentication headers
    headers = dict(request.headers)
    headers_to_remove = [
        "authorization",
        "x-api-key",
        "host",  # We'll use MLflow's host
        "content-length",  # Will be recalculated
    ]
    for header in headers_to_remove:
        headers.pop(header, None)
    
    # Get query parameters
    query_params = dict(request.query_params)
    
    # Get request body if applicable
    body = None
    if method in ["post", "put", "patch"]:
        body = await request.body()
    
    try:
        # Create async HTTP client
        async with httpx.AsyncClient(timeout=PROXY_TIMEOUT) as client:
            # Make the request to MLflow
            response = await client.request(
                method=method,
                url=target_url,
                headers=headers,
                params=query_params,
                content=body,
                follow_redirects=False
            )
            
            # Create response headers
            response_headers = dict(response.headers)
            # Remove transfer encoding header as FastAPI handles it
            response_headers.pop("transfer-encoding", None)
            response_headers.pop("content-encoding", None)
            
            # Return the response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers
            )
            
    except httpx.TimeoutException:
        logger.error(f"Timeout connecting to MLflow server at {target_url}")
        raise HTTPException(
            status_code=504,
            detail="MLflow server request timeout"
        )
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to MLflow server at {target_url}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to connect to MLflow server"
        )
    except Exception as e:
        logger.error(f"Error proxying request to MLflow: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while proxying to MLflow"
        )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def mlflow_proxy(request: Request, path: str):
    """
    Proxy all requests to MLflow server.
    
    This endpoint forwards all requests under /mlflow/* to the MLflow tracking server,
    stripping authentication headers and handling responses appropriately.
    """
    # Special handling for MLflow UI assets
    if path == "" or path == "/":
        # Redirect to MLflow UI
        return await proxy_request(request, "", MLFLOW_SERVER_URL)
    
    # Handle API endpoints
    if path.startswith("api/"):
        return await proxy_request(request, path, MLFLOW_SERVER_URL)
    
    # Handle static assets and other paths
    return await proxy_request(request, path, MLFLOW_SERVER_URL)


# Health check endpoint for MLflow connectivity
@router.get("/health/mlflow")
async def mlflow_health_check():
    """Check if MLflow server is accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MLFLOW_SERVER_URL}/health")
            
            # MLflow returns 200 or 308 for health checks
            if response.status_code in [200, 308]:
                return {
                    "status": "healthy",
                    "mlflow_server": MLFLOW_SERVER_URL,
                    "message": "MLflow server is accessible"
                }
            else:
                return {
                    "status": "unhealthy",
                    "mlflow_server": MLFLOW_SERVER_URL,
                    "message": f"MLflow server returned status {response.status_code}"
                }
    except Exception as e:
        logger.error(f"MLflow health check failed: {e}")
        return {
            "status": "unhealthy",
            "mlflow_server": MLFLOW_SERVER_URL,
            "message": f"Failed to connect to MLflow server: {str(e)}"
        }