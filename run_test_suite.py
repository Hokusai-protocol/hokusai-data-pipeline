#!/usr/bin/env python3
"""
Test suite runner for service degradation fixes.

This script runs all the comprehensive tests created for the service degradation fixes:
- Unit tests for circuit breaker logic
- Integration tests for health endpoints
- Load tests for service capacity
- Chaos engineering tests for failure recovery
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ PASSED")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("❌ FAILED")
        print(f"Error: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("❌ FAILED - Command not found")
        return False


def main():
    """Run all test suites."""
    print("🧪 Service Degradation Fix Test Suite Runner")
    print("=" * 60)
    
    # Change to the project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    test_suites = [
        {
            "cmd": ["python", "-m", "pytest", "tests/unit/test_circuit_breaker_enhanced.py", "-v"],
            "description": "Circuit Breaker Unit Tests",
            "critical": True
        },
        {
            "cmd": ["python", "-m", "pytest", "tests/integration/test_health_endpoints_enhanced.py", "-v", "--tb=short"],
            "description": "Health Endpoints Integration Tests",
            "critical": True
        },
        {
            "cmd": ["python", "-m", "pytest", "tests/load/test_service_load.py", "-v", "--tb=short"],
            "description": "Service Load Tests",
            "critical": False
        },
        {
            "cmd": ["python", "-m", "pytest", "tests/chaos/test_failure_recovery.py", "-v", "--tb=short"],
            "description": "Chaos Engineering Tests",
            "critical": False
        }
    ]
    
    results = []
    
    for suite in test_suites:
        success = run_command(suite["cmd"], suite["description"])
        results.append({
            "description": suite["description"],
            "success": success,
            "critical": suite["critical"]
        })
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 TEST SUITE SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    critical_failed = sum(1 for r in results if not r["success"] and r["critical"])
    
    for result in results:
        status = "✅ PASSED" if result["success"] else "❌ FAILED"
        critical_marker = " (CRITICAL)" if result["critical"] else ""
        print(f"{status} - {result['description']}{critical_marker}")
    
    print(f"\nTotal: {len(results)} suites")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Critical Failures: {critical_failed}")
    
    if critical_failed > 0:
        print("\n🚨 CRITICAL TESTS FAILED - Service degradation fixes may not be working correctly!")
        sys.exit(1)
    elif failed > 0:
        print(f"\n⚠️  Some non-critical tests failed, but core functionality appears to be working.")
        sys.exit(0)
    else:
        print(f"\n🎉 ALL TESTS PASSED - Service degradation fixes are working correctly!")
        sys.exit(0)


if __name__ == "__main__":
    main()