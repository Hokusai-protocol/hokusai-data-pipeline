#!/usr/bin/env python3
"""Fix remaining line length issues that ruff format couldn't handle."""

import subprocess
from typing import Optional


def get_line_length_issues():
    """Get all line length issues from ruff."""
    result = subprocess.run(
        ["ruff", "check", ".", "--select", "E501"],
        capture_output=True,
        text=True
    )

    # Parse the output to get file and line information
    issues = []
    for line in result.stderr.split("\n"):
        if ":" in line and "E501" in line:
            parts = line.split(":")
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = parts[1]
                if file_path and line_num.isdigit():
                    issues.append((file_path, int(line_num)))

    return issues


def fix_line_in_file(file_path: str, line_num) -> Optional[bool]:
    """Fix a specific line in a file."""
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()

        if line_num <= len(lines):
            line = lines[line_num - 1]

            # Skip if line is a comment or string that shouldn't be broken
            if line.strip().startswith("#") or '"""' in line or "'''" in line:
                return False

            # For long f-strings, use concatenation
            if 'f"' in line or "f'" in line:
                # This is complex, skip for manual fixing
                return False

            # For long strings, use implicit concatenation
            if '"' in line or "'" in line:
                # Complex case, skip for manual fixing
                return False

            # For function calls with many parameters, break after commas
            if "(" in line and ")" in line and "," in line:
                # Try to intelligently break the line
                indent = len(line) - len(line.lstrip())
                # This is complex, skip for manual fixing
                return False

        return False

    except Exception as e:
        print(f"Error fixing {file_path}:{line_num} - {e}")
        return False


def main() -> None:
    """Main function to fix line length issues."""
    print("Getting line length issues...")
    issues = get_line_length_issues()

    # Group by file
    files_to_fix = {}
    for file_path, line_num in issues:
        if file_path not in files_to_fix:
            files_to_fix[file_path] = []
        files_to_fix[file_path].append(line_num)

    print(f"Found {len(issues)} line length issues in {len(files_to_fix)} files")

    # For now, just run black on specific files with line length 100
    # This is more reliable than trying to fix individual lines
    for file_path in files_to_fix:
        print(f"Formatting {file_path}...")
        subprocess.run(
            ["black", "--line-length", "100", file_path],
            capture_output=True
        )

    # Check how many issues remain
    remaining = get_line_length_issues()
    print(f"\nRemaining issues: {len(remaining)}")

    if remaining:
        print("\nSome files need manual fixing:")
        remaining_files = set(issue[0] for issue in remaining)
        for f in sorted(remaining_files):
            print(f"  - {f}")


if __name__ == "__main__":
    main()