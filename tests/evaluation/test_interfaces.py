"""Tests for provider-agnostic evaluation interfaces."""

from src.evaluation import EvalAdapter


class TestEvalAdapterProtocol:
    """Test EvalAdapter protocol behavior."""

    def test_structural_subtyping_runtime_check(self) -> None:
        """Verify compatible classes satisfy EvalAdapter without inheritance."""

        class MyAdapter:
            def run(self, eval_spec: str, model_ref: str) -> str:
                return "run-123"

        adapter = MyAdapter()
        assert isinstance(adapter, EvalAdapter)

    def test_incompatible_class_fails_runtime_check(self) -> None:
        """Verify classes missing run are not treated as EvalAdapter."""

        class NotAnAdapter:
            def execute(self, eval_spec: str, model_ref: str) -> str:
                return "run-123"

        adapter = NotAnAdapter()
        assert not isinstance(adapter, EvalAdapter)
