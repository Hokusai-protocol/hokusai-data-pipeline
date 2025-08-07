#!/usr/bin/env python3
"""
Test script to verify documentation endpoints work without authentication.

This script tests:
1. /docs endpoint accessibility
2. /redoc endpoint accessibility  
3. /openapi.json endpoint accessibility
4. Verifies FastAPI configuration for docs
5. Tests in different environments
"""

import asyncio
import httpx
import json
import sys
import os
from typing import Dict, Any

# Add src to path for local testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.api.utils.config import get_settings


async def test_endpoint(client: httpx.AsyncClient, url: str, endpoint: str) -> Dict[str, Any]:
    """Test a single endpoint and return results."""
    full_url = f"{url}{endpoint}"
    
    try:
        response = await client.get(full_url)
        return {
            "endpoint": endpoint,
            "url": full_url,
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "content_type": response.headers.get("content-type", ""),
            "content_length": len(response.content),
            "error": None
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "url": full_url,
            "status_code": None,
            "success": False,
            "content_type": "",
            "content_length": 0,
            "error": str(e)
        }


async def test_docs_endpoints(base_url: str = "http://localhost:8001") -> Dict[str, Any]:
    """Test all documentation endpoints."""
    
    endpoints_to_test = [
        "/docs",
        "/redoc", 
        "/openapi.json",
        "/health"  # Also test health endpoint as a control
    ]
    
    results = {
        "base_url": base_url,
        "endpoints": [],
        "summary": {
            "total": len(endpoints_to_test),
            "passed": 0,
            "failed": 0
        }
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in endpoints_to_test:
            result = await test_endpoint(client, base_url, endpoint)
            results["endpoints"].append(result)
            
            if result["success"]:
                results["summary"]["passed"] += 1
            else:
                results["summary"]["failed"] += 1
    
    return results


def check_fastapi_configuration():
    """Check FastAPI app configuration for docs settings."""
    try:
        # Import the FastAPI app
        from src.api.main import app
        
        config_info = {
            "title": app.title,
            "version": app.version,
            "docs_url": app.docs_url,
            "redoc_url": app.redoc_url,
            "openapi_url": app.openapi_url,
            "description": app.description
        }
        
        # Check if docs are disabled
        docs_disabled = (
            app.docs_url is None and 
            app.redoc_url is None and 
            app.openapi_url is None
        )
        
        return {
            "configuration": config_info,
            "docs_disabled": docs_disabled,
            "middleware_count": len(app.middleware_stack),
            "routes_count": len(app.routes)
        }
        
    except Exception as e:
        return {
            "error": f"Failed to check FastAPI configuration: {str(e)}",
            "configuration": None,
            "docs_disabled": None
        }


def check_environment_settings():
    """Check environment settings that might affect docs access."""
    try:
        settings = get_settings()
        
        env_info = {
            "environment": os.getenv("ENVIRONMENT", "development"),
            "api_host": settings.api_host,
            "api_port": settings.api_port,
            "cors_origins": settings.cors_origins,
            "auth_service_url": settings.auth_service_url,
        }
        
        # Check for environment variables that might disable docs
        docs_env_vars = {
            "DISABLE_DOCS": os.getenv("DISABLE_DOCS"),
            "ENVIRONMENT": os.getenv("ENVIRONMENT"),
            "DEBUG": os.getenv("DEBUG"),
            "PRODUCTION": os.getenv("PRODUCTION")
        }
        
        return {
            "settings": env_info,
            "env_vars": docs_env_vars
        }
        
    except Exception as e:
        return {
            "error": f"Failed to check environment settings: {str(e)}",
            "settings": None,
            "env_vars": None
        }


def check_auth_middleware_config():
    """Check authentication middleware configuration."""
    try:
        from src.middleware.auth import APIKeyAuthMiddleware
        
        # Create a test instance to check excluded paths
        middleware = APIKeyAuthMiddleware(app=None)
        
        return {
            "excluded_paths": middleware.excluded_paths,
            "docs_excluded": "/docs" in middleware.excluded_paths,
            "redoc_excluded": "/redoc" in middleware.excluded_paths,
            "openapi_excluded": "/openapi.json" in middleware.excluded_paths
        }
        
    except Exception as e:
        return {
            "error": f"Failed to check auth middleware: {str(e)}",
            "excluded_paths": None
        }


async def run_comprehensive_test():
    """Run comprehensive test of documentation endpoints."""
    
    print("🔍 Hokusai API Documentation Endpoints Test")
    print("=" * 50)
    
    # Test 1: Check FastAPI Configuration
    print("\n📋 Checking FastAPI Configuration...")
    fastapi_config = check_fastapi_configuration()
    
    if fastapi_config.get("error"):
        print(f"❌ Error: {fastapi_config['error']}")
    else:
        print(f"✅ App Title: {fastapi_config['configuration']['title']}")
        print(f"✅ Docs URL: {fastapi_config['configuration']['docs_url']}")
        print(f"✅ Redoc URL: {fastapi_config['configuration']['redoc_url']}")
        print(f"✅ OpenAPI URL: {fastapi_config['configuration']['openapi_url']}")
        
        if fastapi_config['docs_disabled']:
            print("⚠️  WARNING: Documentation endpoints appear to be disabled!")
        else:
            print("✅ Documentation endpoints are enabled in FastAPI config")
    
    # Test 2: Check Environment Settings
    print("\n🌍 Checking Environment Settings...")
    env_config = check_environment_settings()
    
    if env_config.get("error"):
        print(f"❌ Error: {env_config['error']}")
    else:
        print(f"✅ Environment: {env_config['env_vars']['ENVIRONMENT'] or 'development'}")
        print(f"✅ API Host: {env_config['settings']['api_host']}")
        print(f"✅ API Port: {env_config['settings']['api_port']}")
        
        # Check for docs-disabling environment variables
        if env_config['env_vars']['DISABLE_DOCS']:
            print(f"⚠️  WARNING: DISABLE_DOCS is set to {env_config['env_vars']['DISABLE_DOCS']}")
        
        if env_config['env_vars']['ENVIRONMENT'] == 'production':
            print("⚠️  NOTE: Running in production environment")
    
    # Test 3: Check Authentication Middleware
    print("\n🔐 Checking Authentication Middleware Configuration...")
    auth_config = check_auth_middleware_config()
    
    if auth_config.get("error"):
        print(f"❌ Error: {auth_config['error']}")
    else:
        print(f"✅ Excluded paths: {auth_config['excluded_paths']}")
        
        if auth_config['docs_excluded']:
            print("✅ /docs is excluded from authentication")
        else:
            print("❌ /docs is NOT excluded from authentication")
            
        if auth_config['redoc_excluded']:
            print("✅ /redoc is excluded from authentication")
        else:
            print("❌ /redoc is NOT excluded from authentication")
            
        if auth_config['openapi_excluded']:
            print("✅ /openapi.json is excluded from authentication")
        else:
            print("❌ /openapi.json is NOT excluded from authentication")
    
    # Test 4: Test Actual Endpoints
    print("\n🌐 Testing Documentation Endpoints...")
    
    # Test multiple possible URLs
    test_urls = [
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://0.0.0.0:8001"
    ]
    
    for base_url in test_urls:
        print(f"\n  Testing {base_url}...")
        
        results = await test_docs_endpoints(base_url)
        
        print(f"  📊 Results: {results['summary']['passed']}/{results['summary']['total']} passed")
        
        for endpoint_result in results['endpoints']:
            status = "✅" if endpoint_result['success'] else "❌"
            status_code = endpoint_result['status_code'] or "ERROR"
            
            print(f"    {status} {endpoint_result['endpoint']}: {status_code}")
            
            if endpoint_result['error']:
                print(f"      Error: {endpoint_result['error']}")
            elif endpoint_result['success']:
                print(f"      Content-Type: {endpoint_result['content_type']}")
                print(f"      Size: {endpoint_result['content_length']} bytes")
        
        # If any endpoint succeeded, we found the right URL
        if results['summary']['passed'] > 0:
            break
    
    # Test 5: Generate Recommendations
    print("\n💡 Recommendations...")
    
    # Check if server is running
    if all(r['summary']['failed'] == r['summary']['total'] for r in [results]):
        print("❌ No endpoints are accessible. Possible issues:")
        print("   • API server is not running")
        print("   • Wrong host/port configuration") 
        print("   • Firewall blocking access")
        print("\n   Try starting the server:")
        print("   python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001")
    
    elif fastapi_config.get('docs_disabled'):
        print("❌ Documentation is disabled in FastAPI configuration")
        print("   • Check if docs_url, redoc_url, openapi_url are set to None")
        print("   • Look for environment variables disabling docs")
    
    elif not auth_config.get('docs_excluded', True):
        print("❌ Documentation endpoints require authentication")
        print("   • Add docs endpoints to auth middleware excluded_paths")
        print("   • Update APIKeyAuthMiddleware configuration")
    
    else:
        print("✅ Configuration looks good!")
        print("   • Documentation endpoints should be accessible")
        print("   • Try accessing http://localhost:8001/docs in your browser")


def create_fixed_fastapi_config():
    """Generate a fixed FastAPI configuration ensuring docs are enabled."""
    
    config_template = '''"""Fixed FastAPI main.py with guaranteed docs access."""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.middleware.auth import APIKeyAuthMiddleware
from src.middleware.rate_limiter import RateLimitMiddleware
from src.api.routes import dspy, health, models, health_mlflow, mlflow_proxy_improved as mlflow_proxy
from src.api.utils.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Check environment - only disable docs in production if explicitly requested
environment = os.getenv("ENVIRONMENT", "development").lower()
disable_docs = os.getenv("DISABLE_DOCS", "false").lower() in ("true", "1", "yes")
in_production = environment in ("production", "prod")

# Force enable docs unless explicitly disabled
enable_docs = not disable_docs
docs_url = "/docs" if enable_docs else None
redoc_url = "/redoc" if enable_docs else None
openapi_url = "/openapi.json" if enable_docs else None

logger.info(f"Environment: {environment}")
logger.info(f"Docs enabled: {enable_docs}")
logger.info(f"Docs URL: {docs_url}")

# Create FastAPI app with explicit docs configuration
app = FastAPI(
    title="Hokusai MLOps API",
    description="API for model registry, performance tracking, and experiment management",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add authentication middleware with explicit docs exclusion
auth_excluded_paths = [
    "/health",
    "/docs",
    "/openapi.json", 
    "/redoc",
    "/favicon.ico",
    "/api/v1/dspy/health"
]

# Add docs paths even if disabled to prevent auth issues
if docs_url:
    auth_excluded_paths.append(docs_url)
if redoc_url:
    auth_excluded_paths.append(redoc_url)  
if openapi_url:
    auth_excluded_paths.append(openapi_url)

app.add_middleware(
    APIKeyAuthMiddleware,
    excluded_paths=auth_excluded_paths
)

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

# MLflow proxy
app.include_router(mlflow_proxy.router, prefix="/mlflow", tags=["mlflow"])
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
    logger.info(f"Documentation available at: {docs_url if docs_url else 'DISABLED'}")


# Shutdown event  
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    logger.info("Shutting down Hokusai MLOps API...")
'''
    
    return config_template


if __name__ == "__main__":
    print("🚀 Starting comprehensive documentation endpoint test...")
    
    # Check if --fix flag was provided
    if "--fix" in sys.argv:
        print("\n🔧 Generating fixed configuration...")
        fixed_config = create_fixed_fastapi_config()
        
        with open("src/api/main_fixed.py", "w") as f:
            f.write(fixed_config)
        
        print("✅ Fixed configuration written to src/api/main_fixed.py")
        print("   Review the changes and replace main.py if needed")
    
    # Run the comprehensive test
    asyncio.run(run_comprehensive_test())