#!/usr/bin/env python3
"""Test script to validate API connectivity fixes for MLflow integration."""

import os
import sys
import json
import requests
from typing import Optional, Dict, Any
import time
from datetime import datetime

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{text:^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def print_success(text: str):
    """Print success message."""
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text: str):
    """Print error message."""
    print(f"{RED}❌ {text}{RESET}")

def print_warning(text: str):
    """Print warning message."""
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_info(text: str):
    """Print info message."""
    print(f"{BLUE}ℹ️  {text}{RESET}")

class APIConnectivityTester:
    """Test API connectivity and MLflow integration."""
    
    def __init__(self, api_key: str, base_url: str = "https://registry.hokus.ai"):
        """Initialize the tester.
        
        Args:
            api_key: Hokusai API key for authentication
            base_url: Base URL of the API
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0
        }
    
    def test_health_check(self) -> bool:
        """Test the API health endpoint."""
        print_header("Testing API Health Check")
        self.test_results["total"] += 1
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            
            if response.status_code == 200:
                print_success(f"API health check successful (200 OK)")
                self.test_results["passed"] += 1
                return True
            elif response.status_code == 503:
                print_warning(f"API health check returned 503 - service may be starting up")
                self.test_results["warnings"] += 1
                return False
            else:
                print_error(f"API health check failed: {response.status_code}")
                print_info(f"Response: {response.text}")
                self.test_results["failed"] += 1
                return False
                
        except Exception as e:
            print_error(f"Failed to connect to API: {e}")
            self.test_results["failed"] += 1
            return False
    
    def test_authentication(self) -> bool:
        """Test API key authentication."""
        print_header("Testing Authentication")
        self.test_results["total"] += 1
        
        try:
            # Test with the MLflow experiments endpoint through proxy
            response = requests.get(
                f"{self.base_url}/api/mlflow/api/2.0/mlflow/experiments/search",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                print_success(f"Authentication successful with API key")
                data = response.json()
                if "experiments" in data:
                    print_info(f"Found {len(data['experiments'])} experiments")
                self.test_results["passed"] += 1
                return True
            elif response.status_code == 401:
                print_error(f"Authentication failed - invalid API key")
                self.test_results["failed"] += 1
                return False
            elif response.status_code == 404:
                print_error(f"MLflow proxy endpoint not found (404)")
                print_info("ALB routing may not be configured correctly")
                self.test_results["failed"] += 1
                return False
            elif response.status_code == 502:
                print_error(f"Bad Gateway (502) - API cannot reach MLflow internally")
                print_info("Check service discovery configuration")
                self.test_results["failed"] += 1
                return False
            else:
                print_error(f"Authentication test failed: {response.status_code}")
                print_info(f"Response: {response.text}")
                self.test_results["failed"] += 1
                return False
                
        except Exception as e:
            print_error(f"Authentication test failed: {e}")
            self.test_results["failed"] += 1
            return False
    
    def test_mlflow_connectivity(self) -> bool:
        """Test MLflow service connectivity through the proxy."""
        print_header("Testing MLflow Connectivity")
        self.test_results["total"] += 1
        
        endpoints = [
            ("/api/mlflow/api/2.0/mlflow/experiments/search", "Experiments API"),
            ("/api/mlflow/api/2.0/mlflow/registered-models/search", "Model Registry API"),
            ("/api/mlflow/api/2.0/mlflow-artifacts/artifacts", "Artifacts API")
        ]
        
        all_passed = True
        
        for endpoint, name in endpoints:
            try:
                response = requests.get(
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    print_success(f"{name}: Connected successfully")
                elif response.status_code == 404:
                    print_warning(f"{name}: Endpoint not found (404)")
                    all_passed = False
                elif response.status_code == 502:
                    print_error(f"{name}: Bad Gateway (502) - internal connection failed")
                    all_passed = False
                elif response.status_code == 401:
                    print_error(f"{name}: Authentication failed")
                    all_passed = False
                else:
                    print_warning(f"{name}: Returned {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                print_error(f"{name}: Connection failed - {e}")
                all_passed = False
        
        if all_passed:
            self.test_results["passed"] += 1
        else:
            self.test_results["failed"] += 1
        
        return all_passed
    
    def test_create_experiment(self) -> Optional[str]:
        """Test creating an MLflow experiment."""
        print_header("Testing Experiment Creation")
        self.test_results["total"] += 1
        
        experiment_name = f"connectivity-test-{int(time.time())}"
        
        try:
            response = requests.post(
                f"{self.base_url}/api/mlflow/api/2.0/mlflow/experiments/create",
                headers=self.headers,
                json={"name": experiment_name},
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                experiment_id = data.get("experiment_id")
                print_success(f"Created experiment: {experiment_name} (ID: {experiment_id})")
                self.test_results["passed"] += 1
                return experiment_id
            elif response.status_code == 502:
                print_error(f"Failed to create experiment - Bad Gateway (502)")
                print_info("API cannot communicate with MLflow service internally")
                self.test_results["failed"] += 1
                return None
            else:
                print_error(f"Failed to create experiment: {response.status_code}")
                print_info(f"Response: {response.text}")
                self.test_results["failed"] += 1
                return None
                
        except Exception as e:
            print_error(f"Experiment creation failed: {e}")
            self.test_results["failed"] += 1
            return None
    
    def test_model_registration(self) -> bool:
        """Test model registration workflow."""
        print_header("Testing Model Registration")
        self.test_results["total"] += 1
        
        model_name = f"test-model-{int(time.time())}"
        
        try:
            # Create a registered model
            response = requests.post(
                f"{self.base_url}/api/mlflow/api/2.0/mlflow/registered-models/create",
                headers=self.headers,
                json={"name": model_name, "description": "Connectivity test model"},
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                print_success(f"Model registered successfully: {model_name}")
                self.test_results["passed"] += 1
                return True
            elif response.status_code == 502:
                print_error(f"Model registration failed - Bad Gateway (502)")
                print_info("This confirms the internal connectivity issue")
                self.test_results["failed"] += 1
                return False
            else:
                print_error(f"Model registration failed: {response.status_code}")
                print_info(f"Response: {response.text}")
                self.test_results["failed"] += 1
                return False
                
        except Exception as e:
            print_error(f"Model registration failed: {e}")
            self.test_results["failed"] += 1
            return False
    
    def run_all_tests(self):
        """Run all connectivity tests."""
        print_header("API CONNECTIVITY TEST SUITE")
        print_info(f"Testing against: {self.base_url}")
        print_info(f"API Key: {self.api_key[:20]}...{self.api_key[-4:]}")
        print_info(f"Timestamp: {datetime.now().isoformat()}")
        
        # Run tests in sequence
        health_ok = self.test_health_check()
        auth_ok = self.test_authentication()
        
        if auth_ok:
            mlflow_ok = self.test_mlflow_connectivity()
            experiment_id = self.test_create_experiment()
            model_ok = self.test_model_registration()
        else:
            print_warning("Skipping remaining tests due to authentication failure")
        
        # Print summary
        print_header("TEST SUMMARY")
        
        success_rate = (self.test_results["passed"] / self.test_results["total"] * 100) if self.test_results["total"] > 0 else 0
        
        print(f"Total Tests: {self.test_results['total']}")
        print(f"{GREEN}Passed: {self.test_results['passed']}{RESET}")
        print(f"{RED}Failed: {self.test_results['failed']}{RESET}")
        print(f"{YELLOW}Warnings: {self.test_results['warnings']}{RESET}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.test_results["failed"] == 0:
            print_success("\n🎉 All connectivity issues have been resolved!")
            return 0
        else:
            print_error(f"\n💔 {self.test_results['failed']} connectivity issues remain")
            
            # Provide specific recommendations
            print_header("RECOMMENDATIONS")
            
            if not auth_ok:
                print_info("1. Fix authentication middleware - ensure service_id is 'platform'")
                print_info("2. Verify auth service is running and accessible")
            
            if self.test_results["failed"] > 0:
                print_info("1. Apply terraform changes for service discovery")
                print_info("2. Update ECS services with service_registries blocks")
                print_info("3. Ensure security groups allow inter-service communication")
                print_info("4. Verify MLflow service is running and healthy")
            
            return 1


if __name__ == "__main__":
    # Get API key from environment or command line
    api_key = os.getenv("HOKUSAI_API_KEY")
    
    if not api_key:
        if len(sys.argv) > 1:
            api_key = sys.argv[1]
        else:
            print_error("Please provide API key via HOKUSAI_API_KEY env var or as argument")
            sys.exit(1)
    
    # Use the platform API key mentioned in the issue
    # api_key = "hk_live_NVWOYDfNfTJyFzUDkQDBk2LLA4pB5qza"
    
    tester = APIConnectivityTester(api_key)
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)