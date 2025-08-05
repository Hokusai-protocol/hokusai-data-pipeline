#!/usr/bin/env python3
"""Test Hokusai services directly through their specific ALBs."""

import requests
import json
import sys

# Direct service endpoints - using service-specific ALBs
SERVICES = {
    "API": {
        "alb_url": "http://hokusai-dp-development-465790699.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/health", "GET"),
            ("/api/health", "GET"),
            ("/api/v1/health", "GET"),
        ]
    },
    "MLflow": {
        "alb_url": "http://internal-hokusai-mlflow-int-development-601484920.us-east-1.elb.amazonaws.com",
        "endpoints": [
            ("/health", "GET"),
            ("/api/2.0/mlflow/experiments/search", "GET"),
        ]
    }
}

def test_endpoint(url, method="GET"):
    """Test a single endpoint."""
    try:
        response = requests.request(method, url, timeout=10, allow_redirects=False)
        return response.status_code, response.text[:200]
    except Exception as e:
        return 0, str(e)

def main():
    print("🔍 Testing Hokusai Services Directly\n")
    
    for service_name, config in SERVICES.items():
        print(f"\n{'='*60}")
        print(f"Testing {service_name} Service")
        print(f"ALB URL: {config['alb_url']}")
        print(f"{'='*60}\n")
        
        for endpoint, method in config['endpoints']:
            url = f"{config['alb_url']}{endpoint}"
            status_code, response = test_endpoint(url, method)
            
            status_emoji = "✅" if 200 <= status_code < 300 else "❌"
            print(f"{status_emoji} {method} {endpoint} [{status_code}]")
            print(f"   Response: {response}")
            print()

if __name__ == "__main__":
    main()