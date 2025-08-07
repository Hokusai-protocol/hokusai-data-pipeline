#!/usr/bin/env python3
"""
Comprehensive API endpoint testing script.

This script tests all API endpoints for:
1. Accessibility at correct URLs
2. Proper authentication behavior
3. Correct HTTP status codes
4. Response format validation
5. Error handling

Usage:
    python scripts/test_api_endpoints.py [--base-url http://localhost:8000] [--api-key your-key]
"""

import argparse
import asyncio
import json
import sys
import time
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin

import httpx
import tabulate


class APIEndpointTester:
    """Comprehensive API endpoint testing utility."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.results = []
        self.headers = {"Content-Type": "application/json"}
        
        if api_key:
            self.headers["X-API-Key"] = api_key
        
        # Define test endpoints with expected behaviors
        self.endpoints = [
            # Health and Status endpoints (public)
            {
                "path": "/health",
                "method": "GET", 
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["status", "services", "timestamp"],
                "description": "Basic health check"
            },
            {
                "path": "/health?detailed=true",
                "method": "GET",
                "auth_required": False, 
                "expected_status": [200],
                "expected_fields": ["status", "services", "system_info"],
                "description": "Detailed health check"
            },
            {
                "path": "/ready",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200, 503],
                "expected_fields": ["ready", "checks"],
                "description": "Readiness check"
            },
            {
                "path": "/live", 
                "method": "GET",
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["alive"],
                "description": "Liveness check"
            },
            {
                "path": "/version",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200], 
                "expected_fields": ["version", "api_version"],
                "description": "Version information"
            },
            {
                "path": "/metrics",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": None,  # Can be Prometheus or JSON format
                "description": "Service metrics"
            },
            
            # Model endpoints (auth required)
            {
                "path": "/models/",
                "method": "GET",
                "auth_required": False,  # This endpoint is public
                "expected_status": [200],
                "expected_fields": ["models"],
                "description": "List all models"
            },
            {
                "path": "/models/?name=test_model",
                "method": "GET", 
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["models"],
                "description": "List models with filter"
            },
            {
                "path": "/models/test_model/1",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200, 404], 
                "expected_fields": None,  # Depends on model existence
                "description": "Get specific model"
            },
            {
                "path": "/models/test_model/lineage",
                "method": "GET",
                "auth_required": True,
                "expected_status": [200, 401, 404],
                "expected_fields": None,
                "description": "Get model lineage"
            },
            {
                "path": "/models/register",
                "method": "POST",
                "auth_required": True,
                "expected_status": [201, 400, 401, 422],
                "expected_fields": None,
                "description": "Register new model",
                "payload": {
                    "model_name": "test_model",
                    "model_type": "lead_scoring",
                    "model_data": {"path": "s3://test/model.pkl"},
                    "metadata": {"version": "1.0.0"}
                }
            },
            {
                "path": "/models/compare",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200, 400],
                "expected_fields": None,
                "description": "Compare models",
                "query_params": "?model1=test:1&model2=test:2"
            },
            {
                "path": "/models/production",
                "method": "GET", 
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["models"],
                "description": "Get production models"
            },
            
            # DSPy endpoints (auth required)  
            {
                "path": "/api/v1/dspy/health",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["status"],
                "description": "DSPy service health"
            },
            {
                "path": "/api/v1/dspy/programs",
                "method": "GET",
                "auth_required": True,
                "expected_status": [200, 401],
                "expected_fields": None,
                "description": "List DSPy programs"
            },
            {
                "path": "/api/v1/dspy/stats",
                "method": "GET",
                "auth_required": True,
                "expected_status": [200, 401], 
                "expected_fields": ["statistics"],
                "description": "DSPy execution statistics"
            },
            {
                "path": "/api/v1/dspy/execute",
                "method": "POST",
                "auth_required": True,
                "expected_status": [200, 400, 401],
                "expected_fields": None,
                "description": "Execute DSPy program",
                "payload": {
                    "program_id": "test_program",
                    "inputs": {"text": "test input"}
                }
            },
            
            # MLflow proxy endpoints
            {
                "path": "/mlflow/api/2.0/mlflow/experiments/search?max_results=1",
                "method": "GET", 
                "auth_required": False,
                "expected_status": [200, 502, 503],
                "expected_fields": None,
                "description": "MLflow experiments proxy"
            },
            
            # MLflow health endpoints
            {
                "path": "/api/health/mlflow",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200, 503, 500],
                "expected_fields": None,
                "description": "MLflow health check"
            },
            {
                "path": "/api/health/mlflow/connectivity", 
                "method": "GET",
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["status", "mlflow_server"],
                "description": "MLflow connectivity check"
            },
            {
                "path": "/api/health/mlflow/detailed",
                "method": "GET",
                "auth_required": False,
                "expected_status": [200],
                "expected_fields": ["mlflow_server", "tests"],
                "description": "MLflow detailed health"
            },
            
            # Protected endpoints that should require auth
            {
                "path": "/health/mlflow/reset",
                "method": "POST",
                "auth_required": True,
                "expected_status": [200, 401, 500],
                "expected_fields": None,
                "description": "Reset MLflow circuit breaker"
            },
            {
                "path": "/health/status",
                "method": "GET", 
                "auth_required": True,
                "expected_status": [200, 401, 500],
                "expected_fields": None,
                "description": "Detailed service status"
            },
        ]

    async def test_endpoint(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single endpoint and return results."""
        path = endpoint["path"]
        method = endpoint["method"]
        auth_required = endpoint["auth_required"]
        expected_status = endpoint["expected_status"]
        expected_fields = endpoint.get("expected_fields", [])
        payload = endpoint.get("payload")
        query_params = endpoint.get("query_params", "")
        
        url = urljoin(self.base_url, path + query_params)
        result = {
            "endpoint": f"{method} {path}",
            "description": endpoint["description"],
            "url": url,
            "auth_required": auth_required,
            "expected_status": expected_status,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test without auth first
                start_time = time.time()
                
                if method == "GET":
                    response = await client.get(url)
                elif method == "POST":
                    response = await client.post(url, json=payload or {})
                else:
                    response = await client.request(method, url, json=payload)
                
                response_time = time.time() - start_time
                
                result.update({
                    "status_code": response.status_code,
                    "response_time_ms": round(response_time * 1000, 2),
                    "content_type": response.headers.get("content-type", ""),
                    "status_in_expected": response.status_code in expected_status,
                })
                
                # Check if we got 401 when auth is required
                if auth_required and response.status_code == 401:
                    result["auth_check"] = "✓ Correctly requires auth"
                elif auth_required and response.status_code != 401 and not self.api_key:
                    result["auth_check"] = "⚠ Should require auth but doesn't"
                elif not auth_required and response.status_code == 401:
                    result["auth_check"] = "⚠ Requires auth but shouldn't"
                else:
                    result["auth_check"] = "✓ Auth behavior correct"
                
                # Try to parse JSON response
                try:
                    response_data = response.json()
                    result["response_format"] = "JSON"
                    
                    # Check for expected fields
                    if expected_fields and response.status_code in [200, 201]:
                        missing_fields = [field for field in expected_fields if field not in response_data]
                        if missing_fields:
                            result["field_check"] = f"⚠ Missing fields: {missing_fields}"
                        else:
                            result["field_check"] = "✓ All expected fields present"
                    else:
                        result["field_check"] = "N/A"
                        
                except (json.JSONDecodeError, ValueError):
                    result["response_format"] = "Non-JSON"
                    result["field_check"] = "N/A"
                
                # Test with auth if required and we have a key
                if auth_required and self.api_key:
                    auth_headers = {**self.headers}
                    
                    if method == "GET":
                        auth_response = await client.get(url, headers=auth_headers)
                    elif method == "POST":
                        auth_response = await client.post(url, json=payload or {}, headers=auth_headers)
                    else:
                        auth_response = await client.request(method, url, json=payload, headers=auth_headers)
                    
                    result["auth_status_code"] = auth_response.status_code
                    result["auth_works"] = auth_response.status_code != 401
                
        except httpx.TimeoutException:
            result.update({
                "status_code": "TIMEOUT", 
                "error": "Request timed out",
                "status_in_expected": False,
                "auth_check": "N/A - Timeout",
                "field_check": "N/A - Timeout"
            })
        except Exception as e:
            result.update({
                "status_code": "ERROR",
                "error": str(e),
                "status_in_expected": False,
                "auth_check": "N/A - Error", 
                "field_check": "N/A - Error"
            })
        
        return result

    async def run_all_tests(self) -> List[Dict[str, Any]]:
        """Run tests for all endpoints."""
        print(f"🚀 Testing API endpoints at: {self.base_url}")
        print(f"🔑 Using API key: {'Yes' if self.api_key else 'No'}")
        print("=" * 80)
        
        tasks = [self.test_endpoint(endpoint) for endpoint in self.endpoints]
        results = await asyncio.gather(*tasks)
        
        return results

    def print_results(self, results: List[Dict[str, Any]]):
        """Print test results in a formatted table."""
        # Summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.get("status_in_expected", False))
        failed_tests = total_tests - passed_tests
        timeout_errors = sum(1 for r in results if r.get("status_code") == "TIMEOUT")
        connection_errors = sum(1 for r in results if r.get("status_code") == "ERROR")
        
        print("\n📊 TEST SUMMARY")
        print("=" * 80)
        print(f"Total endpoints tested: {total_tests}")
        print(f"✅ Passed (correct status): {passed_tests}")
        print(f"❌ Failed (wrong status): {failed_tests}")
        print(f"⏰ Timeouts: {timeout_errors}")
        print(f"🔌 Connection errors: {connection_errors}")
        print(f"📈 Success rate: {(passed_tests/total_tests)*100:.1f}%")
        
        # Detailed results table
        print("\n📋 DETAILED RESULTS")
        print("=" * 80)
        
        table_data = []
        for result in results:
            status_code = result.get("status_code", "N/A")
            expected = result.get("expected_status", [])
            
            # Status indicator
            if result.get("status_in_expected", False):
                status_indicator = "✅"
            elif status_code in ["TIMEOUT", "ERROR"]:
                status_indicator = "🔴"
            else:
                status_indicator = "⚠️"
            
            table_data.append([
                status_indicator,
                result.get("endpoint", ""),
                status_code,
                f"{expected}",
                result.get("response_time_ms", "N/A"),
                result.get("auth_check", "N/A"),
                result.get("field_check", "N/A")[:30] + "..." if len(str(result.get("field_check", ""))) > 30 else result.get("field_check", "N/A")
            ])
        
        headers = ["Status", "Endpoint", "Code", "Expected", "Time(ms)", "Auth Check", "Fields"]
        print(tabulate.tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Failed tests details
        failed_results = [r for r in results if not r.get("status_in_expected", False)]
        if failed_results:
            print("\n🔍 FAILED TESTS DETAILS")
            print("=" * 80)
            for result in failed_results:
                print(f"❌ {result.get('endpoint', '')}")
                print(f"   URL: {result.get('url', '')}")
                print(f"   Expected: {result.get('expected_status', [])}")  
                print(f"   Got: {result.get('status_code', 'N/A')}")
                if result.get('error'):
                    print(f"   Error: {result['error']}")
                print()
        
        # Authentication summary
        auth_tests = [r for r in results if r.get("auth_required", False)]
        if auth_tests:
            print(f"\n🔐 AUTHENTICATION SUMMARY ({len(auth_tests)} endpoints)")
            print("=" * 80)
            auth_correct = sum(1 for r in auth_tests if "✓" in str(r.get("auth_check", "")))
            print(f"✅ Correct auth behavior: {auth_correct}/{len(auth_tests)}")
            
            auth_issues = [r for r in auth_tests if "⚠" in str(r.get("auth_check", ""))]
            if auth_issues:
                print("⚠️  Auth issues found:")
                for result in auth_issues:
                    print(f"   • {result.get('endpoint', '')}: {result.get('auth_check', '')}")

    def export_results(self, results: List[Dict[str, Any]], filename: str = "api_test_results.json"):
        """Export results to JSON file."""
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results exported to: {filename}")


async def main():
    """Main function to run endpoint tests."""
    parser = argparse.ArgumentParser(description="Test Hokusai API endpoints")
    parser.add_argument(
        "--base-url", 
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (optional)"
    )
    parser.add_argument(
        "--export",
        default="api_test_results.json",
        help="Export results to JSON file (default: api_test_results.json)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)"
    )
    
    args = parser.parse_args()
    
    # Create tester and run tests
    tester = APIEndpointTester(args.base_url, args.api_key)
    
    try:
        results = await tester.run_all_tests()
        tester.print_results(results)
        
        if args.export:
            tester.export_results(results, args.export)
            
        # Exit with non-zero code if any tests failed
        failed_count = sum(1 for r in results if not r.get("status_in_expected", False))
        if failed_count > 0:
            print(f"\n❌ {failed_count} tests failed!")
            sys.exit(1)
        else:
            print(f"\n✅ All tests passed!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Install required packages
    try:
        import httpx
        import tabulate
    except ImportError:
        print("Missing required packages. Install with:")
        print("pip install httpx tabulate")
        sys.exit(1)
    
    asyncio.run(main())