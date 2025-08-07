#!/usr/bin/env python3
"""
Configuration check script for documentation endpoints.
Use this to ensure proper docs configuration in production deployments.
"""

import os
import sys
from typing import Dict, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)


def check_environment_config() -> Dict[str, Any]:
    """Check environment variables that affect documentation."""
    
    config = {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "disable_docs": os.getenv("DISABLE_DOCS", "false"),
        "debug": os.getenv("DEBUG", "false"),
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": os.getenv("PORT", "8001")
    }
    
    # Analyze configuration
    analysis = {
        "docs_should_be_enabled": True,
        "warnings": [],
        "errors": []
    }
    
    # Check if docs are explicitly disabled
    if config["disable_docs"].lower() in ("true", "1", "yes"):
        analysis["docs_should_be_enabled"] = False
        analysis["warnings"].append("Documentation explicitly disabled via DISABLE_DOCS")
    
    # Check production environment
    if config["environment"].lower() in ("production", "prod"):
        if analysis["docs_should_be_enabled"]:
            analysis["warnings"].append("Documentation enabled in production environment")
        else:
            analysis["warnings"].append("Documentation disabled in production (recommended)")
    
    return {"config": config, "analysis": analysis}


def check_fastapi_config() -> Dict[str, Any]:
    """Check FastAPI application configuration."""
    
    try:
        from src.api.main import app
        
        config = {
            "docs_url": app.docs_url,
            "redoc_url": app.redoc_url,
            "openapi_url": app.openapi_url,
            "title": app.title,
            "version": app.version
        }
        
        analysis = {
            "docs_enabled": bool(app.docs_url or app.redoc_url or app.openapi_url),
            "warnings": [],
            "errors": []
        }
        
        # Check if all docs endpoints are disabled
        if not config["docs_url"] and not config["redoc_url"] and not config["openapi_url"]:
            analysis["errors"].append("All documentation endpoints are disabled in FastAPI config")
        
        # Check individual endpoints
        if not config["docs_url"]:
            analysis["warnings"].append("Swagger UI (/docs) is disabled")
        if not config["redoc_url"]:
            analysis["warnings"].append("ReDoc (/redoc) is disabled")
        if not config["openapi_url"]:
            analysis["warnings"].append("OpenAPI spec (/openapi.json) is disabled")
        
        return {"config": config, "analysis": analysis, "error": None}
        
    except Exception as e:
        return {
            "config": None,
            "analysis": {"docs_enabled": False, "warnings": [], "errors": [str(e)]},
            "error": str(e)
        }


def check_auth_middleware_config() -> Dict[str, Any]:
    """Check authentication middleware configuration."""
    
    try:
        from src.middleware.auth import APIKeyAuthMiddleware
        
        # Create instance to check default excluded paths
        middleware = APIKeyAuthMiddleware(app=None)
        
        config = {
            "excluded_paths": middleware.excluded_paths
        }
        
        analysis = {
            "docs_excluded": "/docs" in middleware.excluded_paths,
            "redoc_excluded": "/redoc" in middleware.excluded_paths,
            "openapi_excluded": "/openapi.json" in middleware.excluded_paths,
            "warnings": [],
            "errors": []
        }
        
        # Check if docs endpoints are excluded from auth
        if not analysis["docs_excluded"]:
            analysis["errors"].append("/docs endpoint requires authentication")
        if not analysis["redoc_excluded"]:
            analysis["errors"].append("/redoc endpoint requires authentication")
        if not analysis["openapi_excluded"]:
            analysis["errors"].append("/openapi.json endpoint requires authentication")
        
        return {"config": config, "analysis": analysis, "error": None}
        
    except Exception as e:
        return {
            "config": None,
            "analysis": {"docs_excluded": False, "warnings": [], "errors": [str(e)]},
            "error": str(e)
        }


