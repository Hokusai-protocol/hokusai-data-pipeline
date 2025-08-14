#!/usr/bin/env python3
"""
Comprehensive validation of all Hokusai services after deployment.
Tests all endpoints, health checks, and inter-service communication.
"""

import json
import requests
import time
from datetime import datetime
from typing import Dict, Any, List
import subprocess
import sys

# Service endpoints to test
ENDPOINTS = {
    "registry_health": "https://registry.hokus.ai/health",
    "registry_mlflow_version": "https://registry.hokus.ai/api/mlflow/version",
    "registry_mlflow_experiments": "https://registry.hokus.ai/api/mlflow/api/2.0/mlflow/experiments/search",
    "api_health": "https://api.hokus.ai/health",
    "auth_health": "https://auth.hokus.ai/health",
    "auth_docs": "https://auth.hokus.ai/docs",
    "mlflow_ui": "https://registry.hokus.ai/mlflow",
}

# ANSI colors
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def check_endpoint(name: str, url: str, timeout: int = 30) -> Dict[str, Any]:
    """Check endpoint availability with extended timeout."""
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
        response_time = (time.time() - start) * 1000
        
        result["response_time"] = f"{response_time:.0f}ms"
        result["status_code"] = response.status_code
        
        if response.status_code == 200:
            result["status"] = "healthy"
            try:
                data = response.json()
                result["details"] = data
            except:
                result["details"] = {"text": response.text[:500]}
        elif response.status_code == 401:
            result["status"] = "requires_auth"
        elif response.status_code == 404:
            result["status"] = "not_found"
        elif 500 <= response.status_code < 600:
            result["status"] = "error"
            result["error"] = f"HTTP {response.status_code}"
        else:
            result["status"] = "degraded"
            
    except requests.exceptions.Timeout:
        result["status"] = "timeout"
        result["error"] = f"Request timed out after {timeout}s"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "unreachable"
        result["error"] = str(e)[:200]
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
    
    return result

def check_ecs_services() -> List[Dict[str, Any]]:
    """Check ECS service status."""
    services = []
    try:
        # Check ECS services
        cmd = """aws ecs describe-services \
            --cluster hokusai-development \
            --services hokusai-api-development hokusai-mlflow-development hokusai-auth-development \
            --region us-east-1 \
            --query 'services[*].{name:serviceName,desired:desiredCount,running:runningCount,status:status}' \
            --output json"""
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            services = json.loads(result.stdout)
    except Exception as e:
        print(f"Error checking ECS: {e}")
    
    return services

def check_target_health() -> Dict[str, List]:
    """Check ALB target group health."""
    health_status = {}
    try:
        # Get target groups
        cmd = """aws elbv2 describe-target-groups \
            --region us-east-1 \
            --query 'TargetGroups[?contains(TargetGroupName, `hokusai`) && contains(TargetGroupName, `development`)].[TargetGroupName,TargetGroupArn]' \
            --output text"""
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) == 2:
                        tg_name, tg_arn = parts
                        
                        # Check health for this target group
                        health_cmd = f"""aws elbv2 describe-target-health \
                            --target-group-arn {tg_arn} \
                            --region us-east-1 \
                            --query 'TargetHealthDescriptions[*].{{target:Target.Id,health:TargetHealth.State}}' \
                            --output json"""
                        
                        health_result = subprocess.run(health_cmd, shell=True, capture_output=True, text=True)
                        if health_result.returncode == 0:
                            targets = json.loads(health_result.stdout)
                            if targets:
                                health_status[tg_name] = targets
    except Exception as e:
        print(f"Error checking target health: {e}")
    
    return health_status

def print_status(name: str, status: str, details: str = ""):
    """Print formatted status."""
    if status == "healthy":
        print(f"  ✅ {Colors.GREEN}{name}: {status}{Colors.RESET} {details}")
    elif status in ["degraded", "requires_auth"]:
        print(f"  ⚠️  {Colors.YELLOW}{name}: {status}{Colors.RESET} {details}")
    else:
        print(f"  ❌ {Colors.RED}{name}: {status}{Colors.RESET} {details}")

