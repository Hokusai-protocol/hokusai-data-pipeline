#!/usr/bin/env python3
"""Test script to verify MLflow connectivity and configuration."""

import os
import sys
import requests
import mlflow
from datetime import datetime


def test_direct_api_access():
    """Test direct API access to MLflow server."""
    print("\n1. Testing direct API access to MLflow server...")
    
    mlflow_url = os.getenv("MLFLOW_TRACKING_URI", "http://registry.hokus.ai/mlflow")
    
    # Test health endpoint
    try:
        response = requests.get(f"{mlflow_url}/health/mlflow", timeout=5)
        if response.status_code == 200:
            print(f"   ✓ MLflow health check passed: {response.json()}")
        else:
            print(f"   ✗ MLflow health check failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Failed to connect to MLflow server: {e}")
        return False
    
    # Test API endpoint (list experiments)
    try:
        response = requests.get(f"{mlflow_url}/api/2.0/mlflow/experiments/list", timeout=5)
        if response.status_code == 200:
            experiments = response.json().get("experiments", [])
            print(f"   ✓ MLflow API accessible, found {len(experiments)} experiments")
        else:
            print(f"   ✗ MLflow API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Failed to access MLflow API: {e}")
        return False
    
    return True


def test_mlflow_client_connection():
    """Test MLflow Python client connection."""
    print("\n2. Testing MLflow Python client connection...")
    
    mlflow_url = os.getenv("MLFLOW_TRACKING_URI", "http://registry.hokus.ai/mlflow")
    mlflow.set_tracking_uri(mlflow_url)
    
    try:
        # List experiments
        experiments = mlflow.search_experiments()
        print(f"   ✓ MLflow client connected, found {len(experiments)} experiments")
        
        # Try to get or create an experiment
        experiment_name = "test_connection_experiment"
        experiment = mlflow.get_experiment_by_name(experiment_name)
        
        if experiment is None:
            experiment_id = mlflow.create_experiment(experiment_name)
            print(f"   ✓ Created test experiment with ID: {experiment_id}")
        else:
            print(f"   ✓ Found existing test experiment with ID: {experiment.experiment_id}")
        
        return True
        
    except Exception as e:
        print(f"   ✗ MLflow client error: {e}")
        return False


def test_hokusai_sdk_integration():
    """Test Hokusai SDK integration with MLflow."""
    print("\n3. Testing Hokusai SDK integration...")
    
    try:
        # Add the SDK to Python path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hokusai-ml-platform", "src"))
        
        from hokusai.tracking import ExperimentManager
        
        # Test default configuration
        print("   Testing with default configuration...")
        try:
            manager = ExperimentManager()
            print(f"   ✓ ExperimentManager initialized with tracking URI: {manager.tracking_uri}")
        except Exception as e:
            print(f"   ✗ Failed to initialize ExperimentManager: {e}")
            
        # Test mock mode
        print("   Testing mock mode...")
        os.environ["HOKUSAI_MOCK_MODE"] = "true"
        try:
            mock_manager = ExperimentManager()
            print(f"   ✓ Mock mode enabled successfully")
        except Exception as e:
            print(f"   ✗ Failed to initialize in mock mode: {e}")
        finally:
            os.environ.pop("HOKUSAI_MOCK_MODE", None)
        
        return True
        
    except ImportError as e:
        print(f"   ✗ Failed to import Hokusai SDK: {e}")
        print("     Make sure hokusai-ml-platform is installed")
        return False
    except Exception as e:
        print(f"   ✗ Unexpected error: {e}")
        return False


def test_authentication_bypass():
    """Test that MLflow endpoints bypass authentication."""
    print("\n4. Testing authentication bypass for MLflow endpoints...")
    
    base_url = "http://registry.hokus.ai"
    
    # Test MLflow endpoint without auth headers
    try:
        response = requests.get(f"{base_url}/mlflow/api/2.0/mlflow/experiments/list", timeout=5)
        if response.status_code == 200:
            print(f"   ✓ MLflow endpoints accessible without authentication")
        elif response.status_code == 403:
            print(f"   ✗ MLflow endpoints still require authentication (403 Forbidden)")
            return False
        else:
            print(f"   ? MLflow endpoint returned status {response.status_code}")
    except Exception as e:
        print(f"   ✗ Failed to test authentication bypass: {e}")
        return False
    
    # Test that other endpoints still require auth
    try:
        response = requests.get(f"{base_url}/api/v1/models", timeout=5)
        if response.status_code == 401:
            print(f"   ✓ Other API endpoints still require authentication")
        else:
            print(f"   ? Non-MLflow endpoint returned unexpected status {response.status_code}")
    except Exception as e:
        print(f"   ! Could not verify other endpoint authentication: {e}")
    
    return True


def main():
    """Run all connectivity tests."""
    print("=" * 60)
    print("MLflow Connectivity Test Suite")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Check environment
    mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://registry.hokus.ai/mlflow")
    mock_mode = os.getenv("HOKUSAI_MOCK_MODE", "false")
    
    print(f"\nEnvironment:")
    print(f"  MLFLOW_TRACKING_URI: {mlflow_uri}")
    print(f"  HOKUSAI_MOCK_MODE: {mock_mode}")
    
    # Run tests
    tests = [
        ("Direct API Access", test_direct_api_access),
        ("MLflow Client Connection", test_mlflow_client_connection),
        ("Hokusai SDK Integration", test_hokusai_sdk_integration),
        ("Authentication Bypass", test_authentication_bypass),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' failed with unexpected error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"  {test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! MLflow connectivity is working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())