def generate_production_recommendations(env_config: Dict, fastapi_config: Dict, auth_config: Dict) -> list:
    """Generate recommendations for production deployment."""
    
    recommendations = []
    environment = env_config["config"]["environment"].lower()
    
    if environment in ("production", "prod"):
        # Production-specific recommendations
        if fastapi_config["analysis"]["docs_enabled"]:
            recommendations.append({
                "type": "security",
                "priority": "medium",
                "message": "Consider disabling docs in production for security",
                "action": "Set DISABLE_DOCS=true environment variable"
            })
        
        recommendations.append({
            "type": "monitoring",
            "priority": "low", 
            "message": "Monitor docs endpoint access in production",
            "action": "Set up alerts for unusual access patterns to /docs, /redoc"
        })
    else:
        # Development recommendations
        if not fastapi_config["analysis"]["docs_enabled"]:
            recommendations.append({
                "type": "development",
                "priority": "high",
                "message": "Documentation should be enabled in development",
                "action": "Remove DISABLE_DOCS or set DISABLE_DOCS=false"
            })
    
    # Authentication recommendations
    if auth_config["error"]:
        recommendations.append({
            "type": "configuration",
            "priority": "high",
            "message": "Authentication middleware configuration error",
            "action": f"Fix middleware error: {auth_config['error']}"
        })
    else:
        if not auth_config["analysis"]["docs_excluded"]:
            recommendations.append({
                "type": "security",
                "priority": "high",
                "message": "Documentation endpoints require authentication",
                "action": "Add docs endpoints to auth middleware excluded_paths"
            })
    
    return recommendations


def main():
    """Main configuration check."""
    
    print("🔧 Hokusai API Documentation Configuration Check")
    print("=" * 55)
    
    # Check environment configuration
    print("\n🌍 Environment Configuration:")
    env_config = check_environment_config()
    
    for key, value in env_config["config"].items():
        print(f"  {key.upper()}: {value}")
    
    if env_config["analysis"]["warnings"]:
        print("\n  ⚠️  Warnings:")
        for warning in env_config["analysis"]["warnings"]:
            print(f"    • {warning}")
    
    # Check FastAPI configuration  
    print("\n📋 FastAPI Configuration:")
    fastapi_config = check_fastapi_config()
    
    if fastapi_config["error"]:
        print(f"  ❌ Error: {fastapi_config['error']}")
    else:
        print(f"  Title: {fastapi_config['config']['title']}")
        print(f"  Docs URL: {fastapi_config['config']['docs_url']}")
        print(f"  ReDoc URL: {fastapi_config['config']['redoc_url']}")
        print(f"  OpenAPI URL: {fastapi_config['config']['openapi_url']}")
        
        if fastapi_config["analysis"]["warnings"]:
            print("\n  ⚠️  Warnings:")
            for warning in fastapi_config["analysis"]["warnings"]:
                print(f"    • {warning}")
        
        if fastapi_config["analysis"]["errors"]:
            print("\n  ❌ Errors:")
            for error in fastapi_config["analysis"]["errors"]:
                print(f"    • {error}")
    
    # Check authentication middleware
    print("\n🔐 Authentication Middleware:")
    auth_config = check_auth_middleware_config()
    
    if auth_config["error"]:
        print(f"  ❌ Error: {auth_config['error']}")
    else:
        print(f"  Excluded paths: {len(auth_config['config']['excluded_paths'])} paths")
        print(f"  Docs excluded: {auth_config['analysis']['docs_excluded']}")
        print(f"  ReDoc excluded: {auth_config['analysis']['redoc_excluded']}")
        print(f"  OpenAPI excluded: {auth_config['analysis']['openapi_excluded']}")
        
        if auth_config["analysis"]["errors"]:
            print("\n  ❌ Errors:")
            for error in auth_config["analysis"]["errors"]:
                print(f"    • {error}")
    
    # Generate recommendations
    print("\n💡 Recommendations:")
    recommendations = generate_production_recommendations(env_config, fastapi_config, auth_config)
    
    if not recommendations:
        print("  ✅ Configuration looks good!")
    else:
        for rec in recommendations:
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            icon = priority_icon.get(rec["priority"], "ℹ️")
            print(f"  {icon} [{rec['type'].upper()}] {rec['message']}")
            print(f"     Action: {rec['action']}")
    
    # Overall status
    print("\n📊 Overall Status:")
    
    has_errors = (
        any(env_config["analysis"].get("errors", [])) or
        any(fastapi_config["analysis"].get("errors", [])) or  
        any(auth_config["analysis"].get("errors", []))
    )
    
    if has_errors:
        print("  ❌ Configuration has errors that need to be fixed")
        sys.exit(1)
    else:
        print("  ✅ Configuration is valid")
        
        docs_accessible = (
            fastapi_config["analysis"].get("docs_enabled", False) and
            auth_config["analysis"].get("docs_excluded", False)
        )
        
        if docs_accessible:
            print("  ✅ Documentation endpoints should be accessible")
        else:
            print("  ⚠️  Documentation endpoints may not be accessible")


if __name__ == "__main__":
    main()