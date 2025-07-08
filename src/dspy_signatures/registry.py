"""Registry for managing DSPy signatures."""

from typing import Dict, List, Optional, Any, Type
import threading

from .base import BaseSignature
from .metadata import SignatureMetadata


class SignatureRegistry:
    """Registry for managing DSPy signatures."""

    def __init__(self):
        self.signatures: Dict[str, BaseSignature] = {}
        self.metadata: Dict[str, SignatureMetadata] = {}
        self.aliases: Dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, signature: BaseSignature, metadata: SignatureMetadata) -> None:
        """Register a new signature."""
        with self._lock:
            if signature.name in self.signatures:
                raise ValueError(f"Signature '{signature.name}' already registered")

            self.signatures[signature.name] = signature
            self.metadata[signature.name] = metadata

    def get(self, name: str) -> BaseSignature:
        """Get a signature by name or alias."""
        with self._lock:
            # Check if it's an alias
            if name in self.aliases:
                name = self.aliases[name]

            if name not in self.signatures:
                raise KeyError(f"Signature '{name}' not found")

            return self.signatures[name]

    def get_metadata(self, name: str) -> SignatureMetadata:
        """Get metadata for a signature."""
        with self._lock:
            # Resolve alias if needed
            if name in self.aliases:
                name = self.aliases[name]

            if name not in self.metadata:
                raise KeyError(f"Metadata for signature '{name}' not found")

            return self.metadata[name]

    def create_alias(self, alias: str, signature_name: str) -> None:
        """Create an alias for a signature."""
        with self._lock:
            if signature_name not in self.signatures:
                raise KeyError(f"Cannot create alias: signature '{signature_name}' not found")

            self.aliases[alias] = signature_name

    def list_signatures(self) -> List[str]:
        """List all registered signature names."""
        with self._lock:
            return list(self.signatures.keys())

    def search(self, category: Optional[str] = None, tags: Optional[List[str]] = None) -> List[str]:
        """Search for signatures by category or tags."""
        results = []

        with self._lock:
            for name, metadata in self.metadata.items():
                # Filter by category
                if category and metadata.category != category:
                    continue

                # Filter by tags (all specified tags must be present)
                if tags:
                    sig_tags = set(metadata.tags)
                    if not all(tag in sig_tags for tag in tags):
                        continue

                results.append(name)

        return results

    def check_compatibility(self, sig1_name: str, sig2_name: str) -> bool:
        """Check if two signatures are compatible for chaining."""
        try:
            sig1 = self.get(sig1_name)
            sig2 = self.get(sig2_name)

            # Get output fields from sig1 and input fields from sig2
            sig1_outputs = {f.name for f in sig1.output_fields}
            sig2_inputs = {f.name for f in sig2.input_fields}

            # Check if any output from sig1 matches input of sig2
            return bool(sig1_outputs.intersection(sig2_inputs))
        except KeyError:
            return False

    def export_catalog(self) -> List[Dict[str, Any]]:
        """Export the signature catalog."""
        catalog = []

        with self._lock:
            for name, signature in self.signatures.items():
                metadata = self.metadata[name]

                entry = {
                    "name": name,
                    "metadata": metadata.to_dict(),
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
                            "type": str(f.type_hint)
                        }
                        for f in signature.output_fields
                    ],
                    "aliases": [alias for alias, target in self.aliases.items() if target == name]
                }

                catalog.append(entry)

        return catalog

    def remove(self, name: str) -> None:
        """Remove a signature from the registry."""
        with self._lock:
            if name not in self.signatures:
                raise KeyError(f"Signature '{name}' not found")

            # Remove signature and metadata
            del self.signatures[name]
            del self.metadata[name]

            # Remove any aliases pointing to this signature
            aliases_to_remove = [alias for alias, target in self.aliases.items() if target == name]
            for alias in aliases_to_remove:
                del self.aliases[alias]

    def update_metadata(self, name: str, metadata: SignatureMetadata) -> None:
        """Update metadata for a signature."""
        with self._lock:
            if name not in self.signatures:
                raise KeyError(f"Signature '{name}' not found")

            self.metadata[name] = metadata


# Global registry instance
_global_registry: Optional[SignatureRegistry] = None
_registry_lock = threading.Lock()


def get_global_registry() -> SignatureRegistry:
    """Get the global signature registry (singleton)."""
    global _global_registry

    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = SignatureRegistry()

    return _global_registry
