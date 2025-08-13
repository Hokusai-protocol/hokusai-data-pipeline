#!/usr/bin/env python3
"""Comprehensive system health check for Hokusai Data Pipeline."""

import json
import requests
import time
from datetime import datetime
from typing import Dict, Any, List
import os

# Service endpoints
ENDPOINTS = {
    "registry_health": "https://registry.hokus.ai/health",
    "registry_mlflow": "https://registry.hokus.ai/api/mlflow/version",
    "api_health": "https://api.hokus.ai/health",
    "auth_health": "https://auth.hokus.ai/health",
    "mlflow_ui": "https://registry.hokus.ai/mlflow",
}

# ANSI color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def check_endpoint(name: str, url: str, timeout: int = 10) -> Dict[str, Any]:
    """Check if an endpoint is accessible."""
    result = {
        "name": name,
        "url": url,
        "status": "unknown",
        "response_time": None,
        "status_code": None,
        "error": None,
        "details": {}
    }
    
    try:
        start = time.time()
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        response_time = (time.time() - start) * 1000  # Convert to ms
        
        result["response_time"] = f"{response_time:.0f}ms"
        result["status_code"] = response.status_code
        
        if response.status_code == 200:
            result["status"] = "healthy"
            # Try to parse JSON response
            try:
                data = response.json()
                result["details"] = data
            except:
                result["details"] = {"text": response.text[:200]}
        elif response.status_code == 401:
            result["status"] = "requires_auth"
        elif response.status_code == 404:
            result["status"] = "not_found"
        elif 500 <= response.status_code < 600:
            result["status"] = "error"
        else:
            result["status"] = "degraded"
            
    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = "Request timed out"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "unreachable"
        result["error"] = str(e)[:100]
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:100]
    
    return result

def check_health_details(health_url: str) -> Dict[str, Any]:
    """Get detailed health information from health endpoint."""
    try:
        response = requests.get(health_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "overall_status": data.get("status", "unknown"),
                "services": data.get("services", {}),
                "checks": data.get("checks", {}),
                "version": data.get("version", "unknown")
            }
    except:
        pass
    return {}

def print_service_status(result: Dict[str, Any]):
    """Print formatted service status."""
    status = result["status"]
    name = result["name"]
    
    # Choose color based on status
    if status == "healthy":
        color = Colors.GREEN
        symbol = "✅"
    elif status == "requires_auth":
        color = Colors.YELLOW
        symbol = "🔒"
    elif status in ["timeout", "unreachable", "not_found"]:
        color = Colors.RED
        symbol = "❌"
    elif status == "degraded":
        color = Colors.YELLOW
        symbol = "⚠️"
    else:
        color = Colors.RED
        symbol = "❌"
    
    # Print main status
    print(f"{symbol} {Colors.BOLD}{name}{Colors.RESET}")
    print(f"   Status: {color}{status}{Colors.RESET}")
    print(f"   URL: {result['url']}")
    
    if result["response_time"]:
        print(f"   Response Time: {result['response_time']}")
    if result["status_code"]:
        print(f"   HTTP Status: {result['status_code']}")
    if result["error"]:
        print(f"   Error: {Colors.RED}{result['error']}{Colors.RESET}")
    
    # Print service details if available
    if result.get("details") and isinstance(result["details"], dict):
        services = result["details"].get("services", {})
        if services:
            print(f"   {Colors.BLUE}Sub-services:{Colors.RESET}")
            for service_name, service_status in services.items():
                if isinstance(service_status, dict):
                    status_val = service_status.get("status", "unknown")
                    if status_val == "healthy":
                        print(f"     • {service_name}: {Colors.GREEN}healthy{Colors.RESET}")
                    elif status_val == "degraded":
                        print(f"     • {service_name}: {Colors.YELLOW}degraded{Colors.RESET}")
                    else:
                        print(f"     • {service_name}: {Colors.RED}{status_val}{Colors.RESET}")
                else:
                    print(f"     • {service_name}: {service_status}")
    print()

def test_redis_status():
    """Check Redis status from the health endpoint."""
    print(f"{Colors.BOLD}Checking Redis Status...{Colors.RESET}")
    try:
        response = requests.get("https://registry.hokus.ai/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            redis_status = data.get("services", {}).get("redis", {})
            if isinstance(redis_status, dict):
                status = redis_status.get("status", "unknown")
                if status == "healthy":
                    print(f"✅ Redis: {Colors.GREEN}healthy{Colors.RESET}")
                elif status == "degraded":
                    print(f"⚠️ Redis: {Colors.YELLOW}degraded (fallback mode){Colors.RESET}")
                    print("   Note: Service operating without Redis - using fallback publisher")
                else:
                    print(f"❌ Redis: {Colors.RED}{status}{Colors.RESET}")
                    error = redis_status.get("error")
                    if error:
                        print(f"   Error: {error}")
            else:
                print(f"❓ Redis status: {redis_status}")
    except Exception as e:
        print(f"❌ Could not check Redis status: {e}")
    print()

def main():
    """Run comprehensive system health check."""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Hokusai Data Pipeline - System Health Check{Colors.RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    
    # Check all endpoints
    results = []
    for name, url in ENDPOINTS.items():
        print(f"Checking {name}...")
        result = check_endpoint(name, url)
        results.append(result)
    
    print(f"\n{Colors.BOLD}Service Status Summary:{Colors.RESET}\n")
    
    # Print results
    for result in results:
        print_service_status(result)
    
    # Check Redis specifically
    test_redis_status()
    
    # Calculate overall health
    healthy_count = sum(1 for r in results if r["status"] == "healthy")
    auth_required_count = sum(1 for r in results if r["status"] == "requires_auth")
    degraded_count = sum(1 for r in results if r["status"] == "degraded")
    failed_count = sum(1 for r in results if r["status"] in ["error", "timeout", "unreachable", "not_found"])
    
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Overall System Status:{Colors.RESET}")
    print(f"  Healthy Services: {Colors.GREEN}{healthy_count}/{len(results)}{Colors.RESET}")
    print(f"  Auth Required: {Colors.YELLOW}{auth_required_count}/{len(results)}{Colors.RESET}")
    print(f"  Degraded Services: {Colors.YELLOW}{degraded_count}/{len(results)}{Colors.RESET}")
    print(f"  Failed Services: {Colors.RED}{failed_count}/{len(results)}{Colors.RESET}")
    
    # Overall assessment
    if failed_count == 0 and degraded_count == 0:
        print(f"\n{Colors.GREEN}✅ All systems operational!{Colors.RESET}")
    elif failed_count == 0:
        print(f"\n{Colors.YELLOW}⚠️ System operational with degraded services{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}❌ System has failed services requiring attention{Colors.RESET}")
    
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    
    # Save detailed report
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "summary": {
            "healthy": healthy_count,
            "auth_required": auth_required_count,
            "degraded": degraded_count,
            "failed": failed_count,
            "total": len(results)
        }
    }
    
    with open("system_health_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"Detailed report saved to: system_health_report.json")

if __name__ == "__main__":
    main()