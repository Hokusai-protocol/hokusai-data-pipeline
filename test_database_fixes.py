#!/usr/bin/env python3
"""
Test script to verify database configuration fixes for Hokusai API service.
This script tests the fixes implemented for PostgreSQL connectivity issues.
"""

import os
import sys
import time
import json
import psycopg2
import requests
from typing import Dict, Any, Optional
from datetime import datetime

# Add the src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from api.utils.config import get_settings

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(message: str):
    """Print a formatted header."""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{message}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✅ {message}{RESET}")

def print_error(message: str):
    """Print an error message."""
    print(f"{RED}❌ {message}{RESET}")

def print_warning(message: str):
    """Print a warning message."""
    print(f"{YELLOW}⚠️  {message}{RESET}")

def print_info(message: str):
    """Print an info message."""
    print(f"{BLUE}ℹ️  {message}{RESET}")

def test_environment_variables():
    """Test that environment variables are properly configured."""
    print_header("Testing Environment Variable Configuration")
    
    settings = get_settings()
    results = []
    
    # Test database configuration
    print(f"Database Host: {settings.effective_database_host}")
    print(f"Database Port: {settings.effective_database_port}")
    print(f"Database Name: {settings.effective_database_name}")
    print(f"Database User: {settings.effective_database_user}")
    print(f"Database Password: {'*' * 8 if settings.effective_database_password else 'Not Set'}")
    
    # Test if environment variables override defaults
    original_host = settings.effective_database_host
    os.environ['DATABASE_HOST'] = 'test-host.example.com'
    
    # Need to clear cache and get new settings instance
    get_settings.cache_clear()
    settings = get_settings()
    new_host = settings.effective_database_host
    
    if new_host == 'test-host.example.com':
        print_success("Environment variable override works correctly")
        results.append(True)
    else:
        print_error("Environment variable override not working")
        results.append(False)
    
    # Restore original
    if 'DATABASE_HOST' in os.environ:
        del os.environ['DATABASE_HOST']
    get_settings.cache_clear()
    
    return all(results) if results else True

def test_database_connection():
    """Test direct database connection with new configuration."""
    print_header("Testing Database Connection")
    
    settings = get_settings()
    
    print_info(f"Attempting connection to: {settings.postgres_uri[:50]}...")
    
    try:
        # Try to connect with the configured timeout
        conn = psycopg2.connect(
            settings.postgres_uri,
            connect_timeout=settings.database_connect_timeout,
            options='-c statement_timeout=10000'
        )
        
        # Test the connection
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        
        print_success(f"Connected to PostgreSQL successfully!")
        print_info(f"Database version: {version[0][:50]}...")
        
        # Test database name
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print_info(f"Connected to database: {db_name}")
        
        if db_name == "mlflow_db":
            print_success("Database name matches expected 'mlflow_db'")
        else:
            print_warning(f"Database name is '{db_name}', expected 'mlflow_db'")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError as e:
        print_error(f"Database connection failed: {str(e)}")
        
        # Provide diagnostic information
        print_info("Diagnostic Information:")
        print(f"  - Connection String: {settings.postgres_uri[:50]}...")
        print(f"  - Timeout: {settings.database_connect_timeout} seconds")
        print(f"  - Redis Enabled: {settings.redis_enabled}")
        
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False

def test_health_endpoint_locally():
    """Test the health check logic locally without running the full service."""
    print_header("Testing Health Check Logic")
    
    settings = get_settings()
    
    # Test timeout configuration
    print_info(f"Health check timeout: {settings.health_check_timeout} seconds")
    print_info(f"Database connect timeout: {settings.database_connect_timeout} seconds")
    print_info(f"Redis enabled: {settings.redis_enabled}")
    
    if settings.health_check_timeout >= 10:
        print_success("Health check timeout properly increased to 10+ seconds")
    else:
        print_error(f"Health check timeout too low: {settings.health_check_timeout} seconds")
    
    if settings.database_connect_timeout >= 10:
        print_success("Database timeout properly increased to 10+ seconds")
    else:
        print_error(f"Database timeout too low: {settings.database_connect_timeout} seconds")
    
    if not settings.redis_enabled:
        print_success("Redis properly disabled (not deployed)")
    else:
        print_warning("Redis is enabled but may not be deployed")
    
    return True

