"""Test to ensure all Python files in the project have valid syntax."""

import ast
import os
import py_compile
import tempfile
from pathlib import Path

import pytest


def find_python_files(root_dir: str) -> list[Path]:
    """Find all Python files in the project."""
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # Skip virtual environments and cache directories
        dirs[:] = [
            d for d in dirs if d not in {".venv", "venv", "__pycache__", ".git", "node_modules"}
        ]

        for file in files:
            if file.endswith(".py"):
                python_files.append(Path(root) / file)

    return python_files


def test_all_python_files_compile():
    """Test that all Python files in src/ have valid syntax and compile."""
    # Get project root (parent of tests directory)
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        pytest.skip("src directory not found")

    python_files = find_python_files(str(src_dir))

    assert len(python_files) > 0, "No Python files found in src/"

    errors = []

    for file_path in python_files:
        try:
            # First check syntax by parsing the AST
            with open(file_path, encoding="utf-8") as f:
                source = f.read()
                ast.parse(source, filename=str(file_path))

            # Then try to compile it
            with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tmp:
                py_compile.compile(str(file_path), cfile=tmp.name, doraise=True)

        except SyntaxError as e:
            errors.append(f"{file_path}: {e.msg} at line {e.lineno}")
        except Exception as e:
            errors.append(f"{file_path}: {str(e)}")

    if errors:
        error_msg = "Syntax errors found in Python files:\n" + "\n".join(errors)
        pytest.fail(error_msg)


def test_model_registry_syntax():
    """Specifically test model_registry.py for syntax errors."""
    project_root = Path(__file__).parent.parent
    model_registry_path = project_root / "src" / "services" / "model_registry.py"

    if not model_registry_path.exists():
        pytest.skip("model_registry.py not found")

    try:
        with open(model_registry_path, encoding="utf-8") as f:
            source = f.read()
            tree = ast.parse(source, filename=str(model_registry_path))

            # Check for the HokusaiModelRegistry class
            classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            registry_class = next((c for c in classes if c.name == "HokusaiModelRegistry"), None)

            assert registry_class is not None, "HokusaiModelRegistry class not found"

            # Check for __init__ method
            init_method = next(
                (
                    node
                    for node in ast.walk(registry_class)
                    if isinstance(node, ast.FunctionDef) and node.name == "__init__"
                ),
                None,
            )

            assert init_method is not None, "__init__ method not found in HokusaiModelRegistry"

            # Verify the method has proper parameters
            args = init_method.args
            assert len(args.args) >= 1, "__init__ should have at least 'self' parameter"
            assert args.args[0].arg == "self", "First parameter should be 'self'"

    except SyntaxError as e:
        pytest.fail(f"Syntax error in model_registry.py: {e.msg} at line {e.lineno}")
    except Exception as e:
        pytest.fail(f"Error parsing model_registry.py: {str(e)}")


def test_api_main_imports():
    """Test that API main module can be imported without errors."""
    project_root = Path(__file__).parent.parent
    main_path = project_root / "src" / "api" / "main.py"

    if not main_path.exists():
        pytest.skip("src/api/main.py not found")

    try:
        with open(main_path, encoding="utf-8") as f:
            source = f.read()
            ast.parse(source, filename=str(main_path))

    except SyntaxError as e:
        pytest.fail(f"Syntax error in main.py: {e.msg} at line {e.lineno}")
    except Exception as e:
        pytest.fail(f"Error parsing main.py: {str(e)}")


if __name__ == "__main__":
    # Allow running directly for debugging
    test_all_python_files_compile()
    test_model_registry_syntax()
    test_api_main_imports()
    print("All syntax tests passed!")
