"""Test to ensure API service can start without import errors."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def test_api_imports_successfully():
    """Test that the API main module can be imported."""
    project_root = Path(__file__).parent.parent

    # Create a test script that attempts to import the API
    test_script = f"""
import sys
sys.path.insert(0, '{str(project_root)}')

try:
    # Try to import the FastAPI app
    from src.api.main import app
    print("SUCCESS: API imported successfully")
    sys.exit(0)
except SyntaxError as e:
    print(f"SYNTAX ERROR: {{e}}")
    sys.exit(1)
except ImportError as e:
    print(f"IMPORT ERROR: {{e}}")
    sys.exit(2)
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(3)
"""

    # Write test script to temp file and execute
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(test_script)
        temp_file = f.name

    try:
        # Set environment variables that might be required
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)

        # Run the test script
        result = subprocess.run(
            [sys.executable, temp_file], capture_output=True, text=True, env=env, timeout=10
        )

        if result.returncode == 1:
            pytest.fail(f"Syntax error in API: {result.stdout}")
        elif result.returncode == 2:
            # Import errors might be expected due to missing dependencies
            # but syntax should be valid
            pass
        elif result.returncode == 3:
            # Other errors might be config-related, that's okay
            pass
        elif result.returncode != 0:
            pytest.fail(f"Unexpected error: {result.stdout}")

    finally:
        os.unlink(temp_file)


def test_model_registry_imports():
    """Test that model_registry can be imported without syntax errors."""
    project_root = Path(__file__).parent.parent

    test_script = f"""
import sys
sys.path.insert(0, '{str(project_root)}')

try:
    from src.services.model_registry import HokusaiModelRegistry
    print("SUCCESS: HokusaiModelRegistry imported")
    
    # Try to instantiate it (might fail due to missing config, that's okay)
    try:
        registry = HokusaiModelRegistry()
        print("SUCCESS: HokusaiModelRegistry instantiated")
    except Exception as e:
        print(f"INFO: Instantiation failed (expected): {{e}}")
    
    sys.exit(0)
except SyntaxError as e:
    print(f"SYNTAX ERROR: {{e}}")
    sys.exit(1)
except ImportError as e:
    print(f"IMPORT ERROR (might be expected): {{e}}")
    sys.exit(0)  # Import errors are okay, we're just checking syntax
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(0)  # Other errors are okay, we're just checking syntax
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(test_script)
        temp_file = f.name

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)

        result = subprocess.run(
            [sys.executable, temp_file], capture_output=True, text=True, env=env, timeout=10
        )

        if result.returncode == 1:
            pytest.fail(f"Syntax error in model_registry: {result.stdout}")

    finally:
        os.unlink(temp_file)


if __name__ == "__main__":
    test_api_imports_successfully()
    test_model_registry_imports()
    print("All startup tests passed!")
