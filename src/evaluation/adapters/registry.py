"""Registry for benchmark adapters used by the evaluation worker."""

from __future__ import annotations

from src.evaluation.adapters.base import AbstractBenchmarkAdapter
from src.evaluation.adapters.kaggle import KaggleBenchmarkAdapter

_benchmark_adapters: dict[str, AbstractBenchmarkAdapter] = {}


def register_benchmark_adapter(name: str, adapter: AbstractBenchmarkAdapter) -> None:
    """Register a benchmark adapter by name."""
    if name in _benchmark_adapters:
        raise ValueError(f"Benchmark adapter '{name}' is already registered")
    _benchmark_adapters[name] = adapter


def get_benchmark_adapter(name: str) -> AbstractBenchmarkAdapter:
    """Retrieve a benchmark adapter by name."""
    try:
        return _benchmark_adapters[name]
    except KeyError as exc:
        raise KeyError(f"Benchmark adapter '{name}' is not registered") from exc


def list_benchmark_adapters() -> list[str]:
    """Return the list of registered benchmark adapter names."""
    return list(_benchmark_adapters.keys())


def clear_benchmark_adapters() -> None:
    """Clear registry entries (for test isolation)."""
    _benchmark_adapters.clear()


def register_default_benchmark_adapters() -> None:
    """Register built-in benchmark adapters."""
    if "kaggle" not in _benchmark_adapters:
        _benchmark_adapters["kaggle"] = KaggleBenchmarkAdapter()


register_default_benchmark_adapters()
