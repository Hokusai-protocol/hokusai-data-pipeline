#!/usr/bin/env python3
"""
Comprehensive diagnostic script for Hokusai registry service health.
Checks all components: ALB, ECS, MLflow, Database, Circuit Breaker state.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import boto3
import psycopg2
import redis
import requests
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ServiceDiagnostic:
    """Comprehensive service diagnostic tool."""
    
    def __init__(self, api_url: str = None, api_key: str = None, aws_region: str = "us-west-2"):
        self.api_url = api_url or os.getenv("API_URL", "https://data.hokus.ai")
        self.api_key = api_key or os.getenv("API_KEY")
        self.aws_region = aws_region
        self.results = {}
        self.session = requests.Session()
        self.session.timeout = 10
        
        # AWS clients
        try:
            self.elbv2_client = boto3.client('elbv2', region_name=aws_region)
            self.ecs_client = boto3.client('ecs', region_name=aws_region)
            self.rds_client = boto3.client('rds', region_name=aws_region)
            self.ec2_client = boto3.client('ec2', region_name=aws_region)
            self.aws_available = True
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"AWS clients not available: {e}")
            self.aws_available = False

    def run_diagnostic(self) -> Dict:
        """Run comprehensive diagnostic check."""
        logger.info("Starting comprehensive service diagnostic...")
        start_time = time.time()
        
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "diagnostic_duration_seconds": 0,
            "overall_status": "unknown",
            "critical_issues": [],
            "warnings": [],
            "recommendations": [],
            "checks": {}
        }
        
        # Run all diagnostic checks
        checks = [
            ("api_connectivity", self._check_api_connectivity),
            ("health_endpoints", self._check_health_endpoints),
            ("circuit_breaker", self._check_circuit_breaker_state),
            ("mlflow_service", self._check_mlflow_service),
            ("database", self._check_database_connectivity),
            ("redis", self._check_redis_connectivity),
            ("aws_infrastructure", self._check_aws_infrastructure),
            ("service_metrics", self._check_service_metrics),
        ]
        
        for check_name, check_func in checks:
            logger.info(f"Running check: {check_name}")
            try:
                self.results["checks"][check_name] = check_func()
            except Exception as e:
                logger.error(f"Check {check_name} failed with exception: {e}")
                self.results["checks"][check_name] = {
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
        
        # Analyze results and provide overall assessment
        self._analyze_results()
        
        self.results["diagnostic_duration_seconds"] = time.time() - start_time
        logger.info(f"Diagnostic completed in {self.results['diagnostic_duration_seconds']:.2f} seconds")
        
        return self.results

    def _check_api_connectivity(self) -> Dict:
        """Check basic API connectivity."""
        result = {
            "status": "unknown",
            "response_time_ms": None,
            "status_code": None,
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            response = self.session.get(f"{self.api_url}/health", timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            result["response_time_ms"] = response_time
            result["status_code"] = response.status_code
            
            if response.status_code == 200:
                result["status"] = "healthy"
                data = response.json()
                result["api_status"] = data.get("status", "unknown")
            elif response.status_code in [503, 502, 504]:
                result["status"] = "degraded"
                result["error"] = f"Service unavailable (HTTP {response.status_code})"
            else:
                result["status"] = "unhealthy"
                result["error"] = f"Unexpected status code: {response.status_code}"
                
            if response_time > 5000:
                result["warning"] = f"Slow response time: {response_time:.0f}ms"
                
        except requests.exceptions.Timeout:
            result["status"] = "unhealthy"
            result["error"] = "Request timeout"
        except requests.exceptions.ConnectionError as e:
            result["status"] = "unhealthy"
            result["error"] = f"Connection error: {str(e)}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_health_endpoints(self) -> Dict:
        """Check all health endpoints."""
        endpoints = {
            "/health": "Main health check",
            "/ready": "Readiness check", 
            "/live": "Liveness check",
            "/health/mlflow": "MLflow health check",
            "/metrics": "Metrics endpoint"
        }
        
        result = {
            "status": "unknown",
            "endpoints": {},
            "healthy_count": 0,
            "total_count": len(endpoints),
            "timestamp": datetime.now().isoformat()
        }
        
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        for endpoint, description in endpoints.items():
            endpoint_result = {
                "description": description,
                "status": "unknown",
                "response_time_ms": None,
                "status_code": None,
                "error": None
            }
            
            try:
                start_time = time.time()
                response = self.session.get(
                    f"{self.api_url}{endpoint}",
                    headers=headers,
                    timeout=10
                )
                response_time = (time.time() - start_time) * 1000
                
                endpoint_result["response_time_ms"] = response_time
                endpoint_result["status_code"] = response.status_code
                
                if response.status_code == 200:
                    endpoint_result["status"] = "healthy"
                    result["healthy_count"] += 1
                    
                    # Parse response for additional details
                    try:
                        data = response.json()
                        if endpoint == "/health":
                            endpoint_result["services"] = data.get("services", {})
                        elif endpoint == "/ready":
                            endpoint_result["ready"] = data.get("ready", False)
                            endpoint_result["degraded_mode"] = data.get("degraded_mode", False)
                        elif endpoint == "/health/mlflow":
                            endpoint_result["circuit_breaker_state"] = data.get("circuit_breaker_state")
                            endpoint_result["connected"] = data.get("connected", False)
                    except:
                        pass  # Not JSON response, that's ok
                        
                elif response.status_code == 503:
                    endpoint_result["status"] = "degraded"
                    endpoint_result["error"] = "Service unavailable"
                else:
                    endpoint_result["status"] = "unhealthy"
                    endpoint_result["error"] = f"HTTP {response.status_code}"
                    
            except Exception as e:
                endpoint_result["status"] = "error"
                endpoint_result["error"] = str(e)
                
            result["endpoints"][endpoint] = endpoint_result
        
        # Overall endpoint health
        if result["healthy_count"] == result["total_count"]:
            result["status"] = "healthy"
        elif result["healthy_count"] > 0:
            result["status"] = "degraded"
        else:
            result["status"] = "unhealthy"
            
        return result

    def _check_circuit_breaker_state(self) -> Dict:
        """Check MLflow circuit breaker state."""
        result = {
            "status": "unknown",
            "circuit_breaker_state": "unknown",
            "details": {},
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                
            response = self.session.get(
                f"{self.api_url}/health/mlflow",
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 503]:
                data = response.json()
                result["circuit_breaker_state"] = data.get("circuit_breaker_state", "unknown")
                result["details"] = data.get("circuit_breaker_details", {})
                
                if result["circuit_breaker_state"] == "CLOSED":
                    result["status"] = "healthy"
                elif result["circuit_breaker_state"] == "HALF_OPEN":
                    result["status"] = "recovering"
                elif result["circuit_breaker_state"] == "OPEN":
                    result["status"] = "degraded"
                    result["error"] = "Circuit breaker is open"
                else:
                    result["status"] = "unknown"
                    result["error"] = f"Unknown circuit breaker state: {result['circuit_breaker_state']}"
            else:
                result["status"] = "error"
                result["error"] = f"HTTP {response.status_code}: {response.text}"
                
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_mlflow_service(self) -> Dict:
        """Check MLflow service directly."""
        result = {
            "status": "unknown",
            "mlflow_url": None,
            "response_time_ms": None,
            "error": None,
            "experiments_accessible": False,
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to determine MLflow URL
        mlflow_urls = [
            os.getenv("MLFLOW_TRACKING_URI"),
            "http://mlflow.hokusai-development.local:5000",
            "https://mlflow.hokus.ai",
            "http://localhost:5000"
        ]
        
        for url in mlflow_urls:
            if not url:
                continue
                
            result["mlflow_url"] = url
            
            try:
                start_time = time.time()
                response = self.session.get(f"{url}/health", timeout=5)
                response_time = (time.time() - start_time) * 1000
                
                result["response_time_ms"] = response_time
                
                if response.status_code == 200:
                    result["status"] = "healthy"
                    
                    # Try to access experiments
                    try:
                        exp_response = self.session.get(f"{url}/api/2.0/mlflow/experiments/list", timeout=5)
                        if exp_response.status_code == 200:
                            result["experiments_accessible"] = True
                    except:
                        pass
                    break
                    
            except requests.exceptions.Timeout:
                result["error"] = "Timeout connecting to MLflow"
            except requests.exceptions.ConnectionError:
                result["error"] = "Connection error to MLflow"
            except Exception as e:
                result["error"] = str(e)
        
        if result["status"] == "unknown":
            result["status"] = "unhealthy"
            if not result["error"]:
                result["error"] = "Could not connect to any MLflow URL"
                
        return result

    def _check_database_connectivity(self) -> Dict:
        """Check PostgreSQL database connectivity."""
        result = {
            "status": "unknown",
            "connection_time_ms": None,
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to get database URL from various sources
        db_urls = [
            os.getenv("POSTGRES_URI"),
            os.getenv("DATABASE_URL"),
            "postgresql://mlflow:mlflow_password@postgres/mlflow_db"
        ]
        
        for db_url in db_urls:
            if not db_url:
                continue
                
            try:
                start_time = time.time()
                conn = psycopg2.connect(db_url, connect_timeout=5)
                connection_time = (time.time() - start_time) * 1000
                
                # Test basic query
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                conn.close()
                
                result["status"] = "healthy"
                result["connection_time_ms"] = connection_time
                break
                
            except psycopg2.OperationalError as e:
                result["error"] = f"Database connection error: {str(e)}"
            except Exception as e:
                result["error"] = str(e)
        
        if result["status"] == "unknown":
            result["status"] = "unhealthy"
            if not result["error"]:
                result["error"] = "No database connection available"
                
        return result

    def _check_redis_connectivity(self) -> Dict:
        """Check Redis connectivity."""
        result = {
            "status": "unknown",
            "response_time_ms": None,
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        redis_configs = [
            {"host": os.getenv("REDIS_HOST", "redis"), "port": int(os.getenv("REDIS_PORT", 6379))},
            {"host": "localhost", "port": 6379},
        ]
        
        for config in redis_configs:
            try:
                start_time = time.time()
                r = redis.Redis(
                    host=config["host"],
                    port=config["port"],
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                r.ping()
                response_time = (time.time() - start_time) * 1000
                
                result["status"] = "healthy"
                result["response_time_ms"] = response_time
                break
                
            except redis.ConnectionError as e:
                result["error"] = f"Redis connection error: {str(e)}"
            except Exception as e:
                result["error"] = str(e)
        
        if result["status"] == "unknown":
            result["status"] = "unhealthy"
            if not result["error"]:
                result["error"] = "No Redis connection available"
                
        return result

    def _check_aws_infrastructure(self) -> Dict:
        """Check AWS infrastructure components."""
        result = {
            "status": "unknown",
            "checks": {},
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        if not self.aws_available:
            result["status"] = "skipped"
            result["error"] = "AWS clients not available"
            return result
            
        try:
            # Check ALB
            result["checks"]["alb"] = self._check_alb_health()
            
            # Check ECS Services
            result["checks"]["ecs"] = self._check_ecs_services()
            
            # Check RDS
            result["checks"]["rds"] = self._check_rds_health()
            
            # Overall AWS infrastructure status
            aws_statuses = [check.get("status") for check in result["checks"].values()]
            if all(status == "healthy" for status in aws_statuses):
                result["status"] = "healthy"
            elif any(status == "healthy" for status in aws_statuses):
                result["status"] = "degraded"
            else:
                result["status"] = "unhealthy"
                
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_alb_health(self) -> Dict:
        """Check Application Load Balancer health."""
        result = {
            "status": "unknown",
            "load_balancers": [],
            "error": None
        }
        
        try:
            # Find ALBs related to Hokusai
            response = self.elbv2_client.describe_load_balancers()
            hokusai_albs = [
                alb for alb in response["LoadBalancers"]
                if "hokusai" in alb["LoadBalancerName"].lower()
            ]
            
            if not hokusai_albs:
                result["status"] = "unknown"
                result["error"] = "No Hokusai ALBs found"
                return result
            
            healthy_count = 0
            for alb in hokusai_albs:
                alb_info = {
                    "name": alb["LoadBalancerName"],
                    "state": alb["State"]["Code"],
                    "dns_name": alb["DNSName"],
                    "healthy_targets": 0,
                    "total_targets": 0
                }
                
                # Check target health
                try:
                    tg_response = self.elbv2_client.describe_target_groups(
                        LoadBalancerArn=alb["LoadBalancerArn"]
                    )
                    
                    for tg in tg_response["TargetGroups"]:
                        health_response = self.elbv2_client.describe_target_health(
                            TargetGroupArn=tg["TargetGroupArn"]
                        )
                        
                        total_targets = len(health_response["TargetHealthDescriptions"])
                        healthy_targets = sum(
                            1 for target in health_response["TargetHealthDescriptions"]
                            if target["TargetHealth"]["State"] == "healthy"
                        )
                        
                        alb_info["total_targets"] += total_targets
                        alb_info["healthy_targets"] += healthy_targets
                        
                except Exception as e:
                    alb_info["target_health_error"] = str(e)
                
                if alb["State"]["Code"] == "active" and alb_info["healthy_targets"] > 0:
                    healthy_count += 1
                    
                result["load_balancers"].append(alb_info)
            
            if healthy_count == len(hokusai_albs):
                result["status"] = "healthy"
            elif healthy_count > 0:
                result["status"] = "degraded"
            else:
                result["status"] = "unhealthy"
                
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_ecs_services(self) -> Dict:
        """Check ECS services."""
        result = {
            "status": "unknown",
            "services": [],
            "error": None
        }
        
        try:
            # List ECS clusters
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
                        service_info = {
                            "name": service["serviceName"],
                            "status": service["status"],
                            "running_count": service["runningCount"],
                            "desired_count": service["desiredCount"],
                            "pending_count": service["pendingCount"],
                            "cluster": cluster_arn.split("/")[-1]
                        }
                        result["services"].append(service_info)
            
            if not result["services"]:
                result["status"] = "unknown"
                result["error"] = "No Hokusai ECS services found"
            else:
                healthy_services = sum(
                    1 for svc in result["services"]
                    if svc["status"] == "ACTIVE" and svc["running_count"] == svc["desired_count"]
                )
                
                if healthy_services == len(result["services"]):
                    result["status"] = "healthy"
                elif healthy_services > 0:
                    result["status"] = "degraded"
                else:
                    result["status"] = "unhealthy"
                    
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_rds_health(self) -> Dict:
        """Check RDS database instances."""
        result = {
            "status": "unknown",
            "instances": [],
            "error": None
        }
        
        try:
            response = self.rds_client.describe_db_instances()
            hokusai_instances = [
                db for db in response["DBInstances"]
                if "hokusai" in db["DBInstanceIdentifier"].lower() or 
                   "mlflow" in db["DBInstanceIdentifier"].lower()
            ]
            
            if not hokusai_instances:
                result["status"] = "unknown"
                result["error"] = "No Hokusai RDS instances found"
                return result
            
            healthy_count = 0
            for db in hokusai_instances:
                db_info = {
                    "identifier": db["DBInstanceIdentifier"],
                    "status": db["DBInstanceStatus"],
                    "engine": db["Engine"],
                    "endpoint": db.get("Endpoint", {}).get("Address"),
                    "port": db.get("Endpoint", {}).get("Port")
                }
                
                if db["DBInstanceStatus"] == "available":
                    healthy_count += 1
                    
                result["instances"].append(db_info)
            
            if healthy_count == len(hokusai_instances):
                result["status"] = "healthy"
            elif healthy_count > 0:
                result["status"] = "degraded"
            else:
                result["status"] = "unhealthy"
                
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _check_service_metrics(self) -> Dict:
        """Check service metrics and performance indicators."""
        result = {
            "status": "unknown",
            "metrics": {},
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Get metrics endpoint
            response = self.session.get(f"{self.api_url}/metrics", timeout=10)
            
            if response.status_code == 200:
                result["status"] = "healthy"
                
                # Parse Prometheus metrics if available
                metrics_text = response.text
                result["metrics"]["raw_size"] = len(metrics_text)
                result["metrics"]["lines"] = len(metrics_text.split('\n'))
                
                # Look for specific metrics
                if "mlflow_circuit_breaker" in metrics_text:
                    result["metrics"]["circuit_breaker_metrics"] = True
                if "http_requests_total" in metrics_text:
                    result["metrics"]["request_metrics"] = True
                    
            else:
                result["status"] = "degraded" 
                result["error"] = f"HTTP {response.status_code}"
                
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _analyze_results(self):
        """Analyze diagnostic results and provide recommendations."""
        critical_issues = []
        warnings = []
        recommendations = []
        
        # Check API connectivity
        api_check = self.results["checks"].get("api_connectivity", {})
        if api_check.get("status") == "unhealthy":
            critical_issues.append("API is not accessible - service is completely down")
            recommendations.append("Check ALB and ECS service status immediately")
        elif api_check.get("status") == "degraded":
            warnings.append("API is responding but with errors - service degraded")
        
        # Check circuit breaker
        cb_check = self.results["checks"].get("circuit_breaker", {})
        if cb_check.get("circuit_breaker_state") == "OPEN":
            critical_issues.append("MLflow circuit breaker is OPEN - MLflow functionality unavailable")
            recommendations.append("Check MLflow service and consider manual reset if needed")
        elif cb_check.get("circuit_breaker_state") == "HALF_OPEN":
            warnings.append("MLflow circuit breaker is in recovery mode")
            recommendations.append("Monitor MLflow recovery progress")
        
        # Check database
        db_check = self.results["checks"].get("database", {})
        if db_check.get("status") == "unhealthy":
            critical_issues.append("Database is not accessible - core functionality affected")
            recommendations.append("Check RDS instance and network connectivity")
        elif db_check.get("connection_time_ms", 0) > 1000:
            warnings.append(f"Database response time is slow: {db_check['connection_time_ms']:.0f}ms")
        
        # Check AWS infrastructure
        aws_check = self.results["checks"].get("aws_infrastructure", {})
        if aws_check.get("status") == "unhealthy":
            critical_issues.append("AWS infrastructure components are unhealthy")
            recommendations.append("Check ALB, ECS services, and RDS instances in AWS console")
        
        # Overall status assessment
        if critical_issues:
            overall_status = "critical"
        elif warnings:
            overall_status = "degraded" 
        else:
            overall_status = "healthy"
        
        # Add general recommendations based on findings
        if overall_status != "healthy":
            recommendations.extend([
                "Run the recovery script: scripts/recover_service.py",
                "Check AWS CloudWatch logs for detailed error information",
                "Consider scaling ECS services if under high load"
            ])
        
        self.results.update({
            "overall_status": overall_status,
            "critical_issues": critical_issues,
            "warnings": warnings,
            "recommendations": recommendations
        })

    def print_summary(self):
        """Print a human-readable summary of the diagnostic results."""
        print("\n" + "="*80)
        print("🏥 HOKUSAI REGISTRY SERVICE DIAGNOSTIC SUMMARY")
        print("="*80)
        
        # Overall status
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "critical": "🚨",
            "unhealthy": "❌",
            "unknown": "❓"
        }
        
        overall = self.results["overall_status"]
        print(f"\n🎯 Overall Status: {status_emoji.get(overall, '❓')} {overall.upper()}")
        
        # Critical issues
        if self.results["critical_issues"]:
            print(f"\n🚨 Critical Issues ({len(self.results['critical_issues'])}):")
            for issue in self.results["critical_issues"]:
                print(f"   • {issue}")
        
        # Warnings
        if self.results["warnings"]:
            print(f"\n⚠️  Warnings ({len(self.results['warnings'])}):")
            for warning in self.results["warnings"]:
                print(f"   • {warning}")
        
        # Component status summary
        print(f"\n📊 Component Status:")
        for check_name, check_result in self.results["checks"].items():
            status = check_result.get("status", "unknown")
            emoji = status_emoji.get(status, "❓")
            check_display = check_name.replace("_", " ").title()
            print(f"   {emoji} {check_display}: {status}")
            
            # Add specific details for key components
            if check_name == "circuit_breaker" and "circuit_breaker_state" in check_result:
                cb_state = check_result["circuit_breaker_state"]
                print(f"      └─ Circuit Breaker: {cb_state}")
            elif check_name == "api_connectivity" and check_result.get("response_time_ms"):
                response_time = check_result["response_time_ms"]
                print(f"      └─ Response Time: {response_time:.0f}ms")
        
        # Recommendations
        if self.results["recommendations"]:
            print(f"\n💡 Recommendations:")
            for i, rec in enumerate(self.results["recommendations"], 1):
                print(f"   {i}. {rec}")
        
        print(f"\n⏱️  Diagnostic completed in {self.results['diagnostic_duration_seconds']:.2f} seconds")
        print("="*80)


def main():
    parser = argparse.ArgumentParser(description="Diagnose Hokusai registry service health")
    parser.add_argument("--api-url", help="API URL to check (default: https://data.hokus.ai)")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--aws-region", default="us-west-2", help="AWS region")
    parser.add_argument("--output", help="Output file for JSON results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run diagnostic
    diagnostic = ServiceDiagnostic(
        api_url=args.api_url,
        api_key=args.api_key,
        aws_region=args.aws_region
    )
    
    results = diagnostic.run_diagnostic()
    
    # Print summary
    diagnostic.print_summary()
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n📁 Detailed results saved to: {args.output}")
    
    # Exit with appropriate code
    if results["overall_status"] == "critical":
        sys.exit(2)
    elif results["overall_status"] in ["degraded", "unhealthy"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()