#!/usr/bin/env python3
"""Test script with the fix for LSCOR model registration issue."""

import os
import sys
from pathlib import Path

# Add the SDK to path
sdk_path = Path(__file__).parent / "hokusai-ml-platform" / "src"
sys.path.insert(0, str(sdk_path))


def test_with_hokusai_api_key():
    """Test registry initialization with HOKUSAI_API_KEY"""
    print("\n=== TEST: Registry with HOKUSAI_API_KEY ===")

    # Set BOTH environment variables
    os.environ["HOKUSAI_API_KEY"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
    os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"
    os.environ["MLFLOW_TRACKING_TOKEN"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"

    try:
        from hokusai.core import ModelRegistry

        # Initialize registry (no parameters as per docs)
        registry = ModelRegistry()
        print("✅ Successfully initialized ModelRegistry!")

        # Check methods
        if hasattr(registry, "register_tokenized_model"):
            print("✅ register_tokenized_model method exists")

            # Check signature
            import inspect

            sig = inspect.signature(registry.register_tokenized_model)
            print(f"   Method signature: {sig}")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def test_alternative_initialization():
    """Test alternative initialization with api_key parameter"""
    print("\n=== TEST: Registry with api_key parameter ===")

    try:
        from hokusai.core import ModelRegistry

        # Initialize with explicit api_key
        api_key = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
        registry = ModelRegistry(api_key=api_key)
        print("✅ Successfully initialized ModelRegistry with api_key parameter!")

        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def main():
    print("=" * 60)
    print("LSCOR Model Registration - Testing Fixes")
    print("=" * 60)

    # Test 1: With HOKUSAI_API_KEY env var
    test1 = test_with_hokusai_api_key()

    # Test 2: With api_key parameter
    test2 = test_alternative_initialization()

    print("\n" + "=" * 60)
    print("SOLUTION SUMMARY")
    print("=" * 60)

    if test1:
        print("✅ Solution 1: Set HOKUSAI_API_KEY environment variable")
        print("   export HOKUSAI_API_KEY='your_api_key'")

    if test2:
        print("✅ Solution 2: Pass api_key to ModelRegistry constructor")
        print("   registry = ModelRegistry(api_key='your_api_key')")

    print("\n" + "=" * 60)
    print("CORRECTED CODE EXAMPLE")
    print("=" * 60)
    print("""
import os
import mlflow
from hokusai.core import ModelRegistry

# Solution 1: Set environment variable
os.environ["HOKUSAI_API_KEY"] = "hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN"
os.environ["MLFLOW_TRACKING_URI"] = "https://registry.hokus.ai/api/mlflow"

# Initialize registry
registry = ModelRegistry()

# OR Solution 2: Pass api_key directly
registry = ModelRegistry(api_key="hk_live_pIDV2HHxM4S7nNYgYjz16MvsazH7DQtN")

# Then register the model
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, "model", registered_model_name="LSCOR_Lead_Scorer")

    model_uri = f"runs:/{run.info.run_id}/model"
    registered_model = registry.register_tokenized_model(
        model_uri=model_uri,
        model_name="LSCOR_Lead_Scorer",
        token_id="LSCOR",
        metric_name="accuracy",
        baseline_value=0.933
    )
""")


if __name__ == "__main__":
    main()
