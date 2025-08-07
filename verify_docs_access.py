#!/usr/bin/env python3
"""
Quick verification script for documentation endpoints.
Use this to verify docs are accessible in any environment.
"""

import asyncio
import httpx
import sys
import os
from typing import Optional


async def verify_docs_access(base_url: str = None) -> bool:
    """Verify that documentation endpoints are accessible."""
    
    # Auto-detect base URL if not provided
    if not base_url:
        port = os.getenv("PORT", "8001")
        host = os.getenv("HOST", "localhost")
        base_url = f"http://{host}:{port}"
    
    print(f"🔍 Verifying docs access at {base_url}")
    
    endpoints = ["/docs", "/redoc", "/openapi.json"]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for endpoint in endpoints:
                response = await client.get(f"{base_url}{endpoint}")
                
                if response.status_code == 200:
                    print(f"✅ {endpoint}: OK ({len(response.content)} bytes)")
                else:
                    print(f"❌ {endpoint}: HTTP {response.status_code}")
                    return False
        
        print("✅ All documentation endpoints are accessible!")
        print(f"📖 Visit {base_url}/docs for Swagger UI")
        print(f"📖 Visit {base_url}/redoc for ReDoc")
        return True
        
    except Exception as e:
        print(f"❌ Error accessing {base_url}: {e}")
        return False


async def main():
    """Main verification function."""
    base_url = None
    
    # Check for URL argument
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    success = await verify_docs_access(base_url)
    
    if not success:
        print("\n💡 Troubleshooting tips:")
        print("1. Ensure the API server is running")
        print("2. Check if docs are disabled in production")
        print("3. Verify authentication middleware excludes docs paths")
        print("4. Try: python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())