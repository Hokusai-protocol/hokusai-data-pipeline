#!/usr/bin/env python3
"""Quick health test for Hokusai services."""

import requests
import json
from datetime import datetime

def test_endpoints():
    """Test all Hokusai endpoints."""
    print("=" * 70)
    print("HOKUSAI QUICK HEALTH TEST")
    print("=" * 70)
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    endpoints = [
        ("Auth Service", "https://auth.hokus.ai/health"),
        ("Registry Health", "https://registry.hokus.ai/health"),
        ("Registry MLflow", "https://registry.hokus.ai/mlflow"),
        ("Registry API MLflow", "https://registry.hokus.ai/api/mlflow"),
    ]
    
    results = []
    for name, url in endpoints:
        print(f"Testing {name}: {url}")
        try:
            response = requests.get(url, timeout=5)
            status = response.status_code
            
            if status == 200:
                print(f"  ✅ Success: {status}")
                results.append((name, "OK"))
            elif status in [301, 302, 307]:
                print(f"  ↗️  Redirect: {status}")
                results.append((name, "REDIRECT"))
            elif status == 401:
                print(f"  🔒 Auth Required: {status}")
                results.append((name, "AUTH"))
            elif status == 404:
                print(f"  ❌ Not Found: {status}")
                results.append((name, "NOT_FOUND"))
            elif status in [502, 503, 504]:
                print(f"  ⚠️  Gateway Error: {status}")
                results.append((name, "GATEWAY_ERROR"))
            else:
                print(f"  ❓ Unexpected: {status}")
                results.append((name, f"STATUS_{status}"))
                
        except requests.exceptions.Timeout:
            print(f"  ⏱️  Timeout")
            results.append((name, "TIMEOUT"))
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:50]}")
            results.append((name, "ERROR"))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    working = [r for r in results if r[1] in ["OK", "REDIRECT", "AUTH"]]
    broken = [r for r in results if r[1] not in ["OK", "REDIRECT", "AUTH"]]
    
    if working:
        print("\n✅ Working Services:")
        for name, status in working:
            print(f"  • {name}: {status}")
    
    if broken:
        print("\n❌ Broken Services:")
        for name, status in broken:
            print(f"  • {name}: {status}")
    
    print(f"\n📊 Score: {len(working)}/{len(results)} services accessible")
    
    if len(working) == len(results):
        print("🎉 All services are accessible!")
    elif len(working) > 0:
        print("⚠️  Some services need attention")
    else:
        print("🚨 Critical: No services are accessible")

if __name__ == "__main__":
    test_endpoints()