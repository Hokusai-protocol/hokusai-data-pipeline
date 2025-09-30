#!/usr/bin/env python3
"""Test Hokusai API for Model ID 21 - Sales Lead Scoring Model.

This simulates how a client would use the Hokusai API to score sales leads.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables
load_dotenv()

# Import our API components


def simulate_sales_lead_data() -> List[Dict[str, Any]]:
    """Generate sample sales lead data for scoring."""
    return [
        {
            "lead_id": "LEAD001",
            "company_size": 500,
            "industry": "Technology",
            "engagement_score": 85,
            "website_visits": 12,
            "email_opens": 8,
            "content_downloads": 3,
            "demo_requested": True,
            "budget_confirmed": True,
            "decision_timeline": "Q1 2025",
            "title": "VP of Engineering",
        },
        {
            "lead_id": "LEAD002",
            "company_size": 50,
            "industry": "Retail",
            "engagement_score": 35,
            "website_visits": 2,
            "email_opens": 1,
            "content_downloads": 0,
            "demo_requested": False,
            "budget_confirmed": False,
            "decision_timeline": "Not specified",
            "title": "Marketing Intern",
        },
        {
            "lead_id": "LEAD003",
            "company_size": 2000,
            "industry": "Finance",
            "engagement_score": 65,
            "website_visits": 8,
            "email_opens": 5,
            "content_downloads": 2,
            "demo_requested": True,
            "budget_confirmed": False,
            "decision_timeline": "Q2 2025",
            "title": "Director of IT",
        },
    ]


async def test_hokusai_api_model_21():
    """Test the Hokusai API flow for Model 21 - Sales Lead Scoring."""
    print("=" * 60)
    print("🎯 HOKUSAI API TEST - MODEL 21: SALES LEAD SCORING")
    print("=" * 60)

    # Step 1: Check if we have necessary credentials
    print("\n📋 Step 1: Checking credentials...")

    # In production, clients would use HOKUSAI_API_KEY
    hokusai_api_key = os.getenv("HOKUSAI_API_KEY", "hk_test_123456789")  # Simulated
    huggingface_api_key = os.getenv("HUGGINGFACE_API_KEY")

    print(f"  ✅ Hokusai API Key: {hokusai_api_key[:10]}... (simulated)")
    print(
        f"  ✅ HuggingFace API Key: {huggingface_api_key[:10] if huggingface_api_key else '❌ Not found'}..."
    )

    # Step 2: Explain the architecture
    print("\n🏗️  Step 2: Architecture Overview")
    print("  " + "-" * 50)
    print("  CLIENT → HOKUSAI API → MODEL PROVIDER → INFERENCE")
    print("  " + "-" * 50)
    print("  1. Client sends request with Hokusai API key")
    print("  2. Hokusai API validates the key and checks permissions")
    print("  3. Hokusai API routes to appropriate model (ID 21)")
    print("  4. Model runs inference (via HuggingFace or local)")
    print("  5. Results returned to client")

    # Step 3: Simulate the deployed model
    print("\n🚀 Step 3: Simulating deployed model...")

    deployed_model = {
        "model_id": "21",
        "model_name": "sales-lead-scorer-v1",
        "description": "Sales Lead Scoring Model - Predicts conversion probability",
        "provider": "huggingface",
        "status": "deployed",
        "endpoint_url": "https://api-inference.huggingface.co/models/salesforce/sales-lead-scorer",  # Example
        "created_at": datetime.now().isoformat(),
        "model_type": "tabular-classification",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_size": {"type": "integer"},
                "industry": {"type": "string"},
                "engagement_score": {"type": "number"},
                "website_visits": {"type": "integer"},
                "email_opens": {"type": "integer"},
                "content_downloads": {"type": "integer"},
                "demo_requested": {"type": "boolean"},
                "budget_confirmed": {"type": "boolean"},
                "decision_timeline": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "lead_score": {"type": "number", "minimum": 0, "maximum": 100},
                "conversion_probability": {"type": "number", "minimum": 0, "maximum": 1},
                "recommendation": {"type": "string", "enum": ["Hot", "Warm", "Cold"]},
                "factors": {"type": "array", "items": {"type": "string"}},
            },
        },
    }

    print(f"  Model ID: {deployed_model['model_id']}")
    print(f"  Model Name: {deployed_model['model_name']}")
    print(f"  Provider: {deployed_model['provider']}")
    print(f"  Status: {deployed_model['status']}")

    # Step 4: Test the scoring endpoint
    print("\n📊 Step 4: Testing Sales Lead Scoring...")
    print("  " + "=" * 50)

    leads = simulate_sales_lead_data()

    for lead in leads:
        print(f"\n  🔍 Scoring Lead: {lead['lead_id']}")
        print(f"     Company Size: {lead['company_size']} employees")
        print(f"     Industry: {lead['industry']}")
        print(f"     Engagement Score: {lead['engagement_score']}/100")
        print(f"     Demo Requested: {'Yes' if lead['demo_requested'] else 'No'}")
        print(f"     Budget Confirmed: {'Yes' if lead['budget_confirmed'] else 'No'}")

        # Simulate scoring (in production, this would call the actual model)
        score = simulate_lead_scoring(lead)

        print("\n     📈 RESULTS:")
        print(f"     Lead Score: {score['lead_score']}/100")
        print(f"     Conversion Probability: {score['conversion_probability']:.1%}")
        print(
            f"     Recommendation: {score['recommendation']} 🔥"
            if score["recommendation"] == "Hot"
            else f"     Recommendation: {score['recommendation']}"
        )
        print(f"     Key Factors: {', '.join(score['factors'][:3])}")

    # Step 5: Deployment Options
    print("\n" + "=" * 60)
    print("🔧 DEPLOYMENT OPTIONS FOR MODEL 21")
    print("=" * 60)

    print("\n Option 1: HuggingFace Inference API (FREE but limited)")
    print("  ✅ No additional cost")
    print("  ✅ Quick to set up")
    print("  ❌ Rate limited (100 requests/day)")
    print("  ❌ Shared infrastructure (can be slow)")
    print("  ❌ Not suitable for production")

    print("\n Option 2: HuggingFace Inference Endpoints (PAID)")
    print("  ✅ Dedicated infrastructure")
    print("  ✅ No rate limits")
    print("  ✅ Production-ready with SLA")
    print("  ✅ Auto-scaling available")
    print("  💰 Cost: ~$0.06/hour for small instance")
    print("  💰 Cost: ~$0.60/hour for production instance")

    print("\n Option 3: Self-hosted on AWS/GCP")
    print("  ✅ Full control")
    print("  ✅ Can optimize costs with spot instances")
    print("  ✅ Can use existing infrastructure")
    print("  ❌ Requires DevOps management")
    print("  💰 Cost: Variable based on instance type")

    print("\n Option 4: Local Model (if small enough)")
    print("  ✅ No external API calls")
    print("  ✅ Lowest latency")
    print("  ✅ Most secure (data doesn't leave server)")
    print("  ❌ Requires model to be small (<1GB)")
    print("  ❌ Uses server resources")

    # Step 6: Recommendation
    print("\n" + "=" * 60)
    print("💡 RECOMMENDATION FOR SALES LEAD SCORING MODEL")
    print("=" * 60)

    print("\nFor Production Deployment:")
    print("1. START with Option 1 (Free HF API) for testing")
    print("2. EVALUATE model performance and usage patterns")
    print("3. IF <100 requests/day: Keep using free tier")
    print("4. IF >100 requests/day: Move to Option 2 or 3")
    print("5. IF model is small (<500MB): Consider Option 4")

    print("\n📝 Implementation Steps:")
    print("1. Train/fine-tune sales lead scoring model")
    print("2. Upload model to HuggingFace Hub")
    print("3. Test with free Inference API")
    print("4. Implement caching for common requests")
    print("5. Monitor usage and latency")
    print("6. Scale to paid tier when needed")

    return True


def simulate_lead_scoring(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate lead scoring logic.
    In production, this would call the actual ML model.
    """
    # Simple scoring heuristic for demonstration
    score = 0
    factors = []

    # Company size scoring
    if lead["company_size"] > 1000:
        score += 20
        factors.append("Enterprise company")
    elif lead["company_size"] > 100:
        score += 15
        factors.append("Mid-market company")
    else:
        score += 5
        factors.append("Small business")

    # Engagement scoring
    if lead["engagement_score"] > 70:
        score += 25
        factors.append("High engagement")
    elif lead["engagement_score"] > 40:
        score += 15
        factors.append("Moderate engagement")
    else:
        score += 5
        factors.append("Low engagement")

    # Activity scoring
    if lead["website_visits"] > 10:
        score += 10
        factors.append("Frequent visitor")

    if lead["content_downloads"] > 2:
        score += 10
        factors.append("Content engaged")

    # Intent signals
    if lead["demo_requested"]:
        score += 20
        factors.append("Demo requested")

    if lead["budget_confirmed"]:
        score += 15
        factors.append("Budget confirmed")

    # Decision timeline
    if "Q1" in lead["decision_timeline"] or "Q2" in lead["decision_timeline"]:
        score += 10
        factors.append("Near-term timeline")

    # Title scoring
    if any(title in lead["title"].lower() for title in ["vp", "director", "chief", "head"]):
        score += 10
        factors.append("Senior decision maker")

    # Calculate recommendation
    if score >= 70:
        recommendation = "Hot"
    elif score >= 40:
        recommendation = "Warm"
    else:
        recommendation = "Cold"

    return {
        "lead_score": min(score, 100),
        "conversion_probability": min(score / 100, 1.0),
        "recommendation": recommendation,
        "factors": factors,
    }


if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_hokusai_api_model_21())

    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed.")

    sys.exit(0 if success else 1)