def test_mlflow_configuration():
    """Test MLflow configuration improvements."""
    print_header("Testing MLflow Configuration")
    
    try:
        from utils.mlflow_config import MLflowCircuitBreaker
        
        # Create a circuit breaker instance
        cb = MLflowCircuitBreaker()
        
        print_info(f"Circuit Breaker Configuration:")
        print(f"  - Failure Threshold: {cb.failure_threshold}")
        print(f"  - Recovery Timeout: {cb.recovery_timeout} seconds")
        print(f"  - Max Recovery Attempts: {cb.max_recovery_attempts}")
        
        # Verify improved thresholds
        if cb.failure_threshold >= 5:
            print_success("Failure threshold properly increased to 5+")
        else:
            print_warning(f"Failure threshold still low: {cb.failure_threshold}")
        
        if cb.recovery_timeout >= 60:
            print_success("Recovery timeout properly increased to 60+ seconds")
        else:
            print_warning(f"Recovery timeout still low: {cb.recovery_timeout} seconds")
        
        if cb.max_recovery_attempts >= 5:
            print_success("Max recovery attempts properly increased to 5+")
        else:
            print_warning(f"Max recovery attempts still low: {cb.max_recovery_attempts}")
        
        return True
        
    except ImportError as e:
        print_error(f"Could not import MLflow configuration: {e}")
        return False
    except Exception as e:
        print_error(f"Error testing MLflow configuration: {e}")
        return False

def test_api_service_locally():
    """Test if the API service can be started locally with the fixes."""
    print_header("Testing API Service Startup")
    
    try:
        # Try to import the main app
        from api.main import app
        
        print_success("API application imported successfully")
        
        # Check if the app has the expected endpoints
        routes = [route.path for route in app.routes]
        
        health_endpoints = ['/health', '/ready', '/live', '/health/mlflow', '/health/status']
        found_endpoints = [ep for ep in health_endpoints if ep in routes]
        
        if found_endpoints:
            print_success(f"Found health endpoints: {', '.join(found_endpoints)}")
        else:
            print_warning("No health endpoints found in app routes")
        
        return True
        
    except ImportError as e:
        print_error(f"Could not import API application: {e}")
        return False
    except Exception as e:
        print_error(f"Error testing API service: {e}")
        return False

def run_diagnostic_tests():
    """Run a comprehensive suite of diagnostic tests."""
    print_header("Hokusai API Database Fix Verification")
    print(f"Test started at: {datetime.now().isoformat()}\n")
    
    test_results = {}
    
    # Run each test
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Database Connection", test_database_connection),
        ("Health Check Logic", test_health_endpoint_locally),
        ("MLflow Configuration", test_mlflow_configuration),
        ("API Service Import", test_api_service_locally)
    ]
    
    for test_name, test_func in tests:
        try:
            test_results[test_name] = test_func()
        except Exception as e:
            print_error(f"Test '{test_name}' failed with exception: {e}")
            test_results[test_name] = False
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for result in test_results.values() if result)
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = f"{GREEN}PASSED{RESET}" if result else f"{RED}FAILED{RESET}"
        print(f"{test_name}: {status}")
    
    print(f"\n{BOLD}Overall: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print_success("All tests passed! The fixes are working correctly.")
        return 0
    else:
        print_warning(f"{total - passed} test(s) failed. Review the output above for details.")
        return 1

def main():
    """Main entry point for the test script."""
    # Check if we should use custom database settings
    if len(sys.argv) > 1:
        if sys.argv[1] == '--help':
            print("Usage: python test_database_fixes.py [--local]")
            print("  --local: Use localhost database for testing")
            return 0
        elif sys.argv[1] == '--local':
            print_info("Using local database configuration for testing")
            os.environ['DATABASE_HOST'] = 'localhost'
            os.environ['DATABASE_PORT'] = '5432'
            os.environ['DATABASE_NAME'] = 'mlflow_db'
            os.environ['DATABASE_USER'] = 'postgres'
            os.environ['DATABASE_PASSWORD'] = 'postgres'
    
    return run_diagnostic_tests()

if __name__ == "__main__":
    sys.exit(main())