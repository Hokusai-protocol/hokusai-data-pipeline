"""Configuration parser for DSPy models."""

import yaml
from pathlib import Path
from typing import Any, Dict, Union
import json

from ...utils.logging_utils import get_pipeline_logger

logger = get_pipeline_logger(__name__)


class DSPyConfigParser:
    """Parser for DSPy configuration files.
    
    Supports parsing YAML configurations that define DSPy programs,
    including their signatures, chains, and source locations.
    """

    # Schema for DSPy configuration
    CONFIG_SCHEMA = {
        "required": ["name", "version", "source"],
        "optional": ["description", "author", "signatures", "chains", "dependencies"]
    }

    def parse_yaml(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """Parse a YAML configuration file.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            Parsed configuration dictionary
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If YAML is invalid or missing required fields

        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")

        # Validate required fields
        self._validate_config(config)

        # Process nested structures
        config = self._process_config(config)

        logger.info(f"Successfully parsed DSPy configuration: {config['name']} v{config['version']}")
        return config

    def parse_json(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """Parse a JSON configuration file.
        
        Args:
            config_path: Path to the JSON configuration file
            
        Returns:
            Parsed configuration dictionary
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If JSON is invalid or missing required fields

        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

        # Validate required fields
        self._validate_config(config)

        # Process nested structures
        config = self._process_config(config)

        logger.info(f"Successfully parsed DSPy configuration: {config['name']} v{config['version']}")
        return config

    def parse_python_config(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Python dictionary configuration.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            Validated and processed configuration dictionary
            
        Raises:
            ValueError: If configuration is invalid

        """
        # Validate required fields
        self._validate_config(config_dict)

        # Process nested structures
        config = self._process_config(config_dict)

        logger.info(f"Successfully parsed DSPy configuration: {config['name']} v{config['version']}")
        return config

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration has required fields.
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ValueError: If required fields are missing

        """
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a dictionary")

        missing_fields = []
        for field in self.CONFIG_SCHEMA["required"]:
            if field not in config:
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(f"Missing required fields in configuration: {', '.join(missing_fields)}")

        # Validate source structure
        if not isinstance(config["source"], dict):
            raise ValueError("'source' must be a dictionary")

        if "type" not in config["source"]:
            raise ValueError("'source' must have a 'type' field")

        # Validate source type
        valid_source_types = ["local", "huggingface", "github"]
        if config["source"]["type"] not in valid_source_types:
            raise ValueError(f"Invalid source type: {config['source']['type']}. "
                           f"Must be one of: {', '.join(valid_source_types)}")

    def _process_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process and normalize configuration.
        
        Args:
            config: Raw configuration dictionary
            
        Returns:
            Processed configuration dictionary

        """
        # Ensure version is a string
        config["version"] = str(config["version"])

        # Process signatures if present
        if "signatures" in config:
            config["signatures"] = self._process_signatures(config["signatures"])

        # Process chains if present
        if "chains" in config:
            config["chains"] = self._process_chains(config["chains"])

        # Add default values for optional fields
        for field in self.CONFIG_SCHEMA["optional"]:
            if field not in config:
                config[field] = self._get_default_value(field)

        return config

    def _process_signatures(self, signatures: Any) -> Dict[str, Dict[str, Any]]:
        """Process signature definitions.
        
        Args:
            signatures: Raw signature definitions
            
        Returns:
            Processed signature dictionary

        """
        if not isinstance(signatures, dict):
            raise ValueError("Signatures must be a dictionary")

        processed = {}
        for name, sig_def in signatures.items():
            if not isinstance(sig_def, dict):
                raise ValueError(f"Signature '{name}' must be a dictionary")

            # Ensure required signature fields
            if "inputs" not in sig_def or "outputs" not in sig_def:
                raise ValueError(f"Signature '{name}' must have 'inputs' and 'outputs'")

            processed[name] = {
                "inputs": sig_def["inputs"],
                "outputs": sig_def["outputs"],
                "description": sig_def.get("description", ""),
                "examples": sig_def.get("examples", [])
            }

        return processed

    def _process_chains(self, chains: Any) -> Dict[str, Dict[str, Any]]:
        """Process chain definitions.
        
        Args:
            chains: Raw chain definitions
            
        Returns:
            Processed chain dictionary

        """
        if not isinstance(chains, dict):
            raise ValueError("Chains must be a dictionary")

        processed = {}
        for name, chain_def in chains.items():
            if not isinstance(chain_def, dict):
                raise ValueError(f"Chain '{name}' must be a dictionary")

            # Ensure required chain fields
            if "steps" not in chain_def:
                raise ValueError(f"Chain '{name}' must have 'steps'")

            processed[name] = {
                "steps": chain_def["steps"],
                "description": chain_def.get("description", ""),
                "input_signature": chain_def.get("input_signature"),
                "output_signature": chain_def.get("output_signature")
            }

        return processed

    def _get_default_value(self, field: str) -> Any:
        """Get default value for optional field.
        
        Args:
            field: Field name
            
        Returns:
            Default value for the field

        """
        defaults = {
            "description": "",
            "author": "unknown",
            "signatures": {},
            "chains": {},
            "dependencies": []
        }
        return defaults.get(field, None)

    def create_example_config(self, output_path: Union[str, Path]) -> None:
        """Create an example DSPy configuration file.
        
        Args:
            output_path: Path where to save the example configuration

        """
        example_config = {
            "name": "example-dspy-model",
            "version": "1.0.0",
            "description": "Example DSPy model configuration",
            "author": "Hokusai Team",
            "source": {
                "type": "local",
                "path": "./models/my_dspy_program.py",
                "class_name": "MyDSPyProgram",
                "format": "python"
            },
            "signatures": {
                "text_generation": {
                    "inputs": ["prompt", "context"],
                    "outputs": ["generated_text"],
                    "description": "Generate text based on prompt and context"
                },
                "text_classification": {
                    "inputs": ["text"],
                    "outputs": ["label", "confidence"],
                    "description": "Classify text into categories"
                }
            },
            "chains": {
                "main_chain": {
                    "description": "Main processing chain",
                    "steps": ["text_generation", "text_classification"],
                    "input_signature": "text_generation",
                    "output_signature": "text_classification"
                }
            },
            "dependencies": ["transformers>=4.0.0", "torch>=2.0.0"]
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Created example DSPy configuration at: {output_path}")
