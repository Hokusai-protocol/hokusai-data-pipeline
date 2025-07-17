#!/usr/bin/env python3
"""
Test Authenticated Model Registration

This script verifies that third-party users with a valid Hokusai API key
can successfully register models. This is the primary use case that must work.
"""

import os
import sys
import logging
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import make_classification

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("=" * 80)
print("Authenticated Model Registration Test")
print("=" * 80)
print()

# Simulate a third-party developer with API key
TEST_API_KEY = "test-hokusai-api-key-12345"

def create_test_model():
    """Create a simple test model."""
    X, y = make_classification(n_samples=100, n_features=20, n_informative=15, random_state=42)
    model = LogisticRegression(random_state=42)
    model.fit(X, y)
    return model, X, y

def test_authenticated_registration():
    """Test model registration with Hokusai API key authentication."""
    
    print("Test Configuration:")
    print(f"  HOKUSAI_API_KEY: {TEST_API_KEY}")
    print(f"  MLFLOW_TRACKING_URI: {os.environ.get('MLFLOW_TRACKING_URI', 'Not set (will use SDK default)')}")
    print()
    
    # Set up environment as a third-party would
    os.environ["HOKUSAI_API_KEY"] = TEST_API_KEY
    
    # Import SDK after setting environment
    try:
        from hokusai import setup
        from hokusai.core import ModelRegistry
        from hokusai.core.models import ClassificationModel
        from hokusai.config import get_mlflow_status
    except ImportError as e:
        print(f"ERROR: Failed to import Hokusai SDK: {e}")
        print("Please ensure hokusai-ml-platform is installed")
        return False
    
    # Step 1: Initialize Hokusai
    print("Step 1: Initializing Hokusai SDK...")
    try:
        setup(api_key=TEST_API_KEY)
        print("  ✓ SDK initialized with API key")
    except Exception as e:
        print(f"  ✗ Failed to initialize SDK: {e}")
        return False
    
    # Step 2: Create test model
    print("\nStep 2: Creating test model...")
    sklearn_model, X, y = create_test_model()
    accuracy = sklearn_model.score(X, y)
    print(f"  ✓ Model created with accuracy: {accuracy:.4f}")
    
    # Step 3: Create Hokusai model
    print("\nStep 3: Creating Hokusai model...")
    try:
        # Use the ClassificationModel provided by the SDK
        hokusai_model = ClassificationModel(
            model_id="AUTHENTICATED_TEST",
            version="v1.0.0",
            n_classes=2,
            metadata={
                "description": "Authenticated third-party test model",
                "author": "external_developer",
                "framework": "sklearn",
                "api_key_used": True,
                "original_model": "LogisticRegression"
            },
            metrics={
                "accuracy": accuracy,
                "test_samples": len(y)
            }
        )
        # Store the sklearn model as an attribute
        hokusai_model.sklearn_model = sklearn_model
        print("  ✓ Model created successfully")
    except Exception as e:
        print(f"  ✗ Failed to create model: {e}")
        return False
    
    # Step 4: Initialize ModelRegistry
    print("\nStep 4: Initializing ModelRegistry...")
    try:
        registry = ModelRegistry()
        print("  ✓ Registry initialized")
        
        # Check MLflow configuration status
        try:
            mlflow_status = get_mlflow_status()
            print(f"  MLflow configuration: {mlflow_status}")
        except Exception as e:
            print(f"  Warning: Could not get MLflow status: {e}")
            
    except Exception as e:
        print(f"  ✗ Failed to initialize registry: {e}")
        return False
    
    # Step 5: Register model
    print("\nStep 5: Registering model with authentication...")
    try:
        result = registry.register_baseline(
            model=hokusai_model,
            model_type="sklearn",
            metadata={
                "test_type": "authenticated_registration",
                "api_key_provided": True
            }
        )
        
        print(f"  ✓ SUCCESS! Model registered")
        print(f"    - Model ID: {result.model_id}")
        print(f"    - Version: {result.version}")
        print(f"    - MLflow Version: {result.mlflow_version}")
        print(f"    - Timestamp: {result.timestamp}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Registration failed: {type(e).__name__}: {e}")
        
        # Provide diagnostic information
        print("\nDiagnostic Information:")
        print(f"  - Error Type: {type(e).__name__}")
        print(f"  - Error Message: {str(e)}")
        
        # Check environment variables
        print("\nEnvironment Variables:")
        for var in ["HOKUSAI_API_KEY", "MLFLOW_TRACKING_URI", "MLFLOW_TRACKING_TOKEN"]:
            print(f"  - {var}: {os.environ.get(var, 'Not set')}")
        
        # If it's a 403 error, provide specific guidance
        if "403" in str(e):
            print("\nAuthentication Error Detected!")
            print("The MLflow server is rejecting the authentication token.")
            print("\nPossible causes:")
            print("1. The Hokusai API key is not valid for MLflow authentication")
            print("2. MLflow server requires a different authentication method")
            print("3. The MLflow tracking URI is incorrect")
            
        return False

# Run the test
print("\nRunning authenticated registration test...\n")
success = test_authenticated_registration()

# Summary and recommendations
print("\n" + "=" * 80)
print("Test Result:", "PASSED ✓" if success else "FAILED ✗")
print("=" * 80)

if not success:
    print("\nRecommendations:")
    print("1. Verify that the Hokusai API key is valid")
    print("2. Check if MLflow server accepts Hokusai API keys as tokens")
    print("3. Ensure MLflow server is accessible at the configured URI")
    print("4. Contact Hokusai support if authentication continues to fail")
else:
    print("\nAuthentication is working correctly!")
    print("Third-party developers can register models using their Hokusai API key.")