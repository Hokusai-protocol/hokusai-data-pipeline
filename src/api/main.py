"""Main FastAPI application for Hokusai MLOps services."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.endpoints import model_serving
from src.api.routes import dspy, health, health_mlflow, models
from src.api.routes import mlflow_proxy_improved as mlflow_proxy

# TODO: Fix missing APIKeyModel dependency before enabling auth
# from src.api import auth
from src.api.utils.config import get_settings
from src.middleware.auth import APIKeyAuthMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Hokusai MLOps API",
    description="API for model registry, performance tracking, and experiment management",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add authentication middleware
app.add_middleware(APIKeyAuthMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Configure additional rate limiting with slowapi
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(health.router, tags=["health"])


# Add explicit root health endpoint for ALB
@app.get("/health")
async def root_health_check():
    """Root-level health check endpoint for ALB."""
    from src.api.routes.health import health_check

    return await health_check()


# Add root endpoint that returns available health paths
@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Hokusai Data Pipeline API",
        "version": "1.0.0",
        "health_check": "/health",
        "health_endpoints": ["/health", "/ready", "/live", "/health/mlflow", "/health/status"],
        "documentation": "/docs",
    }


app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(dspy.router, tags=["dspy"])
app.include_router(model_serving.router, tags=["model-serving"])  # Model 21 serving endpoint
# TODO: Enable auth router after fixing APIKeyModel dependency
# app.include_router(auth.router, tags=["authentication"])

# MLflow proxy - mount at multiple prefixes for MLflow client compatibility
# /mlflow - for direct access
# /api/mlflow - for API versioned access
# /api/2.0/mlflow - for MLflow Python client (uses this path by default)
app.include_router(mlflow_proxy.router, prefix="/mlflow", tags=["mlflow"])
app.include_router(mlflow_proxy.router, prefix="/api/mlflow", tags=["mlflow"])
app.include_router(mlflow_proxy.router, prefix="/api/2.0/mlflow", tags=["mlflow"])

# MLflow health check endpoints at /api/health
app.include_router(health_mlflow.router, prefix="/api/health", tags=["health"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Startup event
@app.on_event("startup")
async def startup_event() -> None:
    """Initialize services on startup."""
    logger.info("Starting Hokusai MLOps API...")

    # Configure mTLS for internal MLflow communication
    try:
        from src.utils.mlflow_config import configure_internal_mtls

        configure_internal_mtls()
        logger.info("mTLS configuration completed")
    except Exception as e:
        logger.error(f"Failed to configure mTLS: {e}")
        # Don't fail startup - will fall back to API key auth

    # Initialize database connections, caches, etc.


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down Hokusai MLOps API...")
    # Close database connections, flush caches, etc.
