"""Loader for DSPy signatures."""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, Type

from .registry import get_global_registry
from .base import BaseSignature, SignatureField


class SignatureLoader:
    """Loads and manages DSPy signatures."""
    
    def __init__(self):
        self.registry = get_global_registry()
    
    def load(self, name: str) -> BaseSignature:
        """Load a signature by name or alias from the registry."""
        return self.registry.get(name)
    
    def load_from_yaml(self, path: str) -> Dict[str, Any]:
        """Load signature configuration from YAML file."""
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    
    def load_from_json(self, path: str) -> Dict[str, Any]:
        """Load signature configuration from JSON file."""
        with open(path, 'r') as f:
            config = json.load(f)
        return config
    
    def create_custom_signature(self, config: Dict[str, Any]) -> Type[BaseSignature]:
        """Create a custom signature from configuration."""
        name = config.get("name", "CustomSignature")
        base_signature_name = config.get("base")
        overrides = config.get("overrides", {})
        additional_fields = config.get("additional_fields", {})
        
        # Get base signature if specified
        if base_signature_name:
            base_sig = self.registry.get(base_signature_name)
            base_input_fields = base_sig.get_input_fields()
            base_output_fields = base_sig.get_output_fields()
        else:
            base_input_fields = []
            base_output_fields = []
        
        # Create custom signature class
        class CustomSignature(BaseSignature):
            category = config.get("category", "custom")
            tags = config.get("tags", ["custom"])
            version = config.get("version", "1.0.0")
            
            @classmethod
            def get_input_fields(cls):
                fields = list(base_input_fields)
                
                # Add additional input fields
                for field_name, field_config in additional_fields.items():
                    if field_config.get("field_type") == "input":
                        field = SignatureField(
                            name=field_name,
                            description=field_config.get("description", ""),
                            type_hint=eval(field_config.get("type", "str")),
                            required=field_config.get("required", False),
                            default=field_config.get("default")
                        )
                        fields.append(field)
                
                # Apply overrides
                for field in fields:
                    if field.name in overrides:
                        for key, value in overrides[field.name].items():
                            setattr(field, key, value)
                
                return fields
            
            @classmethod
            def get_output_fields(cls):
                fields = list(base_output_fields)
                
                # Add additional output fields
                for field_name, field_config in additional_fields.items():
                    if field_config.get("field_type") == "output":
                        field = SignatureField(
                            name=field_name,
                            description=field_config.get("description", ""),
                            type_hint=eval(field_config.get("type", "str")),
                            required=field_config.get("required", True)
                        )
                        fields.append(field)
                
                return fields
            
            @classmethod
            def get_examples(cls):
                return config.get("examples", [])
        
        CustomSignature.__name__ = name
        CustomSignature.__doc__ = config.get("description", f"Custom signature: {name}")
        
        return CustomSignature
    
    def save_signature_config(self, signature: BaseSignature, path: str, format: str = "yaml") -> None:
        """Save signature configuration to file."""
        config = {
            "name": signature.name,
            "description": signature.description,
            "category": signature.category,
            "tags": getattr(signature, 'tags', []),
            "version": getattr(signature, 'version', '1.0.0'),
            "input_fields": [
                {
                    "name": f.name,
                    "description": f.description,
                    "type": str(f.type_hint),
                    "required": f.required,
                    "default": f.default
                }
                for f in signature.input_fields
            ],
            "output_fields": [
                {
                    "name": f.name,
                    "description": f.description,
                    "type": str(f.type_hint),
                    "required": f.required
                }
                for f in signature.output_fields
            ],
            "examples": signature.get_examples() if hasattr(signature, 'get_examples') else []
        }
        
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "yaml":
            with open(path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
        elif format == "json":
            with open(path, 'w') as f:
                json.dump(config, f, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def load_all_from_directory(self, directory: str) -> Dict[str, BaseSignature]:
        """Load all signature configurations from a directory."""
        signatures = {}
        path = Path(directory)
        
        # Load YAML files
        for yaml_file in path.glob("*.yaml"):
            config = self.load_from_yaml(str(yaml_file))
            sig = self.create_custom_signature(config)
            signatures[sig.__name__] = sig()
        
        # Load JSON files
        for json_file in path.glob("*.json"):
            config = self.load_from_json(str(json_file))
            sig = self.create_custom_signature(config)
            signatures[sig.__name__] = sig()
        
        return signatures