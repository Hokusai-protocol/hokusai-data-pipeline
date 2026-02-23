"""Tests for provider-agnostic evaluation interfaces."""

from src.evaluation import AbstractBenchmarkAdapter, BenchmarkSpec, EvalAdapter, MetricSpec
from src.evaluation.manifest import HokusaiEvaluationManifest


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


class TestAbstractBenchmarkAdapterProtocol:
    """Test benchmark adapter protocol behavior."""

    def test_structural_subtyping_runtime_check(self) -> None:
        """Verify compatible classes satisfy AbstractBenchmarkAdapter."""

        class MyBenchmarkAdapter:
            def run(
                self,
                spec: BenchmarkSpec,
                model_fn,
                seed: int,
            ) -> HokusaiEvaluationManifest:
                _ = model_fn
                _ = seed
                return HokusaiEvaluationManifest(
                    model_id="m",
                    eval_id=spec.benchmark_id,
                    dataset={"id": "d", "hash": "sha256:x", "num_samples": 1},
                    primary_metric={"name": "accuracy", "value": 1.0, "higher_is_better": True},
                    metrics=[{"name": "accuracy", "value": 1.0, "higher_is_better": True}],
                    mlflow_run_id="run-1",
                )

        adapter = MyBenchmarkAdapter()
        assert isinstance(adapter, AbstractBenchmarkAdapter)

    def test_incompatible_class_fails_runtime_check(self) -> None:
        """Verify classes missing run are not treated as benchmark adapters."""

        class NotABenchmarkAdapter:
            def execute(self, spec: BenchmarkSpec, model_fn, seed: int) -> dict:
                _ = spec
                _ = model_fn
                _ = seed
                return {}

        adapter = NotABenchmarkAdapter()
        assert not isinstance(adapter, AbstractBenchmarkAdapter)


def test_benchmark_spec_from_dict_defaults() -> None:
    spec = BenchmarkSpec.from_dict(
        {
            "benchmark_id": "bench-1",
            "dataset_ref": "owner/dataset",
            "dataset_version_hash": "abc123",
            "eval_split_path": "eval.csv",
            "target_column": "label",
            "metric": {"name": "accuracy", "version": "1"},
        }
    )
    assert spec.metric == MetricSpec(name="accuracy", version="1", higher_is_better=True)
    assert spec.input_columns == []
