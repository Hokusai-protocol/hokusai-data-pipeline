#!/usr/bin/env python3
"""Test script to reproduce the LSCOR model registration issue.
This simulates what the third party was trying to do.
"""

import logging
import os
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add the SDK to path for testing
sdk_path = Path(__file__).parent / "hokusai-ml-platform" / "src"
sys.path.insert(0, str(sdk_path))


def test_imports():
    """Test 1: Can we import the components the user claims are missing?"""
    print("\n=== TEST 1: Import Components ===")

    try:
        from hokusai.tracking import ExperimentManager, PerformanceTracker

        print("✅ Successfully imported ExperimentManager and PerformanceTracker")
        return True
    except ImportError as e:
        print(f"❌ Failed to import tracking components: {e}")
        return False


def test_registry_initialization():
    """Test 2: Can we initialize ModelRegistry with no parameters?"""
    print("\n=== TEST 2: Registry Initialization ===")

    try:
        from hokusai.core import ModelRegistry

        # Test with no parameters (as per documentation)
        registry = ModelRegistry()
        print("✅ Successfully initialized ModelRegistry with no parameters")

        # Check if register_tokenized_model exists
        if hasattr(registry, "register_tokenized_model"):
            print("✅ register_tokenized_model method exists")
        else:
            print("❌ register_tokenized_model method NOT found")

        return True
    except Exception as e:
        print(f"❌ Failed to initialize registry: {e}")
        return False


def test_authentication_setup():
    """Test 3: Test authentication configuration"""
    print("\n=== TEST 3: Authentication Setup ===")

    # Set the environment variables as the user would
    os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
    os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"

    try:
        import mlflow
        from hokusai.config import setup_mlflow_auth

        # Check current configuration
        print(f"Tracking URI: {mlflow.get_tracking_uri()}")
        print(f"Token configured: {'MLFLOW_TRACKING_TOKEN' in os.environ}")

        # Try to setup auth
        setup_mlflow_auth()
        print("✅ Authentication setup completed")

        return True
    except Exception as e:
        print(f"❌ Authentication setup failed: {e}")
        return False


def test_mlflow_connection():
    """Test 4: Can we connect to MLflow server?"""
    print("\n=== TEST 4: MLflow Connection Test ===")

    try:
        import mlflow

        # Try to list experiments (this will test the connection)
        try:
            experiments = mlflow.search_experiments(max_results=1)
            print("✅ Successfully connected to MLflow server")
            return True
        except Exception as e:
            if "403" in str(e):
                print(f"❌ Authentication failed (403 Forbidden): {e}")
            elif "401" in str(e):
                print(f"❌ Authentication failed (401 Unauthorized): {e}")
            else:
                print(f"❌ Connection failed: {e}")
            return False

    except Exception as e:
        print(f"❌ Failed to test connection: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("LSCOR Model Registration Issue - Reproduction Test")
    print("=" * 60)

    results = {
        "imports": test_imports(),
        "registry": test_registry_initialization(),
        "auth": test_authentication_setup(),
        "connection": test_mlflow_connection(),
    }

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test.capitalize()}: {status}")

    # Diagnostic information
    print("\n" + "=" * 60)
    print("DIAGNOSTIC INFORMATION")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    print(f"SDK path exists: {sdk_path.exists()}")
    print(f"Tracking module exists: {(sdk_path / 'hokusai' / 'tracking').exists()}")
    print(f"Registry module exists: {(sdk_path / 'hokusai' / 'core' / 'registry.py').exists()}")

    # Check if __init__.py files are empty
    tracking_init = sdk_path / "hokusai" / "tracking" / "__init__.py"
    if tracking_init.exists():
        size = tracking_init.stat().st_size
        print(f"Tracking __init__.py size: {size} bytes")
        if size == 0:
            print("⚠️  WARNING: Tracking __init__.py is empty!")


if __name__ == "__main__":
    main()
