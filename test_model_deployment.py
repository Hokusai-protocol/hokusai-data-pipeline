#!/usr/bin/env python3
"""Test script to deploy a model using HuggingFace API."""

import json
import os
import sys

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables
load_dotenv()

from src.config.providers import ProviderConfigManager
from src.services.providers.huggingface_provider import HuggingFaceProvider
from src.services.providers.provider_registry import ProviderRegistry


def test_deploy_model():
    """Test deploying model ID 21 with HuggingFace."""
    print("🚀 Testing model deployment for model ID 21")

    # Check HuggingFace API key
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    if not api_key:
        print("❌ Error: HUGGINGFACE_API_KEY not found in environment")
        return False
    print(f"✅ HuggingFace API key found: {api_key[:10]}...")

    # Initialize provider registry and register HuggingFace provider
    provider_registry = ProviderRegistry()
    provider_registry.register_provider("huggingface", HuggingFaceProvider)

    # Get HuggingFace configuration
    config_manager = ProviderConfigManager()
    hf_config = config_manager.get_huggingface_config()

    if not hf_config:
        print("❌ Error: Could not create HuggingFace configuration")
        return False

    print("\n📦 Configuration:")
    print("  - Provider: huggingface")
    print(f"  - Instance Type: {hf_config.default_instance_type}")
    print(f"  - Timeout: {hf_config.timeout}s")
    print(f"  - Max Retries: {hf_config.max_retries}")

    try:
        # Get HuggingFace provider instance
        provider = provider_registry.get_provider("huggingface", hf_config)
        print("\n✅ HuggingFace provider initialized")

        # Model configuration for ID 21
        model_id = "21"
        # Using a small model for testing - you can change this to any HuggingFace model
        model_name = "distilbert-base-uncased-finetuned-sst-2-english"  # Sentiment analysis model

        deployment_config = {
            "model_id": model_id,
            "model": f"distilbert/{model_name}",
            "task": "text-classification",
            "framework": "pytorch",
            "instance_size": "x1",  # Small instance for testing
        }

        print("\n📊 Deployment Configuration:")
        print(f"  - Model ID: {model_id}")
        print(f"  - Model: {deployment_config['model']}")
        print(f"  - Task: {deployment_config['task']}")

        # Deploy the model
        print("\n🔄 Deploying model to HuggingFace Inference Endpoint...")
        deployment = provider.deploy(model_id=model_id, model_name=model_name, **deployment_config)

        print("\n✅ Model deployment initiated!")
        print("📊 Deployment Details:")
        print(f"  - Deployment ID: {deployment.deployment_id}")
        print(f"  - Status: {deployment.status}")
        print(f"  - Endpoint URL: {deployment.endpoint_url}")
        print(f"  - Provider: {deployment.provider}")

        # Check deployment status
        print("\n🔍 Checking deployment status...")
        status = provider.get_status(deployment.deployment_id)
        print(f"  Current Status: {status}")

        # Test inference if the endpoint is ready
        if deployment.endpoint_url and status in ["running", "deployed", "ready"]:
            print("\n🧪 Testing inference...")
            test_text = "This movie is absolutely fantastic! I loved every minute of it."

            result = provider.predict(
                deployment_id=deployment.deployment_id, inputs={"inputs": test_text}
            )

            print(f"📝 Test Input: '{test_text}'")
            print(f"🎯 Prediction Result: {json.dumps(result, indent=2)}")
        else:
            print(f"\n⏳ Model is still deploying. Status: {status}")
            print("   Please wait a few minutes for the model to be ready.")

            # You can check the status later
            print("\n💡 To check status later, use deployment ID:", deployment.deployment_id)

        return True

    except Exception as e:
        print(f"\n❌ Error during deployment: {str(e)}")
        import traceback

        traceback.print_exc()

        # Check if it's an API error
        if "401" in str(e) or "403" in str(e):
            print("\n⚠️  This might be an authentication issue. Please check:")
            print("  1. Your HuggingFace API key is valid")
            print("  2. You have access to Inference Endpoints (may require Pro account)")
        elif "insufficient" in str(e).lower() or "quota" in str(e).lower():
            print("\n⚠️  This might be a quota issue. Please check:")
            print("  1. Your HuggingFace account has sufficient credits")
            print("  2. You haven't exceeded your endpoint limits")

        return False


if __name__ == "__main__":
    success = test_deploy_model()

    if success:
        print("\n🎉 Test completed successfully!")
    else:
        print("\n❌ Test failed. Please check the errors above.")

    sys.exit(0 if success else 1)
