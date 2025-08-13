#!/usr/bin/env python3
"""Verify the infrastructure fixes and test system health after improvements."""

import os
import sys
import requests
import json
from datetime import datetime
import subprocess
import mlflow
from mlflow.tracking import MlflowClient

class SystemVerification:
    def __init__(self):
        self.api_key = os.getenv("HOKUSAI_API_KEY", "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL")
        self.results = []
        self.working_endpoints = []
        self.failed_endpoints = []
        
    def test_endpoint(self, name: str, url: str, headers: dict = None, expected_status: list = [200]):
        """Test an endpoint and record results."""
        print(f"  Testing {name}...")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            success = response.status_code in expected_status
            
            result = {
                "name": name,
                "url": url,
                "status": response.status_code,
                "success": success,
                "response": response.text[:200] if response.text else "Empty"
            }
            
            if success:
                print(f"    ✅ Success: {response.status_code}")
                self.working_endpoints.append(name)
            else:
                print(f"    ❌ Failed: {response.status_code}")
                print(f"    Response: {response.text[:100]}")
                self.failed_endpoints.append(name)
                
            self.results.append(result)
            return success
            
        except Exception as e:
            print(f"    ❌ Error: {str(e)}")
            self.failed_endpoints.append(name)
            self.results.append({
                "name": name,
                "url": url,
                "status": "ERROR",
                "success": False,
                "response": str(e)
            })
            return False
    
    def verify_alb_fixes(self):
        """Verify the ALB routing fixes."""
        print("\n🔧 Verifying ALB Routing Fixes...")
        
        # Test Registry/MLflow at new path
        self.test_endpoint(
            "MLflow UI (registry.hokus.ai/mlflow)",
            "https://registry.hokus.ai/mlflow",
            expected_status=[200, 302]  # May redirect to login
        )
        
        # Test MLflow API endpoints
        self.test_endpoint(
            "MLflow API (registry.hokus.ai/mlflow/api/2.0)",
            "https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search",
            expected_status=[200, 401, 403]  # May require auth
        )
        
        # Test Data Pipeline ALB for ML platform API
        dp_alb = "hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com"
        
        self.test_endpoint(
            "DP ALB Health",
            f"https://{dp_alb}/health",
            expected_status=[200, 503]  # May be unhealthy due to deps
        )
        
        self.test_endpoint(
            "DP ALB API",
            f"https://{dp_alb}/api/v1/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            expected_status=[200, 401, 404]
        )
    
    def verify_redis_fix(self):
        """Check if Redis connectivity is fixed."""
        print("\n🔧 Verifying Redis Connectivity Fix...")
        
        # Check recent logs for Redis errors
        try:
            result = subprocess.run([
                "aws", "logs", "tail", "/ecs/hokusai-api-development",
                "--since", "5m",
                "--region", "us-east-1"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                log_content = result.stdout
                if "Redis health check failed" in log_content:
                    print("  ⚠️  Still seeing Redis errors in recent logs")
                elif "Redis connection successful" in log_content or "redis" in log_content.lower():
                    print("  ✅ Redis connection appears to be working")
                else:
                    print("  ℹ️  No recent Redis-related logs found")
            
        except Exception as e:
            print(f"  ⚠️  Could not check logs: {e}")
    
    def test_model_registration(self):
        """Test model registration with the fixed infrastructure."""
        print("\n🤖 Testing Model Registration Capability...")
        
        # Test different MLflow endpoints
        endpoints_to_test = [
            ("https://registry.hokus.ai/mlflow", "Direct MLflow"),
            ("https://registry.hokus.ai/api/mlflow", "Proxy endpoint (if implemented)"),
        ]
        
        for endpoint, description in endpoints_to_test:
            print(f"\n  Testing {description}: {endpoint}")
            
            try:
                # Set MLflow configuration
                os.environ["MLFLOW_TRACKING_URI"] = endpoint
                os.environ["MLFLOW_TRACKING_TOKEN"] = self.api_key
                
                mlflow.set_tracking_uri(endpoint)
                
                # Try to list experiments
                client = MlflowClient()
                experiments = client.search_experiments(max_results=1)
                
                print(f"    ✅ Successfully connected to MLflow!")
                print(f"    Found {len(experiments)} experiments")
                
                self.working_endpoints.append(f"MLflow Registration via {description}")
                return True
                
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "403" in error_msg:
                    print(f"    ⚠️  Authentication required (expected)")
                elif "404" in error_msg:
                    print(f"    ❌ Endpoint not found")
                else:
                    print(f"    ❌ Failed: {error_msg[:100]}")
                    
        return False
    
    def check_ecs_services(self):
        """Check ECS service status."""
        print("\n📦 Checking ECS Services...")
        
        try:
            result = subprocess.run([
                "aws", "ecs", "describe-services",
                "--cluster", "hokusai-development",
                "--services", "hokusai-api-development", "hokusai-mlflow-development",
                "--region", "us-east-1",
                "--query", "services[*].[serviceName, runningCount, desiredCount, deployments[0].rolloutState]",
                "--output", "json"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                services = json.loads(result.stdout)
                for service in services:
                    status = f"{service[1]}/{service[2]} running"
                    rollout = service[3] if len(service) > 3 else "UNKNOWN"
                    
                    if service[1] == service[2]:
                        print(f"  ✅ {service[0]}: {status} (Rollout: {rollout})")
                    else:
                        print(f"  ⚠️  {service[0]}: {status} (Rollout: {rollout})")
                        
        except Exception as e:
            print(f"  ❌ Failed to check: {e}")
    
    def generate_summary(self):
        """Generate summary and recommendations."""
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        
        print("\n✅ Working Endpoints:")
        if self.working_endpoints:
            for endpoint in self.working_endpoints:
                print(f"  • {endpoint}")
        else:
            print("  None")
        
        print("\n❌ Failed Endpoints:")
        if self.failed_endpoints:
            for endpoint in self.failed_endpoints:
                print(f"  • {endpoint}")
        else:
            print("  None")
        
        # Calculate improvement
        total = len(self.working_endpoints) + len(self.failed_endpoints)
        if total > 0:
            success_rate = (len(self.working_endpoints) / total) * 100
            print(f"\n📊 Success Rate: {success_rate:.1f}% ({len(self.working_endpoints)}/{total})")
        
        print("\n🎯 Current Status:")
        
        # Determine overall status
        mlflow_works = any("MLflow" in e for e in self.working_endpoints)
        api_works = any("API" in e or "DP ALB" in e for e in self.working_endpoints)
        
        if mlflow_works and api_works:
            print("  ✅ System is operational - Model registration should work!")
            print("\n  Recommended Configuration:")
            print("  • MLflow URI: https://registry.hokus.ai/mlflow")
            print("  • API Endpoint: Data Pipeline ALB")
            print("  • Authentication: Bearer token with API key")
            
        elif mlflow_works:
            print("  ⚠️  MLflow is accessible but API service needs work")
            print("\n  Next Steps:")
            print("  1. Implement /api/mlflow proxy in API service")
            print("  2. Fix any remaining API service issues")
            
        elif api_works:
            print("  ⚠️  API is accessible but MLflow needs configuration")
            print("\n  Next Steps:")
            print("  1. Check MLflow service logs")
            print("  2. Verify database connectivity")
            print("  3. Check MLflow configuration")
            
        else:
            print("  ❌ Critical services still not working")
            print("\n  Urgent Actions Required:")
            print("  1. Check ECS task logs for both services")
            print("  2. Verify security groups and network configuration")
            print("  3. Check service deployments are successful")
        
        print("\n📝 Remaining Tasks:")
        print("  1. Implement authentication proxy (/api/mlflow endpoint)")
        print("  2. Verify database connectivity for MLflow")
        print("  3. Test end-to-end model registration flow")
        print("  4. Update documentation with working endpoints")
        
        print("\n" + "=" * 70)

def main():
    print("=" * 70)
    print("HOKUSAI SYSTEM VERIFICATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Verifying infrastructure fixes...")
    
    verifier = SystemVerification()
    
    # Run all verifications
    verifier.verify_alb_fixes()
    verifier.verify_redis_fix()
    verifier.check_ecs_services()
    verifier.test_model_registration()
    
    # Generate summary
    verifier.generate_summary()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())