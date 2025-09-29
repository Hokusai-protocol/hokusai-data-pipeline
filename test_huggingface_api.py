#!/usr/bin/env python3
"""Simple test to verify HuggingFace API connectivity."""

import json
import os

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_huggingface_inference_api():
    """Test HuggingFace Inference API with model ID 21."""
    print("🚀 Testing HuggingFace API connectivity for model ID 21")

    # Check API key
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    if not api_key:
        print("❌ Error: HUGGINGFACE_API_KEY not found in .env file")
        return False

    print(f"✅ HuggingFace API key found: {api_key[:10]}...")

    # Model configuration for testing
    # Using the public inference API (not dedicated endpoints)
    # This is a popular sentiment analysis model on HuggingFace
    model_name = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    api_url = f"https://api-inference.huggingface.co/models/{model_name}"

    print("\n📊 Test Configuration:")
    print("  - Model ID: 21 (simulated)")
    print(f"  - Model: {model_name}")
    print(f"  - API Endpoint: {api_url}")

    # Test input
    test_inputs = [
        "This is absolutely fantastic! I love it!",
        "This is terrible, I hate it.",
        "It's okay, nothing special.",
    ]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print("\n🧪 Testing inference...")

    try:
        for i, test_text in enumerate(test_inputs, 1):
            print(f"\n  Test {i}: '{test_text}'")

            payload = {"inputs": test_text}

            response = requests.post(api_url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                print(f"  ✅ Response: {json.dumps(result, indent=4)}")

                # Parse sentiment results
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], list):
                        # Get top prediction
                        predictions = result[0]
                        top_pred = max(predictions, key=lambda x: x["score"])
                        print(
                            f"  📊 Top Prediction: {top_pred['label']} (confidence: {top_pred['score']:.2%})"
                        )
            else:
                print(f"  ❌ Error {response.status_code}: {response.text}")

                if response.status_code == 503:
                    print("  ⏳ Model is loading. Please wait and try again in a few seconds.")
                elif response.status_code == 401:
                    print("  🔑 Authentication failed. Please check your API key.")
                elif response.status_code == 429:
                    print("  ⚠️  Rate limit exceeded. Please wait before trying again.")

                return False

        print("\n✅ All tests passed successfully!")
        print("\n📌 Summary:")
        print("  - Model ID: 21 (would be assigned in production)")
        print("  - Provider: HuggingFace")
        print(f"  - Model: {model_name}")
        print("  - Status: Available via Inference API")
        print("\n💡 Note: This test uses the public Inference API.")
        print("   For dedicated endpoints (model deployment), a HuggingFace")
        print("   Inference Endpoints subscription is required.")

        return True

    except requests.exceptions.Timeout:
        print("\n❌ Request timed out. The model might be loading.")
        print("   Please try again in a few moments.")
        return False

    except requests.exceptions.ConnectionError:
        print("\n❌ Connection error. Please check your internet connection.")
        return False

    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_huggingface_inference_api()

    if success:
        print("\n🎉 HuggingFace API test completed successfully!")
    else:
        print("\n❌ HuggingFace API test failed.")

    import sys

    sys.exit(0 if success else 1)
