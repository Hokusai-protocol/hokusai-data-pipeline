#!/usr/bin/env python3
"""
Master Test Runner Script
Executes all test scripts and aggregates results
"""

import os
import sys
import subprocess
import json
import time
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestRunner:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "test_runs": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0
            }
        }
        
        # Define test scripts to run
        self.test_scripts = [
            {
                "name": "Infrastructure Health Check",
                "script": "tests/test_infrastructure_health.py",
                "requires_api_key": False,
                "critical": True
            },
            {
                "name": "Authentication Tests",
                "script": "tests/test_authentication.py",
                "requires_api_key": True,
                "critical": True
            },
            {
                "name": "Model Registration Flow",
                "script": "tests/test_model_registration_flow.py",
                "requires_api_key": True,
                "critical": True
            },
            {
                "name": "Endpoint Availability",
                "script": "test_endpoint_availability.py",
                "requires_api_key": False,
                "critical": True
            },
            {
                "name": "MLflow Routing Test",
                "script": "scripts/test_mlflow_routing.py",
                "requires_api_key": True,
                "critical": True
            },
            {
                "name": "Health Endpoints Test",
                "script": "scripts/test_health_endpoints.py",
                "requires_api_key": False,
                "critical": False
            },
            {
                "name": "Auth Registration Test",
                "script": "test_auth_registration.py",
                "requires_api_key": True,
                "critical": False
            },
            {
                "name": "Real Registration Test",
                "script": "test_real_registration.py",
                "requires_api_key": True,
                "critical": True
            },
            {
                "name": "MLflow Proxy Integration",
                "script": "tests/integration/test_mlflow_proxy_integration.py",
                "requires_api_key": True,
                "critical": False
            }
        ]
        
    def check_script_exists(self, script_path: str) -> bool:
        """Check if a test script exists"""
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), script_path)
        return os.path.exists(full_path)
        
    def run_test_script(self, test_info: Dict) -> Dict:
        """Run a single test script and capture results"""
        script_name = test_info["name"]
        script_path = test_info["script"]
        
        print(f"\n{'='*60}")
        print(f"🧪 Running: {script_name}")
        print(f"📄 Script: {script_path}")
        print(f"{'='*60}")
        
        result = {
            "name": script_name,
            "script": script_path,
            "start_time": datetime.now().isoformat(),
            "status": "unknown",
            "duration_seconds": 0,
            "output": "",
            "error": ""
        }
        
        # Check if script exists
        if not self.check_script_exists(script_path):
            print(f"❌ Script not found: {script_path}")
            result["status"] = "not_found"
            result["error"] = "Script file not found"
            return result
            
        # Check if API key is required
        if test_info["requires_api_key"] and not self.api_key:
            print(f"⏭️  Skipping (requires API key)")
            result["status"] = "skipped"
            result["error"] = "API key required but not provided"
            return result
            
        # Build command
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), script_path)
        cmd = [sys.executable, full_path]
        
        # Set up environment
        env = os.environ.copy()
        if self.api_key:
            env["HOKUSAI_API_KEY"] = self.api_key
            
        # Run the test
        start_time = time.time()
        try:
            process = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            duration = time.time() - start_time
            result["duration_seconds"] = round(duration, 2)
            result["output"] = process.stdout
            result["error"] = process.stderr
            result["return_code"] = process.returncode
            
            if process.returncode == 0:
                result["status"] = "passed"
                print(f"✅ Test passed in {duration:.1f}s")
            else:
                result["status"] = "failed"
                print(f"❌ Test failed with code {process.returncode}")
                
            # Print last few lines of output
            output_lines = process.stdout.strip().split('\n')
            if len(output_lines) > 5:
                print("\nLast 5 lines of output:")
                for line in output_lines[-5:]:
                    print(f"  {line}")
                    
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            result["duration_seconds"] = round(duration, 2)
            result["status"] = "timeout"
            result["error"] = f"Test timed out after {duration:.1f}s"
            print(f"⏱️  Test timed out after {duration:.1f}s")
            
        except Exception as e:
            duration = time.time() - start_time
            result["duration_seconds"] = round(duration, 2)
            result["status"] = "error"
            result["error"] = str(e)
            print(f"❌ Error running test: {str(e)}")
            
        return result
        
    def analyze_test_output(self, result: Dict) -> Dict:
        """Analyze test output for key findings"""
        findings = {
            "errors": [],
            "warnings": [],
            "successes": []
        }
        
        output = result.get("output", "")
        
        # Look for common patterns
        if "401" in output or "Unauthorized" in output:
            findings["errors"].append("Authentication failures detected")
        if "404" in output:
            findings["warnings"].append("Some endpoints not found")
        if "503" in output:
            findings["errors"].append("Service unavailable errors")
        if "Connection refused" in output:
            findings["errors"].append("Connection refused - service may be down")
        if "timeout" in output.lower():
            findings["warnings"].append("Timeout issues detected")
            
        # Look for success indicators
        if "✅" in output:
            success_count = output.count("✅")
            findings["successes"].append(f"{success_count} successful checks")
        if "Model registered successfully" in output:
            findings["successes"].append("Model registration successful")
            
        return findings
        
    def generate_summary_report(self):
        """Generate a comprehensive summary report"""
        print("\n" + "="*60)
        print("📊 TEST EXECUTION SUMMARY REPORT")
        print("="*60)
        
        print(f"\n📅 Timestamp: {self.results['timestamp']}")
        print(f"🔑 API Key: {self.api_key[:10]}...{self.api_key[-4:] if self.api_key else 'Not provided'}")
        
        # Overall summary
        print(f"\n📈 Overall Results:")
        print(f"  Total Tests: {self.results['summary']['total_tests']}")
        print(f"  ✅ Passed: {self.results['summary']['passed']}")
        print(f"  ❌ Failed: {self.results['summary']['failed']}")
        print(f"  ⏭️  Skipped: {self.results['summary']['skipped']}")
        
        if self.results['summary']['total_tests'] > 0:
            success_rate = (self.results['summary']['passed'] / 
                          self.results['summary']['total_tests']) * 100
            print(f"  📊 Success Rate: {success_rate:.1f}%")
            
        # Critical test results
        print("\n🚨 Critical Test Results:")
        critical_tests = [t for t in self.test_scripts if t.get("critical")]
        for test in critical_tests:
            test_name = test["name"]
            if test_name in self.results["test_runs"]:
                result = self.results["test_runs"][test_name]
                status_icon = {
                    "passed": "✅",
                    "failed": "❌",
                    "skipped": "⏭️",
                    "timeout": "⏱️",
                    "not_found": "❓",
                    "error": "💥"
                }.get(result["status"], "❓")
                
                print(f"  {status_icon} {test_name}: {result['status']}")
                if result["status"] == "failed":
                    # Extract key error from output
                    error_lines = result.get("error", "").strip().split('\n')
                    if error_lines and error_lines[0]:
                        print(f"     → {error_lines[0][:80]}...")
                        
        # Key findings across all tests
        print("\n🔍 Key Findings:")
        all_errors = []
        all_warnings = []
        all_successes = []
        
        for test_name, result in self.results["test_runs"].items():
            findings = self.analyze_test_output(result)
            all_errors.extend(findings["errors"])
            all_warnings.extend(findings["warnings"])
            all_successes.extend(findings["successes"])
            
        if all_errors:
            print("\n  ❌ Errors:")
            for error in set(all_errors):
                print(f"     • {error}")
        
        if all_warnings:
            print("\n  ⚠️  Warnings:")
            for warning in set(all_warnings):
                print(f"     • {warning}")
                
        if all_successes:
            print("\n  ✅ Successes:")
            for success in set(all_successes):
                print(f"     • {success}")
                
        # Infrastructure status
        print("\n🏗️  Infrastructure Status:")
        infra_test = self.results["test_runs"].get("Infrastructure Health Check", {})
        if infra_test.get("status") == "passed":
            print("  ✅ Infrastructure health checks passed")
        else:
            print("  ❌ Infrastructure health checks failed or not run")
            
        # Authentication status
        auth_test = self.results["test_runs"].get("Authentication Tests", {})
        if auth_test.get("status") == "passed":
            print("  ✅ Authentication system working")
        elif auth_test.get("status") == "skipped":
            print("  ⏭️  Authentication tests skipped (no API key)")
        else:
            print("  ❌ Authentication system has issues")
            
        # Model registration status
        reg_test = self.results["test_runs"].get("Model Registration Flow", {})
        if reg_test.get("status") == "passed":
            print("  ✅ Model registration workflow functional")
        elif reg_test.get("status") == "skipped":
            print("  ⏭️  Model registration tests skipped (no API key)")
        else:
            print("  ❌ Model registration workflow has issues")
            
        # Save detailed results
        report_file = "test_execution_summary.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed results saved to: {report_file}")
        
        # Generate recommendations
        print("\n🔧 Recommendations for Infrastructure Team:")
        
        recommendations = []
        
        if any("503" in r.get("output", "") for r in self.results["test_runs"].values()):
            recommendations.append("Fix service availability issues (503 errors)")
            
        if any("404" in r.get("output", "") for r in self.results["test_runs"].values()):
            recommendations.append("Review ALB routing rules for missing endpoints")
            
        if any("authentication" in r.get("error", "").lower() for r in self.results["test_runs"].values()):
            recommendations.append("Verify auth service configuration and API key validation")
            
        if any("artifact" in r.get("output", "") and "failed" in r.get("output", "") 
               for r in self.results["test_runs"].values()):
            recommendations.append("Configure MLflow artifact storage (S3 bucket)")
            
        if not recommendations:
            recommendations.append("All systems appear operational - continue monitoring")
            
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
            
        # Create issues summary for infrastructure team
        self.create_infrastructure_issues_report()
        
        print("\n✅ Test execution completed!")
        
    def create_infrastructure_issues_report(self):
        """Create a focused report for the infrastructure team"""
        report = {
            "title": "Infrastructure Issues Report - Model Registration Testing",
            "generated_at": datetime.now().isoformat(),
            "executive_summary": "",
            "critical_issues": [],
            "warnings": [],
            "working_features": [],
            "recommendations": []
        }
        
        # Analyze results for infrastructure issues
        for test_name, result in self.results["test_runs"].items():
            if result["status"] == "failed":
                # Extract infrastructure-related failures
                output = result.get("output", "") + result.get("error", "")
                
                if "503" in output:
                    report["critical_issues"].append({
                        "issue": "Service Unavailable (503)",
                        "test": test_name,
                        "impact": "API endpoints returning 503, preventing model registration",
                        "recommendation": "Check ECS task health and ALB target group configuration"
                    })
                    
                if "404" in output and "mlflow" in output.lower():
                    report["critical_issues"].append({
                        "issue": "MLflow endpoints not found (404)",
                        "test": test_name,
                        "impact": "MLflow proxy routing not working correctly",
                        "recommendation": "Review ALB listener rules for /api/mlflow/* paths"
                    })
                    
                if "connection refused" in output.lower():
                    report["critical_issues"].append({
                        "issue": "Connection Refused",
                        "test": test_name,
                        "impact": "Service unreachable",
                        "recommendation": "Verify security groups and network ACLs"
                    })
                    
            elif result["status"] == "passed":
                # Note working features
                if "Infrastructure Health" in test_name:
                    report["working_features"].append("Basic infrastructure health checks pass")
                elif "Authentication" in test_name:
                    report["working_features"].append("Authentication system operational")
                elif "Model Registration" in test_name:
                    report["working_features"].append("Model registration workflow functional")
                    
        # Generate executive summary
        if report["critical_issues"]:
            report["executive_summary"] = (
                f"Testing identified {len(report['critical_issues'])} critical infrastructure issues "
                f"preventing model registration. Immediate attention required."
            )
        else:
            report["executive_summary"] = (
                "Infrastructure testing completed successfully. "
                "Model registration functionality is operational."
            )
            
        # Save infrastructure report
        with open("infrastructure_issues_report.json", 'w') as f:
            json.dump(report, f, indent=2)
            
        # Also create a markdown version
        with open("INFRASTRUCTURE_ISSUES.md", 'w') as f:
            f.write(f"# Infrastructure Issues Report\n\n")
            f.write(f"**Generated**: {report['generated_at']}\n\n")
            f.write(f"## Executive Summary\n\n{report['executive_summary']}\n\n")
            
            if report["critical_issues"]:
                f.write("## Critical Issues\n\n")
                for i, issue in enumerate(report["critical_issues"], 1):
                    f.write(f"### {i}. {issue['issue']}\n\n")
                    f.write(f"- **Test**: {issue['test']}\n")
                    f.write(f"- **Impact**: {issue['impact']}\n")
                    f.write(f"- **Recommendation**: {issue['recommendation']}\n\n")
                    
            if report["working_features"]:
                f.write("## Working Features\n\n")
                for feature in report["working_features"]:
                    f.write(f"- ✅ {feature}\n")
                    
        print("\n📄 Infrastructure issues report created: INFRASTRUCTURE_ISSUES.md")
        
    def run_all_tests(self):
        """Run all test scripts"""
        print("🚀 Starting Comprehensive Test Suite...")
        print(f"📋 Running {len(self.test_scripts)} test scripts")
        
        if self.api_key:
            print(f"🔑 Using API key: {self.api_key[:10]}...{self.api_key[-4:]}")
        else:
            print("⚠️  No API key provided - some tests will be skipped")
            
        # Run each test
        for test_info in self.test_scripts:
            result = self.run_test_script(test_info)
            self.results["test_runs"][test_info["name"]] = result
            self.results["summary"]["total_tests"] += 1
            
            if result["status"] == "passed":
                self.results["summary"]["passed"] += 1
            elif result["status"] == "failed":
                self.results["summary"]["failed"] += 1
            elif result["status"] in ["skipped", "not_found"]:
                self.results["summary"]["skipped"] += 1
            else:
                self.results["summary"]["failed"] += 1
                
            # Small delay between tests
            time.sleep(1)
            
        # Generate summary report
        self.generate_summary_report()
        
        return self.results


if __name__ == "__main__":
    # Check for API key
    api_key = os.environ.get("HOKUSAI_API_KEY")
    if not api_key and len(sys.argv) > 1:
        api_key = sys.argv[1]
        
    runner = TestRunner(api_key)
    results = runner.run_all_tests()
    
    # Exit with appropriate code
    if results["summary"]["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)