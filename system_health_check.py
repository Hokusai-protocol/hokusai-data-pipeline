#!/usr/bin/env python3
"""Comprehensive Hokusai System Health Check"""

import os
import sys
import requests
import json
from datetime import datetime
from typing import Dict, List, Tuple
import mlflow
import subprocess

class HokusaiHealthChecker:
    def __init__(self):
        self.api_key = os.getenv("HOKUSAI_API_KEY", "hk_live_chnn8EMMos4Lcwj3i3C3JeAkoNoDcOWL")
        self.results = []
        self.issues = []
        self.recommendations = []
        
    def check_service_health(self, name: str, url: str, headers: Dict = None) -> bool:
        """Check if a service endpoint is healthy."""
        try:
            response = requests.get(url, headers=headers, timeout=5)
            success = response.status_code == 200
            self.results.append({
                "service": name,
                "url": url,
                "status": response.status_code,
                "success": success,
                "response": response.text[:100] if not success else "OK"
            })
            return success
        except Exception as e:
            self.results.append({
                "service": name,
                "url": url,
                "status": "ERROR",
                "success": False,
                "response": str(e)
            })
            return False
    
    def check_aws_resources(self):
        """Check AWS resource status."""
        print("\n🔍 Checking AWS Resources...")
        
        # Check ECS services
        try:
            result = subprocess.run([
                "aws", "ecs", "describe-services",
                "--cluster", "hokusai-development",
                "--services", "hokusai-api-development", "hokusai-mlflow-development",
                "--region", "us-east-1",
                "--query", "services[*].[serviceName, runningCount, desiredCount, status]",
                "--output", "json"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                services = json.loads(result.stdout)
                for service in services:
                    running = service[1] == service[2] and service[3] == "ACTIVE"
                    self.results.append({
                        "service": f"ECS/{service[0]}",
                        "status": f"{service[1]}/{service[2]} tasks",
                        "success": running
                    })
                    if not running:
                        self.issues.append(f"ECS service {service[0]} not fully running")
        except Exception as e:
            self.issues.append(f"Failed to check ECS services: {e}")
    
    def test_model_registration(self):
        """Test model registration capability."""
        print("\n🤖 Testing Model Registration...")
        
        # Test 1: MLflow proxy endpoint
        headers = {"Authorization": f"Bearer {self.api_key}"}
        proxy_works = self.check_service_health(
            "MLflow Proxy",
            "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search",
            headers
        )
        
        # Test 2: Direct MLflow endpoint
        direct_works = self.check_service_health(
            "MLflow Direct",
            "https://registry.hokus.ai/mlflow/api/2.0/mlflow/experiments/search",
            None
        )
        
        if not proxy_works and not direct_works:
            self.issues.append("Neither MLflow proxy nor direct access is working")
            self.recommendations.append("Check MLflow service deployment and ALB routing")
    
    def analyze_results(self):
        """Analyze all results and generate recommendations."""
        print("\n📊 Analyzing Results...")
        
        # Check for critical issues
        critical_services = ["Auth Service", "MLflow"]
        for result in self.results:
            if not result.get("success", False):
                if any(cs in result.get("service", "") for cs in critical_services):
                    self.issues.append(f"Critical service {result['service']} is down")
        
        # Generate recommendations based on issues
        if any("Redis" in str(issue) for issue in self.issues):
            self.recommendations.append("Fix Redis connectivity - check ElastiCache endpoint and auth token")
        
        if any("MLflow" in str(issue) for issue in self.issues):
            self.recommendations.append("MLflow service issues detected - check ECS task logs and database connectivity")
        
        if any("API" in str(issue) for issue in self.issues):
            self.recommendations.append("API service issues - check health endpoint and dependencies")
    
    def run_full_check(self):
        """Run complete health check."""
        print("=" * 70)
        print("HOKUSAI SYSTEM HEALTH CHECK")
        print("=" * 70)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"API Key: {self.api_key[:10]}...{self.api_key[-4:]}")
        
        # Check public endpoints
        print("\n🌐 Checking Public Endpoints...")
        self.check_service_health("Auth Service", "https://auth.hokus.ai/health")
        self.check_service_health("API Service", "https://api.hokus.ai/health")
        self.check_service_health("Registry", "https://registry.hokus.ai/health")
        
        # Check AWS resources
        self.check_aws_resources()
        
        # Test model registration
        self.test_model_registration()
        
        # Analyze results
        self.analyze_results()
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate final health report."""
        print("\n" + "=" * 70)
        print("HEALTH CHECK SUMMARY")
        print("=" * 70)
        
        # Service status
        print("\n📋 Service Status:")
        for result in self.results:
            status_icon = "✅" if result.get("success") else "❌"
            print(f"  {status_icon} {result.get('service', 'Unknown')}: {result.get('status', 'N/A')}")
        
        # Issues found
        if self.issues:
            print("\n⚠️  Issues Found:")
            for issue in self.issues:
                print(f"  • {issue}")
        else:
            print("\n✅ No critical issues found!")
        
        # Recommendations
        if self.recommendations:
            print("\n💡 Recommendations:")
            for i, rec in enumerate(self.recommendations, 1):
                print(f"  {i}. {rec}")
        
        # Overall health score
        total_checks = len(self.results)
        successful_checks = sum(1 for r in self.results if r.get("success", False))
        health_score = (successful_checks / total_checks * 100) if total_checks > 0 else 0
        
        print(f"\n📊 Overall Health Score: {health_score:.1f}% ({successful_checks}/{total_checks} checks passed)")
        
        # Critical assessment
        print("\n🎯 Critical Assessment:")
        if health_score >= 80:
            print("  System is mostly healthy but has some issues")
        elif health_score >= 50:
            print("  System has significant issues that need attention")
        else:
            print("  System has critical failures - immediate action required")
        
        # Specific recommendations for model registration
        print("\n🤖 Model Registration Capability:")
        mlflow_working = any(r.get("service") in ["MLflow Proxy", "MLflow Direct"] 
                            and r.get("success") for r in self.results)
        
        if mlflow_working:
            print("  ✅ Model registration is possible")
            print("  Use the following configuration:")
            proxy_works = any(r.get("service") == "MLflow Proxy" and r.get("success") for r in self.results)
            if proxy_works:
                print("    - Tracking URI: https://registry.hokus.ai/api/mlflow")
                print("    - Authentication: Bearer token (API key)")
            else:
                print("    - Tracking URI: https://registry.hokus.ai/mlflow")
                print("    - Authentication: May work without auth for reads")
        else:
            print("  ❌ Model registration is NOT currently possible")
            print("  Critical fixes needed:")
            print("    1. Deploy MLflow service to ECS")
            print("    2. Configure ALB routing for registry.hokus.ai")
            print("    3. Fix database connectivity")
            print("    4. Implement authentication proxy")
        
        print("\n" + "=" * 70)

if __name__ == "__main__":
    checker = HokusaiHealthChecker()
    checker.run_full_check()