#!/usr/bin/env python3
"""Fix all line length issues in the codebase."""

import subprocess


def get_files_with_line_length_issues():
    """Get all files with E501 line length issues."""
    result = subprocess.run(
        ["ruff", "check", "src/", "tests/", "--select", "E501"],
        capture_output=True,
        text=True
    )

    files = set()
    for line in result.stdout.split("\n"):
        if line and ":" in line:
            file_path = line.split(":")[0]
            if file_path.endswith(".py"):
                files.add(file_path)

    return sorted(files)

def fix_file_line_lengths(file_path: str) -> None:
    """Fix line length issues in a specific file."""
    print(f"Processing {file_path}...")

    # Run ruff with line length fixes
    subprocess.run(
        ["ruff", "format", "--line-length", "100", file_path],
        capture_output=True
    )

    # Also try to fix with ruff check
    subprocess.run(
        ["ruff", "check", "--select", "E501", "--fix", "--unsafe-fixes", file_path],
        capture_output=True
    )

def main() -> None:
    """Main function to fix all line length issues."""
    print("Getting list of files with line length issues...")
    files = get_files_with_line_length_issues()

    print(f"Found {len(files)} files with line length issues")

    for file_path in files:
        fix_file_line_lengths(file_path)

    # Check remaining issues
    result = subprocess.run(
        ["ruff", "check", "src/", "tests/", "--select", "E501"],
        capture_output=True,
        text=True
    )

    remaining = len([l for l in result.stdout.split("\n") if l and "E501" in l])
    print(f"\nRemaining line length issues: {remaining}")

if __name__ == "__main__":
    main()