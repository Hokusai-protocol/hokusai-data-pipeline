"""Metadata structures for DSPy signatures."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SignatureMetadata:
    """Metadata for a DSPy signature."""

    name: str
    description: str
    category: str
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: Optional[str] = None
    examples: list[dict[str, Any]] = field(default_factory=list)
    deprecated: bool = False
    replacement: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "version": self.version,
            "author": self.author,
            "examples": self.examples,
            "deprecated": self.deprecated,
            "replacement": self.replacement,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignatureMetadata":
        """Create metadata from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            category=data["category"],
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
            author=data.get("author"),
            examples=data.get("examples", []),
            deprecated=data.get("deprecated", False),
            replacement=data.get("replacement"),
        )
