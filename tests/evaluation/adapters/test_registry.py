"""Tests for benchmark adapter registry."""

from src.evaluation.adapters.registry import (
    clear_benchmark_adapters,
    get_benchmark_adapter,
    list_benchmark_adapters,
    register_benchmark_adapter,
    register_default_benchmark_adapters,
)


class DummyAdapter:
    def run(self, spec, model_fn, seed):  # noqa: ANN001
        _ = spec
        _ = model_fn
        _ = seed
        raise NotImplementedError


def test_default_registry_contains_kaggle() -> None:
    clear_benchmark_adapters()
    register_default_benchmark_adapters()
    assert "kaggle" in list_benchmark_adapters()


def test_register_get_list_and_clear() -> None:
    clear_benchmark_adapters()
    register_default_benchmark_adapters()

    adapter = DummyAdapter()
    register_benchmark_adapter("dummy", adapter)

    assert get_benchmark_adapter("dummy") is adapter
    assert set(list_benchmark_adapters()) == {"kaggle", "dummy"}

    clear_benchmark_adapters()
    assert list_benchmark_adapters() == []
