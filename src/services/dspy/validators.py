"""Validators for DSPy models and configurations."""

from typing import Any, Dict, List, Optional, Set
import inspect

from ...utils.logging_utils import get_pipeline_logger

logger = get_pipeline_logger(__name__)


class DSPyValidator:
    """Validator for DSPy programs and configurations.
    
    Validates:
    - DSPy program structure and signatures
    - Configuration files
    - Chain definitions
    - Input/output specifications
    """

    # Required attributes for a valid DSPy program
    REQUIRED_PROGRAM_ATTRS = ["forward"]

    # Valid signature field types
    VALID_FIELD_TYPES = ["input", "output", "instruction", "example"]

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a DSPy configuration dictionary.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Validation result with 'valid' boolean and 'errors' list

        """
        errors = []

        # Check required fields
        required_fields = ["name", "version", "source"]
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        # Validate source configuration
        if "source" in config:
            source_errors = self._validate_source_config(config["source"])
            errors.extend(source_errors)

        # Validate signatures if present
        if "signatures" in config:
            sig_errors = self._validate_signatures_config(config["signatures"])
            errors.extend(sig_errors)

        # Validate chains if present
        if "chains" in config:
            chain_errors = self._validate_chains_config(
                config["chains"],
                config.get("signatures", {})
            )
            errors.extend(chain_errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def validate_program(self, program: Any) -> Dict[str, Any]:
        """Validate a DSPy program instance.
        
        Args:
            program: DSPy program instance to validate
            
        Returns:
            Validation result with program metadata

        """
        errors = []
        signatures = {}
        chains = {}

        # Check if it's a valid object
        if program is None:
            errors.append("Program is None")
            return {
                "valid": False,
                "errors": errors,
                "signatures": signatures,
                "chains": chains
            }

        # Check required attributes
        for attr in self.REQUIRED_PROGRAM_ATTRS:
            if not hasattr(program, attr):
                errors.append(f"Missing required attribute: {attr}")

        # Extract and validate signatures
        try:
            signatures = self._extract_signatures(program)
            if not signatures:
                errors.append("No signatures found in program")
        except Exception as e:
            errors.append(f"Error extracting signatures: {str(e)}")

        # Extract and validate chains
        try:
            chains = self._extract_chains(program)
        except Exception as e:
            errors.append(f"Error extracting chains: {str(e)}")

        # Validate forward method
        if hasattr(program, "forward"):
            forward_errors = self._validate_forward_method(program)
            errors.extend(forward_errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "signatures": signatures,
            "chains": chains,
            "program_type": type(program).__name__
        }

    def validate_signature(self, signature: Any) -> Dict[str, Any]:
        """Validate a single DSPy signature.
        
        Args:
            signature: DSPy signature to validate
            
        Returns:
            Validation result with signature metadata

        """
        errors = []
        fields = {}

        # Check if signature has required methods/attributes
        if not hasattr(signature, "fields"):
            errors.append("Signature missing 'fields' attribute")
        else:
            # Extract field information
            try:
                for field_name, field_info in signature.fields.items():
                    fields[field_name] = {
                        "type": getattr(field_info, "type", "unknown"),
                        "description": getattr(field_info, "description", "")
                    }
            except Exception as e:
                errors.append(f"Error processing signature fields: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "fields": fields
        }

    def _validate_source_config(self, source: Any) -> List[str]:
        """Validate source configuration."""
        errors = []

        if not isinstance(source, dict):
            errors.append("Source must be a dictionary")
            return errors

        if "type" not in source:
            errors.append("Source missing 'type' field")

        source_type = source.get("type")

        # Validate based on source type
        if source_type == "local":
            if "path" not in source:
                errors.append("Local source missing 'path' field")
        elif source_type == "huggingface":
            if "repo_id" not in source or "filename" not in source:
                errors.append("HuggingFace source missing 'repo_id' or 'filename'")
        elif source_type == "github":
            if "repo_url" not in source or "file_path" not in source:
                errors.append("GitHub source missing 'repo_url' or 'file_path'")

        return errors

    def _validate_signatures_config(self, signatures: Any) -> List[str]:
        """Validate signatures configuration."""
        errors = []

        if not isinstance(signatures, dict):
            errors.append("Signatures must be a dictionary")
            return errors

        for sig_name, sig_def in signatures.items():
            if not isinstance(sig_def, dict):
                errors.append(f"Signature '{sig_name}' must be a dictionary")
                continue

            # Check required fields
            if "inputs" not in sig_def:
                errors.append(f"Signature '{sig_name}' missing 'inputs'")
            elif not isinstance(sig_def["inputs"], list):
                errors.append(f"Signature '{sig_name}' inputs must be a list")

            if "outputs" not in sig_def:
                errors.append(f"Signature '{sig_name}' missing 'outputs'")
            elif not isinstance(sig_def["outputs"], list):
                errors.append(f"Signature '{sig_name}' outputs must be a list")

        return errors

    def _validate_chains_config(self, chains: Any, signatures: Dict[str, Any]) -> List[str]:
        """Validate chains configuration."""
        errors = []

        if not isinstance(chains, dict):
            errors.append("Chains must be a dictionary")
            return errors

        for chain_name, chain_def in chains.items():
            if not isinstance(chain_def, dict):
                errors.append(f"Chain '{chain_name}' must be a dictionary")
                continue

            # Check required fields
            if "steps" not in chain_def:
                errors.append(f"Chain '{chain_name}' missing 'steps'")
            elif not isinstance(chain_def["steps"], list):
                errors.append(f"Chain '{chain_name}' steps must be a list")
            else:
                # Validate step references
                for step in chain_def["steps"]:
                    if isinstance(step, str) and step not in signatures:
                        errors.append(f"Chain '{chain_name}' references unknown signature: {step}")

        return errors

    def _extract_signatures(self, program: Any) -> Dict[str, Any]:
        """Extract signatures from a DSPy program."""
        signatures = {}

        # Look for signature attributes
        for attr_name in dir(program):
            if attr_name.startswith("_"):
                continue

            attr = getattr(program, attr_name)

            # Check if it looks like a signature
            if hasattr(attr, "fields") or hasattr(attr, "input_fields"):
                sig_info = {
                    "name": attr_name,
                    "type": type(attr).__name__
                }

                # Extract fields if possible
                if hasattr(attr, "fields"):
                    sig_info["fields"] = list(attr.fields.keys())
                elif hasattr(attr, "input_fields") and hasattr(attr, "output_fields"):
                    sig_info["input_fields"] = list(attr.input_fields.keys())
                    sig_info["output_fields"] = list(attr.output_fields.keys())

                signatures[attr_name] = sig_info

        return signatures

    def _extract_chains(self, program: Any) -> Dict[str, Any]:
        """Extract chain information from a DSPy program."""
        chains = {}

        # Look for methods that might be chains
        for method_name in dir(program):
            if method_name.startswith("_") or method_name == "forward":
                continue

            method = getattr(program, method_name)

            if callable(method):
                # Try to get method signature
                try:
                    sig = inspect.signature(method)
                    chains[method_name] = {
                        "parameters": list(sig.parameters.keys()),
                        "type": "method"
                    }
                except:
                    pass

        return chains

    def _validate_forward_method(self, program: Any) -> List[str]:
        """Validate the forward method of a DSPy program."""
        errors = []

        forward = getattr(program, "forward", None)
        if not callable(forward):
            errors.append("'forward' attribute is not callable")
            return errors

        # Check method signature
        try:
            sig = inspect.signature(forward)
            params = list(sig.parameters.keys())

            # Remove 'self' if present
            if params and params[0] == "self":
                params.pop(0)

            if len(params) == 0:
                errors.append("'forward' method has no parameters")

        except Exception as e:
            errors.append(f"Error inspecting 'forward' method: {str(e)}")

        return errors

    def create_validation_report(self, program: Any, config: Optional[Dict[str, Any]] = None) -> str:
        """Create a detailed validation report for a DSPy program.
        
        Args:
            program: DSPy program to validate
            config: Optional configuration to validate
            
        Returns:
            Formatted validation report string

        """
        report_lines = ["DSPy Program Validation Report", "=" * 40]

        # Validate program
        program_result = self.validate_program(program)
        report_lines.append(f"\nProgram Type: {program_result.get('program_type', 'Unknown')}")
        report_lines.append(f"Program Valid: {program_result['valid']}")

        if program_result["errors"]:
            report_lines.append("\nProgram Errors:")
            for error in program_result["errors"]:
                report_lines.append(f"  - {error}")

        if program_result["signatures"]:
            report_lines.append("\nSignatures Found:")
            for sig_name, sig_info in program_result["signatures"].items():
                report_lines.append(f"  - {sig_name}: {sig_info}")

        # Validate config if provided
        if config:
            config_result = self.validate_config(config)
            report_lines.append(f"\nConfiguration Valid: {config_result['valid']}")

            if config_result["errors"]:
                report_lines.append("\nConfiguration Errors:")
                for error in config_result["errors"]:
                    report_lines.append(f"  - {error}")

        return "\n".join(report_lines)
