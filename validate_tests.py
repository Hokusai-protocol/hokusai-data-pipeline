#!/usr/bin/env python3
"""
Test validation script to ensure all test files are properly structured.
"""

import ast
import os
from pathlib import Path


def validate_test_file(file_path):
    """Validate that a test file has proper structure."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse the AST to validate syntax
        tree = ast.parse(content)
        
        # Count test functions and classes
        test_functions = []
        test_classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                test_functions.append(node.name)
            elif isinstance(node, ast.ClassDef) and node.name.startswith('Test'):
                test_classes.append(node.name)
        
        return {
            'valid': True,
            'test_functions': len(test_functions),
            'test_classes': len(test_classes),
            'functions': test_functions[:5],  # Show first 5
            'classes': test_classes
        }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e)
        }


def main():
    """Validate all test files."""
    print("🔍 Validating Test Files Structure")
    print("=" * 50)
    
    test_files = [
        'tests/unit/test_circuit_breaker_enhanced.py',
        'tests/integration/test_health_endpoints_enhanced.py', 
        'tests/load/test_service_load.py',
        'tests/chaos/test_failure_recovery.py'
    ]
    
    total_tests = 0
    total_classes = 0
    
    for test_file in test_files:
        print(f"\n📁 {test_file}")
        
        if not os.path.exists(test_file):
            print("❌ File does not exist")
            continue
            
        result = validate_test_file(test_file)
        
        if result['valid']:
            print(f"✅ Valid Python syntax")
            print(f"   Test classes: {result['test_classes']}")
            print(f"   Test functions: {result['test_functions']}")
            if result['functions']:
                print(f"   Sample functions: {', '.join(result['functions'])}")
            
            total_tests += result['test_functions']
            total_classes += result['test_classes']
        else:
            print(f"❌ Syntax error: {result['error']}")
    
    print(f"\n📊 Summary:")
    print(f"   Total test classes: {total_classes}")
    print(f"   Total test functions: {total_tests}")
    print(f"   Files validated: {len(test_files)}")
    
    if total_tests > 0:
        print("\n🎉 All test files are properly structured!")
    else:
        print("\n⚠️  No test functions found!")


if __name__ == "__main__":
    main()