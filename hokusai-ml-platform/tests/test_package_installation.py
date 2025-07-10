"""Tests for package installation and imports."""
import subprocess
import sys
from pathlib import Path

import pytest


class TestPackageInstallation:
    """Test suite for verifying package installation works correctly."""

    @pytest.fixture
    def temp_venv(self, tmp_path: str):
        """Create a temporary virtual environment for testing."""
        venv_path = tmp_path / "test_venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

        # Get paths for the virtual environment
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python.exe"
            pip_path = venv_path / "Scripts" / "pip.exe"
        else:
            python_path = venv_path / "bin" / "python"
            pip_path = venv_path / "bin" / "pip"

        return {
            "path": venv_path,
            "python": str(python_path),
            "pip": str(pip_path)
        }

    def test_package_metadata(self) -> None:
        """Test that package metadata is correctly configured."""
        # This test runs in the current environment where the package should be installed
        try:
            import hokusai
            assert hasattr(hokusai, "__version__")
        except ImportError:
            pytest.skip("Package not installed in current environment")

    def test_all_modules_importable(self) -> None:
        """Test that all main modules can be imported."""
        modules_to_test = [
            "hokusai",
            "hokusai.core",
            "hokusai.core.models",
            "hokusai.core.registry",
            "hokusai.core.versioning",
            "hokusai.core.ab_testing",
            "hokusai.core.inference",
            "hokusai.tracking",
            "hokusai.tracking.experiments",
            "hokusai.tracking.performance",
            "hokusai.api",
            "hokusai.utils",
        ]

        for module_name in modules_to_test:
            try:
                __import__(module_name)
            except ImportError as e:
                # Check if it's because package isn't installed
                if "hokusai" in str(e):
                    pytest.skip("Package not installed in current environment")
                else:
                    # It's a different import error - let it fail
                    raise

    def test_build_package(self, tmp_path: str) -> None:
        """Test that package can be built successfully."""
        # Get the package root directory
        package_root = Path(__file__).parent.parent

        # Create a temporary directory for build artifacts
        build_dir = tmp_path / "build"
        build_dir.mkdir()

        # Run build command
        result = subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(build_dir)],
            cwd=str(package_root),
            capture_output=True,
            text=True
        )

        # Check build was successful
        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Check that wheel and sdist were created
        files = list(build_dir.glob("*"))
        wheel_files = [f for f in files if f.suffix == ".whl"]
        sdist_files = [f for f in files if f.suffix == ".gz"]

        assert len(wheel_files) == 1, "Expected exactly one wheel file"
        assert len(sdist_files) == 1, "Expected exactly one sdist file"

        # Verify wheel filename format
        wheel_name = wheel_files[0].name
        assert "hokusai_ml_platform" in wheel_name
        assert "1.0.0" in wheel_name

    @pytest.mark.slow
    def test_install_from_source(self, temp_venv, tmp_path: str) -> None:
        """Test that package can be installed from source."""
        package_root = Path(__file__).parent.parent

        # Install the package in editable mode
        result = subprocess.run(
            [temp_venv["pip"], "install", "-e", str(package_root)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0, f"Installation failed: {result.stderr}"

        # Test that package can be imported in the new environment
        test_import = subprocess.run(
            [temp_venv["python"], "-c", "import hokusai; print(hokusai.__name__)"],
            capture_output=True,
            text=True
        )

        assert test_import.returncode == 0
        assert "hokusai" in test_import.stdout

    @pytest.mark.slow
    def test_install_from_wheel(self, temp_venv, tmp_path: str) -> None:
        """Test that package can be installed from built wheel."""
        package_root = Path(__file__).parent.parent
        build_dir = tmp_path / "build"
        build_dir.mkdir()

        # Build the package
        build_result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(build_dir)],
            cwd=str(package_root),
            capture_output=True,
            text=True
        )

        assert build_result.returncode == 0

        # Find the wheel file
        wheel_file = next(build_dir.glob("*.whl"))

        # Install from wheel
        install_result = subprocess.run(
            [temp_venv["pip"], "install", str(wheel_file)],
            capture_output=True,
            text=True
        )

        assert install_result.returncode == 0, f"Installation failed: {install_result.stderr}"

        # Verify installation
        check_result = subprocess.run(
            [temp_venv["python"], "-c",
             "import hokusai.core.registry; print('Import successful')"],
            capture_output=True,
            text=True
        )

        assert check_result.returncode == 0
        assert "Import successful" in check_result.stdout

    def test_dependencies_specified(self) -> None:
        """Test that all required dependencies are specified in pyproject.toml."""
        package_root = Path(__file__).parent.parent
        pyproject_path = package_root / "pyproject.toml"

        assert pyproject_path.exists(), "pyproject.toml not found"

        # Read pyproject.toml
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        # Check required fields
        assert "project" in pyproject
        assert "dependencies" in pyproject["project"]

        # Check key dependencies are listed
        deps = pyproject["project"]["dependencies"]
        dep_names = [d.split(">=")[0] for d in deps]

        required_deps = ["mlflow", "metaflow", "redis", "fastapi", "pydantic"]
        for dep in required_deps:
            assert dep in dep_names, f"Missing required dependency: {dep}"

    def test_package_version(self) -> None:
        """Test that package version is accessible and follows semantic versioning."""
        package_root = Path(__file__).parent.parent
        pyproject_path = package_root / "pyproject.toml"

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        version = pyproject["project"]["version"]

        # Check semantic versioning format
        parts = version.split(".")
        assert len(parts) == 3, "Version should be in X.Y.Z format"

        for part in parts:
            assert part.isdigit(), f"Version part '{part}' is not numeric"

    def test_package_urls(self) -> None:
        """Test that package URLs are correctly configured."""
        package_root = Path(__file__).parent.parent
        pyproject_path = package_root / "pyproject.toml"

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        urls = pyproject["project"]["urls"]
        required_urls = ["Homepage", "Documentation", "Repository", "Issues"]

        for url_type in required_urls:
            assert url_type in urls, f"Missing URL: {url_type}"
            assert urls[url_type].startswith("https://"), f"Invalid URL for {url_type}"


class TestPackageStructure:
    """Test the package structure and organization."""

    def test_src_layout(self) -> None:
        """Test that package uses src layout correctly."""
        package_root = Path(__file__).parent.parent
        src_dir = package_root / "src" / "hokusai"

        assert src_dir.exists(), "src/hokusai directory not found"
        assert (src_dir / "__init__.py").exists(), "Missing __init__.py in hokusai"

        # Check main subdirectories exist
        expected_dirs = ["core", "tracking", "api", "utils"]
        for dir_name in expected_dirs:
            dir_path = src_dir / dir_name
            assert dir_path.exists(), f"Missing directory: {dir_name}"
            assert (dir_path / "__init__.py").exists(), f"Missing __init__.py in {dir_name}"

    def test_no_missing_init_files(self) -> None:
        """Test that all Python directories have __init__.py files."""
        package_root = Path(__file__).parent.parent
        src_dir = package_root / "src"

        for py_file in src_dir.rglob("*.py"):
            # Skip __pycache__ directories
            if "__pycache__" in str(py_file):
                continue

            # Check that parent directory has __init__.py
            parent = py_file.parent
            if parent != src_dir and parent.name != "src":
                init_file = parent / "__init__.py"
                assert init_file.exists(), f"Missing __init__.py in {parent}"