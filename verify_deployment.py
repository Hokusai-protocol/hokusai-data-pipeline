#!/usr/bin/env python3
"""
Deployment verification script for database fixes.
Run this after deploying to verify the fixes are working in production.
"""

import os
import sys
import time
import json
import requests
from typing import Dict, Any, Optional
from datetime import datetime

# ANSI color codes
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

def test_health_endpoint(base_url: str, api_key: Optional[str] = None) -> bool:
    """Test the main health endpoint."""
    print_header("Testing Main Health Endpoint")
    
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
        headers['Authorization'] = f'Bearer {api_key}'
    
    try:
        response = requests.get(
            f"{base_url}/health",
            headers=headers,
            timeout=15
        )
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print_success("Health endpoint accessible")
            
            # Check overall status
            overall_status = data.get('status', 'unknown')
            print_info(f"Overall Status: {overall_status}")
            
            if overall_status == 'healthy':
                print_success("Service is fully healthy!")
            elif overall_status == 'degraded':
                print_warning("Service is degraded but operational")
            else:
                print_error(f"Service is unhealthy: {overall_status}")
            
            # Check individual services
            services = data.get('services', {})
            print("\nService Status:")
            for service, status in services.items():
                emoji = "✅" if status == "healthy" else "⚠️" if status in ["degraded", "disabled"] else "❌"
                print(f"  {emoji} {service}: {status}")
            
            # Check response times if available
            response_times = data.get('response_times', {})
            if response_times:
                print("\nResponse Times:")
                for service, time_ms in response_times.items():
                    print(f"  - {service}: {time_ms}ms")
            
            return overall_status in ['healthy', 'degraded']
            
        elif response.status_code == 503:
            print_warning("Service returned 503 - Service Unavailable")
            try:
                data = response.json()
                print(f"Details: {json.dumps(data, indent=2)}")
            except:
                print(f"Response: {response.text[:200]}")
            return False
        else:
            print_error(f"Unexpected status code: {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print_error("Request timed out (15 seconds)")
        return False
    except requests.exceptions.ConnectionError as e:
        print_error(f"Connection failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

def test_specific_health_endpoints(base_url: str, api_key: Optional[str] = None) -> Dict[str, bool]:
    """Test specific health endpoints."""
    print_header("Testing Specific Health Endpoints")
    
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
        headers['Authorization'] = f'Bearer {api_key}'
    
    endpoints = {
        '/live': 'Liveness Probe',
        '/ready': 'Readiness Probe',
        '/health/mlflow': 'MLflow Health',
        '/health/status': 'Detailed Status'
    }
    
    results = {}
    
    for endpoint, description in endpoints.items():
        try:
            response = requests.get(
                f"{base_url}{endpoint}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                print_success(f"{description} ({endpoint}): OK")
                results[endpoint] = True
            else:
                print_warning(f"{description} ({endpoint}): {response.status_code}")
                results[endpoint] = False
                
        except Exception as e:
            print_error(f"{description} ({endpoint}): {str(e)[:50]}")
            results[endpoint] = False
    
    return results

def test_database_through_api(base_url: str, api_key: Optional[str] = None) -> bool:
    """Test database connectivity through the API."""
    print_header("Testing Database Connectivity via API")
    
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
        headers['Authorization'] = f'Bearer {api_key}'
    
    try:
        # Try the detailed status endpoint
        response = requests.get(
            f"{base_url}/health/status",
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check PostgreSQL status
            postgres_status = data.get('services', {}).get('postgres', 'unknown')
            
            if postgres_status == 'healthy':
                print_success("PostgreSQL connection is healthy")
                return True
            elif postgres_status == 'disabled':
                print_info("PostgreSQL health check is disabled")
                return True
            else:
                print_error(f"PostgreSQL status: {postgres_status}")
                
                # Check for error details
                errors = data.get('errors', {})
                if 'postgres' in errors:
                    print_error(f"PostgreSQL error: {errors['postgres']}")
                
                return False
        else:
            print_warning(f"Could not get detailed status: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Error testing database: {e}")
        return False

def test_mlflow_connectivity(base_url: str, api_key: Optional[str] = None) -> bool:
    """Test MLflow connectivity through the API."""
    print_header("Testing MLflow Connectivity")
    
    headers = {}
    if api_key:
        headers['X-API-Key'] = api_key
        headers['Authorization'] = f'Bearer {api_key}'
    
    try:
        # Test MLflow health endpoint
        response = requests.get(
            f"{base_url}/health/mlflow",
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            mlflow_status = data.get('mlflow_status', 'unknown')
            circuit_breaker = data.get('circuit_breaker_state', 'unknown')
            
            print_info(f"MLflow Status: {mlflow_status}")
            print_info(f"Circuit Breaker State: {circuit_breaker}")
            
            if mlflow_status == 'healthy' and circuit_breaker == 'CLOSED':
                print_success("MLflow is healthy and circuit breaker is closed")
                return True
            elif circuit_breaker == 'OPEN':
                print_error("Circuit breaker is OPEN - MLflow experiencing issues")
                return False
            elif circuit_breaker == 'HALF_OPEN':
                print_warning("Circuit breaker is HALF_OPEN - MLflow recovering")
                return True
            else:
                print_warning(f"MLflow status unclear: {mlflow_status}")
                return mlflow_status == 'healthy'
                
        else:
            print_error(f"MLflow health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Error testing MLflow: {e}")
        return False

def verify_deployment(base_url: str, api_key: Optional[str] = None) -> int:
    """Run all deployment verification tests."""
    print_header("Hokusai API Deployment Verification")
    print(f"Target: {base_url}")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    if api_key:
        print_info(f"Using API Key: {api_key[:20]}...")
    else:
        print_warning("No API key provided - some endpoints may not be accessible")
    
    test_results = {}
    
    # Run main health test
    test_results['Main Health'] = test_health_endpoint(base_url, api_key)
    
    # Run specific endpoint tests
    endpoint_results = test_specific_health_endpoints(base_url, api_key)
    test_results.update(endpoint_results)
    
    # Test database connectivity
    test_results['Database'] = test_database_through_api(base_url, api_key)
    
    # Test MLflow
    test_results['MLflow'] = test_mlflow_connectivity(base_url, api_key)
    
    # Print summary
    print_header("Deployment Verification Summary")
    
    passed = sum(1 for result in test_results.values() if result)
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = f"{GREEN}PASSED{RESET}" if result else f"{RED}FAILED{RESET}"
        print(f"{test_name}: {status}")
    
    print(f"\n{BOLD}Overall: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print_success("Deployment verification successful! All systems operational.")
        return 0
    elif passed >= total * 0.7:  # 70% or more passed
        print_warning("Deployment partially successful. Some services may be degraded.")
        return 0
    else:
        print_error("Deployment verification failed. Critical issues detected.")
        return 1

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify Hokusai API deployment')
    parser.add_argument(
        '--url',
        default='https://registry.hokus.ai',
        help='Base URL of the API (default: https://registry.hokus.ai)'
    )
    parser.add_argument(
        '--api-key',
        help='API key for authentication'
    )
    parser.add_argument(
        '--local',
        action='store_true',
        help='Test local development server (http://localhost:8000)'
    )
    
    args = parser.parse_args()
    
    if args.local:
        base_url = 'http://localhost:8000'
    else:
        base_url = args.url.rstrip('/')
    
    return verify_deployment(base_url, args.api_key)

if __name__ == "__main__":
    sys.exit(main())