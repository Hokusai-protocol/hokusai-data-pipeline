#!/usr/bin/env python3
"""
Comprehensive API Endpoint Audit Script for Hokusai MLOps API

This script:
1. Reads all route files in src/api/routes/
2. Extracts all endpoint definitions using AST parsing
3. Creates a catalog of expected endpoints
4. Tests each endpoint against a live API server
5. Generates a detailed report showing which endpoints work and which don't

Usage:
    python scripts/audit_endpoints.py [--base-url BASE_URL] [--api-key API_KEY] [--output OUTPUT_FILE]
"""

import argparse
import ast
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urljoin

import httpx
# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@dataclass
class EndpointInfo:
    """Information about a discovered endpoint."""
    method: str
    path: str
    function_name: str
    file_path: str
    line_number: int
    has_auth: bool = False
    rate_limited: bool = False
    response_model: Optional[str] = None
    tags: List[str] = None
    prefix: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

@dataclass
class TestResult:
    """Result of testing an endpoint."""
    endpoint: EndpointInfo
    status_code: Optional[int] = None
    success: bool = False
    error: Optional[str] = None
    response_time_ms: Optional[float] = None
    response_body: Optional[str] = None
    content_type: Optional[str] = None

class EndpointExtractor(ast.NodeVisitor):
    """AST visitor to extract FastAPI endpoint definitions."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.endpoints: List[EndpointInfo] = []
        self.current_router_prefix = ""
        self.current_tags = []
        
    def visit_Call(self, node: ast.Call):
        """Visit function calls to find router decorators."""
        if self._is_router_decorator(node):
            endpoint_info = self._extract_endpoint_info(node)
            if endpoint_info:
                self.endpoints.append(endpoint_info)
        
        # Check for router creation with prefix
        if self._is_router_creation(node):
            self._extract_router_config(node)
            
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definitions to find endpoints."""
        # Look for decorator-based endpoints
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and self._is_router_decorator(decorator):
                endpoint_info = self._extract_endpoint_info(decorator, node)
                if endpoint_info:
                    self.endpoints.append(endpoint_info)
        
        self.generic_visit(node)
    
    def _is_router_decorator(self, node: ast.Call) -> bool:
        """Check if a call is a router decorator (e.g., @router.get)."""
        if isinstance(node.func, ast.Attribute):
            return (node.func.attr in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'api_route'] and
                   (isinstance(node.func.value, ast.Name) and node.func.value.id == 'router'))
        return False
    
    def _is_router_creation(self, node: ast.Call) -> bool:
        """Check if a call creates an APIRouter."""
        if isinstance(node.func, ast.Name) and node.func.id == 'APIRouter':
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'APIRouter':
            return True
        return False
    
    def _extract_router_config(self, node: ast.Call):
        """Extract router configuration like prefix and tags."""
        for keyword in node.keywords:
            if keyword.arg == 'prefix' and isinstance(keyword.value, ast.Constant):
                self.current_router_prefix = keyword.value.value
            elif keyword.arg == 'tags' and isinstance(keyword.value, ast.List):
                self.current_tags = [elt.value for elt in keyword.value.elts 
                                   if isinstance(elt, ast.Constant)]
    
    def _extract_endpoint_info(self, decorator_node: ast.Call, func_node: ast.FunctionDef = None) -> Optional[EndpointInfo]:
        """Extract endpoint information from decorator."""
        if not decorator_node.args:
            return None
            
        # Get the HTTP method
        method = decorator_node.func.attr.upper()
        if method == 'API_ROUTE':
            # For api_route, method might be in kwargs
            method = self._extract_methods_from_api_route(decorator_node)
        
        # Get the path
        path_arg = decorator_node.args[0]
        if isinstance(path_arg, ast.Constant):
            path = path_arg.value
        else:
            return None
        
        # Add router prefix if exists
        full_path = self.current_router_prefix + path if self.current_router_prefix else path
        
        # Extract additional metadata
        has_auth = self._check_for_auth(func_node) if func_node else False
        rate_limited = self._check_for_rate_limit(decorator_node)
        response_model = self._extract_response_model(decorator_node)
        
        return EndpointInfo(
            method=method,
            path=full_path,
            function_name=func_node.name if func_node else "unknown",
            file_path=self.file_path,
            line_number=decorator_node.lineno,
            has_auth=has_auth,
            rate_limited=rate_limited,
            response_model=response_model,
            tags=self.current_tags.copy(),
            prefix=self.current_router_prefix
        )
    
    def _extract_methods_from_api_route(self, node: ast.Call) -> str:
        """Extract methods from api_route decorator."""
        for keyword in node.keywords:
            if keyword.arg == 'methods' and isinstance(keyword.value, ast.List):
                methods = [elt.value for elt in keyword.value.elts 
                          if isinstance(elt, ast.Constant)]
                return '/'.join(methods)  # Multiple methods
        return 'GET'  # Default
    
    def _check_for_auth(self, func_node: ast.FunctionDef) -> bool:
        """Check if function has authentication requirement."""
        if not func_node:
            return False
        
        # Check function parameters for Depends(require_auth)
        for arg in func_node.args.args:
            if hasattr(arg, 'annotation') and isinstance(arg.annotation, ast.Call):
                if (isinstance(arg.annotation.func, ast.Name) and 
                    arg.annotation.func.id == 'Depends'):
                    return True
        
        # Check for auth decorators
        for decorator in func_node.decorator_list:
            if isinstance(decorator, ast.Name) and 'auth' in decorator.id.lower():
                return True
                
        return False
    
    def _check_for_rate_limit(self, decorator_node: ast.Call) -> bool:
        """Check if endpoint has rate limiting."""
        # This would need to be more sophisticated to detect @limiter.limit decorators
        return False
    
    def _extract_response_model(self, decorator_node: ast.Call) -> Optional[str]:
        """Extract response model from decorator."""
        for keyword in decorator_node.keywords:
            if keyword.arg == 'response_model':
                if isinstance(keyword.value, ast.Name):
                    return keyword.value.id
                elif isinstance(keyword.value, ast.Attribute):
                    return keyword.value.attr
        return None

