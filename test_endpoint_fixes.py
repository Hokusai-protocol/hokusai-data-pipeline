#!/usr/bin/env python3
"""
Quick test to verify endpoint fixes are working correctly.
"""

import requests
import json
from typing import Dict, List, Tuple
from datetime import datetime

def test_local_api(base_url: str = "http://localhost:8001") -> Dict[str, any]:
    """Test local API endpoints to verify fixes."""
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "base_url": base_url,
        "tests": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0
        }
    }
    
    # Test cases: (endpoint, method, expected_status, description)
    test_cases = [
        # Documentation endpoints (should work without auth)
        ("/docs", "GET", 200, "FastAPI documentation"),
        ("/redoc", "GET", 200, "ReDoc documentation"),
        ("/openapi.json", "GET", 200, "OpenAPI schema"),
        
        # Health endpoints (should work without auth)
        ("/health", "GET", 200, "Health check"),
        ("/ready", "GET", 200, "Readiness check"),
        ("/live", "GET", 200, "Liveness check"),
        
        # Models endpoints (fixed double prefix)
        ("/models", "GET", [200, 401], "List models"),
        ("/models/test/1", "GET", [200, 404, 401], "Get model by ID"),
        ("/models/compare", "GET", [200, 401], "Compare models"),
        
        # MLflow health
        ("/api/health/mlflow", "GET", 200, "MLflow health check"),
    ]
    
    for endpoint, method, expected_status, description in test_cases:
        url = f"{base_url}{endpoint}"
        results["summary"]["total"] += 1
        
        try:
            response = requests.request(method, url, timeout=5)
            status = response.status_code
            
            # Handle multiple acceptable statuses
            if isinstance(expected_status, list):
                success = status in expected_status
                expected_str = f"one of {expected_status}"
            else:
                success = status == expected_status
                expected_str = str(expected_status)
            
            # Check content type for successful responses
            content_type = response.headers.get("content-type", "")
            is_json = "application/json" in content_type
            is_html = "text/html" in content_type
            
            test_result = {
                "endpoint": endpoint,
                "description": description,
                "status": status,
                "expected": expected_str,
                "success": success,
                "content_type": content_type.split(";")[0] if content_type else "none"
            }
            
            # For successful responses, check content
            if status == 200:
                if endpoint == "/openapi.json":
                    try:
                        data = response.json()
                        test_result["has_openapi"] = "openapi" in data
                        test_result["title"] = data.get("info", {}).get("title", "N/A")
                    except:
                        test_result["has_openapi"] = False
                elif endpoint in ["/docs", "/redoc"]:
                    test_result["is_html"] = is_html
                elif is_json:
                    try:
                        data = response.json()
                        if endpoint == "/health":
                            test_result["health_status"] = data.get("status", "unknown")
                    except:
                        pass
            
            if success:
                results["summary"]["passed"] += 1
                print(f"✅ {description}: {endpoint} -> {status}")
            else:
                results["summary"]["failed"] += 1
                print(f"❌ {description}: {endpoint} -> {status} (expected {expected_str})")
            
            results["tests"].append(test_result)
            
        except requests.exceptions.RequestException as e:
            results["summary"]["failed"] += 1
            print(f"❌ {description}: {endpoint} -> ERROR: {str(e)}")
            results["tests"].append({
                "endpoint": endpoint,
                "description": description,
                "error": str(e),
                "success": False
            })
    
    return results

def print_summary(results: Dict[str, any]):
    """Print test summary."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    summary = results["summary"]
    success_rate = (summary["passed"] / summary["total"] * 100) if summary["total"] > 0 else 0
    
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    print("\n" + "="*60)
    print("KEY FIXES VERIFIED:")
    print("="*60)
    
    # Check specific fixes
    docs_working = any(t["endpoint"] == "/docs" and t.get("success") for t in results["tests"])
    models_working = any(t["endpoint"] == "/models" and t.get("success") for t in results["tests"])
    health_working = any(t["endpoint"] == "/health" and t.get("success") for t in results["tests"])
    
    print(f"{'✅' if docs_working else '❌'} Documentation endpoints accessible")
    print(f"{'✅' if models_working else '❌'} Models endpoint (no double prefix)")
    print(f"{'✅' if health_working else '❌'} Health endpoints working")
    
    # Show failed tests
    failed_tests = [t for t in results["tests"] if not t.get("success")]
    if failed_tests:
        print("\n" + "="*60)
        print("FAILED TESTS:")
        print("="*60)
        for test in failed_tests:
            if "error" in test:
                print(f"- {test['endpoint']}: {test['error']}")
            else:
                print(f"- {test['endpoint']}: Got {test['status']}, expected {test['expected']}")

if __name__ == "__main__":
    import sys
    
    # Check if server is specified
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
    
    print(f"Testing API at: {base_url}")
    print("="*60)
    
    results = test_local_api(base_url)
    print_summary(results)
    
    # Save results to file
    output_file = "endpoint_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_file}")
    
    # Exit with appropriate code
    sys.exit(0 if results["summary"]["failed"] == 0 else 1)