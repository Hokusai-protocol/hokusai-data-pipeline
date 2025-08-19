#!/usr/bin/env python3
"""
Validate proxy configuration to ensure authentication headers are preserved.
"""

import sys
import ast
import re
from pathlib import Path
from typing import List, Tuple

class ProxyValidator(ast.NodeVisitor):
    """AST visitor to validate proxy functions."""
    
    def __init__(self):
        self.issues: List[Tuple[int, str]] = []
        self.proxy_functions = []
        self.current_function = None
        
    def visit_FunctionDef(self, node):
        """Check function definitions for proxy-related code."""
        if 'proxy' in node.name.lower() or 'forward' in node.name.lower():
            self.current_function = node.name
            self.proxy_functions.append(node.name)
            self.check_proxy_function(node)
        self.generic_visit(node)
        self.current_function = None
    
    def check_proxy_function(self, node):
        """Validate that proxy function handles auth headers correctly."""
        function_code = ast.unparse(node)
        
        # Check for header preservation patterns
        required_patterns = [
            (r'["\']Authorization["\']\s*[:=]', "Authorization header handling"),
            (r'headers\s*=\s*request\.headers', "Header forwarding from request"),
            (r'X-User-ID|x-user-id', "X-User-ID header handling (recommended)"),
        ]
        
        has_auth_handling = False
        for pattern, description in required_patterns:
            if re.search(pattern, function_code, re.IGNORECASE):
                has_auth_handling = True
                break
        
        if not has_auth_handling:
            self.issues.append((
                node.lineno,
                f"Function '{node.name}' appears to be a proxy but doesn't explicitly handle auth headers"
            ))
        
        # Check for header stripping anti-patterns
        anti_patterns = [
            (r'headers\s*=\s*\{\}', "Creates empty headers dict"),
            (r'del\s+.*headers\[["\']Authorization', "Deletes Authorization header"),
            (r'headers\.pop\(["\']Authorization', "Removes Authorization header"),
        ]
        
        for pattern, description in anti_patterns:
            if re.search(pattern, function_code):
                self.issues.append((
                    node.lineno,
                    f"Function '{node.name}' {description} - this will break authentication!"
                ))

def validate_file(filepath: Path) -> bool:
    """Validate a single Python file for proxy auth handling."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        
        tree = ast.parse(source)
        validator = ProxyValidator()
        validator.visit(tree)
        
        if validator.issues:
            print(f"\n❌ Issues found in {filepath}:")
            for line_no, issue in validator.issues:
                print(f"  Line {line_no}: {issue}")
            return False
        elif validator.proxy_functions:
            print(f"✅ {filepath}: {len(validator.proxy_functions)} proxy function(s) validated")
        
        return True
    except Exception as e:
        print(f"⚠️  Error validating {filepath}: {e}")
        return False

def main():
    """Main entry point for pre-commit hook."""
    if len(sys.argv) < 2:
        print("No files to check")
        return 0
    
    files_to_check = [Path(f) for f in sys.argv[1:] if f.endswith('.py')]
    
    if not files_to_check:
        return 0
    
    print("Validating proxy authentication handling...")
    print("-" * 50)
    
    all_valid = True
    for filepath in files_to_check:
        if not validate_file(filepath):
            all_valid = False
    
    if not all_valid:
        print("\n" + "=" * 50)
        print("⚠️  PROXY VALIDATION FAILED")
        print("=" * 50)
        print("\nProxy functions MUST preserve authentication headers!")
        print("Required headers to forward:")
        print("  - Authorization (Bearer token)")
        print("  - X-User-ID (user identifier)")
        print("  - X-Request-ID (request tracing)")
        print("\nExample pattern:")
        print("  headers = dict(request.headers)  # Preserve all headers")
        print("  response = requests.post(url, headers=headers, ...)")
        print("\nSee docs/PROXY_CHECKLIST.md for details")
        return 1
    
    print("\n✅ All proxy functions properly handle authentication")
    return 0

if __name__ == "__main__":
    sys.exit(main())