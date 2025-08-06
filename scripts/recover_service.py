#!/usr/bin/env python3
"""
Automated recovery script for Hokusai registry service.
Handles common failure scenarios and service restoration.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import boto3
import requests
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ServiceRecovery:
    """Automated service recovery tool."""
    
    def __init__(self, api_url: str = None, api_key: str = None, aws_region: str = "us-west-2"):
        self.api_url = api_url or os.getenv("API_URL", "https://data.hokus.ai")
        self.api_key = api_key or os.getenv("API_KEY")
        self.aws_region = aws_region
        self.recovery_log = []
        self.session = requests.Session()
        self.session.timeout = 30
        
        # AWS clients
        try:
            self.ecs_client = boto3.client('ecs', region_name=aws_region)
            self.elbv2_client = boto3.client('elbv2', region_name=aws_region)
            self.rds_client = boto3.client('rds', region_name=aws_region)
            self.aws_available = True
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"AWS clients not available: {e}")
            self.aws_available = False

    def log_action(self, action: str, status: str, details: str = None):
        """Log recovery action."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "status": status,
            "details": details
        }
        self.recovery_log.append(entry)
        
        status_emoji = {"success": "✅", "warning": "⚠️", "error": "❌", "info": "ℹ️"}
        emoji = status_emoji.get(status, "📝")
        logger.info(f"{emoji} {action}: {status}" + (f" - {details}" if details else ""))

    def run_recovery(self, dry_run: bool = False) -> Dict:
        """Run automated recovery process."""
        logger.info("🔧 Starting automated service recovery...")
        if dry_run:
            logger.info("🧪 Running in DRY RUN mode - no changes will be made")
        
        start_time = time.time()
        recovery_result = {
            "start_time": datetime.now().isoformat(),
            "dry_run": dry_run,
            "recovery_log": [],
            "overall_success": False,
            "duration_seconds": 0
        }
        
        try:
            # Step 1: Check current service status
            self.log_action("Initial Health Check", "info", "Assessing current service state")
            health_status = self._check_service_health()
            
            if health_status.get("overall_status") == "healthy":
                self.log_action("Service Already Healthy", "success", "No recovery needed")
                recovery_result["overall_success"] = True
                return self._finalize_recovery(recovery_result, start_time)
            
            # Step 2: Reset circuit breaker if open
            if self._is_circuit_breaker_open():
                self.log_action("Reset Circuit Breaker", "info", "Attempting to reset MLflow circuit breaker")
                if not dry_run:
                    self._reset_circuit_breaker()
                else:
                    self.log_action("Reset Circuit Breaker", "info", "[DRY RUN] Would reset circuit breaker")
            
            # Step 3: Restart ECS services if needed
            if self._should_restart_ecs_services():
                self.log_action("Restart ECS Services", "info", "Restarting unhealthy ECS services")
                if not dry_run:
                    self._restart_ecs_services()
                else:
                    self.log_action("Restart ECS Services", "info", "[DRY RUN] Would restart ECS services")
            
            # Step 4: Check and fix ALB target health
            if self.aws_available:
                self.log_action("Check ALB Health", "info", "Checking Application Load Balancer targets")
                if not dry_run:
                    self._fix_alb_targets()
                else:
                    self.log_action("Check ALB Health", "info", "[DRY RUN] Would check and fix ALB targets")
            
            # Step 5: Wait for services to stabilize
            if not dry_run:
                self.log_action("Service Stabilization", "info", "Waiting for services to stabilize")
                self._wait_for_stabilization()
            
            # Step 6: Verify recovery
            self.log_action("Final Health Check", "info", "Verifying service recovery")
            final_health = self._check_service_health()
            
            if final_health.get("overall_status") == "healthy":
                self.log_action("Recovery Successful", "success", "All services restored to healthy state")
                recovery_result["overall_success"] = True
            elif final_health.get("overall_status") in ["degraded", "recovering"]:
                self.log_action("Recovery Partial", "warning", "Services partially recovered but still degraded")
                recovery_result["overall_success"] = False
            else:
                self.log_action("Recovery Failed", "error", "Services still unhealthy after recovery attempt")
                recovery_result["overall_success"] = False
        
        except Exception as e:
            self.log_action("Recovery Exception", "error", str(e))
            logger.exception("Recovery process failed with exception")
            recovery_result["overall_success"] = False
        
        return self._finalize_recovery(recovery_result, start_time)

    def _finalize_recovery(self, recovery_result: Dict, start_time: float) -> Dict:
        """Finalize recovery process and return results."""
        recovery_result["recovery_log"] = self.recovery_log
        recovery_result["duration_seconds"] = time.time() - start_time
        
        logger.info(f"🏁 Recovery process completed in {recovery_result['duration_seconds']:.2f} seconds")
        logger.info(f"📊 Recovery success: {'✅ YES' if recovery_result['overall_success'] else '❌ NO'}")
        
        return recovery_result

    def _check_service_health(self) -> Dict:
        """Quick service health check."""
        try:
            # Check main health endpoint
            response = self.session.get(f"{self.api_url}/health", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "overall_status": data.get("status", "unknown"),
                    "services": data.get("services", {}),
                    "api_accessible": True
                }
            else:
                return {
                    "overall_status": "unhealthy", 
                    "api_accessible": False,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            return {
                "overall_status": "unhealthy",
                "api_accessible": False,
                "error": str(e)
            }

    def _is_circuit_breaker_open(self) -> bool:
        """Check if MLflow circuit breaker is open."""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            response = self.session.get(f"{self.api_url}/health/mlflow", headers=headers, timeout=10)
            
            if response.status_code in [200, 503]:
                data = response.json()
                return data.get("circuit_breaker_state") == "OPEN"
                
        except Exception as e:
            self.log_action("Circuit Breaker Check", "error", str(e))
            
        return False

    def _reset_circuit_breaker(self):
        """Reset the MLflow circuit breaker."""
        try:
            # Try to call a reset endpoint if available
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # First try a direct reset endpoint
            try:
                response = self.session.post(f"{self.api_url}/health/mlflow/reset", headers=headers, timeout=10)
                if response.status_code == 200:
                    self.log_action("Circuit Breaker Reset", "success", "Reset via API endpoint")
                    return
            except:
                pass
            
            # Alternative: Try to trigger a reset by making a test connection
            try:
                response = self.session.get(f"{self.api_url}/health/mlflow", headers=headers, timeout=10)
                # Wait a moment and check again
                time.sleep(2)
                response = self.session.get(f"{self.api_url}/health/mlflow", headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("circuit_breaker_state") in ["CLOSED", "HALF_OPEN"]:
                        self.log_action("Circuit Breaker Reset", "success", "Reset via health check")
                        return
            except:
                pass
            
            self.log_action("Circuit Breaker Reset", "warning", "Could not reset circuit breaker automatically")
            
        except Exception as e:
            self.log_action("Circuit Breaker Reset", "error", str(e))

    def _should_restart_ecs_services(self) -> bool:
        """Determine if ECS services need restart."""
        if not self.aws_available:
            return False
            
        try:
            clusters = self.ecs_client.list_clusters()["clusterArns"]
            
            for cluster_arn in clusters:
                if "hokusai" not in cluster_arn.lower():
                    continue
                
                services = self.ecs_client.list_services(cluster=cluster_arn)["serviceArns"]
                
                if services:
                    service_details = self.ecs_client.describe_services(
                        cluster=cluster_arn,
                        services=services
                    )
                    
                    for service in service_details["services"]:
                        if (service["status"] != "ACTIVE" or 
                            service["runningCount"] < service["desiredCount"]):
                            return True
                            
        except Exception as e:
            self.log_action("ECS Service Check", "error", str(e))
            
        return False

    def _restart_ecs_services(self):
        """Restart unhealthy ECS services."""
        if not self.aws_available:
            self.log_action("ECS Service Restart", "warning", "AWS not available")
            return
            
        try:
            clusters = self.ecs_client.list_clusters()["clusterArns"]
            restarted_services = []
            
            for cluster_arn in clusters:
                if "hokusai" not in cluster_arn.lower():
                    continue
                
                cluster_name = cluster_arn.split("/")[-1]
                services = self.ecs_client.list_services(cluster=cluster_arn)["serviceArns"]
                
                if not services:
                    continue
                    
                service_details = self.ecs_client.describe_services(
                    cluster=cluster_arn,
                    services=services
                )
                
                for service in service_details["services"]:
                    service_name = service["serviceName"]
                    
                    # Check if service needs restart
                    needs_restart = (
                        service["status"] != "ACTIVE" or 
                        service["runningCount"] < service["desiredCount"] or
                        service["runningCount"] == 0
                    )
                    
                    if needs_restart:
                        try:
                            # Force new deployment
                            self.ecs_client.update_service(
                                cluster=cluster_arn,
                                service=service_name,
                                forceNewDeployment=True
                            )
                            
                            restarted_services.append(f"{cluster_name}/{service_name}")
                            self.log_action("ECS Service Restart", "success", f"Restarted {service_name}")
                            
                        except Exception as e:
                            self.log_action("ECS Service Restart", "error", f"Failed to restart {service_name}: {e}")
            
            if restarted_services:
                self.log_action("ECS Services Restarted", "success", f"Restarted {len(restarted_services)} services")
            else:
                self.log_action("ECS Services", "info", "No services needed restart")
                
        except Exception as e:
            self.log_action("ECS Service Restart", "error", str(e))

    def _fix_alb_targets(self):
        """Check and fix ALB target health."""
        if not self.aws_available:
            return
            
        try:
            # Find Hokusai ALBs
            response = self.elbv2_client.describe_load_balancers()
            hokusai_albs = [
                alb for alb in response["LoadBalancers"]
                if "hokusai" in alb["LoadBalancerName"].lower()
            ]
            
            if not hokusai_albs:
                self.log_action("ALB Check", "warning", "No Hokusai ALBs found")
                return
            
            for alb in hokusai_albs:
                alb_name = alb["LoadBalancerName"]
                
                # Get target groups
                tg_response = self.elbv2_client.describe_target_groups(
                    LoadBalancerArn=alb["LoadBalancerArn"]
                )
                
                for tg in tg_response["TargetGroups"]:
                    tg_name = tg["TargetGroupName"]
                    
                    # Check target health
                    health_response = self.elbv2_client.describe_target_health(
                        TargetGroupArn=tg["TargetGroupArn"]
                    )
                    
                    unhealthy_targets = [
                        target for target in health_response["TargetHealthDescriptions"]
                        if target["TargetHealth"]["State"] != "healthy"
                    ]
                    
                    if unhealthy_targets:
                        self.log_action("ALB Target Health", "warning", 
                                      f"{len(unhealthy_targets)} unhealthy targets in {tg_name}")
                        
                        # Log details about unhealthy targets
                        for target in unhealthy_targets:
                            state = target["TargetHealth"]["State"]
                            reason = target["TargetHealth"].get("Reason", "Unknown")
                            target_id = target["Target"]["Id"]
                            self.log_action("Unhealthy Target", "info", 
                                          f"{target_id}: {state} - {reason}")
                    else:
                        self.log_action("ALB Target Health", "success", f"All targets healthy in {tg_name}")
                        
        except Exception as e:
            self.log_action("ALB Target Check", "error", str(e))

    def _wait_for_stabilization(self, timeout: int = 300):
        """Wait for services to stabilize."""
        logger.info(f"⏳ Waiting up to {timeout} seconds for services to stabilize...")
        
        start_time = time.time()
        stable_checks = 0
        required_stable_checks = 3
        
        while time.time() - start_time < timeout:
            try:
                health = self._check_service_health()
                
                if health.get("overall_status") == "healthy":
                    stable_checks += 1
                    logger.info(f"✅ Service healthy ({stable_checks}/{required_stable_checks} stable checks)")
                    
                    if stable_checks >= required_stable_checks:
                        self.log_action("Service Stabilization", "success", 
                                      f"Service stable after {time.time() - start_time:.1f} seconds")
                        return
                else:
                    stable_checks = 0
                    logger.info(f"⏸️  Service status: {health.get('overall_status', 'unknown')}")
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.warning(f"Error during stabilization check: {e}")
                time.sleep(10)
        
        self.log_action("Service Stabilization", "warning", "Timeout waiting for stabilization")

    def print_recovery_summary(self, results: Dict):
        """Print recovery summary."""
        print("\n" + "="*80)
        print("🔧 HOKUSAI REGISTRY SERVICE RECOVERY SUMMARY")
        print("="*80)
        
        # Overall result
        success = results["overall_success"]
        print(f"\n🎯 Recovery Result: {'✅ SUCCESS' if success else '❌ FAILED'}")
        print(f"⏱️  Duration: {results['duration_seconds']:.2f} seconds")
        
        if results["dry_run"]:
            print("🧪 Mode: DRY RUN (no actual changes made)")
        
        # Recovery actions
        print(f"\n📋 Recovery Actions ({len(results['recovery_log'])}):")
        for entry in results["recovery_log"]:
            timestamp = entry["timestamp"].split("T")[1].split(".")[0]  # Extract time
            status_emoji = {"success": "✅", "warning": "⚠️", "error": "❌", "info": "ℹ️"}
            emoji = status_emoji.get(entry["status"], "📝")
            
            print(f"   {timestamp} {emoji} {entry['action']}")
            if entry["details"]:
                print(f"      └─ {entry['details']}")
        
        # Next steps
        print(f"\n💡 Next Steps:")
        if success:
            print("   1. Monitor service for continued stability")
            print("   2. Check application logs for any remaining issues")
            print("   3. Run diagnostic script to verify all components")
        else:
            print("   1. Run diagnostic script for detailed analysis")
            print("   2. Check AWS CloudWatch logs for detailed errors")
            print("   3. Consider manual intervention or contact support")
            print("   4. Review recovery log above for specific failures")
        
        print("="*80)


def create_reset_endpoint():
    """Create a simple reset endpoint implementation."""
    reset_code = '''
# Add this endpoint to your health.py routes file:

@router.post("/health/mlflow/reset")
async def reset_mlflow_circuit_breaker():
    """Manually reset the MLflow circuit breaker."""
    from fastapi import HTTPException
    
    try:
        from src.utils.mlflow_config import reset_circuit_breaker
        reset_circuit_breaker()
        
        return {
            "message": "Circuit breaker reset successfully",
            "timestamp": datetime.utcnow(),
            "reset_by": "manual_api_call"
        }
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
'''
    
    print("\n📝 To enable circuit breaker reset via API, add this endpoint:")
    print(reset_code)


def main():
    parser = argparse.ArgumentParser(description="Recover Hokusai registry service")
    parser.add_argument("--api-url", help="API URL (default: https://data.hokus.ai)")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--aws-region", default="us-west-2", help="AWS region")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--output", help="Output file for recovery log")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--create-reset-endpoint", action="store_true", 
                        help="Show code to create circuit breaker reset endpoint")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.create_reset_endpoint:
        create_reset_endpoint()
        return
    
    # Run recovery
    recovery = ServiceRecovery(
        api_url=args.api_url,
        api_key=args.api_key,
        aws_region=args.aws_region
    )
    
    results = recovery.run_recovery(dry_run=args.dry_run)
    
    # Print summary
    recovery.print_recovery_summary(results)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n📁 Recovery log saved to: {args.output}")
    
    # Exit with appropriate code
    if results["overall_success"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()