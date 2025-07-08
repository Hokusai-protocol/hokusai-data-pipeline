#!/usr/bin/env python3
"""Analyze test coverage for the project."""

import os
from pathlib import Path


def find_python_files(src_dir: str = "src"):
    """Find all Python files in the source directory."""
    python_files = []
    for root, dirs, files in os.walk(src_dir):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.endswith(".py") and not file.startswith("__pycache__"):
                path = Path(root) / file
                python_files.append(str(path))

    return sorted(python_files)

def find_test_files(test_dir: str = "tests"):
    """Find all test files."""
    test_files = []
    for root, dirs, files in os.walk(test_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]

        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                path = Path(root) / file
                test_files.append(str(path))

    return sorted(test_files)

def check_test_exists(src_file: str):
    """Check if a test file exists for a source file."""
    # Convert src/foo/bar.py to tests/unit/test_bar.py or tests/test_bar.py
    path = Path(src_file)
    test_name = f"test_{path.stem}.py"

    # Check various test locations
    possible_tests = [
        f"tests/unit/{test_name}",
        f"tests/{test_name}",
        f"tests/unit/{path.parent.name}/{test_name}",
        f"tests/integration/{test_name}",
    ]

    for test_path in possible_tests:
        if os.path.exists(test_path):
            return test_path

    return None

def main() -> None:
    """Main analysis function."""
    src_files = find_python_files()
    test_files = find_test_files()

    print(f"Found {len(src_files)} source files")
    print(f"Found {len(test_files)} test files")
    print("\n" + "="*80 + "\n")

    # Group by module
    modules = {}
    for src_file in src_files:
        parts = Path(src_file).parts
        if len(parts) > 1:
            module = parts[1]
            if module not in modules:
                modules[module] = {"src": [], "missing_tests": []}
            modules[module]["src"].append(src_file)

    # Check which files are missing tests
    for module, info in modules.items():
        for src_file in info["src"]:
            if "__init__.py" in src_file:
                continue

            test_file = check_test_exists(src_file)
            if not test_file:
                info["missing_tests"].append(src_file)

    # Print summary by module
    print("MODULES NEEDING MORE TESTS:\n")

    priority_modules = []

    for module, info in sorted(modules.items()):
        missing_count = len(info["missing_tests"])
        total_count = len([f for f in info["src"] if "__init__.py" not in f])

        if missing_count > 0:
            coverage_pct = (
                ((total_count - missing_count) / total_count * 100)
                if total_count > 0 else 0
            )
            priority_modules.append((missing_count, module, info, coverage_pct))

    # Sort by number of missing tests (descending)
    priority_modules.sort(reverse=True)

    for missing_count, module, info, coverage_pct in priority_modules:
        print(
            f"\n{module.upper()} - {coverage_pct:.0f}% files have tests "
            f"({missing_count} files need tests):"
        )
        for src_file in info["missing_tests"][:5]:  # Show first 5
            print(f"  - {src_file}")
        if len(info["missing_tests"]) > 5:
            print(f"  ... and {len(info['missing_tests']) - 5} more")

    # Calculate overall stats
    total_src = sum(
        len([f for f in info["src"] if "__init__.py" not in f])
        for info in modules.values()
    )
    total_missing = sum(len(info["missing_tests"]) for info in modules.values())

    print(f"\n{'='*80}")
    print(f"\nOVERALL: {total_src - total_missing}/{total_src} source files have tests")
    print(f"Current file coverage: {(total_src - total_missing) / total_src * 100:.1f}%")
    print(f"Need to add tests for {total_missing} more files to improve coverage")

if __name__ == "__main__":
    main()
