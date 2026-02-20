"""Tests verifying that the base install does not require ML dependencies.

These tests mock-remove ML packages to simulate a base-only environment and
verify that:
- Base modules (auth, exceptions, core.models, core.ab_testing) import cleanly
- ML modules (core.registry, tracking, config) raise MissingMLExtraError
- The error messages contain the actionable install command
"""

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Packages that should only be available with the [ml] extra
ML_PACKAGES = frozenset(
    {
        "mlflow",
        "metaflow",
        "redis",
        "numpy",
        "pandas",
        "sklearn",
        "scipy",
    }
)


def _block_ml_imports(name, *args, **kwargs):
    """A side_effect for builtins.__import__ that blocks ML packages."""
    top = name.split(".")[0]
    if top in ML_PACKAGES:
        raise ImportError(f"No module named {name!r} (blocked by test)")
    return importlib.__import__(name, *args, **kwargs)


def _fresh_import(module_name):
    """Import a module after purging its cached copy and all sub-modules.

    Preserves ``hokusai._lazy`` so that the ``MissingMLExtraError`` class identity
    stays consistent across fresh imports (needed for ``pytest.raises``).
    """
    to_remove = [
        key
        for key in sys.modules
        if (key == module_name or key.startswith(module_name + ".")) and key != "hokusai._lazy"
    ]
    for key in to_remove:
        del sys.modules[key]
    return importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Base-install tests (ML packages blocked)
# ---------------------------------------------------------------------------


class TestBaseInstallImports:
    """Verify that base modules import cleanly when ML packages are absent."""

    def test_import_hokusai_top_level(self):
        """Top-level ``import hokusai`` must succeed without ML deps."""
        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            mod = _fresh_import("hokusai")
            assert mod.__version__ == "1.0.0"

    def test_import_exceptions(self):
        """``hokusai.exceptions`` is pure Python — no ML deps."""
        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            mod = _fresh_import("hokusai.exceptions")
            assert hasattr(mod, "HokusaiException")
            assert hasattr(mod, "ModelNotFoundError")

    def test_import_auth(self):
        """``hokusai.auth`` depends only on ``requests``."""
        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            mod = _fresh_import("hokusai.auth")
            assert hasattr(mod, "HokusaiAuth")
            assert hasattr(mod, "AuthenticatedClient")

    def test_import_core_models(self):
        """``hokusai.core.models`` is pure Python — no ML deps."""
        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            mod = _fresh_import("hokusai.core.models")
            assert hasattr(mod, "HokusaiModel")
            assert hasattr(mod, "ModelFactory")

    def test_import_core_ab_testing(self):
        """``hokusai.core.ab_testing`` is pure Python — no ML deps."""
        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            mod = _fresh_import("hokusai.core.ab_testing")
            assert hasattr(mod, "ModelTrafficRouter")
            assert hasattr(mod, "ABTestConfig")


# ---------------------------------------------------------------------------
# ML-access-without-extra tests
# ---------------------------------------------------------------------------


class TestMLAccessWithoutExtra:
    """Accessing ML features without [ml] must raise MissingMLExtraError."""

    def test_core_registry_raises(self):
        """Accessing ``hokusai.core.ModelRegistry`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            core = _fresh_import("hokusai.core")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = core.ModelRegistry

    def test_core_inference_raises(self):
        """Accessing ``hokusai.core.HokusaiInferencePipeline`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            core = _fresh_import("hokusai.core")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = core.HokusaiInferencePipeline

    def test_core_versioning_raises(self):
        """Accessing ``hokusai.core.ModelVersionManager`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            core = _fresh_import("hokusai.core")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = core.ModelVersionManager

    def test_tracking_experiment_manager_raises(self):
        """Accessing ``hokusai.tracking.ExperimentManager`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            tracking = _fresh_import("hokusai.tracking")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = tracking.ExperimentManager

    def test_tracking_performance_tracker_raises(self):
        """Accessing ``hokusai.tracking.PerformanceTracker`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            tracking = _fresh_import("hokusai.tracking")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = tracking.PerformanceTracker

    def test_config_setup_mlflow_auth_raises(self):
        """Accessing ``hokusai.config.setup_mlflow_auth`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            config = _fresh_import("hokusai.config")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = config.setup_mlflow_auth

    def test_top_level_model_registry_raises(self):
        """Accessing ``hokusai.ModelRegistry`` without [ml] raises."""
        from hokusai._lazy import MissingMLExtraError

        with mock.patch("builtins.__import__", side_effect=_block_ml_imports):
            hok = _fresh_import("hokusai")
            with pytest.raises(MissingMLExtraError, match=r"pip install hokusai-ml-platform\[ml\]"):
                _ = hok.ModelRegistry


