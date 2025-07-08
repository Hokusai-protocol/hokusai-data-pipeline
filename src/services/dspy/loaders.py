"""Loaders for DSPy models from various sources."""

import importlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union
import pickle
import json
from functools import lru_cache

from ...utils.logging_utils import get_pipeline_logger

logger = get_pipeline_logger(__name__)

# Try to import huggingface_hub, make it optional
try:
    from huggingface_hub import hf_hub_download, snapshot_download
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    logger.warning("huggingface_hub not installed. Remote loading from HuggingFace will not be available.")


class LocalDSPyLoader:
    """Loader for DSPy models from local filesystem."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize local loader.
        
        Args:
            cache_dir: Optional directory for caching loaded modules

        """
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "hokusai_dspy_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._module_cache = {}

    def load_from_file(self, file_path: Union[str, Path]) -> Any:
        """Load DSPy program from a file.
        
        Args:
            file_path: Path to the file containing DSPy program
            
        Returns:
            Loaded DSPy program
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ImportError: If file cannot be loaded

        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"DSPy program file not found: {file_path}")

        logger.info(f"Loading DSPy program from file: {file_path}")

        # Check file extension
        if file_path.suffix == ".py":
            return self._load_python_file(file_path)
        elif file_path.suffix == ".pkl":
            return self._load_pickle_file(file_path)
        elif file_path.suffix == ".json":
            return self._load_json_file(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def load_python_class(self, module_path: str, class_name: str) -> Any:
        """Load a DSPy program class from a Python module.
        
        Args:
            module_path: Python module path (e.g., "my_models.dspy_programs")
            class_name: Name of the DSPy program class
            
        Returns:
            Instantiated DSPy program
            
        Raises:
            ImportError: If module or class cannot be imported

        """
        cache_key = f"{module_path}.{class_name}"

        # Check cache
        if cache_key in self._module_cache:
            logger.debug(f"Loading from cache: {cache_key}")
            return self._module_cache[cache_key]

        logger.info(f"Loading DSPy class: {module_path}.{class_name}")

        try:
            # Import the module
            module = importlib.import_module(module_path)

            # Get the class
            if not hasattr(module, class_name):
                raise ImportError(f"Class '{class_name}' not found in module '{module_path}'")

            cls = getattr(module, class_name)

            # Instantiate the class
            instance = cls()

            # Cache the instance
            self._module_cache[cache_key] = instance

            return instance

        except ImportError as e:
            logger.error(f"Failed to import DSPy class: {e}")
            raise

    def _load_python_file(self, file_path: Path) -> Any:
        """Load DSPy program from a Python file."""
        # Create a unique module name
        module_name = f"dspy_module_{file_path.stem}_{id(file_path)}"

        # Load the module from file
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load module spec from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find DSPy program class in the module
        dspy_class = None
        for name, obj in vars(module).items():
            if isinstance(obj, type) and name != "DSPyProgram":  # Avoid base class
                # Simple heuristic: look for classes that might be DSPy programs
                if hasattr(obj, "forward") or "dspy" in name.lower():
                    dspy_class = obj
                    break

        if dspy_class is None:
            raise ImportError(f"No DSPy program class found in {file_path}")

        # Instantiate and return
        return dspy_class()

    def _load_pickle_file(self, file_path: Path) -> Any:
        """Load DSPy program from a pickle file."""
        with open(file_path, "rb") as f:
            return pickle.load(f)

    def _load_json_file(self, file_path: Path) -> Any:
        """Load DSPy program configuration from JSON file."""
        with open(file_path) as f:
            config = json.load(f)

        # This would need custom deserialization logic based on your DSPy format
        # For now, just return the config
        logger.warning("JSON loading returns configuration only, not instantiated program")
        return config


class RemoteDSPyLoader:
    """Loader for DSPy models from remote repositories."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize remote loader.
        
        Args:
            cache_dir: Optional directory for caching downloaded models

        """
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "hokusai_dspy_remote_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not HF_HUB_AVAILABLE:
            logger.warning("RemoteDSPyLoader initialized but huggingface_hub is not installed")

    def load_from_huggingface(self, repo_id: str, filename: str,
                            token: Optional[str] = None) -> Any:
        """Load DSPy program from HuggingFace Hub.
        
        Args:
            repo_id: HuggingFace repository ID (e.g., "username/model-name")
            filename: Name of the file to load from the repository
            token: Optional HuggingFace API token for private repos
            
        Returns:
            Loaded DSPy program
            
        Raises:
            ImportError: If huggingface_hub is not installed
            ConnectionError: If unable to connect to HuggingFace Hub
            FileNotFoundError: If file not found in repository

        """
        if not HF_HUB_AVAILABLE:
            raise ImportError("huggingface_hub is required for remote loading. "
                            "Install with: pip install huggingface_hub")

        logger.info(f"Loading DSPy model from HuggingFace: {repo_id}/{filename}")

        try:
            # Download file from HuggingFace Hub
            local_file = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                token=token,
                cache_dir=self.cache_dir,
                force_download=False
            )

            # Use local loader to load the downloaded file
            local_loader = LocalDSPyLoader()
            return local_loader.load_from_file(local_file)

        except Exception as e:
            logger.error(f"Failed to load from HuggingFace: {e}")
            raise ConnectionError(f"Failed to load DSPy model from HuggingFace: {e}")

    def load_from_github(self, repo_url: str, file_path: str,
                        branch: str = "main", token: Optional[str] = None) -> Any:
        """Load DSPy program from GitHub repository.
        
        Args:
            repo_url: GitHub repository URL
            file_path: Path to file within the repository
            branch: Git branch to use (default: "main")
            token: Optional GitHub token for private repos
            
        Returns:
            Loaded DSPy program
            
        Raises:
            ConnectionError: If unable to connect to GitHub
            FileNotFoundError: If file not found in repository

        """
        # This would require implementing GitHub API access
        # For now, raise NotImplementedError
        raise NotImplementedError("GitHub loading not yet implemented")

    @lru_cache(maxsize=10)
    def list_available_models(self, search_query: Optional[str] = None) -> Dict[str, Any]:
        """List available DSPy models from HuggingFace Hub.
        
        Args:
            search_query: Optional search query to filter models
            
        Returns:
            Dictionary of available models with metadata
            
        Raises:
            ImportError: If huggingface_hub is not installed

        """
        if not HF_HUB_AVAILABLE:
            raise ImportError("huggingface_hub is required for listing models")

        # This would use HuggingFace Hub API to search for DSPy models
        # For now, return empty dict
        logger.info("Model listing not fully implemented yet")
        return {}

    def download_model(self, repo_id: str, local_dir: Optional[Path] = None,
                      token: Optional[str] = None) -> Path:
        """Download entire DSPy model repository.
        
        Args:
            repo_id: HuggingFace repository ID
            local_dir: Optional local directory to save the model
            token: Optional HuggingFace API token
            
        Returns:
            Path to downloaded model directory
            
        Raises:
            ImportError: If huggingface_hub is not installed
            ConnectionError: If download fails

        """
        if not HF_HUB_AVAILABLE:
            raise ImportError("huggingface_hub is required for downloading models")

        local_dir = local_dir or self.cache_dir / repo_id.replace("/", "_")

        try:
            # Download entire repository
            local_path = snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                token=token,
                cache_dir=self.cache_dir
            )

            logger.info(f"Downloaded model to: {local_path}")
            return Path(local_path)

        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise ConnectionError(f"Failed to download model: {e}")
