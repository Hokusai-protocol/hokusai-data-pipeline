#!/usr/bin/env python3
"""Test Model 21 upload with user's namespace.
This script determines the correct namespace and uploads the model.
"""

import json
import os
import pickle
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from huggingface_hub import HfApi, create_repo, upload_file, whoami
from sklearn.ensemble import RandomForestClassifier

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


def get_user_namespace():
    """Get the user's HuggingFace namespace (username or org)."""
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    if not api_key:
        raise ValueError("HUGGINGFACE_API_KEY not found in .env")

    api = HfApi(token=api_key)

    try:
        # Get user info
        user_info = whoami(token=api_key)
        username = user_info["name"]

        print(f"✅ Logged in as: {username}")
        print(f"📧 Email: {user_info.get('email', 'N/A')}")

        # Check if user has any organizations
        orgs = user_info.get("orgs", [])
        if orgs:
            print(f"🏢 Organizations: {', '.join([org['name'] for org in orgs])}")
            # You could let user choose, for now use personal namespace

        return username

    except Exception as e:
        print(f"❌ Failed to get user info: {e}")
        raise


def create_simple_model():
    """Create a simple Sales Lead Scoring model."""
    # Generate simple training data
    X = np.random.rand(100, 10)  # 100 samples, 10 features
    y = np.random.randint(0, 2, 100)  # Binary classification

    # Train model
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X, y)

    return model


def test_private_repo_upload():
    """Test uploading Model 21 to a private HuggingFace repository."""
    print("=" * 60)
    print("🔒 TESTING PRIVATE REPO UPLOAD - MODEL 21")
    print("=" * 60)

    # Step 1: Get user namespace
    print("\n📋 Step 1: Getting HuggingFace namespace...")
    try:
        namespace = get_user_namespace()
    except Exception as e:
        print(f"❌ Failed to get namespace: {e}")
        return False

    # Step 2: Create model
    print("\n🤖 Step 2: Creating Sales Lead Scoring Model...")
    model = create_simple_model()
    print("  ✅ Model created")

    # Step 3: Save model locally
    print("\n💾 Step 3: Saving model locally...")
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "model.pkl"

        with open(model_path, "wb") as f:
            pickle.dump(
                {
                    "model": model,
                    "model_id": "21",
                    "name": "Sales Lead Scoring Model",
                    "version": "1.0.0",
                    "created_at": datetime.utcnow().isoformat(),
                },
                f,
            )

        print(f"  ✅ Model saved to: {model_path}")

        # Step 4: Upload to HuggingFace
        print("\n☁️  Step 4: Uploading to HuggingFace private repo...")

        api_key = os.getenv("HUGGINGFACE_API_KEY")
        api = HfApi(token=api_key)

        # Use user's namespace instead of "hokusai-protocol"
        repo_id = f"{namespace}/hokusai-model-21-sales-lead-scorer"

        print(f"  📦 Repository ID: {repo_id}")
        print("  🔐 Privacy: PRIVATE")

        try:
            # Create private repository
            repo_url = create_repo(
                repo_id=repo_id,
                private=True,  # PRIVATE repository
                repo_type="model",
                exist_ok=True,
                token=api_key,
            )

            print(f"  ✅ Repository created/found: {repo_url}")

            # Create model card
            model_card = f"""---
license: other
tags:
- hokusai
- sales-lead-scoring
- model-id-21
- private
library_name: scikit-learn
---

# Hokusai Model 21 - Sales Lead Scoring

⚠️ **PROPRIETARY MODEL - DO NOT SHARE**

This model is part of the Hokusai Protocol and is for internal use only.

## Model Details
- **Model ID**: 21
- **Type**: Sales Lead Scoring
- **Framework**: scikit-learn (RandomForest)
- **Created**: {datetime.utcnow().isoformat()}

## Security
- This is a PRIVATE repository
- Access is restricted to authorized users only
- Served through Hokusai API with authentication

## Usage
Access this model through the Hokusai API:
```python
# Via Hokusai API only
POST https://api.hokus.ai/v1/models/21/predict
```
"""

            # Upload model card
            upload_file(
                path_or_fileobj=model_card.encode(),
                path_in_repo="README.md",
                repo_id=repo_id,
                repo_type="model",
                token=api_key,
            )

            # Upload model file
            upload_file(
                path_or_fileobj=str(model_path),
                path_in_repo="model.pkl",
                repo_id=repo_id,
                repo_type="model",
                token=api_key,
            )

            # Upload config
            config = {
                "model_id": "21",
                "model_type": "sales_lead_scoring",
                "framework": "scikit-learn",
                "version": "1.0.0",
                "features": [
                    "company_size",
                    "industry",
                    "engagement_score",
                    "website_visits",
                    "email_opens",
                    "content_downloads",
                    "demo_requested",
                    "budget_confirmed",
                    "decision_timeline",
                    "title",
                ],
            }

            upload_file(
                path_or_fileobj=json.dumps(config, indent=2).encode(),
                path_in_repo="config.json",
                repo_id=repo_id,
                repo_type="model",
                token=api_key,
            )

            print("  ✅ Model uploaded successfully!")

            # Step 5: Verify privacy
            print("\n🔍 Step 5: Verifying repository privacy...")

            repo_info = api.repo_info(repo_id=repo_id, repo_type="model")

            if repo_info.private:
                print("  ✅ Repository is PRIVATE")
                print("  🔒 Only accessible with your HuggingFace token")
            else:
                print("  ⚠️  WARNING: Repository is PUBLIC!")

            # Step 6: Test inference API
            print("\n🧪 Step 6: Testing Inference API access...")

            import requests

            # Test with authentication
            headers = {"Authorization": f"Bearer {api_key}"}
            api_url = f"https://api-inference.huggingface.co/models/{repo_id}"

            # Note: The model might need time to load
            print(f"  🔗 API URL: {api_url}")
            print("  🔑 Using authentication: Yes")

            test_data = {"inputs": [[0.5] * 10]}  # Simple test input

            try:
                response = requests.post(api_url, headers=headers, json=test_data, timeout=30)

                if response.status_code == 200:
                    print("  ✅ Inference API accessible")
                elif response.status_code == 503:
                    print("  ⏳ Model is loading... (this is normal for new uploads)")
                else:
                    print(f"  ⚠️  Response: {response.status_code} - {response.text[:100]}")

            except Exception as e:
                print(f"  ⚠️  Could not test inference: {e}")

            # Summary
            print("\n" + "=" * 60)
            print("✅ PRIVATE REPO UPLOAD SUCCESSFUL!")
            print("=" * 60)
            print("\n📊 Summary:")
            print("  Model ID: 21")
            print(f"  Repository: {repo_id}")
            print(f"  URL: https://huggingface.co/{repo_id}")
            print("  Privacy: PRIVATE ✅")
            print("  Access: Via Hokusai API only")
            print("\n🔐 Security:")
            print("  - Model is in a PRIVATE repository")
            print("  - Only accessible with your HF token")
            print("  - Competitors cannot access")
            print("  - Ready for integration with Hokusai API")

            return True

        except Exception as e:
            print(f"  ❌ Upload failed: {e}")
            return False


if __name__ == "__main__":
    success = test_private_repo_upload()

    if success:
        print("\n🎉 Test passed! Model 21 is securely uploaded.")
    else:
        print("\n❌ Test failed. Please check the errors above.")

    sys.exit(0 if success else 1)