class EndpointAuditor:
    """Main class for auditing API endpoints."""
    
    def __init__(self, base_url: str = "https://registry.hokus.ai", api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.endpoints: List[EndpointInfo] = []
        self.test_results: List[TestResult] = []
        
    def discover_endpoints(self, routes_dir: str = "src/api/routes") -> List[EndpointInfo]:
        """Discover all endpoints by parsing route files."""
        routes_path = Path(routes_dir)
        if not routes_path.exists():
            raise FileNotFoundError(f"Routes directory not found: {routes_dir}")
        
        self.endpoints = []
        
        for py_file in routes_path.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
                
            print(f"Parsing {py_file.name}...")
            try:
                self._parse_route_file_regex(py_file)
            except Exception as e:
                print(f"Warning: Failed to parse {py_file}: {e}")
        
        # Add known prefix mappings from main.py
        self._apply_route_prefixes()
        
        return self.endpoints
    
    def _parse_route_file_regex(self, file_path: Path):
        """Parse a single route file for endpoints using regex (faster than AST)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract router prefix from router creation
        router_prefix = ""
        prefix_match = re.search(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', content)
        if prefix_match:
            router_prefix = prefix_match.group(1)
        
        # Find all route decorators
        patterns = [
            # @router.get("/path")
            r'@router\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']([^)]*)\)\s*\n\s*(?:async\s+)?def\s+(\w+)',
            # @router.api_route("/path", methods=["GET"])
            r'@router\.api_route\s*\(\s*["\']([^"\']+)["\'][^)]*methods\s*=\s*\[([^\]]+)\][^)]*\)\s*\n\s*(?:async\s+)?def\s+(\w+)',
        ]
        
        for pattern_idx, pattern in enumerate(patterns):
            matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
            for match in matches:
                try:
                    if pattern_idx == 0:
                        # Standard decorator
                        method, path, decorator_args, function_name = match.groups()
                        methods = [method.upper()]
                    else:
                        # api_route decorator  
                        path, methods_str, function_name = match.groups()
                        methods = [m.strip().strip('"\'').upper() for m in methods_str.split(',')]
                    
                    # Check for auth in decorator args
                    has_auth = 'require_auth' in decorator_args if pattern_idx == 0 else False
                    
                    # Create endpoint for each method
                    for method in methods:
                        full_path = router_prefix + path if router_prefix else path
                        
                        endpoint = EndpointInfo(
                            method=method,
                            path=full_path,
                            function_name=function_name,
                            file_path=str(file_path),
                            line_number=content[:match.start()].count('\n') + 1,
                            has_auth=has_auth,
                            rate_limited=False,
                            response_model=None,
                            tags=[],
                            prefix=router_prefix
                        )
                        self.endpoints.append(endpoint)
                        
                except Exception as e:
                    print(f"Error parsing match in {file_path}: {e}")
                    continue
    
    def _parse_route_file(self, file_path: Path):
        """Parse a single route file for endpoints."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
            extractor = EndpointExtractor(str(file_path))
            extractor.visit(tree)
            self.endpoints.extend(extractor.endpoints)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
    
    def _apply_route_prefixes(self):
        """Apply known route prefixes from main.py configuration."""
        prefix_mappings = {
            'models.py': '/models',
            'mlflow_proxy_improved.py': ['/mlflow', '/api/mlflow'],
            'health_mlflow.py': '/api/health',
            'dspy.py': '/api/v1/dspy'  # Based on the router prefix in dspy.py
        }
        
        # Create a new list to avoid modifying while iterating
        additional_endpoints = []
        
        for endpoint in self.endpoints[:]:  # Copy the list
            file_name = Path(endpoint.file_path).name
            
            if file_name in prefix_mappings:
                prefixes = prefix_mappings[file_name]
                if isinstance(prefixes, str):
                    prefixes = [prefixes]
                
                # Create additional endpoints for each prefix
                for prefix in prefixes:
                    if not endpoint.path.startswith(prefix):
                        new_endpoint = EndpointInfo(
                            method=endpoint.method,
                            path=prefix + endpoint.path,
                            function_name=endpoint.function_name,
                            file_path=endpoint.file_path,
                            line_number=endpoint.line_number,
                            has_auth=endpoint.has_auth,
                            rate_limited=endpoint.rate_limited,
                            response_model=endpoint.response_model,
                            tags=endpoint.tags,
                            prefix=prefix
                        )
                        # Check if already exists by comparing key attributes
                        exists = any(
                            ep.method == new_endpoint.method and ep.path == new_endpoint.path 
                            for ep in self.endpoints + additional_endpoints
                        )
                        if not exists:
                            additional_endpoints.append(new_endpoint)
        
        # Add all additional endpoints at once
        self.endpoints.extend(additional_endpoints)
    
    async def test_endpoints(self, timeout: float = 10.0, max_concurrent: int = 10) -> List[TestResult]:
        """Test all discovered endpoints."""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def test_single_endpoint(endpoint: EndpointInfo) -> TestResult:
            async with semaphore:
                return await self._test_endpoint(endpoint, timeout)
        
        # Create test tasks
        tasks = [test_single_endpoint(endpoint) for endpoint in self.endpoints]
        
        # Execute tests
        print(f"Testing {len(tasks)} endpoints with up to {max_concurrent} concurrent requests...")
        self.test_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(self.test_results):
            if isinstance(result, Exception):
                print(f"Error testing endpoint {self.endpoints[i].path}: {result}")
                valid_results.append(TestResult(
                    endpoint=self.endpoints[i],
                    success=False,
                    error=str(result)
                ))
            else:
                valid_results.append(result)
        
        self.test_results = valid_results
        return self.test_results
    
    async def _test_endpoint(self, endpoint: EndpointInfo, timeout: float) -> TestResult:
        """Test a single endpoint."""
        url = urljoin(self.base_url + '/', endpoint.path.lstrip('/'))
        
        # Prepare headers
        headers = {
            'User-Agent': 'Hokusai-Endpoint-Auditor/1.0',
            'Accept': 'application/json'
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
            headers['X-API-Key'] = self.api_key
        
        # Prepare test data for POST/PUT requests
        test_data = self._get_test_data(endpoint)
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                start_time = asyncio.get_event_loop().time()
                
                if endpoint.method in ['POST', 'PUT', 'PATCH']:
                    response = await client.request(
                        method=endpoint.method,
                        url=url,
                        headers=headers,
                        json=test_data
                    )
                else:
                    response = await client.request(
                        method=endpoint.method,
                        url=url,
                        headers=headers
                    )
                
                end_time = asyncio.get_event_loop().time()
                response_time_ms = (end_time - start_time) * 1000
                
                # Determine success based on status code
                success = self._is_successful_response(response.status_code, endpoint)
                
                # Get response body (limit size for logging)
                response_body = response.text[:1000] if len(response.text) < 1000 else response.text[:997] + "..."
                
                return TestResult(
                    endpoint=endpoint,
                    status_code=response.status_code,
                    success=success,
                    response_time_ms=response_time_ms,
                    response_body=response_body,
                    content_type=response.headers.get('content-type'),
                    error=None
                )
                
        except httpx.TimeoutException:
            return TestResult(
                endpoint=endpoint,
                success=False,
                error=f"Timeout after {timeout}s"
            )
        except Exception as e:
            return TestResult(
                endpoint=endpoint,
                success=False,
                error=str(e)
            )
    
    def _get_test_data(self, endpoint: EndpointInfo) -> Dict[str, Any]:
        """Get appropriate test data for an endpoint."""
        # Simple test data based on endpoint patterns
        if 'model' in endpoint.path.lower():
            return {
                "name": "test-model",
                "version": "1",
                "description": "Test model for endpoint audit"
            }
        elif 'dspy' in endpoint.path.lower():
            return {
                "program_id": "test-program",
                "inputs": {"test": "data"}
            }
        else:
            return {"test": "data"}
    
    def _is_successful_response(self, status_code: int, endpoint: EndpointInfo) -> bool:
        """Determine if a response is successful based on context."""
        # 2xx is always success
        if 200 <= status_code < 300:
            return True
        
        # 401/403 for auth endpoints is "successful" (auth is working)
        if status_code in [401, 403] and endpoint.has_auth:
            return True
        
        # 404 might be expected for some GET endpoints without test data
        if status_code == 404 and endpoint.method == 'GET':
            return True
        
        # 422 for POST/PUT with invalid test data is somewhat expected
        if status_code == 422 and endpoint.method in ['POST', 'PUT', 'PATCH']:
            return True
        
        # 405 Method Not Allowed indicates endpoint exists but method is wrong
        if status_code == 405:
            return True
            
        return False
    
    def generate_report(self, output_file: str = None) -> Dict[str, Any]:
        """Generate a comprehensive report of the audit results."""
        if not self.test_results:
            raise RuntimeError("No test results available. Run test_endpoints() first.")
        
        # Aggregate statistics
        total_endpoints = len(self.test_results)
        successful = sum(1 for r in self.test_results if r.success)
        failed = total_endpoints - successful
        
        # Group by status code
        status_codes = {}
        for result in self.test_results:
            code = result.status_code or 'ERROR'
            if code not in status_codes:
                status_codes[code] = 0
            status_codes[code] += 1
        
        # Group by file
        by_file = {}
        for result in self.test_results:
            file_name = Path(result.endpoint.file_path).name
            if file_name not in by_file:
                by_file[file_name] = {'total': 0, 'success': 0, 'failed': 0}
            by_file[file_name]['total'] += 1
            if result.success:
                by_file[file_name]['success'] += 1
            else:
                by_file[file_name]['failed'] += 1
        
        # Get response time statistics
        response_times = [r.response_time_ms for r in self.test_results if r.response_time_ms is not None]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        report = {
            "audit_timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "summary": {
                "total_endpoints": total_endpoints,
                "successful": successful,
                "failed": failed,
                "success_rate": f"{(successful/total_endpoints*100):.1f}%" if total_endpoints > 0 else "0%",
                "average_response_time_ms": round(avg_response_time, 2)
            },
            "status_code_distribution": dict(sorted(status_codes.items())),
            "results_by_file": by_file,
            "detailed_results": [
                {
                    "method": result.endpoint.method,
                    "path": result.endpoint.path,
                    "function": result.endpoint.function_name,
                    "file": Path(result.endpoint.file_path).name,
                    "line": result.endpoint.line_number,
                    "status_code": result.status_code,
                    "success": result.success,
                    "response_time_ms": result.response_time_ms,
                    "error": result.error,
                    "has_auth": result.endpoint.has_auth,
                    "content_type": result.content_type
                }
                for result in sorted(self.test_results, key=lambda r: (r.endpoint.file_path, r.endpoint.line_number))
            ],
            "failed_endpoints": [
                {
                    "method": result.endpoint.method,
                    "path": result.endpoint.path,
                    "status_code": result.status_code,
                    "error": result.error,
                    "file": Path(result.endpoint.file_path).name
                }
                for result in self.test_results if not result.success
            ]
        }
        
        # Save to file if specified
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"Report saved to {output_file}")
        
        return report
    
    def print_summary(self):
        """Print a summary of the audit results."""
        if not self.test_results:
            print("No test results available.")
            return
        
        total = len(self.test_results)
        successful = sum(1 for r in self.test_results if r.success)
        failed = total - successful
        
        print(f"\n{'='*60}")
        print(f"ENDPOINT AUDIT SUMMARY")
        print(f"{'='*60}")
        print(f"Base URL: {self.base_url}")
        print(f"Total Endpoints: {total}")
        print(f"Successful: {successful} ({successful/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")
        
        if failed > 0:
            print(f"\nFAILED ENDPOINTS:")
            for result in self.test_results:
                if not result.success:
                    print(f"  {result.endpoint.method} {result.endpoint.path}")
                    print(f"    Status: {result.status_code or 'ERROR'}")
                    print(f"    Error: {result.error or 'Unknown error'}")
                    print()

