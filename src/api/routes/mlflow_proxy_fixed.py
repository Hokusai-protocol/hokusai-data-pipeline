"""MLflow proxy router to forward requests to MLflow server - FIXED VERSION."""

import os
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# MLflow server configuration
MLFLOW_SERVER_URL = os.getenv("MLFLOW_SERVER_URL", "https://registry.hokus.ai/mlflow")
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
    # FIXED: Convert standard API paths to MLflow ajax-api paths
    if path.startswith("api/2.0/mlflow/"):
        # MLflow at registry.hokus.ai uses ajax-api instead of api
        path = path.replace("api/2.0/mlflow/", "ajax-api/2.0/mlflow/")
        logger.info(f"Converted path to MLflow format: {path}")
    
    # Construct the target URL
    target_url = f"{mlflow_base_url}/{path}"
    
    # Get the HTTP method
    method = request.method.lower()
    
    # Prepare headers, keeping track of the authenticated user
    headers = dict(request.headers)
    
    # Add user context headers for MLflow tracking
    if hasattr(request.state, "user_id"):
        headers["X-Hokusai-User-Id"] = str(request.state.user_id)
        headers["X-Hokusai-API-Key-Id"] = str(request.state.api_key_id)
    
    # Remove sensitive headers that shouldn't be forwarded
    headers_to_remove = [
        "authorization",  # Don't forward Hokusai API key to MLflow
        "x-api-key",      # Don't forward Hokusai API key to MLflow
        "host",           # We'll use MLflow's host
        "content-length", # Will be recalculated
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
            
            # Log the MLflow access for audit trail
            if hasattr(request.state, "user_id"):
                logger.info(
                    f"MLflow access: user_id={request.state.user_id}, "
                    f"method={method.upper()}, path={path}, "
                    f"status={response.status_code}"
                )
            
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
    
    # Handle ajax-api endpoints (MLflow's actual API path)
    if path.startswith("ajax-api/"):
        return await proxy_request(request, path, MLFLOW_SERVER_URL)
    
    # Handle static assets and other paths
    return await proxy_request(request, path, MLFLOW_SERVER_URL)


# Health check endpoint for MLflow connectivity
@router.get("/health/mlflow")
async def mlflow_health_check():
    """Check if MLflow server is accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try the ajax-api endpoint which MLflow actually uses
            response = await client.get(f"{MLFLOW_SERVER_URL}/ajax-api/2.0/mlflow/experiments/search?max_results=1")
            
            if response.status_code == 200:
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