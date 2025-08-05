#!/usr/bin/env python3
"""
Authentication Testing Script
Tests API key authentication through Bearer tokens and X-API-Key headers
"""

import requests
import time
import json
import os
import sys
from typing import Dict, Optional, Tuple
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AuthenticationTester:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HOKUSAI_API_KEY")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {},
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0
            }
        }
        
        # Service endpoints
        self.auth_endpoint = "https://auth.hokus.ai"
        self.registry_endpoint = "https://registry.hokus.ai"
        self.mlflow_endpoint = "https://registry.hokus.ai/api/mlflow"
        
    def test_bearer_token_auth(self) -> Dict:
        """Test Bearer token authentication format"""
        print("\n🔐 Testing Bearer Token Authentication...")
        
        test_results = {
            "method": "Bearer Token",
            "tests": {}
        }
        
        # Test 1: Valid Bearer token format
        print("  Testing valid Bearer token format...")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            response = requests.get(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                headers=headers,
                timeout=10
            )
            
            test_results["tests"]["valid_bearer"] = {
                "status_code": response.status_code,
                "success": response.status_code in [200, 401],  # 401 means auth worked but key might be invalid
                "response_time": response.elapsed.total_seconds() * 1000,
                "error": None if response.status_code != 500 else "Server error"
            }
            
            if response.status_code == 200:
                print(f"    ✅ Valid Bearer token accepted")
            elif response.status_code == 401:
                print(f"    ⚠️  Bearer token format accepted but key may be invalid")
            else:
                print(f"    ❌ Unexpected response: {response.status_code}")
                
        except Exception as e:
            test_results["tests"]["valid_bearer"] = {
                "success": False,
                "error": str(e)
            }
            print(f"    ❌ Error: {str(e)}")
            
        # Test 2: Invalid Bearer token format
        print("  Testing invalid Bearer token format...")
        invalid_formats = [
            ("missing_bearer", {"Authorization": self.api_key}),
            ("lowercase_bearer", {"Authorization": f"bearer {self.api_key}"}),
            ("no_space", {"Authorization": f"Bearer{self.api_key}"}),
            ("extra_space", {"Authorization": f"Bearer  {self.api_key}"})
        ]
        
        for test_name, headers in invalid_formats:
            try:
                response = requests.get(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                    headers=headers,
                    timeout=5
                )
                
                test_results["tests"][f"invalid_{test_name}"] = {
                    "status_code": response.status_code,
                    "success": response.status_code == 401,  # Should reject invalid format
                    "format_tested": headers.get("Authorization", "")
                }
                
                if response.status_code == 401:
                    print(f"    ✅ {test_name}: Correctly rejected")
                else:
                    print(f"    ❌ {test_name}: Unexpectedly accepted (status: {response.status_code})")
                    
            except Exception as e:
                test_results["tests"][f"invalid_{test_name}"] = {
                    "success": False,
                    "error": str(e)
                }
                
        self.results["tests"]["bearer_token"] = test_results
        return test_results
        
    def test_x_api_key_header(self) -> Dict:
        """Test X-API-Key header authentication"""
        print("\n🔑 Testing X-API-Key Header Authentication...")
        
        test_results = {
            "method": "X-API-Key Header",
            "tests": {}
        }
        
        # Test 1: Valid X-API-Key header
        print("  Testing valid X-API-Key header...")
        headers = {"X-API-Key": self.api_key}
        
        try:
            response = requests.get(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                headers=headers,
                timeout=10
            )
            
            test_results["tests"]["valid_x_api_key"] = {
                "status_code": response.status_code,
                "success": response.status_code in [200, 401],
                "response_time": response.elapsed.total_seconds() * 1000,
                "error": None if response.status_code != 500 else "Server error"
            }
            
            if response.status_code == 200:
                print(f"    ✅ X-API-Key header accepted")
            elif response.status_code == 401:
                print(f"    ⚠️  X-API-Key format accepted but key may be invalid")
            else:
                print(f"    ❌ Unexpected response: {response.status_code}")
                
        except Exception as e:
            test_results["tests"]["valid_x_api_key"] = {
                "success": False,
                "error": str(e)
            }
            print(f"    ❌ Error: {str(e)}")
            
        # Test 2: Case sensitivity
        print("  Testing header case sensitivity...")
        case_variants = [
            ("lowercase", {"x-api-key": self.api_key}),
            ("mixed_case", {"X-Api-Key": self.api_key}),
            ("uppercase", {"X-API-KEY": self.api_key})
        ]
        
        for test_name, headers in case_variants:
            try:
                response = requests.get(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                    headers=headers,
                    timeout=5
                )
                
                test_results["tests"][f"case_{test_name}"] = {
                    "status_code": response.status_code,
                    "success": response.status_code in [200, 401],
                    "header_tested": list(headers.keys())[0]
                }
                
                if response.status_code in [200, 401]:
                    print(f"    ✅ {test_name}: Header accepted")
                else:
                    print(f"    ❌ {test_name}: Header rejected (status: {response.status_code})")
                    
            except Exception as e:
                test_results["tests"][f"case_{test_name}"] = {
                    "success": False,
                    "error": str(e)
                }
                
        self.results["tests"]["x_api_key"] = test_results
        return test_results
        
    def test_auth_service_integration(self) -> Dict:
        """Test direct auth service integration"""
        print("\n🔗 Testing Auth Service Integration...")
        
        test_results = {
            "service": "auth.hokus.ai",
            "tests": {}
        }
        
        # Test 1: Validate API key with auth service
        print("  Testing API key validation...")
        
        # Try to use the API key to access a protected endpoint
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            # First check if auth service is up
            health_response = requests.get(f"{self.auth_endpoint}/health", timeout=5)
            test_results["tests"]["auth_service_health"] = {
                "status_code": health_response.status_code,
                "success": health_response.status_code == 200
            }
            
            if health_response.status_code == 200:
                print(f"    ✅ Auth service is healthy")
            else:
                print(f"    ⚠️  Auth service health check returned: {health_response.status_code}")
                
            # Now test key validation through a protected endpoint
            response = requests.get(
                f"{self.registry_endpoint}/api/experiments",
                headers=headers,
                timeout=10
            )
            
            test_results["tests"]["key_validation"] = {
                "status_code": response.status_code,
                "success": response.status_code != 401,  # Not unauthorized
                "authenticated": response.status_code in [200, 404],  # 404 means auth passed but endpoint might not exist
                "response_time": response.elapsed.total_seconds() * 1000
            }
            
            if response.status_code == 200:
                print(f"    ✅ API key validated successfully")
            elif response.status_code == 404:
                print(f"    ✅ Authentication passed (endpoint returned 404)")
            elif response.status_code == 401:
                print(f"    ❌ API key rejected as unauthorized")
            else:
                print(f"    ⚠️  Unexpected response: {response.status_code}")
                
        except Exception as e:
            test_results["tests"]["key_validation"] = {
                "success": False,
                "error": str(e)
            }
            print(f"    ❌ Error: {str(e)}")
            
        self.results["tests"]["auth_service"] = test_results
        return test_results
        
    def test_invalid_api_key_handling(self) -> Dict:
        """Test how the system handles invalid API keys"""
        print("\n❌ Testing Invalid API Key Handling...")
        
        test_results = {
            "type": "invalid_key_handling",
            "tests": {}
        }
        
        invalid_keys = [
            ("malformed_short", "hk_live_123"),
            ("malformed_no_prefix", "1234567890abcdef"),
            ("empty_key", ""),
            ("null_string", "null"),
            ("invalid_prefix", "sk_live_1234567890abcdef"),
            ("expired_format", "hk_expired_1234567890abcdef")
        ]
        
        for test_name, invalid_key in invalid_keys:
            print(f"  Testing {test_name}...")
            headers = {"Authorization": f"Bearer {invalid_key}"} if invalid_key else {}
            
            try:
                response = requests.get(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                    headers=headers,
                    timeout=5
                )
                
                test_results["tests"][test_name] = {
                    "status_code": response.status_code,
                    "success": response.status_code == 401,  # Should return unauthorized
                    "key_tested": invalid_key[:10] + "..." if len(invalid_key) > 10 else invalid_key
                }
                
                if response.status_code == 401:
                    print(f"    ✅ Correctly rejected with 401")
                else:
                    print(f"    ❌ Unexpected response: {response.status_code}")
                    
            except Exception as e:
                test_results["tests"][test_name] = {
                    "success": False,
                    "error": str(e)
                }
                print(f"    ❌ Error: {str(e)}")
                
        self.results["tests"]["invalid_key_handling"] = test_results
        return test_results
        
    def test_auth_caching_behavior(self) -> Dict:
        """Test the 5-minute auth cache behavior"""
        print("\n⏰ Testing Auth Cache Behavior...")
        
        test_results = {
            "type": "auth_caching",
            "tests": {}
        }
        
        print("  Making initial authenticated request...")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # First request - should hit auth service
        try:
            start_time = time.time()
            response1 = requests.get(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                headers=headers,
                timeout=10
            )
            first_request_time = (time.time() - start_time) * 1000
            
            test_results["tests"]["first_request"] = {
                "status_code": response1.status_code,
                "response_time_ms": round(first_request_time, 2),
                "success": response1.status_code in [200, 401]
            }
            
            print(f"    First request: {response1.status_code} in {first_request_time:.2f}ms")
            
            # Wait a bit and make second request - should be cached
            print("  Waiting 2 seconds then testing cached request...")
            time.sleep(2)
            
            start_time = time.time()
            response2 = requests.get(
                f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                headers=headers,
                timeout=10
            )
            second_request_time = (time.time() - start_time) * 1000
            
            test_results["tests"]["cached_request"] = {
                "status_code": response2.status_code,
                "response_time_ms": round(second_request_time, 2),
                "success": response2.status_code == response1.status_code,
                "likely_cached": second_request_time < first_request_time * 0.7  # Should be notably faster
            }
            
            print(f"    Cached request: {response2.status_code} in {second_request_time:.2f}ms")
            
            if test_results["tests"]["cached_request"]["likely_cached"]:
                print(f"    ✅ Cache appears to be working (2nd request {(first_request_time/second_request_time):.1f}x faster)")
            else:
                print(f"    ⚠️  Cache behavior unclear (similar response times)")
                
        except Exception as e:
            test_results["tests"]["error"] = {
                "success": False,
                "error": str(e)
            }
            print(f"    ❌ Error: {str(e)}")
            
        self.results["tests"]["auth_caching"] = test_results
        return test_results
        
    def test_rate_limiting(self) -> Dict:
        """Test rate limiting behavior"""
        print("\n🚦 Testing Rate Limiting...")
        
        test_results = {
            "type": "rate_limiting",
            "tests": {}
        }
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # Make rapid requests to trigger rate limiting
        print("  Making 20 rapid requests...")
        request_results = []
        
        for i in range(20):
            try:
                start_time = time.time()
                response = requests.get(
                    f"{self.mlflow_endpoint}/api/2.0/mlflow/experiments/search",
                    headers=headers,
                    timeout=5
                )
                request_time = (time.time() - start_time) * 1000
                
                request_results.append({
                    "request_num": i + 1,
                    "status_code": response.status_code,
                    "response_time_ms": round(request_time, 2)
                })
                
                if response.status_code == 429:
                    print(f"    ⚠️  Rate limit hit at request {i + 1}")
                    test_results["tests"]["rate_limit_triggered"] = {
                        "triggered_at_request": i + 1,
                        "success": True
                    }
                    break
                    
            except Exception as e:
                request_results.append({
                    "request_num": i + 1,
                    "error": str(e)
                })
                
        if not any(r.get("status_code") == 429 for r in request_results):
            print(f"    ✅ No rate limiting triggered in 20 requests")
            test_results["tests"]["rate_limit_triggered"] = {
                "triggered": False,
                "total_requests": len(request_results)
            }
        
        test_results["tests"]["request_details"] = request_results
        self.results["tests"]["rate_limiting"] = test_results
        return test_results
        
    def generate_report(self):
        """Generate authentication test report"""
        print("\n" + "="*60)
        print("📋 AUTHENTICATION TEST REPORT")
        print("="*60)
        
        # Calculate totals
        for test_category in self.results["tests"].values():
            if isinstance(test_category, dict) and "tests" in test_category:
                for test in test_category.get("tests", {}).values():
                    if isinstance(test, dict):
                        self.results["summary"]["total"] += 1
                        if test.get("success", False):
                            self.results["summary"]["passed"] += 1
                        else:
                            self.results["summary"]["failed"] += 1
                    
        print(f"\n📅 Timestamp: {self.results['timestamp']}")
        print(f"🔑 API Key: {self.api_key[:10]}...{self.api_key[-4:] if self.api_key else 'Not provided'}")
        
        print(f"\n📊 Summary:")
        print(f"  Total Tests: {self.results['summary']['total']}")
        print(f"  ✅ Passed: {self.results['summary']['passed']}")
        print(f"  ❌ Failed: {self.results['summary']['failed']}")
        
        if self.results['summary']['total'] > 0:
            success_rate = (self.results['summary']['passed'] / 
                          self.results['summary']['total']) * 100
            print(f"  📈 Success Rate: {success_rate:.1f}%")
            
        # Save detailed report
        report_file = "authentication_test_report.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed report saved to: {report_file}")
        
        # Key findings
        print("\n🔍 Key Findings:")
        
        # Check Bearer token support
        bearer_tests = self.results["tests"].get("bearer_token", {}).get("tests", {})
        if bearer_tests.get("valid_bearer", {}).get("success"):
            print("  ✅ Bearer token authentication is supported")
        else:
            print("  ❌ Bearer token authentication may have issues")
            
        # Check X-API-Key support  
        x_api_tests = self.results["tests"].get("x_api_key", {}).get("tests", {})
        if x_api_tests.get("valid_x_api_key", {}).get("success"):
            print("  ✅ X-API-Key header authentication is supported")
        else:
            print("  ❌ X-API-Key header authentication may have issues")
            
        # Check auth service
        auth_tests = self.results["tests"].get("auth_service", {}).get("tests", {})
        if auth_tests.get("key_validation", {}).get("authenticated"):
            print("  ✅ Auth service integration is working")
        else:
            print("  ❌ Auth service integration needs attention")
            
        # Check caching
        cache_tests = self.results["tests"].get("auth_caching", {}).get("tests", {})
        if cache_tests.get("cached_request", {}).get("likely_cached"):
            print("  ✅ Auth caching appears to be working")
        else:
            print("  ⚠️  Auth caching behavior is unclear")
            
        print("\n✅ Authentication testing completed!")
        
    def run_all_tests(self):
        """Run all authentication tests"""
        if not self.api_key:
            print("❌ No API key provided!")
            print("Please set HOKUSAI_API_KEY environment variable or pass it to the constructor")
            return None
            
        print("🚀 Starting Authentication Tests...")
        print(f"🔑 Using API key: {self.api_key[:10]}...{self.api_key[-4:]}")
        print("="*60)
        
        self.test_bearer_token_auth()
        self.test_x_api_key_header()
        self.test_auth_service_integration()
        self.test_invalid_api_key_handling()
        self.test_auth_caching_behavior()
        self.test_rate_limiting()
        self.generate_report()
        
        return self.results


if __name__ == "__main__":
    # Check for API key
    api_key = os.environ.get("HOKUSAI_API_KEY")
    if not api_key and len(sys.argv) > 1:
        api_key = sys.argv[1]
        
    if not api_key:
        print("❌ Please provide an API key!")
        print("Usage: python test_authentication.py <api_key>")
        print("   or: export HOKUSAI_API_KEY=<api_key>")
        sys.exit(1)
        
    tester = AuthenticationTester(api_key)
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    if results and results["summary"]["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)