#!/usr/bin/env python3
"""Script to test MLflow routing through the Hokusai API proxy."""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# Configuration
API_BASE_URL = os.getenv("HOKUSAI_API_URL", "http://localhost:8000")
API_KEY = os.getenv("HOKUSAI_API_KEY", "test-api-key")
MLFLOW_PROXY_DEBUG = os.getenv("MLFLOW_PROXY_DEBUG", "true")


class MLflowRoutingTester:
    """Test MLflow routing through Hokusai API."""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.test_results = []
    
    def log_result(self, test_name: str, success: bool, message: str, details: Optional[Dict] = None):
        """Log test result."""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        # Print result
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        if details and not success:
            print(f"   Details: {json.dumps(details, indent=2)}")
    
    def test_health_check(self) -> bool:
        """Test MLflow health check endpoint."""
        try:
            response = requests.get(
                f"{self.api_url}/mlflow/health/mlflow",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                all_healthy = all(
                    check.get("status") in ["healthy", "enabled", "disabled"]
                    for check in data.get("checks", {}).values()
                )
                
                self.log_result(
                    "MLflow Health Check",
                    all_healthy,
                    f"MLflow server status: {data.get('status', 'unknown')}",
                    data
                )
                return all_healthy
            else:
                self.log_result(
                    "MLflow Health Check",
                    False,
                    f"Health check failed with status {response.status_code}",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_result(
                "MLflow Health Check",
                False,
                f"Health check error: {str(e)}"
            )
            return False
    
    def test_experiment_api(self) -> bool:
        """Test experiment search API."""
        try:
            # Test via /mlflow prefix
            response1 = requests.get(
                f"{self.api_url}/mlflow/api/2.0/mlflow/experiments/search",
                headers=self.headers,
                params={"max_results": 1},
                timeout=10
            )
            
            # Test via /api/mlflow prefix
            response2 = requests.get(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/experiments/search",
                headers=self.headers,
                params={"max_results": 1},
                timeout=10
            )
            
            success = response1.status_code == 200 and response2.status_code == 200
            
            self.log_result(
                "Experiment Search API",
                success,
                f"Both routes working: /mlflow ({response1.status_code}) and /api/mlflow ({response2.status_code})",
                {
                    "/mlflow_status": response1.status_code,
                    "/api/mlflow_status": response2.status_code,
                    "response_sample": response1.json() if response1.status_code == 200 else None
                }
            )
            return success
            
        except Exception as e:
            self.log_result(
                "Experiment Search API",
                False,
                f"API test error: {str(e)}"
            )
            return False
    
    def test_model_registry_api(self) -> bool:
        """Test model registry API."""
        try:
            response = requests.get(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/registered-models/search",
                headers=self.headers,
                timeout=10
            )
            
            success = response.status_code == 200
            
            self.log_result(
                "Model Registry API",
                success,
                f"Model registry API status: {response.status_code}",
                {
                    "status_code": response.status_code,
                    "has_models": len(response.json().get("registered_models", [])) > 0 if success else None
                }
            )
            return success
            
        except Exception as e:
            self.log_result(
                "Model Registry API",
                False,
                f"Model registry error: {str(e)}"
            )
            return False
    
    def test_create_experiment(self) -> Optional[str]:
        """Test creating an experiment."""
        try:
            experiment_name = f"routing-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/experiments/create",
                headers=self.headers,
                json={"name": experiment_name},
                timeout=10
            )
            
            if response.status_code == 200:
                exp_id = response.json().get("experiment_id")
                self.log_result(
                    "Create Experiment",
                    True,
                    f"Created experiment '{experiment_name}' with ID: {exp_id}",
                    {"experiment_id": exp_id, "name": experiment_name}
                )
                return exp_id
            else:
                self.log_result(
                    "Create Experiment",
                    False,
                    f"Failed to create experiment: {response.status_code}",
                    {"status_code": response.status_code, "response": response.text}
                )
                return None
                
        except Exception as e:
            self.log_result(
                "Create Experiment",
                False,
                f"Create experiment error: {str(e)}"
            )
            return None
    
    def test_model_registration_flow(self) -> bool:
        """Test complete model registration flow."""
        try:
            # Step 1: Create experiment
            exp_id = self.test_create_experiment()
            if not exp_id:
                return False
            
            # Step 2: Create run
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/runs/create",
                headers=self.headers,
                json={"experiment_id": exp_id},
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Create Run",
                    False,
                    f"Failed to create run: {response.status_code}",
                    {"response": response.text}
                )
                return False
            
            run_id = response.json()["run"]["info"]["run_id"]
            self.log_result(
                "Create Run",
                True,
                f"Created run with ID: {run_id}"
            )
            
            # Step 3: Log metrics
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/runs/log-metric",
                headers=self.headers,
                json={
                    "run_id": run_id,
                    "key": "test_accuracy",
                    "value": 0.95,
                    "timestamp": int(datetime.now().timestamp() * 1000)
                },
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Log Metrics",
                    False,
                    f"Failed to log metrics: {response.status_code}"
                )
                return False
            
            self.log_result(
                "Log Metrics",
                True,
                "Successfully logged metrics"
            )
            
            # Step 4: Create model
            model_name = f"routing-test-model-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/registered-models/create",
                headers=self.headers,
                json={"name": model_name},
                timeout=10
            )
            
            if response.status_code == 200:
                self.log_result(
                    "Register Model",
                    True,
                    f"Successfully registered model: {model_name}"
                )
                return True
            else:
                self.log_result(
                    "Register Model",
                    False,
                    f"Failed to register model: {response.status_code}",
                    {"response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Model Registration Flow",
                False,
                f"Registration flow error: {str(e)}"
            )
            return False
    
    def test_artifact_endpoints(self) -> bool:
        """Test artifact endpoint routing."""
        try:
            # Test artifact endpoint accessibility (should return 404 for non-existent artifact)
            response = requests.get(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow-artifacts/artifacts/test-run/test-artifact",
                headers=self.headers,
                timeout=10
            )
            
            # 404 is expected for non-existent artifact, 503 if artifacts disabled
            success = response.status_code in [404, 503]
            
            self.log_result(
                "Artifact Endpoints",
                success,
                f"Artifact endpoint accessible: status {response.status_code}",
                {"status_code": response.status_code}
            )
            return success
            
        except Exception as e:
            self.log_result(
                "Artifact Endpoints",
                False,
                f"Artifact endpoint error: {str(e)}"
            )
            return False
    
    def run_all_tests(self):
        """Run all routing tests."""
        print(f"\n🧪 Testing MLflow Routing - {datetime.now()}")
        print(f"API URL: {self.api_url}")
        print(f"Debug Mode: {MLFLOW_PROXY_DEBUG}")
        print("-" * 60)
        
        # Run tests
        tests_passed = 0
        total_tests = 0
        
        # Basic connectivity tests
        if self.test_health_check():
            tests_passed += 1
        total_tests += 1
        
        if self.test_experiment_api():
            tests_passed += 1
        total_tests += 1
        
        if self.test_model_registry_api():
            tests_passed += 1
        total_tests += 1
        
        if self.test_artifact_endpoints():
            tests_passed += 1
        total_tests += 1
        
        # Full workflow test
        if self.test_model_registration_flow():
            tests_passed += 1
        total_tests += 1
        
        # Summary
        print("-" * 60)
        print(f"\n📊 Test Summary: {tests_passed}/{total_tests} tests passed")
        
        if tests_passed == total_tests:
            print("✅ All routing tests passed! MLflow proxy is working correctly.")
            return True
        else:
            print("❌ Some tests failed. Check the logs above for details.")
            failed_tests = [r for r in self.test_results if not r["success"]]
            print("\nFailed tests:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['message']}")
            return False


def main():
    """Main function."""
    # Parse command line arguments
    if len(sys.argv) > 1:
        api_url = sys.argv[1]
    else:
        api_url = API_BASE_URL
    
    if len(sys.argv) > 2:
        api_key = sys.argv[2]
    else:
        api_key = API_KEY
    
    # Run tests
    tester = MLflowRoutingTester(api_url, api_key)
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()