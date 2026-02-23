"""OpenAI Evals adapter package."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .openai_adapter import OpenAIEvalsAdapter

__all__ = ["OpenAIEvalsAdapter"]


def __getattr__(name: str) -> Any:
    """Lazily import public adapter classes."""
    if name == "OpenAIEvalsAdapter":
        return import_module("src.evals.openai_adapter").OpenAIEvalsAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
