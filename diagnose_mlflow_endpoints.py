#!/usr/bin/env python3
"""Diagnose the actual MLFlow endpoints and connection issues."""

import os
import requests
import socket
import json
from urllib.parse import urlparse

def test_dns_resolution(hostname):
    """Test if hostname can be resolved."""
    print(f"\nTesting DNS resolution for: {hostname}")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"✓ Resolved to: {ip}")
        return True
    except socket.gaierror as e:
        print(f"✗ DNS resolution failed: {e}")
        return False

def test_endpoint(url, headers=None, description=""):
    """Test a specific endpoint."""
    print(f"\nTesting: {description or url}")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"  Status: {response.status_code}")
        if response.status_code == 403:
            print(f"  Response: {response.text[:200]}")
        return response
    except requests.exceptions.ConnectionError as e:
        print(f"  ✗ Connection Error: {e}")
    except requests.exceptions.Timeout:
        print(f"  ✗ Timeout after 10 seconds")
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {e}")
    return None

def main():
    print("MLFlow Endpoint Diagnosis")
    print("=" * 60)
    
    # Check environment
    api_key = os.environ.get("HOKUSAI_API_KEY", "")
    print(f"HOKUSAI_API_KEY: {'SET' if api_key else 'NOT SET'}")
    
    # Test different possible MLFlow endpoints
    endpoints_to_test = [
        # Hokusai API endpoints
        ("https://api.hokus.ai/health", "Hokusai API Health"),
        ("https://api.hokus.ai/api/v1/models", "Hokusai Models API"),
        ("https://api.hokus.ai/mlflow", "Hokusai MLFlow Proxy"),
        ("https://api.hokus.ai/mlflow/api/2.0/mlflow/experiments/search", "MLFlow via Hokusai Proxy"),
        
        # Direct MLFlow endpoints (if accessible)
        ("https://registry.hokus.ai/mlflow", "Direct MLFlow Registry"),
        ("http://mlflow-server:5000", "Internal MLFlow (Docker)"),
        ("http://localhost:5000", "Local MLFlow"),
    ]
    
    # Test DNS resolution first
    print("\n" + "-" * 60)
    print("DNS Resolution Tests")
    print("-" * 60)
    
    hostnames = ["api.hokus.ai", "registry.hokus.ai", "mlflow-server"]
    for hostname in hostnames:
        test_dns_resolution(hostname)
    
    # Test endpoints
    print("\n" + "-" * 60)
    print("Endpoint Connectivity Tests")
    print("-" * 60)
    
    headers = {}
    if api_key:
        headers = {"Authorization": f"Bearer {api_key}"}
    
    for url, description in endpoints_to_test:
        # Test without auth first
        response = test_endpoint(url, description=f"{description} (No Auth)")
        
        # If we got 401/403, try with auth
        if response and response.status_code in [401, 403] and api_key:
            test_endpoint(url, headers=headers, description=f"{description} (With Auth)")
    
    # Check what the SDK is actually trying to use
    print("\n" + "-" * 60)
    print("SDK Configuration Analysis")
    print("-" * 60)
    
    try:
        from hokusai.auth import AuthConfig
        config = AuthConfig(api_key=api_key)
        print(f"Default API Endpoint: {config.api_endpoint}")
        print(f"MLFlow URI would be: {config.api_endpoint}/mlflow")
    except Exception as e:
        print(f"Could not load AuthConfig: {e}")
    
    # Check MLFlow configuration
    print("\n" + "-" * 60)
    print("MLFlow Configuration")
    print("-" * 60)
    
    mlflow_env_vars = [
        "MLFLOW_TRACKING_URI",
        "MLFLOW_TRACKING_TOKEN", 
        "MLFLOW_TRACKING_USERNAME",
        "MLFLOW_TRACKING_PASSWORD"
    ]
    
    for var in mlflow_env_vars:
        value = os.environ.get(var)
        if value:
            if "TOKEN" in var or "PASSWORD" in var:
                print(f"{var}: {'SET' if value else 'NOT SET'}")
            else:
                print(f"{var}: {value}")
        else:
            print(f"{var}: NOT SET")
    
    print("\n" + "=" * 60)
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()