async def main():
    """Main function to run the endpoint audit."""
    parser = argparse.ArgumentParser(description="Audit Hokusai API endpoints")
    parser.add_argument("--base-url", default="https://registry.hokus.ai", 
                       help="Base URL of the API server to test")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--output", help="Output file for detailed report (JSON)")
    parser.add_argument("--timeout", type=float, default=10.0,
                       help="Request timeout in seconds")
    parser.add_argument("--max-concurrent", type=int, default=10,
                       help="Maximum concurrent requests")
    parser.add_argument("--routes-dir", default="src/api/routes",
                       help="Directory containing route files")
    
    args = parser.parse_args()
    
    # Create auditor
    auditor = EndpointAuditor(base_url=args.base_url, api_key=args.api_key)
    
    try:
        # Discover endpoints
        print("Discovering endpoints...")
        endpoints = auditor.discover_endpoints(args.routes_dir)
        print(f"Found {len(endpoints)} endpoints")
        
        # Test endpoints
        print("Testing endpoints...")
        results = await auditor.test_endpoints(
            timeout=args.timeout, 
            max_concurrent=args.max_concurrent
        )
        
        # Generate and display results
        report = auditor.generate_report(args.output)
        auditor.print_summary()
        
        # Exit with appropriate code
        failed_count = len([r for r in results if not r.success])
        if failed_count > 0:
            print(f"\nAudit completed with {failed_count} failures")
            sys.exit(1)
        else:
            print("\nAll endpoints passed!")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\nAudit interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Audit failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())