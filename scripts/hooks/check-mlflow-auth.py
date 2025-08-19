#!/usr/bin/env python3
"""
Check MLflow-related code for proper authentication setup.
"""

import sys
import ast
import re
from pathlib import Path
from typing import List, Tuple

class MLflowAuthChecker(ast.NodeVisitor):
    """AST visitor to check MLflow authentication."""
    
    def __init__(self):
        self.issues: List[Tuple[int, str]] = []
        self.mlflow_usage = []
        
    def visit_Import(self, node):
        """Check for MLflow imports."""
        for alias in node.names:
            if 'mlflow' in alias.name:
                self.mlflow_usage.append(('import', node.lineno))
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        """Check for MLflow from imports."""
        if node.module and 'mlflow' in node.module:
            self.mlflow_usage.append(('from_import', node.lineno))
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Check for MLflow client/function calls."""
        call_str = ast.unparse(node.func) if hasattr(ast, 'unparse') else str(node.func)
        
        # Check for MLflow client instantiation
        if 'MlflowClient' in call_str:
            # Check if tracking_uri or headers are passed
            has_auth = False
            for keyword in node.keywords:
                if keyword.arg in ['tracking_uri', 'headers', 'tracking_token']:
                    has_auth = True
                    break
            
            if not has_auth:
                self.issues.append((
                    node.lineno,
                    "MlflowClient instantiated without explicit auth configuration"
                ))
        
        # Check for mlflow.set_tracking_uri or similar setup
        if 'mlflow.' in call_str:
            if 'set_tracking_uri' in call_str or 'set_experiment' in call_str:
                self.mlflow_usage.append(('setup', node.lineno))
        
        self.generic_visit(node)

def check_file_for_auth_setup(source: str) -> List[str]:
    """Check if file has proper MLflow auth setup."""
    issues = []
    
    # Check for environment variable usage
    auth_patterns = [
        r'MLFLOW_TRACKING_TOKEN',
        r'MLFLOW_TRACKING_USERNAME',
        r'MLFLOW_TRACKING_PASSWORD',
        r'Authorization.*Bearer',
        r'headers\s*=.*Authorization',
        r'get_auth_headers',
    ]
    
    has_auth_setup = any(re.search(pattern, source) for pattern in auth_patterns)
    
    # Check for MLflow usage
    if re.search(r'mlflow\.|MlflowClient', source):
        if not has_auth_setup:
            issues.append("File uses MLflow but lacks visible authentication setup")
    
    return issues

def validate_file(filepath: Path) -> bool:
    """Validate a single Python file for MLflow auth."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        
        # Quick check if file uses MLflow
        if not re.search(r'mlflow|MLflow', source, re.IGNORECASE):
            return True  # No MLflow usage, skip
        
        print(f"Checking {filepath} for MLflow authentication...")
        
        # AST-based checking
        tree = ast.parse(source)
        checker = MLflowAuthChecker()
        checker.visit(tree)
        
        # Source-based checking
        source_issues = check_file_for_auth_setup(source)
        
        all_issues = checker.issues
        if source_issues:
            all_issues.extend([(0, issue) for issue in source_issues])
        
        if all_issues:
            print(f"❌ Issues found in {filepath}:")
            for line_no, issue in all_issues:
                if line_no > 0:
                    print(f"  Line {line_no}: {issue}")
                else:
                    print(f"  {issue}")
            return False
        
        if checker.mlflow_usage:
            print(f"✅ {filepath}: MLflow usage with proper auth detected")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Error checking {filepath}: {e}")
        return False

def main():
    """Main entry point for pre-commit hook."""
    if len(sys.argv) < 2:
        return 0
    
    files_to_check = [Path(f) for f in sys.argv[1:] if f.endswith('.py')]
    
    if not files_to_check:
        return 0
    
    print("Checking MLflow authentication setup...")
    print("-" * 50)
    
    all_valid = True
    for filepath in files_to_check:
        if not validate_file(filepath):
            all_valid = False
    
    if not all_valid:
        print("\n" + "=" * 50)
        print("⚠️  MLFLOW AUTHENTICATION CHECK FAILED")
        print("=" * 50)
        print("\nMLflow operations MUST include authentication!")
        print("\nRequired setup (one of):")
        print("  1. Set MLFLOW_TRACKING_TOKEN environment variable")
        print("  2. Pass headers with Authorization Bearer token")
        print("  3. Use get_auth_headers() utility function")
        print("\nExample:")
        print("  headers = get_auth_headers()")
        print("  client = MlflowClient(tracking_uri=uri, headers=headers)")
        print("\nSee docs/AUTH_ARCHITECTURE.md for details")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())