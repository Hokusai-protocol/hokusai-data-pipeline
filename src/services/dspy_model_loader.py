"""Main DSPy Model Loader module for Hokusai ML Platform."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
import mlflow

from .dspy import DSPyConfigParser, LocalDSPyLoader, RemoteDSPyLoader, DSPyValidator
from .model_registry import HokusaiModelRegistry
from ..utils.logging_utils import get_pipeline_logger

logger = get_pipeline_logger(__name__)


class DSPyModelLoader:
    """Main class for loading and managing DSPy models in Hokusai platform.
    
    This loader supports:
    - Loading DSPy programs from YAML configurations
    - Loading DSPy programs from Python classes
    - Loading from local files or remote repositories (HuggingFace)
    - Validation of DSPy module structure
    - Integration with Hokusai model registry
    """
    
    def __init__(self, registry: Optional[HokusaiModelRegistry] = None):
        """Initialize DSPy Model Loader.
        
        Args:
            registry: Optional Hokusai model registry instance. If not provided,
                     a new instance will be created.
        """
        self.registry = registry or HokusaiModelRegistry()
        self.config_parser = DSPyConfigParser()
        self.local_loader = LocalDSPyLoader()
        self.remote_loader = RemoteDSPyLoader()
        self.validator = DSPyValidator()
        
    def load_from_config(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """Load DSPy program from a configuration file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            Dictionary containing loaded DSPy program and metadata
            
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If configuration file not found
        """
        logger.info(f"Loading DSPy model from config: {config_path}")
        
        # Parse configuration
        config = self.config_parser.parse_yaml(config_path)
        
        # Validate configuration
        validation_result = self.validator.validate_config(config)
        if not validation_result["valid"]:
            raise ValueError(f"Invalid DSPy configuration: {validation_result['errors']}")
            
        # Load based on source type
        if config.get("source", {}).get("type") == "local":
            return self._load_local(config)
        elif config.get("source", {}).get("type") == "huggingface":
            return self._load_remote(config)
        else:
            raise ValueError(f"Unsupported source type: {config.get('source', {}).get('type')}")
            
    def load_from_class(self, module_path: str, class_name: str) -> Dict[str, Any]:
        """Load DSPy program directly from a Python class.
        
        Args:
            module_path: Python module path (e.g., "my_models.dspy_programs")
            class_name: Name of the DSPy program class
            
        Returns:
            Dictionary containing loaded DSPy program and metadata
            
        Raises:
            ImportError: If module or class cannot be imported
            ValueError: If class is not a valid DSPy program
        """
        logger.info(f"Loading DSPy model from class: {module_path}.{class_name}")
        
        # Load the class
        program = self.local_loader.load_python_class(module_path, class_name)
        
        # Validate the program
        validation_result = self.validator.validate_program(program)
        if not validation_result["valid"]:
            raise ValueError(f"Invalid DSPy program: {validation_result['errors']}")
            
        return {
            "program": program,
            "metadata": {
                "source_type": "python_class",
                "module_path": module_path,
                "class_name": class_name,
                "signatures": validation_result["signatures"],
                "chains": validation_result["chains"]
            }
        }
        
    def load_from_huggingface(self, repo_id: str, filename: str, 
                            token: Optional[str] = None) -> Dict[str, Any]:
        """Load DSPy program from HuggingFace Hub.
        
        Args:
            repo_id: HuggingFace repository ID (e.g., "username/model-name")
            filename: Name of the file to load from the repository
            token: Optional HuggingFace API token for private repos
            
        Returns:
            Dictionary containing loaded DSPy program and metadata
            
        Raises:
            ValueError: If program is invalid or cannot be loaded
            ConnectionError: If unable to connect to HuggingFace Hub
        """
        logger.info(f"Loading DSPy model from HuggingFace: {repo_id}/{filename}")
        
        # Download and load from HuggingFace
        program = self.remote_loader.load_from_huggingface(repo_id, filename, token)
        
        # Validate the program
        validation_result = self.validator.validate_program(program)
        if not validation_result["valid"]:
            raise ValueError(f"Invalid DSPy program: {validation_result['errors']}")
            
        return {
            "program": program,
            "metadata": {
                "source_type": "huggingface",
                "repo_id": repo_id,
                "filename": filename,
                "signatures": validation_result["signatures"],
                "chains": validation_result["chains"]
            }
        }
        
    def register_dspy_model(self, program_data: Dict[str, Any], 
                          model_name: str,
                          token_id: Optional[str] = None,
                          tags: Optional[Dict[str, str]] = None) -> str:
        """Register a DSPy model with the Hokusai model registry.
        
        Args:
            program_data: Dictionary containing DSPy program and metadata
            model_name: Name for the registered model
            token_id: Optional Hokusai token ID
            tags: Optional additional tags for the model
            
        Returns:
            Model ID of the registered model
            
        Raises:
            ValueError: If registration fails
        """
        logger.info(f"Registering DSPy model: {model_name}")
        
        # Prepare tags
        model_tags = {
            "model_type": "dspy",
            "source_type": program_data["metadata"]["source_type"],
            "num_signatures": str(len(program_data["metadata"]["signatures"])),
            "num_chains": str(len(program_data["metadata"]["chains"]))
        }
        
        if token_id:
            model_tags["hokusai_token_id"] = token_id
            
        if tags:
            model_tags.update(tags)
            
        # Log with MLflow
        with mlflow.start_run() as run:
            # Log metadata
            mlflow.log_params({
                "model_type": "dspy",
                "model_name": model_name,
                "source_type": program_data["metadata"]["source_type"]
            })
            
            # Log program info
            mlflow.log_dict(program_data["metadata"], "dspy_metadata.json")
            
            # Save program (this would need proper serialization)
            # For now, we'll just log the metadata
            model_uri = f"runs:/{run.info.run_id}/dspy_model"
            
            # Register with Hokusai registry
            result = self.registry.register_model(
                model_uri=model_uri,
                name=model_name,
                tags=model_tags
            )
            
            return result.model_version.name
            
    def _load_local(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load DSPy program from local source based on configuration."""
        source = config["source"]
        path = source["path"]
        
        if source.get("format") == "python":
            module_path = source.get("module_path", path)
            class_name = source["class_name"]
            return self.load_from_class(module_path, class_name)
        else:
            # Load from file
            program = self.local_loader.load_from_file(path)
            validation_result = self.validator.validate_program(program)
            
            if not validation_result["valid"]:
                raise ValueError(f"Invalid DSPy program: {validation_result['errors']}")
                
            return {
                "program": program,
                "metadata": {
                    "source_type": "local_file",
                    "path": path,
                    "signatures": validation_result["signatures"],
                    "chains": validation_result["chains"]
                }
            }
            
    def _load_remote(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load DSPy program from remote source based on configuration."""
        source = config["source"]
        repo_id = source["repo_id"]
        filename = source["filename"]
        token = source.get("token")
        
        return self.load_from_huggingface(repo_id, filename, token)