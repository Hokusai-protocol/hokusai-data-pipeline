#!/usr/bin/env python3
"""
Comprehensive test script for PR #60 enhancements.
Tests model registration and all new features after implementation.
"""

import os
import sys
import requests
import json
from datetime import datetime
import time

class PR60EnhancementTester:
    """Test all PR #60 enhancements."""
    
    def __init__(self, api_url, api_key):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.test_results = []
    
    def log_result(self, test_name, success, message, details=None):
        """Log test result."""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        if details:
            result["details"] = details
        
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {message}")
        if details and not success:
            print(f"   Details: {json.dumps(details, indent=2)}")
    
    def test_health_endpoints(self):
        """Test new health check endpoints at /api/health/mlflow."""
        print("\n📋 Testing Health Check Endpoints")
        print("-" * 40)
        
        endpoints = [
            ("/api/health/mlflow", "Basic health check"),
            ("/api/health/mlflow/connectivity", "Connectivity check"),
            ("/api/health/mlflow/detailed", "Detailed health check")
        ]
        
        all_passed = True
        
        for endpoint, description in endpoints:
            try:
                response = requests.get(
                    f"{self.api_url}{endpoint}",
                    headers=self.headers,
                    timeout=10
                )
                
                # Accept both 200 (healthy) and 503 (unhealthy but endpoint exists)
                if response.status_code in [200, 503]:
                    self.log_result(
                        f"Health: {description}",
                        True,
                        f"Endpoint accessible (status: {response.status_code})"
                    )
                else:
                    self.log_result(
                        f"Health: {description}",
                        False,
                        f"Unexpected status: {response.status_code}",
                        {"response": response.text}
                    )
                    all_passed = False
                    
            except Exception as e:
                self.log_result(
                    f"Health: {description}",
                    False,
                    f"Error: {str(e)}"
                )
                all_passed = False
        
        return all_passed
    
    def test_mlflow_proxy_endpoints(self):
        """Test MLflow proxy endpoints."""
        print("\n🔌 Testing MLflow Proxy Endpoints")
        print("-" * 40)
        
        # Test experiments search
        try:
            response = requests.get(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/experiments/search",
                headers=self.headers,
                params={"max_results": 1},
                timeout=10
            )
            
            if response.status_code == 200:
                experiments = response.json().get("experiments", [])
                self.log_result(
                    "MLflow Proxy: Experiments API",
                    True,
                    f"Found {len(experiments)} experiment(s)"
                )
                return True
            else:
                self.log_result(
                    "MLflow Proxy: Experiments API",
                    False,
                    f"Status {response.status_code}",
                    {"response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_result(
                "MLflow Proxy: Experiments API",
                False,
                f"Error: {str(e)}"
            )
            return False
    
    def test_model_registration(self):
        """Test complete model registration flow."""
        print("\n🚀 Testing Model Registration")
        print("-" * 40)
        
        try:
            # Step 1: Create experiment
            experiment_name = f"pr60-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/experiments/create",
                headers=self.headers,
                json={"name": experiment_name}
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Registration: Create experiment",
                    False,
                    f"Failed with status {response.status_code}",
                    {"response": response.text}
                )
                return False
            
            exp_id = response.json()["experiment_id"]
            self.log_result(
                "Registration: Create experiment",
                True,
                f"Created {experiment_name} (ID: {exp_id})"
            )
            
            # Step 2: Create run
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/runs/create",
                headers=self.headers,
                json={"experiment_id": exp_id}
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Registration: Create run",
                    False,
                    f"Failed with status {response.status_code}"
                )
                return False
            
            run_id = response.json()["run"]["info"]["run_id"]
            self.log_result(
                "Registration: Create run",
                True,
                f"Created run {run_id}"
            )
            
            # Step 3: Log metrics
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/runs/log-metric",
                headers=self.headers,
                json={
                    "run_id": run_id,
                    "key": "test_accuracy",
                    "value": 0.95,
                    "timestamp": int(time.time() * 1000)
                }
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Registration: Log metrics",
                    False,
                    f"Failed with status {response.status_code}"
                )
                return False
            
            self.log_result(
                "Registration: Log metrics",
                True,
                "Logged test_accuracy=0.95"
            )
            
            # Step 4: Register model
            model_name = f"pr60-model-{int(time.time())}"
            
            response = requests.post(
                f"{self.api_url}/api/mlflow/api/2.0/mlflow/registered-models/create",
                headers=self.headers,
                json={"name": model_name}
            )
            
            if response.status_code != 200:
                self.log_result(
                    "Registration: Register model",
                    False,
                    f"Failed with status {response.status_code}",
                    {"response": response.text}
                )
                return False
            
            self.log_result(
                "Registration: Register model",
                True,
                f"Registered model {model_name}"
            )
            
            return True
            
        except Exception as e:
            self.log_result(
                "Registration: Error",
                False,
                f"Exception: {str(e)}"
            )
            return False
    
    def test_direct_mlflow_access(self):
        """Test direct MLflow access (expected to fail currently)."""
        print("\n🔗 Testing Direct MLflow Access")
        print("-" * 40)
        
        try:
            response = requests.get(
                f"{self.api_url}/mlflow",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.log_result(
                    "Direct MLflow: Root path",
                    True,
                    "Direct MLflow access working!"
                )
                return True
            else:
                self.log_result(
                    "Direct MLflow: Root path",
                    False,
                    f"Status {response.status_code} (expected until ALB fix deployed)",
                    {"note": "This is a known limitation"}
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Direct MLflow: Root path",
                False,
                f"Error: {str(e)}"
            )
            return False
    
    def run_all_tests(self):
        """Run all PR #60 enhancement tests."""
        print(f"\n🧪 PR #60 Enhancement Tests")
        print(f"Time: {datetime.now()}")
        print(f"API: {self.api_url}")
        print(f"API Key: {self.api_key[:10]}...{self.api_key[-4:]}")
        print("=" * 60)
        
        # Run tests
        health_ok = self.test_health_endpoints()
        proxy_ok = self.test_mlflow_proxy_endpoints()
        registration_ok = self.test_model_registration()
        direct_ok = self.test_direct_mlflow_access()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Test Summary")
        print("-" * 40)
        
        passed = sum(1 for r in self.test_results if r["success"])
        total = len(self.test_results)
        
        for result in self.test_results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']}: {result['message']}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        # Overall assessment
        critical_passed = proxy_ok and registration_ok
        
        if critical_passed:
            print("\n✅ SUCCESS: All critical features working!")
            print("   - Model registration: Working")
            print("   - MLflow proxy: Working")
            print("   - Health endpoints: " + ("Working" if health_ok else "Needs deployment"))
            print("   - Direct MLflow: " + ("Working" if direct_ok else "Needs ALB fix"))
            return True
        else:
            print("\n❌ CRITICAL FAILURE: Core features not working")
            return False


def main():
    """Main test function."""
    # Get configuration
    api_url = os.getenv("HOKUSAI_API_URL", "https://registry.hokus.ai")
    api_key = os.getenv("HOKUSAI_API_KEY")
    
    if not api_key:
        print("❌ Error: HOKUSAI_API_KEY not set")
        print("Please run: export HOKUSAI_API_KEY='your-api-key'")
        return 1
    
    # Run tests
    tester = PR60EnhancementTester(api_url, api_key)
    success = tester.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())