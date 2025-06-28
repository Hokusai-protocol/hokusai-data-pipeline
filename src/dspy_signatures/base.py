"""Base classes for DSPy signatures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Any, Dict, Optional, Type, Union
import dspy

from .metadata import SignatureMetadata


@dataclass
class SignatureField:
    """Represents a field in a DSPy signature."""
    
    name: str
    description: str
    type_hint: Type
    required: bool = True
    default: Any = None
    
    def validate(self, value: Any) -> bool:
        """Validate a value against this field."""
        if value is None:
            return not self.required
        
        # Basic type checking
        if self.type_hint in (str, int, float, bool):
            return isinstance(value, self.type_hint)
        elif self.type_hint == list:
            return isinstance(value, list)
        elif self.type_hint == dict:
            return isinstance(value, dict)
        
        # For other types, just check if value exists
        return True
    
    def to_dspy_field(self) -> str:
        """Convert to DSPy field format."""
        field_str = f"{self.name}"
        if self.description:
            field_str = f"{self.description}"
        return field_str


class BaseSignature(ABC):
    """Base class for all DSPy signatures in the library."""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.description = self.__class__.__doc__ or ""
        self.category = getattr(self.__class__, 'category', 'general')
        self._input_fields = None
        self._output_fields = None
    
    @classmethod
    @abstractmethod
    def get_input_fields(cls) -> List[SignatureField]:
        """Define input fields for the signature."""
        pass
    
    @classmethod
    @abstractmethod  
    def get_output_fields(cls) -> List[SignatureField]:
        """Define output fields for the signature."""
        pass
    
    @classmethod
    def get_examples(cls) -> List[Dict[str, Any]]:
        """Provide example inputs and outputs."""
        return []
    
    @classmethod
    def get_metadata(cls) -> SignatureMetadata:
        """Get signature metadata."""
        return SignatureMetadata(
            name=cls.__name__,
            description=cls.__doc__ or "",
            category=getattr(cls, 'category', 'general'),
            tags=getattr(cls, 'tags', []),
            version=getattr(cls, 'version', '1.0.0'),
            examples=cls.get_examples()
        )
    
    @property
    def input_fields(self) -> List[SignatureField]:
        """Get input fields (cached)."""
        if self._input_fields is None:
            self._input_fields = self.get_input_fields()
        return self._input_fields
    
    @property
    def output_fields(self) -> List[SignatureField]:
        """Get output fields (cached)."""
        if self._output_fields is None:
            self._output_fields = self.get_output_fields()
        return self._output_fields
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate inputs against signature fields."""
        for field in self.input_fields:
            if field.required and field.name not in inputs:
                raise ValueError(f"Missing required field: {field.name}")
            
            if field.name in inputs:
                if not field.validate(inputs[field.name]):
                    raise ValueError(f"Invalid type for field '{field.name}': expected {field.type_hint}")
        
        return True
    
    def to_dspy_signature(self) -> str:
        """Convert to DSPy signature string format."""
        # Build input string
        input_parts = []
        for field in self.input_fields:
            desc = field.description or field.name
            input_parts.append(f"{field.name}: {desc}")
        
        # Build output string  
        output_parts = []
        for field in self.output_fields:
            desc = field.description or field.name
            output_parts.append(f"{field.name}: {desc}")
        
        # Combine into signature
        inputs_str = ", ".join(input_parts)
        outputs_str = ", ".join(output_parts)
        
        return f"{inputs_str} -> {outputs_str}"
    
    def create_dspy_signature_class(self) -> Type[dspy.Signature]:
        """Create a DSPy Signature class dynamically."""
        # Create class attributes
        attrs = {
            "__doc__": self.to_dspy_signature(),
            "__module__": "dspy_signatures.dynamic"
        }
        
        # Add input fields
        for field in self.input_fields:
            field_desc = field.description or field.name
            if not field.required and field.default is not None:
                field_desc += f" (default: {field.default})"
            attrs[field.name] = dspy.InputField(desc=field_desc)
        
        # Add output fields
        for field in self.output_fields:
            field_desc = field.description or field.name  
            attrs[field.name] = dspy.OutputField(desc=field_desc)
        
        # Create the signature class
        signature_class = type(
            f"{self.name}Signature",
            (dspy.Signature,),
            attrs
        )
        
        return signature_class


