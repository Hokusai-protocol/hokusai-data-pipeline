"""Main FastAPI application for Hokusai MLOps services."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.middleware.auth import APIKeyAuthMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware
from src.api.routes import dspy, health, models
from src.api.utils.config import get_settings

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
app.include_router(models.router, prefix="/models", tags=["models"])
app.include_router(dspy.router, tags=["dspy"])


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
    # Initialize database connections, caches, etc.


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down Hokusai MLOps API...")
    # Close database connections, flush caches, etc.