def main():
    """Run comprehensive service validation."""
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}Hokusai Data Pipeline - Deployment Validation{Colors.RESET}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}\n")
    
    # Check ECS Services
    print(f"{Colors.BOLD}1. ECS Service Status:{Colors.RESET}")
    ecs_services = check_ecs_services()
    all_running = True
    for service in ecs_services:
        is_running = service['running'] == service['desired'] and service['status'] == 'ACTIVE'
        status = "healthy" if is_running else "degraded"
        if not is_running:
            all_running = False
        print_status(
            service['name'], 
            status,
            f"({service['running']}/{service['desired']} tasks)"
        )
    
    # Check Target Group Health
    print(f"\n{Colors.BOLD}2. Target Group Health:{Colors.RESET}")
    target_health = check_target_health()
    healthy_targets = 0
    total_targets = 0
    
    for tg_name, targets in target_health.items():
        healthy_count = sum(1 for t in targets if t['health'] == 'healthy')
        total = len(targets)
        total_targets += total
        healthy_targets += healthy_count
        
        if healthy_count == total and total > 0:
            print(f"  ✅ {Colors.GREEN}{tg_name}: {healthy_count}/{total} healthy{Colors.RESET}")
        elif healthy_count > 0:
            print(f"  ⚠️  {Colors.YELLOW}{tg_name}: {healthy_count}/{total} healthy{Colors.RESET}")
        else:
            print(f"  ❌ {Colors.RED}{tg_name}: {healthy_count}/{total} healthy{Colors.RESET}")
    
    # Check Service Endpoints
    print(f"\n{Colors.BOLD}3. Service Endpoint Tests:{Colors.RESET}")
    results = []
    for name, url in ENDPOINTS.items():
        print(f"  Testing {name}...", end='', flush=True)
        result = check_endpoint(name, url)
        results.append(result)
        
        # Clear line and print result
        print('\r' + ' ' * 50 + '\r', end='')
        
        if result["status"] == "healthy":
            print(f"  ✅ {Colors.GREEN}{name}: {result['status']}{Colors.RESET} ({result.get('response_time', 'N/A')})")
        elif result["status"] == "requires_auth":
            print(f"  🔒 {Colors.YELLOW}{name}: {result['status']}{Colors.RESET} ({result.get('response_time', 'N/A')})")
        elif result["status"] == "timeout":
            print(f"  ❌ {Colors.RED}{name}: timeout after 30s{Colors.RESET}")
        else:
            print(f"  ❌ {Colors.RED}{name}: {result['status']}{Colors.RESET} - {result.get('error', '')}")
    
    # Check specific service details
    print(f"\n{Colors.BOLD}4. Service Health Details:{Colors.RESET}")
    
    # Check Registry Health
    registry_health = next((r for r in results if r['name'] == 'registry_health'), None)
    if registry_health and registry_health['status'] == 'healthy':
        services = registry_health.get('details', {}).get('services', {})
        print(f"  {Colors.BLUE}Registry Service Components:{Colors.RESET}")
        for svc_name, svc_info in services.items():
            if isinstance(svc_info, dict):
                svc_status = svc_info.get('status', 'unknown')
                if svc_status == 'healthy':
                    print(f"    • {svc_name}: {Colors.GREEN}healthy{Colors.RESET}")
                elif svc_status == 'degraded':
                    print(f"    • {svc_name}: {Colors.YELLOW}degraded{Colors.RESET}")
                else:
                    print(f"    • {svc_name}: {Colors.RED}{svc_status}{Colors.RESET}")
    
    # Summary
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}DEPLOYMENT VALIDATION SUMMARY{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    
    # Calculate totals
    healthy_endpoints = sum(1 for r in results if r["status"] == "healthy")
    auth_required = sum(1 for r in results if r["status"] == "requires_auth")
    failed_endpoints = sum(1 for r in results if r["status"] in ["error", "timeout", "unreachable", "not_found"])
    
    print(f"\n{Colors.BOLD}ECS Services:{Colors.RESET}")
    if all_running:
        print(f"  ✅ All services running with desired task count")
    else:
        print(f"  ⚠️  Some services have task count mismatch")
    
    print(f"\n{Colors.BOLD}Target Groups:{Colors.RESET}")
    if total_targets > 0:
        health_pct = (healthy_targets / total_targets) * 100
        if health_pct == 100:
            print(f"  ✅ All targets healthy ({healthy_targets}/{total_targets})")
        elif health_pct > 50:
            print(f"  ⚠️  {health_pct:.0f}% targets healthy ({healthy_targets}/{total_targets})")
        else:
            print(f"  ❌ Only {health_pct:.0f}% targets healthy ({healthy_targets}/{total_targets})")
    
    print(f"\n{Colors.BOLD}Endpoints:{Colors.RESET}")
    print(f"  ✅ Healthy: {healthy_endpoints}/{len(results)}")
    print(f"  🔒 Auth Required: {auth_required}/{len(results)}")
    print(f"  ❌ Failed: {failed_endpoints}/{len(results)}")
    
    # Overall Status
    print(f"\n{Colors.BOLD}OVERALL STATUS:{Colors.RESET}")
    if failed_endpoints == 0 and healthy_targets == total_targets:
        print(f"  {Colors.GREEN}✅ DEPLOYMENT SUCCESSFUL - All services operational!{Colors.RESET}")
        return 0
    elif failed_endpoints <= 2 and healthy_targets > 0:
        print(f"  {Colors.YELLOW}⚠️  PARTIAL SUCCESS - Most services operational with some issues{Colors.RESET}")
        return 1
    else:
        print(f"  {Colors.RED}❌ DEPLOYMENT ISSUES - Services not fully operational{Colors.RESET}")
        return 2
    
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}\n")

if __name__ == "__main__":
    sys.exit(main())