#!/usr/bin/env python3
"""Fix docstring punctuation issues (D400, D415)."""

import re
import subprocess
from typing import Optional


def fix_docstring_punctuation(file_path: str) -> Optional[bool]:
    """Fix docstring punctuation in a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Pattern to match docstrings
        # Matches single or multi-line docstrings
        docstring_pattern = r'("""|\'\'\')(.*?)(\1)'

        def fix_punctuation(match):
            quote = match.group(1)
            text = match.group(2)

            if not text.strip():
                return match.group(0)

            # Split into lines
            lines = text.split("\n")

            # Fix first line if it exists and doesn't end with punctuation
            if lines and lines[0].strip():
                first_line = lines[0].rstrip()
                # Check if it doesn't end with period, question mark, or exclamation
                if first_line and not first_line.endswith((".", "?", "!", ":", '"', "'")):
                    # Don't add period to parameter descriptions or similar
                    sections = [
                        "Args:", "Returns:", "Raises:", "Example:",
                        "Note:", "Warning:", "Parameters:", "Attributes:"
                    ]
                    if not any(first_line.strip().startswith(x) for x in sections):
                        lines[0] = first_line + "."

            # Rejoin
            fixed_text = "\n".join(lines)
            return f"{quote}{fixed_text}{quote}"

        # Apply fixes
        content = re.sub(docstring_pattern, fix_punctuation, content, flags=re.DOTALL)

        # Only write if changed
        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main() -> None:
    """Main function to fix docstring punctuation issues."""
    # Get all Python files with D400 or D415 issues
    result = subprocess.run(
        ["ruff", "check", ".", "--select", "D400,D415"],
        capture_output=True,
        text=True
    )

    files_to_fix = set()
    for line in result.stdout.split("\n"):
        if ":" in line and (".py:" in line):
            file_path = line.split(":")[0]
            files_to_fix.add(file_path)

    print(f"Found {len(files_to_fix)} files with docstring punctuation issues")

    fixed_count = 0
    for file_path in sorted(files_to_fix):
        if fix_docstring_punctuation(file_path):
            fixed_count += 1
            print(f"Fixed: {file_path}")

    print(f"\nFixed {fixed_count} files")

    # Check remaining issues
    result = subprocess.run(
        ["ruff", "check", ".", "--select", "D400,D415", "--statistics"],
        capture_output=True,
        text=True
    )

    print("\nRemaining issues:")
    print(result.stdout)


if __name__ == "__main__":
    main()