class SignatureValidator:
    """Validates DSPy signatures."""
    
    def __init__(self):
        self.rules = {
            'min_input_fields': 1,
            'min_output_fields': 1,
            'valid_field_name_pattern': r'^[a-z][a-z0-9_]*$'
        }
    
    def validate_signature_class(self, signature_class: Type[BaseSignature]) -> None:
        """Validate a signature class."""
        # Check if it has required methods
        if not hasattr(signature_class, 'get_input_fields'):
            raise ValueError(f"{signature_class.__name__} must implement get_input_fields()")
        
        if not hasattr(signature_class, 'get_output_fields'):
            raise ValueError(f"{signature_class.__name__} must implement get_output_fields()")
        
        # Instantiate to check fields
        instance = signature_class()
        
        # Check minimum fields
        if len(instance.input_fields) < self.rules['min_input_fields']:
            raise ValueError(f"{signature_class.__name__} must have at least one input field")
        
        if len(instance.output_fields) < self.rules['min_output_fields']:
            raise ValueError(f"{signature_class.__name__} must have at least one output field")
        
        # Validate field names
        import re
        pattern = re.compile(self.rules['valid_field_name_pattern'])
        
        for field in instance.input_fields + instance.output_fields:
            if not pattern.match(field.name):
                raise ValueError(f"Invalid field name '{field.name}' in {signature_class.__name__}")
    
    def validate_field_name(self, name: str) -> bool:
        """Check if field name is valid."""
        import re
        if not name:
            return False
        pattern = re.compile(self.rules['valid_field_name_pattern'])
        return bool(pattern.match(name))


class SignatureComposer:
    """Composes multiple signatures together."""
    
    def compose(self, sig1: Type[BaseSignature], sig2: Type[BaseSignature]) -> Type[BaseSignature]:
        """Compose two signatures in sequence (output of sig1 feeds into sig2)."""
        # Get instances
        s1 = sig1()
        s2 = sig2()
        
        # Check compatibility - at least one output of sig1 should match input of sig2
        s1_outputs = {f.name for f in s1.output_fields}
        s2_inputs = {f.name for f in s2.input_fields}
        
        if not s1_outputs.intersection(s2_inputs):
            raise ValueError(f"Cannot compose {sig1.__name__} and {sig2.__name__}: no matching fields")
        
        # Create composed signature
        class ComposedSignature(BaseSignature):
            category = 'composed'
            
            @classmethod
            def get_input_fields(cls):
                # Use inputs from first signature
                return s1.get_input_fields()
            
            @classmethod
            def get_output_fields(cls):
                # Use outputs from second signature
                return s2.get_output_fields()
        
        ComposedSignature.__name__ = f"{sig1.__name__}_{sig2.__name__}"
        ComposedSignature.__doc__ = f"Composition of {sig1.__name__} and {sig2.__name__}"
        
        return ComposedSignature
    
    def merge(self, sig1: Type[BaseSignature], sig2: Type[BaseSignature]) -> Type[BaseSignature]:
        """Merge two signatures for parallel execution."""
        # Get instances
        s1 = sig1()
        s2 = sig2()
        
        # Create merged signature
        class MergedSignature(BaseSignature):
            category = 'merged'
            
            @classmethod
            def get_input_fields(cls):
                # Union of input fields (avoiding duplicates)
                fields = {}
                for field in s1.get_input_fields():
                    fields[field.name] = field
                for field in s2.get_input_fields():
                    if field.name not in fields:
                        fields[field.name] = field
                return list(fields.values())
            
            @classmethod 
            def get_output_fields(cls):
                # All output fields from both
                return s1.get_output_fields() + s2.get_output_fields()
        
        MergedSignature.__name__ = f"{sig1.__name__}_and_{sig2.__name__}"
        MergedSignature.__doc__ = f"Parallel execution of {sig1.__name__} and {sig2.__name__}"
        
        return MergedSignature