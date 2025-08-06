#!/usr/bin/env python3
"""
Test script for enhanced health check functionality.
Tests circuit breaker states, graceful degradation, and recovery endpoints.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckTester:
    """Test enhanced health check functionality."""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = api_url or os.getenv("API_URL", "http://localhost:8000")
        self.api_key = api_key or os.getenv("API_KEY", "test-api-key")
        self.session = requests.Session()
        self.session.timeout = 10
        self.test_results = []

    def run_tests(self) -> Dict:
        """Run comprehensive health check tests."""
        logger.info("🧪 Starting enhanced health check tests...")
        start_time = time.time()
        
        test_suite = {
            "start_time": datetime.now().isoformat(),
            "api_url": self.api_url,
            "tests": {},
            "summary": {},
            "duration_seconds": 0
        }
        
        # Test cases
        test_cases = [
            ("basic_health", self._test_basic_health_check),
            ("health_detailed", self._test_detailed_health_check),
            ("readiness_check", self._test_readiness_check),
            ("mlflow_health", self._test_mlflow_health_check),
            ("circuit_breaker_status", self._test_circuit_breaker_status),
            ("service_status", self._test_service_status_endpoint),
            ("metrics_endpoint", self._test_metrics_endpoint),
            ("graceful_degradation", self._test_graceful_degradation)
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in test_cases:
            logger.info(f"Running test: {test_name}")
            try:
                result = test_func()
                test_suite["tests"][test_name] = result
                
                if result["passed"]:
                    passed += 1
                    logger.info(f"✅ {test_name}: PASSED")
                else:
                    failed += 1
                    logger.error(f"❌ {test_name}: FAILED - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                failed += 1
                error_result = {
                    "passed": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                test_suite["tests"][test_name] = error_result
                logger.error(f"💥 {test_name}: EXCEPTION - {str(e)}")
        
        # Summary
        test_suite["duration_seconds"] = time.time() - start_time
        test_suite["summary"] = {
            "total_tests": len(test_cases),
            "passed": passed,
            "failed": failed,
            "success_rate": (passed / len(test_cases)) * 100
        }
        
        return test_suite

    def _make_request(self, endpoint: str, method: str = "GET", authenticated: bool = True, **kwargs) -> Dict:
        """Make API request with common handling."""
        headers = kwargs.pop("headers", {})
        if authenticated and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        url = f"{self.api_url}{endpoint}"
        
        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, **kwargs)
            elif method == "POST":
                response = self.session.post(url, headers=headers, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            return {
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "headers": dict(response.headers)
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "status_code": None,
                "data": None
            }

    def _test_basic_health_check(self) -> Dict:
        """Test basic health check endpoint."""
        result = {
            "passed": False,
            "description": "Basic health check endpoint",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/health", authenticated=False)
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        result["status_code"] = response["status_code"]
        result["response_time_ms"] = response["response_time_ms"]
        
        if response["status_code"] == 200:
            data = response["data"]
            
            # Check required fields
            required_fields = ["status", "version", "services", "timestamp"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                result["error"] = f"Missing required fields: {missing_fields}"
                return result
            
            result["overall_status"] = data["status"]
            result["services"] = data["services"]
            result["passed"] = True
            
        else:
            result["error"] = f"Unexpected status code: {response['status_code']}"
        
        return result

    def _test_detailed_health_check(self) -> Dict:
        """Test detailed health check with ?detailed=true."""
        result = {
            "passed": False,
            "description": "Detailed health check with system info",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/health?detailed=true", authenticated=False)
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        if response["status_code"] == 200:
            data = response["data"]
            
            # Should have system_info in detailed mode
            if "system_info" in data:
                result["has_system_info"] = True
                result["system_info"] = data["system_info"]
            
            # Check for service details
            services_with_details = sum(1 for k, v in data.get("services", {}).items() 
                                      if isinstance(v, dict) or k.endswith("_details"))
            
            result["services_with_details"] = services_with_details
            result["passed"] = True
            
        else:
            result["error"] = f"Status code: {response['status_code']}"
        
        return result

    def _test_readiness_check(self) -> Dict:
        """Test readiness endpoint with graceful degradation."""
        result = {
            "passed": False,
            "description": "Readiness check with graceful degradation",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/ready", authenticated=False)
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        result["status_code"] = response["status_code"]
        data = response["data"]
        
        # Readiness check can return 200 or 503
        if response["status_code"] in [200, 503]:
            required_fields = ["ready", "can_serve_traffic", "checks"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                result["error"] = f"Missing required fields: {missing_fields}"
                return result
            
            result["ready"] = data["ready"]
            result["can_serve_traffic"] = data["can_serve_traffic"]
            result["degraded_mode"] = data.get("degraded_mode", False)
            result["checks"] = data["checks"]
            
            # Test graceful degradation logic
            if response["status_code"] == 503 and not data["can_serve_traffic"]:
                result["graceful_degradation"] = "Critical services down - 503 returned"
            elif response["status_code"] == 200 and data.get("degraded_mode"):
                result["graceful_degradation"] = "Degraded mode - still serving traffic"
            elif response["status_code"] == 200 and data["ready"]:
                result["graceful_degradation"] = "Fully healthy"
            
            result["passed"] = True
            
        else:
            result["error"] = f"Unexpected status code: {response['status_code']}"
        
        return result

    def _test_mlflow_health_check(self) -> Dict:
        """Test MLflow-specific health check."""
        result = {
            "passed": False,
            "description": "MLflow health check endpoint",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/health/mlflow")
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        result["status_code"] = response["status_code"]
        
        # MLflow health can return 200, 503, or 500
        if response["status_code"] in [200, 503, 500]:
            data = response["data"]
            
            if "circuit_breaker_state" in data:
                result["circuit_breaker_state"] = data["circuit_breaker_state"]
                result["connected"] = data.get("connected", False)
                
                if "circuit_breaker_details" in data:
                    result["circuit_breaker_details"] = data["circuit_breaker_details"]
                
                result["passed"] = True
            else:
                result["error"] = "Missing circuit_breaker_state field"
        else:
            result["error"] = f"Unexpected status code: {response['status_code']}"
        
        return result

    def _test_circuit_breaker_status(self) -> Dict:
        """Test circuit breaker status reporting."""
        result = {
            "passed": False,
            "description": "Circuit breaker status and details",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/health/mlflow")
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        if response["status_code"] in [200, 503]:
            data = response["data"]
            cb_details = data.get("circuit_breaker_details", {})
            
            # Check for detailed circuit breaker information
            expected_fields = ["state", "failure_count", "recovery_attempts", "time_until_retry"]
            present_fields = [field for field in expected_fields if field in cb_details]
            
            result["circuit_breaker_fields"] = present_fields
            result["circuit_breaker_state"] = cb_details.get("state", "unknown")
            
            if len(present_fields) >= 2:  # At least some detail present
                result["passed"] = True
                
                # Test circuit breaker state logic
                if cb_details.get("state") == "OPEN":
                    result["validation"] = "Circuit breaker open - appropriate 503 response" if response["status_code"] == 503 else "WARNING: Circuit breaker open but 200 response"
                elif cb_details.get("state") == "CLOSED":
                    result["validation"] = "Circuit breaker closed - healthy state"
                elif cb_details.get("state") == "HALF_OPEN":
                    result["validation"] = "Circuit breaker half-open - recovery in progress"
            else:
                result["error"] = f"Insufficient circuit breaker details: {present_fields}"
        else:
            result["error"] = f"Status code: {response['status_code']}"
        
        return result

    def _test_service_status_endpoint(self) -> Dict:
        """Test comprehensive service status endpoint."""
        result = {
            "passed": False,
            "description": "Comprehensive service status endpoint",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/health/status")
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        if response["status_code"] == 200:
            data = response["data"]
            
            expected_fields = ["timestamp", "service_name", "overall_health", "mlflow"]
            present_fields = [field for field in expected_fields if field in data]
            
            result["present_fields"] = present_fields
            
            if len(present_fields) >= 3:
                result["service_name"] = data.get("service_name")
                result["overall_health"] = data.get("overall_health")
                
                # Check MLflow section
                mlflow_section = data.get("mlflow", {})
                if "circuit_breaker" in mlflow_section:
                    result["has_circuit_breaker_info"] = True
                
                result["passed"] = True
            else:
                result["error"] = f"Missing expected fields: {expected_fields}"
        else:
            result["error"] = f"Status code: {response['status_code']}"
        
        return result

    def _test_metrics_endpoint(self) -> Dict:
        """Test metrics endpoint."""
        result = {
            "passed": False,
            "description": "Metrics endpoint availability",
            "timestamp": datetime.now().isoformat()
        }
        
        response = self._make_request("/metrics", authenticated=False)
        
        if response.get("error"):
            result["error"] = response["error"]
            return result
        
        result["status_code"] = response["status_code"]
        
        if response["status_code"] == 200:
            metrics_data = response["data"]
            
            if isinstance(metrics_data, str):
                # Prometheus format
                result["format"] = "prometheus"
                result["size"] = len(metrics_data)
                result["lines"] = len(metrics_data.split('\n'))
                
                # Look for circuit breaker metrics
                if "mlflow_circuit_breaker" in metrics_data:
                    result["has_circuit_breaker_metrics"] = True
                
            elif isinstance(metrics_data, dict):
                # JSON format
                result["format"] = "json"
                result["metrics_count"] = len(metrics_data)
            
            result["passed"] = True
        else:
            result["error"] = f"Status code: {response['status_code']}"
        
        return result

    def _test_graceful_degradation(self) -> Dict:
        """Test graceful degradation behavior."""
        result = {
            "passed": False,
            "description": "Graceful degradation behavior testing",
            "timestamp": datetime.now().isoformat(),
            "degradation_scenarios": []
        }
        
        # Test different endpoints and check for graceful behavior
        endpoints = ["/health", "/ready", "/health/mlflow"]
        
        degradation_found = False
        
        for endpoint in endpoints:
            response = self._make_request(endpoint, authenticated=False)
            
            scenario = {
                "endpoint": endpoint,
                "status_code": response.get("status_code"),
                "graceful": False
            }
            
            if response.get("status_code") == 503:
                # Service unavailable but still responding
                scenario["graceful"] = True
                scenario["reason"] = "Returns 503 but still responsive"
                degradation_found = True
                
            elif response.get("status_code") == 200:
                data = response.get("data", {})
                
                # Check for degradation indicators
                if isinstance(data, dict):
                    if (data.get("status") == "degraded" or 
                        data.get("degraded_mode") == True or
                        data.get("circuit_breaker_state") in ["OPEN", "HALF_OPEN"]):
                        scenario["graceful"] = True
                        scenario["reason"] = "Returns 200 with degradation indicators"
                        degradation_found = True
            
            result["degradation_scenarios"].append(scenario)
        
        # Test passes if we find evidence of graceful degradation handling
        result["passed"] = degradation_found or len([s for s in result["degradation_scenarios"] if s["graceful"]]) > 0
        
        if not result["passed"]:
            result["error"] = "No evidence of graceful degradation behavior found"
        
        return result

    def print_test_summary(self, test_suite: Dict):
        """Print test summary."""
        print("\n" + "="*80)
        print("🧪 ENHANCED HEALTH CHECK TEST SUMMARY")
        print("="*80)
        
        summary = test_suite["summary"]
        print(f"\n📊 Results: {summary['passed']}/{summary['total_tests']} tests passed ({summary['success_rate']:.1f}%)")
        print(f"⏱️  Duration: {test_suite['duration_seconds']:.2f} seconds")
        print(f"🌐 API URL: {test_suite['api_url']}")
        
        print(f"\n📋 Test Results:")
        
        for test_name, test_result in test_suite["tests"].items():
            status = "✅ PASS" if test_result["passed"] else "❌ FAIL"
            description = test_result.get("description", "")
            print(f"   {status} {test_name}: {description}")
            
            if not test_result["passed"] and "error" in test_result:
                print(f"      └─ Error: {test_result['error']}")
            
            # Show key findings
            if test_result["passed"]:
                if test_name == "circuit_breaker_status" and "circuit_breaker_state" in test_result:
                    print(f"      └─ Circuit Breaker: {test_result['circuit_breaker_state']}")
                elif test_name == "readiness_check" and "graceful_degradation" in test_result:
                    print(f"      └─ Degradation: {test_result['graceful_degradation']}")
                elif test_name == "basic_health" and "overall_status" in test_result:
                    print(f"      └─ Status: {test_result['overall_status']}")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        failed_tests = [name for name, result in test_suite["tests"].items() if not result["passed"]]
        
        if not failed_tests:
            print("   ✅ All health check enhancements are working correctly!")
        else:
            print(f"   🔧 Fix failing tests: {', '.join(failed_tests)}")
            print("   📋 Check logs for detailed error information")
            print("   🏥 Run diagnostic script for comprehensive analysis")
        
        print("="*80)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test enhanced health check functionality")
    parser.add_argument("--api-url", help="API URL to test (default: http://localhost:8000)")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--output", help="Output file for test results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run tests
    tester = HealthCheckTester(api_url=args.api_url, api_key=args.api_key)
    results = tester.run_tests()
    
    # Print summary
    tester.print_test_summary(results)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n📁 Test results saved to: {args.output}")
    
    # Exit with appropriate code
    if results["summary"]["failed"] == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()