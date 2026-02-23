"""Registry for provider-agnostic evaluation adapters."""

from src.evaluation.interfaces import EvalAdapter

_adapters: dict[str, EvalAdapter] = {}


def register_adapter(name: str, adapter: EvalAdapter) -> None:
    """Register an evaluation adapter by name."""
    if name in _adapters:
        raise ValueError(f"Adapter '{name}' is already registered")

    _adapters[name] = adapter


def get_adapter(name: str) -> EvalAdapter:
    """Get a registered evaluation adapter by name."""
    try:
        return _adapters[name]
    except KeyError as exc:
        raise KeyError(f"Adapter '{name}' is not registered") from exc


def list_adapters() -> list[str]:
    """List registered adapter names."""
    return list(_adapters.keys())


def clear_adapters() -> None:
    """Clear all registered adapters.

    This function is intended for test isolation.
    """
    _adapters.clear()
