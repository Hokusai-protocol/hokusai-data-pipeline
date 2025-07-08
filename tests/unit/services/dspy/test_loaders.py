"""Unit tests for DSPy loaders."""

import pytest
import tempfile
import pickle
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.services.dspy.loaders import LocalDSPyLoader, RemoteDSPyLoader


class MockDSPyProgram:
    """Mock DSPy program for testing."""

    def __init__(self):
        self.forward = lambda x: x
        self.name = "MockDSPyProgram"


class TestLocalDSPyLoader:
    """Test suite for local DSPy loader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.loader = LocalDSPyLoader(cache_dir=Path(self.temp_dir) / "cache")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_load_pickle_file(self):
        """Test loading DSPy program from pickle file."""
        # Create a mock program and pickle it
        program = MockDSPyProgram()
        pickle_path = Path(self.temp_dir) / "program.pkl"

        with open(pickle_path, "wb") as f:
            pickle.dump(program, f)

        # Load it back
        loaded = self.loader.load_from_file(pickle_path)

        assert loaded.name == "MockDSPyProgram"
        assert callable(loaded.forward)

    def test_load_json_file(self):
        """Test loading configuration from JSON file."""
        config = {
            "name": "test-program",
            "signatures": ["sig1", "sig2"]
        }

        json_path = Path(self.temp_dir) / "config.json"
        with open(json_path, "w") as f:
            json.dump(config, f)

        # Load it (should return config, not program)
        loaded = self.loader.load_from_file(json_path)

        assert loaded["name"] == "test-program"
        assert loaded["signatures"] == ["sig1", "sig2"]

    def test_load_python_file(self):
        """Test loading DSPy program from Python file."""
        # Create a Python file with a DSPy program
        py_content = """
class TestDSPyProgram:
    def __init__(self):
        self.name = "TestProgram"
        
    def forward(self, x):
        return x * 2
"""

        py_path = Path(self.temp_dir) / "program.py"
        with open(py_path, "w") as f:
            f.write(py_content)

        loaded = self.loader.load_from_file(py_path)

        assert hasattr(loaded, "forward")
        assert loaded.forward(5) == 10

    def test_file_not_found(self):
        """Test handling of missing file."""
        with pytest.raises(FileNotFoundError):
            self.loader.load_from_file("nonexistent.pkl")

    def test_unsupported_file_format(self):
        """Test handling of unsupported file format."""
        txt_path = Path(self.temp_dir) / "file.txt"
        txt_path.touch()

        with pytest.raises(ValueError, match="Unsupported file format"):
            self.loader.load_from_file(txt_path)

    def test_load_python_class(self):
        """Test loading a specific class from module."""
        # Mock the import process
        mock_module = MagicMock()
        mock_class = MockDSPyProgram
        setattr(mock_module, "TestClass", mock_class)

        with patch("importlib.import_module", return_value=mock_module):
            loaded = self.loader.load_python_class("test_module", "TestClass")

        assert isinstance(loaded, MockDSPyProgram)

    def test_load_python_class_not_found(self):
        """Test handling of missing class in module."""
        mock_module = MagicMock()

        with patch("importlib.import_module", return_value=mock_module):
            with pytest.raises(ImportError, match="Class 'MissingClass' not found"):
                self.loader.load_python_class("test_module", "MissingClass")

    def test_module_caching(self):
        """Test that loaded modules are cached."""
        mock_module = MagicMock()
        mock_class = MockDSPyProgram
        setattr(mock_module, "TestClass", mock_class)

        with patch("importlib.import_module", return_value=mock_module) as mock_import:
            # Load twice
            loaded1 = self.loader.load_python_class("test_module", "TestClass")
            loaded2 = self.loader.load_python_class("test_module", "TestClass")

            # Should only import once due to caching
            mock_import.assert_called_once()


class TestRemoteDSPyLoader:
    """Test suite for remote DSPy loader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.loader = RemoteDSPyLoader(cache_dir=Path(self.temp_dir) / "cache")

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch("src.services.dspy.loaders.HF_HUB_AVAILABLE", False)
    def test_huggingface_not_available(self):
        """Test handling when huggingface_hub is not installed."""
        with pytest.raises(ImportError, match="huggingface_hub is required"):
            self.loader.load_from_huggingface("test/repo", "model.pkl")

    @patch("src.services.dspy.loaders.HF_HUB_AVAILABLE", True)
    @patch("src.services.dspy.loaders.hf_hub_download")
    def test_load_from_huggingface(self, mock_download):
        """Test loading from HuggingFace Hub."""
        # Create a mock file
        mock_program = MockDSPyProgram()
        mock_file = Path(self.temp_dir) / "downloaded.pkl"

        with open(mock_file, "wb") as f:
            pickle.dump(mock_program, f)

        mock_download.return_value = str(mock_file)

        # Load from HF
        loaded = self.loader.load_from_huggingface("test/repo", "model.pkl")

        assert loaded.name == "MockDSPyProgram"
        mock_download.assert_called_once_with(
            repo_id="test/repo",
            filename="model.pkl",
            token=None,
            cache_dir=self.loader.cache_dir,
            force_download=False
        )

    @patch("src.services.dspy.loaders.HF_HUB_AVAILABLE", True)
    @patch("src.services.dspy.loaders.hf_hub_download")
    def test_load_from_huggingface_with_token(self, mock_download):
        """Test loading from HuggingFace with authentication token."""
        mock_file = Path(self.temp_dir) / "model.pkl"
        mock_file.touch()
        mock_download.return_value = str(mock_file)

        with patch.object(LocalDSPyLoader, "load_from_file", return_value=Mock()):
            self.loader.load_from_huggingface("test/repo", "model.pkl", token="test_token")

        mock_download.assert_called_once()
        assert mock_download.call_args[1]["token"] == "test_token"

    def test_load_from_github_not_implemented(self):
        """Test that GitHub loading raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            self.loader.load_from_github("https://github.com/test/repo", "model.py")

    @patch("src.services.dspy.loaders.HF_HUB_AVAILABLE", True)
    def test_list_available_models(self):
        """Test listing available models."""
        # Currently returns empty dict
        models = self.loader.list_available_models()
        assert isinstance(models, dict)

    @patch("src.services.dspy.loaders.HF_HUB_AVAILABLE", True)
    @patch("src.services.dspy.loaders.snapshot_download")
    def test_download_model(self, mock_snapshot):
        """Test downloading entire model repository."""
        mock_snapshot.return_value = str(self.temp_dir / "downloaded")

        result = self.loader.download_model("test/repo")

        assert isinstance(result, Path)
        mock_snapshot.assert_called_once()
