"""Tests for evaluation provider registry."""

import pytest

from src.evaluation import clear_adapters, get_adapter, list_adapters, register_adapter


class DummyAdapter:
    """Simple adapter used in tests."""

    def run(self, eval_spec: str, model_ref: str) -> str:
        return "dummy-run-id"


class TestProviderRegistry:
    """Test provider registry CRUD behavior."""

    def setup_method(self) -> None:
        """Ensure registry isolation between tests."""
        clear_adapters()

    def teardown_method(self) -> None:
        """Ensure registry isolation after each test."""
        clear_adapters()

    def test_register_and_get_adapter(self) -> None:
        """Registering an adapter should make it retrievable by name."""
        adapter = DummyAdapter()

        register_adapter("openai", adapter)

        assert get_adapter("openai") is adapter

    def test_list_adapters(self) -> None:
        """Listing adapters should return all registered provider names."""
        register_adapter("openai", DummyAdapter())
        register_adapter("native", DummyAdapter())

        assert set(list_adapters()) == {"openai", "native"}

    def test_register_adapter_duplicate_name_raises_value_error(self) -> None:
        """Duplicate adapter names should be rejected."""
        register_adapter("openai", DummyAdapter())

        with pytest.raises(ValueError, match="already registered"):
            register_adapter("openai", DummyAdapter())

    def test_get_adapter_missing_name_raises_key_error(self) -> None:
        """Unknown adapter names should raise KeyError with clear message."""
        with pytest.raises(KeyError, match="not registered"):
            get_adapter("missing")

    def test_clear_adapters_removes_all_entries(self) -> None:
        """Clearing should remove all registered adapters."""
        register_adapter("openai", DummyAdapter())

        clear_adapters()

        assert list_adapters() == []
