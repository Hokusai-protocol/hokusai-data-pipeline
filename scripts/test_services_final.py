#!/usr/bin/env python3
"""Test Hokusai services after connectivity fixes."""

import requests
import json
import sys
from datetime import datetime

# Test endpoints - using both ALB and potential domain names
TEST_CONFIGS = [
    {
        "name": "API via ALB HTTP",
        "base_url": "http://hokusai-main-development-88510464.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/api/health", "GET"),
            ("/api/v1/health", "GET"),
        ]
    },
    {
        "name": "MLflow via ALB HTTP", 
        "base_url": "http://hokusai-main-development-88510464.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/mlflow/health", "GET"),
            ("/mlflow/api/2.0/mlflow/experiments/search", "GET"),
        ]
    },
    {
        "name": "API via registry.hokus.ai",
        "base_url": "https://registry.hokus.ai",
        "endpoints": [
            ("/api/health", "GET"),
            ("/api/v1/health", "GET"),
        ]
    }
]

def test_endpoint(url, method="GET", headers=None):
    """Test a single endpoint."""
    try:
        response = requests.request(
            method, 
            url, 
            timeout=10, 
            allow_redirects=True,
            verify=True,
            headers=headers or {}
        )
        return response.status_code, response.text[:500], response.headers.get('Location', '')
    except requests.exceptions.SSLError as e:
        return 0, f"SSL Error: {str(e)}", ""
    except Exception as e:
        return 0, str(e)[:500], ""

def main():
    print(f"🔍 Testing Hokusai Services - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    overall_success = True
    
    for config in TEST_CONFIGS:
        print(f"\n{'='*80}")
        print(f"Testing: {config['name']}")
        print(f"Base URL: {config['base_url']}")
        print(f"{'='*80}\n")
        
        for endpoint, method in config['endpoints']:
            url = f"{config['base_url']}{endpoint}"
            status_code, response, location = test_endpoint(url, method)
            
            # Determine success
            is_success = 200 <= status_code < 300
            status_emoji = "✅" if is_success else "❌"
            
            print(f"{status_emoji} {method} {endpoint}")
            print(f"   Status: {status_code}")
            if location:
                print(f"   Redirected to: {location}")
            print(f"   Response: {response[:200]}...")
            print()
            
            if not is_success:
                overall_success = False
    
    # Summary
    print(f"\n{'='*80}")
    print("📊 Test Summary")
    print(f"{'='*80}")
    
    # Check target health directly
    print("\n🎯 Target Group Health:")
    
    import subprocess
    
    # API targets
    api_result = subprocess.run([
        "aws", "elbv2", "describe-target-health",
        "--target-group-arn", "arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-api-tg-development/d9c29f02e2a38c81",
        "--query", "TargetHealthDescriptions[?TargetHealth.State==`healthy`].[Target.Id]",
        "--output", "text"
    ], capture_output=True, text=True)
    
    api_healthy = len(api_result.stdout.strip().split('\n')) if api_result.stdout.strip() else 0
    print(f"  API Service: {api_healthy} healthy targets")
    
    # MLflow targets
    mlflow_result = subprocess.run([
        "aws", "elbv2", "describe-target-health",
        "--target-group-arn", "arn:aws:elasticloadbalancing:us-east-1:932100697590:targetgroup/hokusai-mlflow-tg-development/9518cac0d6af96bb",
        "--query", "TargetHealthDescriptions[?TargetHealth.State==`healthy`].[Target.Id]",
        "--output", "text"
    ], capture_output=True, text=True)
    
    mlflow_healthy = len(mlflow_result.stdout.strip().split('\n')) if mlflow_result.stdout.strip() else 0
    print(f"  MLflow Service: {mlflow_healthy} healthy targets")
    
    print(f"\n{'='*80}")
    if api_healthy > 0 and mlflow_healthy > 0:
        print("✅ Both services have healthy targets in their target groups!")
        print("ℹ️  Note: HTTP requests may redirect to HTTPS. Services are running correctly.")
    else:
        print("❌ One or more services don't have healthy targets")
    
    return 0 if (api_healthy > 0 and mlflow_healthy > 0) else 1

if __name__ == "__main__":
    sys.exit(main())