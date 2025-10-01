#!/usr/bin/env python3
"""Comprehensive verification script for Model 21 (LCOR) API.

This script verifies:
1. Model 21 exists in the registry
2. Model 21 has a public API endpoint
3. The API endpoint is accessible and working
4. Predictions can be made through the API
"""

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Model21Verifier:
    """Verifies Model 21 (LCOR) API functionality."""

    def __init__(self, api_base_url: str = "https://api.hokus.ai"):
        self.api_base_url = api_base_url
        self.model_id = "21"
        self.model_name = "LCOR"

        # Try to get API key from environment
        self.api_key = os.getenv("HOKUSAI_API_KEY")

    def print_section(self, title: str):
        """Print a formatted section header."""
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)

    def print_status(self, message: str, status: str = "info"):
        """Print a status message with icon."""
        icons = {"success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️", "pending": "⏳"}
        icon = icons.get(status, "•")
        print(f"{icon} {message}")

    async def verify_model_exists_on_website(self):
        """Verify model 21 exists on the website."""
        self.print_section("Step 1: Verify Model Exists on Website")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"https://hokus.ai/explore-models/{self.model_id}")

                if response.status_code == 200:
                    self.print_status(
                        f"Model {self.model_id} found on website (https://hokus.ai/explore-models/{self.model_id})",
                        "success",
                    )

                    # Try to parse model info
                    content = response.text
                    if "Sales Lead Scoring" in content or "LSCOR" in content:
                        self.print_status(
                            "Model name confirmed: Sales Lead Scoring (LSCOR)", "success"
                        )

                    return True
                else:
                    self.print_status(
                        f"Model not found on website (status: {response.status_code})", "error"
                    )
                    return False

        except Exception as e:
            self.print_status(f"Error checking website: {str(e)}", "error")
            return False

    async def verify_api_endpoint_exists(self):
        """Verify the API endpoint exists for model 21."""
        self.print_section("Step 2: Verify API Endpoint Configuration")

        # Check if we have an API key
        if not self.api_key:
            self.print_status("No HOKUSAI_API_KEY found in environment", "warning")
            self.print_status("API key is required to test endpoints", "info")
            self.print_status(
                "Set HOKUSAI_API_KEY environment variable or add to .env file", "info"
            )
            return False

        self.print_status(f"API key found: {self.api_key[:15]}...", "success")

        # Try to get model info
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}

                # Try the model info endpoint
                response = await client.get(
                    f"{self.api_base_url}/api/v1/models/{self.model_id}/info", headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    self.print_status("Model info endpoint accessible", "success")
                    self.print_status(f"Model name: {data.get('name', 'N/A')}", "info")
                    self.print_status(f"Model type: {data.get('type', 'N/A')}", "info")
                    self.print_status(f"Storage: {data.get('storage', 'N/A')}", "info")
                    return True
                elif response.status_code == 401:
                    self.print_status("API key validation failed", "error")
                    self.print_status("Your API key may be invalid or expired", "warning")
                    return False
                elif response.status_code == 404:
                    self.print_status(f"Model {self.model_id} not found in API", "error")
                    return False
                else:
                    self.print_status(f"Unexpected status: {response.status_code}", "error")
                    self.print_status(f"Response: {response.text[:200]}", "info")
                    return False

        except Exception as e:
            self.print_status(f"Error checking API endpoint: {str(e)}", "error")
            return False

    async def verify_health_endpoint(self):
        """Verify the health endpoint for model 21."""
        self.print_section("Step 3: Verify Model Health Status")

        if not self.api_key:
            self.print_status("Skipping (no API key)", "warning")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"}

                response = await client.get(
                    f"{self.api_base_url}/api/v1/models/{self.model_id}/health", headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "unknown")
                    is_cached = data.get("is_cached", False)

                    if status == "healthy":
                        self.print_status("Model is healthy and ready", "success")
                    else:
                        self.print_status(f"Model status: {status}", "warning")

                    self.print_status(f"Model cached: {'Yes' if is_cached else 'No'}", "info")
                    return True
                else:
                    self.print_status(f"Health check failed: {response.status_code}", "error")
                    return False

        except Exception as e:
            self.print_status(f"Error checking health: {str(e)}", "error")
            return False

    async def test_prediction_endpoint(self):
        """Test making a prediction with model 21."""
        self.print_section("Step 4: Test Prediction Endpoint")

        if not self.api_key:
            self.print_status("Skipping (no API key)", "warning")
            return False

        # Sample lead data for testing
        test_leads = [
            {
                "name": "High-quality lead",
                "data": {
                    "company_size": 1000,
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
            },
            {
                "name": "Low-quality lead",
                "data": {
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
            },
        ]

        success_count = 0

        for lead in test_leads:
            print(f"\n  Testing: {lead['name']}")

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    }

                    payload = {"inputs": lead["data"], "options": {}}

                    response = await client.post(
                        f"{self.api_base_url}/api/v1/models/{self.model_id}/predict",
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        predictions = result.get("predictions", {})

                        self.print_status("Prediction successful", "success")

                        # Print prediction results
                        lead_score = predictions.get("lead_score", "N/A")
                        recommendation = predictions.get("recommendation", "N/A")
                        conversion_prob = predictions.get("conversion_probability", 0)

                        print(f"    Lead Score: {lead_score}/100")
                        print(f"    Recommendation: {recommendation}")
                        print(f"    Conversion Probability: {conversion_prob:.2%}")

                        success_count += 1
                    else:
                        self.print_status(f"Prediction failed: {response.status_code}", "error")
                        print(f"    Response: {response.text[:200]}")

            except Exception as e:
                self.print_status(f"Error: {str(e)}", "error")

        return success_count == len(test_leads)

    async def run_verification(self):
        """Run all verification steps."""
        self.print_section("🎯 Model 21 (LCOR) API Verification")

        print(f"\n  Model ID: {self.model_id}")
        print(f"  Model Name: {self.model_name}")
        print(f"  API Base URL: {self.api_base_url}")

        # Track results
        results = {}

        # Step 1: Check website
        results["website"] = await self.verify_model_exists_on_website()

        # Step 2: Check API endpoint
        results["api_endpoint"] = await self.verify_api_endpoint_exists()

        # Step 3: Check health
        results["health"] = await self.verify_health_endpoint()

        # Step 4: Test predictions
        results["predictions"] = await self.test_prediction_endpoint()

        # Print summary
        self.print_section("📊 Verification Summary")

        print("\n  Results:")
        print(f"    ✓ Model exists on website: {'✅ Yes' if results['website'] else '❌ No'}")
        print(f"    ✓ API endpoint configured: {'✅ Yes' if results['api_endpoint'] else '❌ No'}")
        print(f"    ✓ Model health check: {'✅ Pass' if results['health'] else '❌ Fail'}")
        print(f"    ✓ Prediction API working: {'✅ Yes' if results['predictions'] else '❌ No'}")

        all_passed = all(results.values())

        print("\n  Overall Status:")
        if all_passed:
            self.print_status(
                "All verifications passed! Model 21 API is fully operational.", "success"
            )
        else:
            failed = [k for k, v in results.items() if not v]
            self.print_status(f"Some verifications failed: {', '.join(failed)}", "warning")

        # Print usage example
        if results["api_endpoint"]:
            self.print_section("📝 API Usage Example")

            print("\n  Python:")
            print(f"""
  import requests

  response = requests.post(
      "{self.api_base_url}/api/v1/models/{self.model_id}/predict",
      headers={{"Authorization": "Bearer YOUR_API_KEY"}},
      json={{
          "inputs": {{
              "company_size": 1000,
              "industry": "Technology",
              "engagement_score": 75,
              "website_visits": 10,
              "demo_requested": True,
              "budget_confirmed": False
          }}
      }}
  )

  result = response.json()
  print(result["predictions"])
            """)

            print("\n  cURL:")
            print(f"""
  curl -X POST "{self.api_base_url}/api/v1/models/{self.model_id}/predict" \\
    -H "Authorization: Bearer YOUR_API_KEY" \\
    -H "Content-Type: application/json" \\
    -d '{{
      "inputs": {{
        "company_size": 1000,
        "industry": "Technology",
        "engagement_score": 75,
        "website_visits": 10,
        "demo_requested": true
      }}
    }}'
            """)

        return all_passed


async def main():
    """Main entry point."""
    # Allow custom API URL
    api_url = os.getenv("HOKUSAI_API_URL", "https://api.hokus.ai")

    verifier = Model21Verifier(api_base_url=api_url)
    success = await verifier.run_verification()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
