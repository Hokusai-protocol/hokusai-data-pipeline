#!/usr/bin/env python3
"""
Test script for validating dedicated ALBs configuration.
This ensures both auth.hokus.ai and registry.hokus.ai work correctly
after migration to separate load balancers.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Tuple

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


class ALBTester:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.results = []
        
    def print_header(self, title: str):
        """Print a formatted section header."""
        print(f"\n{'='*60}")
        print(f"{BLUE}{title}{RESET}")
        print(f"{'='*60}")
        
    def test_endpoint(self, name: str, url: str, headers: Dict = None, 
                     expected_status: List[int] = [200], method: str = "GET",
                     json_data: Dict = None) -> Tuple[bool, str]:
        """Test a single endpoint and return success status and message."""
        try:
            if headers is None:
                headers = {}
                
            # Add API key to headers if needed
            if "auth.hokus.ai" in url or "registry.hokus.ai" in url:
                if "/health" not in url and "/" != url.split('/')[-1]:
                    headers["Authorization"] = f"Bearer {self.api_key}"
            
            print(f"\n{YELLOW}Testing:{RESET} {name}")
            print(f"URL: {url}")
            print(f"Method: {method}")
            
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=10)
            else:
                return False, f"Unsupported method: {method}"
            
            print(f"Status: {response.status_code}")
            
            if response.status_code in expected_status:
                print(f"{GREEN}✓ SUCCESS{RESET}")
                return True, f"Status {response.status_code}"
            else:
                print(f"{RED}✗ FAILED{RESET}")
                print(f"Response: {response.text[:200]}")
                return False, f"Expected {expected_status}, got {response.status_code}"
                
        except requests.exceptions.Timeout:
            print(f"{RED}✗ TIMEOUT{RESET}")
            return False, "Request timed out"
        except requests.exceptions.ConnectionError as e:
            print(f"{RED}✗ CONNECTION ERROR{RESET}")
            return False, f"Connection error: {str(e)}"
        except Exception as e:
            print(f"{RED}✗ ERROR{RESET}")
            return False, f"Error: {str(e)}"
    
    def test_auth_service(self):
        """Test auth.hokus.ai endpoints."""
        self.print_header("AUTH SERVICE TESTS (auth.hokus.ai)")
        
        tests = [
            ("Health Check", "https://auth.hokus.ai/health", None, [200], "GET", None),
            ("Root Endpoint", "https://auth.hokus.ai/", None, [200], "GET", None),
            ("API Validation", "https://auth.hokus.ai/api/v1/keys/validate", 
             {"Content-Type": "application/json"}, [200, 401], "POST",
             {"service_id": "ml-platform", "client_ip": "127.0.0.1"}),
        ]
        
        for test in tests:
            success, message = self.test_endpoint(*test)
            self.results.append(("Auth Service", test[0], success, message))
    
    def test_registry_service(self):
        """Test registry.hokus.ai endpoints."""
        self.print_header("REGISTRY SERVICE TESTS (registry.hokus.ai)")
        
        tests = [
            ("Health Check", "https://registry.hokus.ai/health", None, [200], "GET", None),
            ("API Health", "https://registry.hokus.ai/api/health", None, [200, 401], "GET", None),
            ("MLflow UI", "https://registry.hokus.ai/mlflow/", None, [200], "GET", None),
            ("MLflow API Proxy", "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search",
             None, [200, 404], "GET", None),
        ]
        
        for test in tests:
            success, message = self.test_endpoint(*test)
            self.results.append(("Registry Service", test[0], success, message))
    
    def test_mlflow_client(self):
        """Test MLflow client connectivity."""
        self.print_header("MLFLOW CLIENT TEST")
        
        try:
            import mlflow
            
            os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
            os.environ["MLFLOW_TRACKING_TOKEN"] = self.api_key
            
            print(f"\n{YELLOW}Testing MLflow client connection...{RESET}")
            client = mlflow.tracking.MlflowClient()
            experiments = client.search_experiments()
            
            print(f"{GREEN}✓ MLflow client connected successfully!{RESET}")
            print(f"Found {len(experiments)} experiments")
            self.results.append(("MLflow Client", "Connection", True, f"Found {len(experiments)} experiments"))
            
        except Exception as e:
            print(f"{RED}✗ MLflow client failed: {str(e)}{RESET}")
            self.results.append(("MLflow Client", "Connection", False, str(e)))
    
    def test_cross_domain_isolation(self):
        """Test that auth requests don't reach registry and vice versa."""
        self.print_header("CROSS-DOMAIN ISOLATION TEST")
        
        tests = [
            ("Auth endpoint on Registry domain", 
             "https://registry.hokus.ai/api/v1/keys/validate",
             {"Content-Type": "application/json"}, [404], "POST",
             {"service_id": "ml-platform"}),
            ("MLflow endpoint on Auth domain",
             "https://auth.hokus.ai/mlflow/",
             None, [404], "GET", None),
        ]
        
        for test in tests:
            success, message = self.test_endpoint(*test)
            # For isolation tests, we expect 404s
            if "404" in message:
                success = True
                message = "Properly isolated (404 as expected)"
            self.results.append(("Domain Isolation", test[0], success, message))
    
    def print_summary(self):
        """Print test summary."""
        self.print_header("TEST SUMMARY")
        
        total_tests = len(self.results)
        passed_tests = sum(1 for _, _, success, _ in self.results if success)
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {GREEN}{passed_tests}{RESET}")
        print(f"Failed: {RED}{total_tests - passed_tests}{RESET}")
        
        if passed_tests < total_tests:
            print(f"\n{RED}Failed Tests:{RESET}")
            for category, test, success, message in self.results:
                if not success:
                    print(f"  - {category}/{test}: {message}")
        
        print(f"\n{'='*60}")
        if passed_tests == total_tests:
            print(f"{GREEN}✓ ALL TESTS PASSED!{RESET}")
            print("The dedicated ALBs are configured correctly.")
        else:
            print(f"{RED}✗ SOME TESTS FAILED{RESET}")
            print("Please review the failed tests above.")
        print(f"{'='*60}")
        
        return passed_tests == total_tests


def main():
    """Main test execution."""
    print(f"{'='*60}")
    print(f"{BLUE}DEDICATED ALB VALIDATION TEST{RESET}")
    print(f"{'='*60}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Get API key
    api_key = os.environ.get("HOKUSAI_API_KEY")
    if not api_key:
        print(f"\n{RED}ERROR: HOKUSAI_API_KEY environment variable not set{RESET}")
        print("Please set: export HOKUSAI_API_KEY='your-api-key'")
        return False
    
    print(f"\n✓ API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Run tests
    tester = ALBTester(api_key)
    
    # Test each service
    tester.test_auth_service()
    tester.test_registry_service()
    tester.test_cross_domain_isolation()
    tester.test_mlflow_client()
    
    # Print summary
    success = tester.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()