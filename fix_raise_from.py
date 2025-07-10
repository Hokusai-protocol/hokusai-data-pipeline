#!/usr/bin/env python3
"""Fix B904: raise-without-from-inside-except issues."""

import ast
import re
import sys
from pathlib import Path


def fix_raise_from_in_file(filepath: str):
    """Fix raise statements in except blocks to use 'raise ... from'."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Parse the file to find except blocks with raise
    try:
        tree = ast.parse(content)
    except SyntaxError:
        print(f"Skipping {filepath} due to syntax error")
        return False
    
    lines = content.splitlines()
    modified = False
    
    class RaiseVisitor(ast.NodeVisitor):
        def __init__(self):
            self.fixes = []
        
        def visit_ExceptHandler(self, node):
            # Look for raise statements in except handlers
            for child in ast.walk(node):
                if isinstance(child, ast.Raise) and child.cause is None:
                    # Check if it's raising a new exception (not re-raising)
                    if child.exc is not None:
                        line_idx = child.lineno - 1
                        if line_idx < len(lines):
                            line = lines[line_idx]
                            # Check if it already has 'from'
                            if ' from ' not in line:
                                # Get the exception variable name if it exists
                                exc_name = node.name if node.name else 'e'
                                # For HTTPException and similar, we want 'from None' usually
                                # unless there's an actual exception being caught
                                if node.type and node.name:
                                    self.fixes.append((child.lineno, exc_name))
                                else:
                                    self.fixes.append((child.lineno, 'None'))
            self.generic_visit(node)
    
    visitor = RaiseVisitor()
    visitor.visit(tree)
    
    # Apply fixes in reverse order to maintain line numbers
    for lineno, exc_ref in sorted(visitor.fixes, reverse=True):
        line_idx = lineno - 1
        if line_idx < len(lines):
            line = lines[line_idx]
            # Handle multi-line raise statements
            if line.strip().startswith('raise '):
                # Find the end of the raise statement
                paren_count = line.count('(') - line.count(')')
                end_idx = line_idx
                
                while paren_count > 0 and end_idx + 1 < len(lines):
                    end_idx += 1
                    paren_count += lines[end_idx].count('(') - lines[end_idx].count(')')
                
                # Add 'from exc_ref' to the last line of the raise statement
                last_line = lines[end_idx]
                # Remove trailing parenthesis if exists
                if last_line.rstrip().endswith(')'):
                    lines[end_idx] = last_line.rstrip()[:-1] + f') from {exc_ref}'
                else:
                    lines[end_idx] = last_line.rstrip() + f' from {exc_ref}'
                modified = True
    
    if modified:
        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))
        return True
    return False


def main():
    # Get all Python files with B904 issues
    import subprocess
    import json
    
    result = subprocess.run(
        ['ruff', 'check', 'src/', 'tests/', '--select', 'B904', '--output-format=json'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("No B904 issues found!")
        return
    
    issues = json.loads(result.stdout)
    files_to_fix = set(issue['filename'] for issue in issues)
    
    print(f"Found {len(issues)} B904 issues in {len(files_to_fix)} files")
    
    fixed_count = 0
    for filepath in files_to_fix:
        if fix_raise_from_in_file(filepath):
            fixed_count += 1
            print(f"Fixed: {filepath}")
    
    print(f"\nFixed {fixed_count} files")


if __name__ == '__main__':
    main()