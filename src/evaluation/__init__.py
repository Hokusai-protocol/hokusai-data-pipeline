"""Evaluation interfaces and adapter registry."""

from src.evaluation.interfaces import EvalAdapter
from src.evaluation.provider_registry import (
    clear_adapters,
    get_adapter,
    list_adapters,
    register_adapter,
)

__all__ = [
    "EvalAdapter",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "clear_adapters",
]
