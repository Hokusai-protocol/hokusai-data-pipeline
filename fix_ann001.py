#!/usr/bin/env python3
"""Fix ANN001 issues (missing function argument type annotations)."""

import ast
import os
import re
import sys


def infer_type_from_click_decorator(source_lines, func_node, arg_name):
    """Infer type from click decorators."""
    # Look for decorators above the function
    start_line = func_node.lineno - 1
    
    # Look backwards for click decorators
    for i in range(start_line - 1, max(0, start_line - 10), -1):
        line = source_lines[i]
        if f'"{arg_name}"' in line or f"'{arg_name}'" in line:
            # Check for type=click.Path
            if "type=click.Path" in line:
                return "str"
            # Check for type=click.INT
            if "type=click.INT" in line:
                return "int"
            # Check for type=click.FLOAT  
            if "type=click.FLOAT" in line:
                return "float"
            # Check for type=int
            if "type=int" in line:
                return "int"
            # Check for type=float
            if "type=float" in line:
                return "float"
            # Check for is_flag=True
            if "is_flag=True" in line:
                return "bool"
    
    return None


def fix_missing_annotations(file_path: str):
    """Fix missing type annotations in a file."""
    with open(file_path, 'r') as f:
        content = f.read()
        source_lines = content.splitlines()
    
    # Parse the AST
    try:
        tree = ast.parse(content)
    except SyntaxError:
        print(f"Syntax error in {file_path}, skipping")
        return
    
    # Collect all functions with missing annotations
    fixes = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for i, arg in enumerate(node.args.args):
                if arg.annotation is None:
                    arg_name = arg.arg
                    
                    # Skip 'self' and 'cls'
                    if arg_name in ('self', 'cls'):
                        continue
                    
                    # Get the line with the function definition
                    func_line = source_lines[node.lineno - 1]
                    
                    # Try to infer type
                    inferred_type = None
                    
                    # Check for click decorators
                    if "@click" in "\n".join(source_lines[max(0, node.lineno - 10):node.lineno]):
                        inferred_type = infer_type_from_click_decorator(
                            source_lines, node, arg_name
                        )
                    
                    # Common patterns
                    if not inferred_type:
                        if (
                            "path" in arg_name.lower()
                            or "file" in arg_name.lower()
                            or "dir" in arg_name.lower()
                        ):
                            inferred_type = "str"
                        elif "config" in arg_name.lower() and "dict" not in arg_name.lower():
                            inferred_type = "str"
                        elif arg_name in (
                            "token_id", "model_id", "execution_id", "program_id", "batch_id"
                        ):
                            inferred_type = "str"
                        elif arg_name in ("timeout", "max_workers", "limit", "offset"):
                            inferred_type = "int"
                        elif arg_name in ("mode", "level", "status"):
                            inferred_type = "str"
                        elif "request" in arg_name:
                            # Skip request objects - usually typed in signature
                            continue
                    
                    if inferred_type:
                        # Find the argument in the function definition
                        pattern = rf'(\bdef\s+\w+\s*\([^)]*\b{re.escape(arg_name)}\b)'
                        match = re.search(pattern, func_line)
                        
                        if match:
                            # Replace arg_name with arg_name: type
                            old_text = arg_name
                            new_text = f"{arg_name}: {inferred_type}"
                            
                            # Make sure we're not already annotated
                            if f"{arg_name}:" not in func_line:
                                fixes.append((node.lineno - 1, arg_name, old_text, new_text))
    
    # Apply fixes
    if fixes:
        lines = source_lines[:]
        
        # Sort fixes by line number in reverse to avoid offset issues
        fixes.sort(key=lambda x: (x[0], -len(x[1])), reverse=True)
        
        for line_idx, arg_name, old_text, new_text in fixes:
            line = lines[line_idx]
            # Use word boundary to avoid partial matches
            lines[line_idx] = re.sub(rf'\b{re.escape(old_text)}\b(?!:)', new_text, line)
        
        # Write back
        with open(file_path, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"Fixed {len(fixes)} annotations in {file_path}")
        return len(fixes)
    
    return 0


def main():
    """Main function."""
    total_fixed = 0
    
    # Get all Python files with ANN001 issues
    cmd = "ruff check --select ANN001 --no-cache 2>/dev/null"
    cmd += " | grep 'ANN001' | cut -d':' -f1 | sort | uniq"
    result = os.popen(cmd).read()
    files = [f.strip() for f in result.splitlines() if f.strip()]
    
    print(f"Found {len(files)} files with ANN001 issues")
    
    for file_path in files:
        if os.path.exists(file_path):
            fixed = fix_missing_annotations(file_path)
            total_fixed += fixed
    
    print(f"\nTotal annotations fixed: {total_fixed}")


if __name__ == "__main__":
    main()