# ---------------------------------------------------------------------------
# Full-install tests (ML packages available)
# ---------------------------------------------------------------------------


class TestFullInstallImports:
    """With [ml] installed, all modules must import correctly."""

    def test_import_core_registry(self):
        """``hokusai.core.registry`` imports when mlflow is available."""
        mod = _fresh_import("hokusai.core.registry")
        assert hasattr(mod, "ModelRegistry")

    def test_import_core_inference(self):
        """``hokusai.core.inference`` imports when redis is available."""
        mod = _fresh_import("hokusai.core.inference")
        assert hasattr(mod, "HokusaiInferencePipeline")

    def test_import_tracking(self):
        """``hokusai.tracking`` re-exports when mlflow is available."""
        tracking = _fresh_import("hokusai.tracking")
        assert tracking.ExperimentManager is not None
        assert tracking.PerformanceTracker is not None

    def test_import_config(self):
        """``hokusai.config`` re-exports when mlflow is available."""
        config = _fresh_import("hokusai.config")
        assert config.setup_mlflow_auth is not None

    def test_top_level_lazy_attrs(self):
        """All lazy attributes on ``hokusai`` resolve with [ml]."""
        hok = _fresh_import("hokusai")
        assert hok.ModelRegistry is not None
        assert hok.ExperimentManager is not None
        assert hok.PerformanceTracker is not None


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


class TestErrorMessages:
    """Verify that error messages are actionable."""

    def test_missing_ml_extra_message_format(self):
        from hokusai._lazy import MissingMLExtraError

        err = MissingMLExtraError("ModelRegistry")
        msg = str(err)
        assert "ModelRegistry" in msg
        assert "pip install hokusai-ml-platform[ml]" in msg

    def test_missing_ml_extra_is_import_error(self):
        from hokusai._lazy import MissingMLExtraError

        assert issubclass(MissingMLExtraError, ImportError)


# ---------------------------------------------------------------------------
# pyproject.toml structure
# ---------------------------------------------------------------------------


class TestPyprojectStructure:
    """Verify pyproject.toml correctly defines base deps and [ml] extra."""

    @pytest.fixture
    def pyproject(self):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            return tomllib.load(f)

    def test_ml_deps_not_in_base(self, pyproject):
        """ML-heavy packages must NOT be in base dependencies."""
        base_deps = pyproject["project"]["dependencies"]
        base_names = {d.split(">=")[0].split("[")[0].lower() for d in base_deps}

        ml_packages = {"mlflow", "metaflow", "redis", "numpy", "pandas", "scikit-learn"}
        overlap = base_names & ml_packages
        assert not overlap, f"ML packages found in base deps: {overlap}"

    def test_ml_extra_exists(self, pyproject):
        """An [ml] optional extra must exist."""
        extras = pyproject["project"]["optional-dependencies"]
        assert "ml" in extras

    def test_ml_extra_contains_expected_deps(self, pyproject):
        """The [ml] extra must contain the ML-heavy packages."""
        ml_deps = pyproject["project"]["optional-dependencies"]["ml"]
        ml_names = {d.split(">=")[0].split("[")[0].lower() for d in ml_deps}

        expected = {"mlflow", "metaflow", "redis", "numpy", "pandas", "scikit-learn"}
        assert expected.issubset(ml_names), f"Missing from [ml]: {expected - ml_names}"

    def test_dev_extra_includes_ml(self, pyproject):
        """The [dev] extra must include [ml] so tests can run."""
        dev_deps = pyproject["project"]["optional-dependencies"]["dev"]
        has_ml_ref = any("ml" in d for d in dev_deps)
        assert has_ml_ref, "[dev] extra should reference [ml]"
