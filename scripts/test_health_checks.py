#!/usr/bin/env python3
"""
Health Check Testing Script

This script tests the health check endpoints to ensure they respond correctly
and handle various failure scenarios gracefully.
"""

import time
import requests
import json
from typing import Dict, Any
from datetime import datetime


class HealthCheckTester:
    def __init__(self, api_url: str = "http://localhost:8001", mlflow_url: str = "http://localhost:5000"):
        self.api_url = api_url
        self.mlflow_url = mlflow_url
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def test_endpoint(self, name: str, url: str, expected_status: int = 200) -> Dict[str, Any]:
        """Test a single endpoint."""
        self.log(f"Testing {name} endpoint: {url}")
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=30)
            elapsed = time.time() - start_time
            
            result = {
                "name": name,
                "url": url,
                "status_code": response.status_code,
                "elapsed_time": elapsed,
                "success": response.status_code == expected_status,
                "response": response.text if response.status_code != expected_status else "OK"
            }
            
            if result["success"]:
                self.log(f"✓ {name} - Status: {response.status_code} - Time: {elapsed:.2f}s", "SUCCESS")
            else:
                self.log(f"✗ {name} - Status: {response.status_code} - Expected: {expected_status}", "ERROR")
                
        except requests.exceptions.Timeout:
            result = {
                "name": name,
                "url": url,
                "status_code": None,
                "elapsed_time": 30.0,
                "success": False,
                "response": "Timeout after 30 seconds"
            }
            self.log(f"✗ {name} - Timeout after 30 seconds", "ERROR")
            
        except Exception as e:
            result = {
                "name": name,
                "url": url,
                "status_code": None,
                "elapsed_time": 0,
                "success": False,
                "response": str(e)
            }
            self.log(f"✗ {name} - Error: {str(e)}", "ERROR")
            
        self.results.append(result)
        return result
        
    def wait_for_services(self, timeout: int = 300):
        """Wait for services to become healthy."""
        self.log(f"Waiting for services to become healthy (timeout: {timeout}s)...")
        
        start_time = time.time()
        api_healthy = False
        mlflow_healthy = False
        
        while time.time() - start_time < timeout:
            # Check API health
            if not api_healthy:
                try:
                    response = requests.get(f"{self.api_url}/health", timeout=5)
                    if response.status_code == 200:
                        api_healthy = True
                        self.log("API service is healthy", "SUCCESS")
                except:
                    pass
                    
            # Check MLflow health
            if not mlflow_healthy:
                try:
                    response = requests.get(f"{self.mlflow_url}/mlflow", timeout=5)
                    if response.status_code in [200, 308]:
                        mlflow_healthy = True
                        self.log("MLflow service is healthy", "SUCCESS")
                except:
                    pass
                    
            if api_healthy and mlflow_healthy:
                self.log("All services are healthy!", "SUCCESS")
                return True
                
            time.sleep(5)
            
        self.log("Services did not become healthy within timeout", "ERROR")
        return False
        
    def run_tests(self):
        """Run all health check tests."""
        self.log("Starting health check tests...")
        
        # Wait for services to be ready
        if not self.wait_for_services():
            self.log("Aborting tests - services not healthy", "ERROR")
            return
            
        # Test API endpoints
        self.test_endpoint("API Health", f"{self.api_url}/health")
        self.test_endpoint("API Health (Detailed)", f"{self.api_url}/health?detailed=true")
        self.test_endpoint("API Ready", f"{self.api_url}/ready")
        self.test_endpoint("API Live", f"{self.api_url}/live")
        self.test_endpoint("API Version", f"{self.api_url}/version")
        self.test_endpoint("API Metrics", f"{self.api_url}/metrics")
        self.test_endpoint("API MLflow Health", f"{self.api_url}/health/mlflow")
        
        # Test MLflow endpoints
        self.test_endpoint("MLflow Root", f"{self.mlflow_url}/mlflow", expected_status=200)
        self.test_endpoint("MLflow Version", f"{self.mlflow_url}/version")
        
        # Test error scenarios
        self.test_endpoint("API Invalid Endpoint", f"{self.api_url}/invalid", expected_status=404)
        
        # Summary
        self.print_summary()
        
    def print_summary(self):
        """Print test summary."""
        self.log("\n=== TEST SUMMARY ===")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["success"])
        failed = total - passed
        
        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed > 0:
            print("\nFailed Tests:")
            for result in self.results:
                if not result["success"]:
                    print(f"  - {result['name']}: {result['response']}")
                    
        # Performance summary
        print("\nPerformance Summary:")
        for result in self.results:
            if result["success"] and result["elapsed_time"] > 0:
                print(f"  - {result['name']}: {result['elapsed_time']:.2f}s")
                
        # Check for slow endpoints
        slow_endpoints = [r for r in self.results if r["elapsed_time"] > 5.0]
        if slow_endpoints:
            print("\nWARNING: Slow endpoints detected (>5s):")
            for result in slow_endpoints:
                print(f"  - {result['name']}: {result['elapsed_time']:.2f}s")


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test health check endpoints")
    parser.add_argument("--api-url", default="http://localhost:8001", help="API base URL")
    parser.add_argument("--mlflow-url", default="http://localhost:5000", help="MLflow base URL")
    
    args = parser.parse_args()
    
    tester = HealthCheckTester(api_url=args.api_url, mlflow_url=args.mlflow_url)
    tester.run_tests()


if __name__ == "__main__":
    main()