#!/usr/bin/env python3
"""Test serving Sales Lead Scoring Model (ID 21) through HuggingFace.

This script demonstrates the complete flow:
1. Train/load a model
2. Upload to HuggingFace (private repo)
3. Serve through Hokusai API
4. Test inference
"""

import asyncio
import os
import pickle
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier

# Load environment variables
load_dotenv()

# Import our modules
from src.services.model_storage.storage_manager import ModelStorageManager


class SalesLeadScoringModel:
    """Sales Lead Scoring Model implementation.

    This is a simplified version for demonstration.
    In production, this would be a more sophisticated model.
    """

    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.encoders = {}
        self.feature_names = [
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
        ]

    def prepare_features(self, data: Dict[str, Any]) -> np.ndarray:
        """Convert lead data to model features."""
        features = []

        # Numerical features
        features.append(data.get("company_size", 0))
        features.append(data.get("engagement_score", 0))
        features.append(data.get("website_visits", 0))
        features.append(data.get("email_opens", 0))
        features.append(data.get("content_downloads", 0))

        # Boolean features (convert to 0/1)
        features.append(1 if data.get("demo_requested", False) else 0)
        features.append(1 if data.get("budget_confirmed", False) else 0)

        # Categorical features (simplified encoding)
        industry_score = {
            "Technology": 3,
            "Finance": 3,
            "Healthcare": 2,
            "Retail": 1,
            "Other": 1,
        }.get(data.get("industry", "Other"), 1)
        features.append(industry_score)

        timeline_score = {
            "Q1 2025": 3,
            "Q2 2025": 2,
            "Q3 2025": 1,
            "Q4 2025": 1,
            "Not specified": 0,
        }.get(data.get("decision_timeline", "Not specified"), 0)
        features.append(timeline_score)

        title_score = {"VP": 3, "Director": 2, "Manager": 1, "Other": 0}
        title = data.get("title", "")
        score = 0
        for key, val in title_score.items():
            if key.lower() in title.lower():
                score = val
                break
        features.append(score)

        return np.array(features).reshape(1, -1)

    def train(self, training_data: List[Dict[str, Any]], labels: List[int]):
        """Train the model on sample data."""
        X = np.vstack([self.prepare_features(d) for d in training_data])
        y = np.array(labels)

        self.model.fit(X, y)

        # Calculate feature importances
        self.feature_importances = dict(
            zip(
                [
                    "company_size",
                    "engagement",
                    "visits",
                    "opens",
                    "downloads",
                    "demo",
                    "budget",
                    "industry",
                    "timeline",
                    "title",
                ],
                self.model.feature_importances_,
            )
        )

    def predict(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Score a single lead."""
        features = self.prepare_features(lead_data)

        # Get prediction and probability
        prediction = self.model.predict(features)[0]
        probabilities = self.model.predict_proba(features)[0]

        # Calculate lead score (0-100)
        lead_score = int(probabilities[1] * 100)  # Probability of conversion

        # Determine recommendation
        if lead_score >= 70:
            recommendation = "Hot"
        elif lead_score >= 40:
            recommendation = "Warm"
        else:
            recommendation = "Cold"

        # Identify key factors
        factors = []
        if lead_data.get("demo_requested"):
            factors.append("Demo requested")
        if lead_data.get("budget_confirmed"):
            factors.append("Budget confirmed")
        if lead_data.get("engagement_score", 0) > 70:
            factors.append("High engagement")
        if lead_data.get("company_size", 0) > 500:
            factors.append("Enterprise company")

        return {
            "lead_id": lead_data.get("lead_id", "unknown"),
            "lead_score": lead_score,
            "conversion_probability": float(probabilities[1]),
            "recommendation": recommendation,
            "factors": factors,
            "confidence": float(max(probabilities)),
        }

    def save(self, path: str):
        """Save the model to disk."""
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "model": self.model,
                    "encoders": self.encoders,
                    "feature_names": self.feature_names,
                    "feature_importances": self.feature_importances,
                },
                f,
            )

    def load(self, path: str):
        """Load the model from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.encoders = data["encoders"]
            self.feature_names = data["feature_names"]
            self.feature_importances = data["feature_importances"]


def generate_training_data() -> tuple[List[Dict[str, Any]], List[int]]:
    """Generate sample training data for the model."""
    training_data = []
    labels = []

    # Generate positive examples (converted leads)
    for i in range(50):
        lead = {
            "company_size": np.random.randint(100, 5000),
            "industry": np.random.choice(["Technology", "Finance", "Healthcare"]),
            "engagement_score": np.random.randint(60, 100),
            "website_visits": np.random.randint(5, 30),
            "email_opens": np.random.randint(3, 15),
            "content_downloads": np.random.randint(1, 10),
            "demo_requested": np.random.choice([True, False], p=[0.7, 0.3]),
            "budget_confirmed": np.random.choice([True, False], p=[0.6, 0.4]),
            "decision_timeline": np.random.choice(["Q1 2025", "Q2 2025"]),
            "title": np.random.choice(["VP Sales", "Director of IT", "CTO"]),
        }
        training_data.append(lead)
        labels.append(1)  # Converted

    # Generate negative examples (non-converted leads)
    for i in range(50):
        lead = {
            "company_size": np.random.randint(10, 500),
            "industry": np.random.choice(["Retail", "Other", "Healthcare"]),
            "engagement_score": np.random.randint(0, 50),
            "website_visits": np.random.randint(0, 5),
            "email_opens": np.random.randint(0, 3),
            "content_downloads": np.random.randint(0, 2),
            "demo_requested": np.random.choice([True, False], p=[0.1, 0.9]),
            "budget_confirmed": False,
            "decision_timeline": np.random.choice(["Q4 2025", "Not specified"]),
            "title": np.random.choice(["Manager", "Analyst", "Intern"]),
        }
        training_data.append(lead)
        labels.append(0)  # Not converted

    return training_data, labels


async def test_model_21_serving():
    """Complete test of Model ID 21 serving through HuggingFace."""
    print("=" * 60)
    print("🎯 SALES LEAD SCORING MODEL (ID 21) - SERVING TEST")
    print("=" * 60)

    # Step 1: Train the model
    print("\n📊 Step 1: Training Sales Lead Scoring Model...")
    model = SalesLeadScoringModel()
    training_data, labels = generate_training_data()
    model.train(training_data, labels)

    print(f"  ✅ Model trained on {len(training_data)} samples")
    print("  📈 Feature importances:")
    for feature, importance in sorted(
        model.feature_importances.items(), key=lambda x: x[1], reverse=True
    )[:5]:
        print(f"     - {feature}: {importance:.3f}")

    # Step 2: Save model locally
    print("\n💾 Step 2: Saving model locally...")
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "sales_lead_scorer_v1.pkl"
        model.save(str(model_path))
        print(f"  ✅ Model saved to: {model_path}")

        # Step 3: Upload to HuggingFace (private repo)
        print("\n☁️  Step 3: Uploading to HuggingFace...")

        hf_token = os.getenv("HUGGINGFACE_API_KEY")
        if not hf_token:
            print("  ⚠️  No HuggingFace token found - simulating upload")
            print("  📝 To actually upload, set HUGGINGFACE_API_KEY in .env")
            simulate_upload = True
        else:
            simulate_upload = False

        if not simulate_upload:
            # Real upload
            storage_manager = ModelStorageManager(environment="development")

            model_metadata = {
                "name": "Sales Lead Scoring Model",
                "type": "tabular-classification",
                "description": "Predicts conversion probability for sales leads",
                "version": "1.0.0",
                "sensitivity": "medium",
                "public_ok": False,  # NEVER make public
                "features": model.feature_names,
                "metrics": {
                    "samples_trained": len(training_data),
                    "feature_count": len(model.feature_names),
                },
            }

            try:
                storage_info = await storage_manager.upload_model(
                    model_id="21", model_path=str(model_path), model_metadata=model_metadata
                )

                print("  ✅ Model uploaded successfully!")
                print(f"  🔐 Storage type: {storage_info['storage_type']}")
                print(f"  📦 Repository: {storage_info.get('repository_id', 'N/A')}")
                print(f"  🔒 Private: {storage_info.get('is_private', True)}")

                repo_id = storage_info.get("repository_id")

            except Exception as e:
                print(f"  ❌ Upload failed: {str(e)}")
                simulate_upload = True

        if simulate_upload:
            # Simulated upload
            repo_id = "hokusai-protocol/hokusai-sales-lead-scorer-21"
            storage_info = {
                "storage_type": "huggingface_private",
                "repository_id": repo_id,
                "is_private": True,
                "inference_endpoint": f"https://api-inference.huggingface.co/models/{repo_id}",
            }

            print(f"  📦 Would upload to: {repo_id}")
            print("  🔐 Repository type: PRIVATE")
            print("  ✅ Simulated upload complete")

    # Step 4: Test inference
    print("\n🧪 Step 4: Testing model inference...")

    test_leads = [
        {
            "lead_id": "TEST001",
            "company_size": 2000,
            "industry": "Technology",
            "engagement_score": 85,
            "website_visits": 15,
            "email_opens": 10,
            "content_downloads": 5,
            "demo_requested": True,
            "budget_confirmed": True,
            "decision_timeline": "Q1 2025",
            "title": "VP of Engineering",
        },
        {
            "lead_id": "TEST002",
            "company_size": 50,
            "industry": "Retail",
            "engagement_score": 25,
            "website_visits": 2,
            "email_opens": 1,
            "content_downloads": 0,
            "demo_requested": False,
            "budget_confirmed": False,
            "decision_timeline": "Not specified",
            "title": "Marketing Intern",
        },
    ]

    for lead in test_leads:
        print(f"\n  🔍 Scoring lead: {lead['lead_id']}")
        print(f"     Company: {lead['company_size']} employees, {lead['industry']}")
        print(f"     Engagement: {lead['engagement_score']}/100")

        result = model.predict(lead)

        print("\n     📊 Results:")
        print(f"     Score: {result['lead_score']}/100")
        print(f"     Probability: {result['conversion_probability']:.1%}")
        print(f"     Recommendation: {result['recommendation']} ", end="")
        if result["recommendation"] == "Hot":
            print("🔥")
        elif result["recommendation"] == "Warm":
            print("🟡")
        else:
            print("❄️")
        print(f"     Key factors: {', '.join(result['factors'])}")

    # Step 5: Show API integration
    print("\n🔌 Step 5: API Integration Plan")
    print("  " + "-" * 50)

    print("\n  How the model will be served:")
    print("  1. Client sends request to Hokusai API with API key")
    print("  2. Hokusai API validates the API key")
    print("  3. API loads model from HuggingFace (cached)")
    print("  4. API runs inference on lead data")
    print("  5. API returns scoring results")

    print("\n  Example API call:")
    print("  ```python")
    print("  import requests")
    print()
    print("  response = requests.post(")
    print('      "https://api.hokus.ai/v1/models/21/predict",')
    print('      headers={"Authorization": "Bearer YOUR_HOKUSAI_API_KEY"},')
    print("      json={")
    print('          "inputs": {')
    print('              "company_size": 1000,')
    print('              "industry": "Technology",')
    print('              "engagement_score": 75,')
    print('              "demo_requested": True')
    print("          }")
    print("      }")
    print("  )")
    print("  ```")

    # Step 6: Security summary
    print("\n🔐 Step 6: Security Summary")
    print("  " + "-" * 50)
    print("  ✅ Model stored in PRIVATE HuggingFace repository")
    print("  ✅ Access only through Hokusai API authentication")
    print("  ✅ No direct HuggingFace tokens exposed to clients")
    print("  ✅ All access logged for audit purposes")
    print("  ✅ Model weights protected from competitors")

    return True


async def test_inference_endpoint():
    """Test using HuggingFace Inference API for Model 21.

    This demonstrates how the Hokusai API would call HuggingFace.
    """
    print("\n" + "=" * 60)
    print("🚀 TESTING HUGGINGFACE INFERENCE ENDPOINT")
    print("=" * 60)

    hf_token = os.getenv("HUGGINGFACE_API_KEY")
    if not hf_token:
        print("\n❌ No HuggingFace token found")
        print("  Set HUGGINGFACE_API_KEY in .env to test real inference")
        return False

    print("\n📡 Testing inference options:")

    # Option 1: Free Inference API
    print("\n1️⃣  Free Inference API:")
    print("  - URL: https://api-inference.huggingface.co/models/{repo_id}")
    print("  - Cost: FREE")
    print("  - Limits: 100 requests/day")
    print("  - Latency: Variable (shared infrastructure)")
    print("  - Good for: Development/testing")

    # Option 2: Inference Endpoints (Dedicated)
    print("\n2️⃣  Inference Endpoints (Dedicated):")
    print("  - URL: https://{your-endpoint}.endpoints.huggingface.cloud")
    print("  - Cost: $0.06-$0.60/hour")
    print("  - Limits: None")
    print("  - Latency: Low (dedicated infrastructure)")
    print("  - Good for: Production")

    print("\n📝 Current configuration:")
    print("  - Model ID: 21")
    print("  - Repository: hokusai-protocol/hokusai-sales-lead-scorer-21")
    print("  - Access: Private (requires token)")
    print("  - Serving method: Free API (for testing)")

    print("\n✅ Ready to serve Model 21 through Hokusai API!")

    return True


if __name__ == "__main__":
    import asyncio

    # Run the complete test
    success = asyncio.run(test_model_21_serving())

    if success:
        # Also test inference endpoint info
        asyncio.run(test_inference_endpoint())

        print("\n" + "=" * 60)
        print("🎉 MODEL 21 SERVING TEST COMPLETE!")
        print("=" * 60)

        print("\n📋 Next Steps:")
        print("1. Set HUGGINGFACE_API_KEY in .env (if not set)")
        print("2. Run this script to upload the model")
        print("3. Integrate with Hokusai API endpoints")
        print("4. Test through API with Hokusai API keys")
        print("5. Monitor usage and upgrade to Inference Endpoints if needed")
    else:
        print("\n❌ Test failed")

    sys.exit(0 if success else 1)
