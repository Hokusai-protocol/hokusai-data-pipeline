#!/usr/bin/env python3
"""
Endpoint test runner with multiple testing modes.

This script provides different ways to run the comprehensive endpoint tests:
1. Unit tests (with mocks)
2. Integration tests (requires running API)
3. Live API tests (tests against real API server)
4. Full suite (all tests)

Usage:
    python scripts/run_endpoint_tests.py --mode unit
    python scripts/run_endpoint_tests.py --mode integration --api-url http://localhost:8000
    python scripts/run_endpoint_tests.py --mode live --api-url https://api.hokus.ai --api-key your-key
    python scripts/run_endpoint_tests.py --mode full --coverage
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


class EndpointTestRunner:
    """Test runner for endpoint testing with different modes."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.test_dir = self.project_root / "tests"
        
    def run_unit_tests(self, verbose: bool = True, coverage: bool = False) -> int:
        """Run unit tests with mocks."""
        print("🧪 Running Unit Tests (with mocks)")
        print("=" * 50)
        
        cmd = [
            "python", "-m", "pytest",
            "tests/unit/test_api_endpoints_unit.py",
            "-v" if verbose else "-q",
            "--tb=short",
            "-m", "not slow"
        ]
        
        if coverage:
            cmd.extend(["--cov=src.api", "--cov-report=term-missing"])
            
        return subprocess.run(cmd, cwd=self.project_root).returncode
        
    def run_integration_tests(self, api_url: str, api_key: Optional[str] = None, 
                            verbose: bool = True) -> int:
        """Run integration tests against running API."""
        print(f"🔗 Running Integration Tests against {api_url}")
        print("=" * 50)
        
        # Set environment variables for integration tests
        env = os.environ.copy()
        env["TEST_API_URL"] = api_url
        if api_key:
            env["TEST_API_KEY"] = api_key
        env["PYTEST_CURRENT_TEST"] = "integration"
        
        cmd = [
            "python", "-m", "pytest", 
            "tests/integration/test_comprehensive_endpoint_suite.py",
            "-v" if verbose else "-q",
            "--tb=short",
            "-m", "integration"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root, env=env).returncode
        
    def run_live_api_tests(self, api_url: str, api_key: str, verbose: bool = True) -> int:
        """Run tests against live API using the test script."""
        print(f"🌐 Running Live API Tests against {api_url}")
        print("=" * 50)
        
        cmd = [
            "python", "scripts/test_api_endpoints.py",
            "--base-url", api_url,
            "--api-key", api_key
        ]
        
        return subprocess.run(cmd, cwd=self.project_root).returncode
        
    def run_full_suite(self, coverage: bool = False, verbose: bool = True) -> int:
        """Run the complete test suite."""
        print("🎯 Running Full Test Suite")
        print("=" * 50)
        
        cmd = [
            "python", "-m", "pytest",
            "tests/unit/test_api_endpoints_unit.py",
            "tests/integration/test_comprehensive_endpoint_suite.py", 
            "-v" if verbose else "-q",
            "--tb=short"
        ]
        
        if coverage:
            cmd.extend([
                "--cov=src.api",
                "--cov-report=html",
                "--cov-report=term-missing",
                "--cov-fail-under=80"
            ])
            
        return subprocess.run(cmd, cwd=self.project_root).returncode
        
    def run_specific_category(self, category: str, verbose: bool = True) -> int:
        """Run tests for a specific endpoint category."""
        print(f"📂 Running {category.title()} Endpoint Tests")
        print("=" * 50)
        
        cmd = [
            "python", "-m", "pytest",
            "-v" if verbose else "-q", 
            "--tb=short",
            "-m", category
        ]
        
        # Add appropriate test files
        if category in ["health", "models", "dspy", "mlflow"]:
            cmd.extend([
                "tests/unit/test_api_endpoints_unit.py",
                "tests/integration/test_comprehensive_endpoint_suite.py"
            ])
        else:
            print(f"❌ Unknown category: {category}")
            return 1
            
        return subprocess.run(cmd, cwd=self.project_root).returncode
        
    def check_dependencies(self) -> bool:
        """Check if required dependencies are available."""
        required_packages = ["pytest", "fastapi", "httpx", "tabulate"]
        missing = []
        
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)
                
        if missing:
            print(f"❌ Missing required packages: {', '.join(missing)}")
            print("Install with: pip install " + " ".join(missing))
            return False
            
        return True
        
    def setup_test_environment(self) -> bool:
        """Set up the test environment."""
        # Ensure test directories exist
        (self.project_root / "tests" / "unit").mkdir(parents=True, exist_ok=True)
        (self.project_root / "tests" / "integration").mkdir(parents=True, exist_ok=True)
        
        # Check if main API app exists
        api_main = self.project_root / "src" / "api" / "main.py"
        if not api_main.exists():
            print(f"❌ API main file not found: {api_main}")
            return False
            
        # Check test files exist
        unit_tests = self.project_root / "tests" / "unit" / "test_api_endpoints_unit.py"
        integration_tests = self.project_root / "tests" / "integration" / "test_comprehensive_endpoint_suite.py"
        
        if not unit_tests.exists():
            print(f"❌ Unit test file not found: {unit_tests}")
            return False
            
        if not integration_tests.exists():
            print(f"❌ Integration test file not found: {integration_tests}")
            return False
            
        return True
        
    def print_help(self):
        """Print comprehensive help information."""
        help_text = """
🧪 HOKUSAI API ENDPOINT TEST RUNNER

MODES:
  unit        Run unit tests with mocks (fast, no dependencies)
  integration Run integration tests against running API
  live        Test against live API with real requests
  full        Run complete test suite
  category    Run tests for specific endpoint category

CATEGORIES:
  health      Health and status endpoints
  models      Model management endpoints  
  dspy        DSPy pipeline endpoints
  mlflow      MLflow proxy endpoints
  auth        Authentication tests

EXAMPLES:
  # Quick unit tests
  python scripts/run_endpoint_tests.py --mode unit

  # Test against local development server
  python scripts/run_endpoint_tests.py --mode integration --api-url http://localhost:8000

  # Test against production API
  python scripts/run_endpoint_tests.py --mode live --api-url https://api.hokus.ai --api-key hok_your_key

  # Full suite with coverage
  python scripts/run_endpoint_tests.py --mode full --coverage

  # Test only health endpoints
  python scripts/run_endpoint_tests.py --mode category --category health

REQUIREMENTS:
  - pytest, fastapi, httpx, tabulate
  - For integration/live tests: running API server
  - For live tests: valid API key

OUTPUT:
  - Test results printed to console
  - Coverage reports (if --coverage used)
  - JUnit XML (if --junit used)
  - Results exported to JSON (for live tests)
        """
        print(help_text)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Hokusai API endpoint tests",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--mode",
        choices=["unit", "integration", "live", "full", "category", "help"],
        required=True,
        help="Test mode to run"
    )
    
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000", 
        help="API base URL for integration/live tests"
    )
    
    parser.add_argument(
        "--api-key",
        help="API key for authentication (required for live tests)"
    )
    
    parser.add_argument(
        "--category",
        choices=["health", "models", "dspy", "mlflow", "auth"],
        help="Specific endpoint category to test"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage reports"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Verbose output"
    )
    
    parser.add_argument(
        "--quiet", "-q", 
        action="store_true",
        help="Quiet output"
    )
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = EndpointTestRunner()
    
    # Handle help mode
    if args.mode == "help":
        runner.print_help()
        return 0
    
    # Check dependencies and setup
    if not runner.check_dependencies():
        return 1
        
    if not runner.setup_test_environment():
        return 1
    
    verbose = args.verbose and not args.quiet
    exit_code = 0
    
    try:
        # Run appropriate tests based on mode
        if args.mode == "unit":
            exit_code = runner.run_unit_tests(verbose=verbose, coverage=args.coverage)
            
        elif args.mode == "integration":
            if not args.api_url:
                print("❌ --api-url required for integration tests")
                return 1
            exit_code = runner.run_integration_tests(
                api_url=args.api_url,
                api_key=args.api_key,
                verbose=verbose
            )
            
        elif args.mode == "live":
            if not args.api_key:
                print("❌ --api-key required for live API tests")
                return 1
            exit_code = runner.run_live_api_tests(
                api_url=args.api_url,
                api_key=args.api_key,
                verbose=verbose
            )
            
        elif args.mode == "full":
            exit_code = runner.run_full_suite(coverage=args.coverage, verbose=verbose)
            
        elif args.mode == "category":
            if not args.category:
                print("❌ --category required for category tests")
                return 1
            exit_code = runner.run_specific_category(
                category=args.category,
                verbose=verbose
            )
    
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"💥 Test runner error: {e}")
        return 1
    
    # Print final results
    if exit_code == 0:
        print("\n✅ All tests completed successfully!")
    else:
        print(f"\n❌ Tests failed with exit code: {exit_code}")
        
    return exit_code


if __name__ == "__main__":
    sys.exit(main())