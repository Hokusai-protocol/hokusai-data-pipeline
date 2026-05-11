"""Unit tests for custom_eval dispatch logic."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.evaluation.custom_eval import (
    CustomEvalError,
    CustomEvalRuntimeError,
    DatasetAccessNotImplementedError,
    DatasetHashUnresolvableError,
    DatasetLoadError,
    MetricNameCollisionError,
    ScorerLoadError,
    _all_scorer_refs,
    _load_sales_outcome_rows,
    compute_dataset_hash,
    is_genai_spec,
    run_custom_eval,
)
from src.evaluation.schema import MetricFamily
from src.evaluation.scorers import (
    Aggregation,
    register_scorer,
)
from src.evaluation.spec_translation import (
    RuntimeAdapterSpec,
    RuntimeGuardrailSpec,
    RuntimeMetricSpec,
)
from src.evaluation.tags import (
    DATASET_HASH_TAG,
    FAILURE_REASON_TAG,
    MEASUREMENT_POLICY_TAG,
    MLFLOW_NAME_TAG,
    PRIMARY_METRIC_TAG,
    SCORER_REF_TAG,
    STATUS_TAG,
)
from src.utils.dataset_hash import (
    format_sha256_dataset_version,
    parse_sha256_dataset_version,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_spec(
    scorer_ref: str | None = None,
    metric_family: MetricFamily = MetricFamily.OUTCOME,
    guardrail_scorer_refs: list[str | None] | None = None,
) -> RuntimeAdapterSpec:
    """Build a minimal RuntimeAdapterSpec for testing."""
    guardrails: tuple[RuntimeGuardrailSpec, ...] = ()
    if guardrail_scorer_refs:
        guardrails = tuple(
            RuntimeGuardrailSpec(
                name=f"guardrail_{i}",
                direction="lower_is_better",
                threshold=0.1,
                scorer_ref=ref,
            )
            for i, ref in enumerate(guardrail_scorer_refs)
        )
    return RuntimeAdapterSpec(
        spec_id="spec-001",
        model_id="model-a",
        dataset_id="dataset-x",
        dataset_version="sha256:" + "a" * 64,
        eval_split="test",
        input_schema={},
        output_schema={},
        primary_metric=RuntimeMetricSpec(
            name="accuracy",
            direction="higher_is_better",
            scorer_ref=scorer_ref,
        ),
        guardrails=guardrails,
    )


def _make_benchmark_spec(
    *,
    scorer_ref: str | None = "pass_rate",
    is_active: bool = True,
    measurement_policy: dict | None = None,
    guardrails: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "spec_id": "spec-001",
        "model_id": "model-a",
        "is_active": is_active,
        "dataset_reference": "s3://bucket/data.json",
        "dataset_version": "sha256:" + "a" * 64,
        "dataset_id": "dataset-x",
        "eval_split": "test",
        "metric_name": "accuracy",
        "metric_direction": "higher_is_better",
        "eval_spec": {
            "primary_metric": {
                "name": "accuracy",
                "direction": "higher_is_better",
                "scorer_ref": scorer_ref,
            },
            "secondary_metrics": [],
            "guardrails": guardrails or [],
            "measurement_policy": measurement_policy,
        },
    }


def _sales_rows() -> list[dict[str, Any]]:
    return [
        {
            "row_id": "row-1",
            "unit_id": "unit-1",
            "schema_version": "sales_outcome_row/v1",
            "delivered_count": 1,
            "revenue_amount_cents": 500,
            "unsubscribe": False,
            "spam_complaint": False,
        }
    ]


class _FakeRun:
    def __init__(self, run_id: str = "run-custom-001") -> None:
        self.info = SimpleNamespace(run_id=run_id)

    def __enter__(self) -> _FakeRun:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _FakeMlflow:
    def __init__(self, metrics: dict | None = None, raise_on_evaluate: bool = False) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self._metrics = metrics or {"accuracy": 0.88}
        self._raise = raise_on_evaluate
        self.tags: dict[str, str] = {}
        self.metrics_logged: dict[str, float] = {}
        self.evaluate_kwargs: dict | None = None
        self.logged_artifacts: list[tuple[str, str]] = []

    def start_run(self, run_name: str | None = None, run_id: str | None = None) -> _FakeRun:
        return _FakeRun()

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def log_metric(self, key: str, value: float) -> None:
        self.metrics_logged[key] = value

    def log_param(self, key: str, value: Any) -> None:
        pass

    def log_artifact(self, local_path: str, artifact_path: str = "") -> None:
        self.logged_artifacts.append((local_path, artifact_path))

    def evaluate(self, **kwargs: Any) -> Any:
        if self._raise:
            raise RuntimeError("mlflow evaluate boom")
        self.evaluate_kwargs = kwargs
        return SimpleNamespace(metrics=self._metrics)


@pytest.fixture(autouse=True)
def _isolated_scorer_registry():
    """Snapshot built-in registrations, restore after test."""
    from src.evaluation.scorers import registry as _reg

    snapshot = dict(_reg._REGISTRY)
    yield
    _reg._REGISTRY.clear()
    _reg._REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# is_genai_spec
# ---------------------------------------------------------------------------


def test_is_genai_spec_with_quality_scorer() -> None:
    def _stub_scorer(values: list[float]) -> float:
        return 0.0

    register_scorer(
        "quality_judge",
        callable_=_stub_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("quality_judge",),
        metric_family=MetricFamily.QUALITY,
        aggregation=Aggregation.MEAN,
    )
    spec = _make_spec(scorer_ref="quality_judge")
    assert is_genai_spec(spec) is True


def test_is_genai_spec_deterministic_only() -> None:
    spec = _make_spec(scorer_ref="pass_rate")
    assert is_genai_spec(spec) is False


def test_is_genai_spec_genai_prefixed_ref() -> None:
    spec = _make_spec(scorer_ref="genai:correctness")
    assert is_genai_spec(spec) is True


def test_is_genai_spec_judge_prefixed_ref() -> None:
    spec = _make_spec(scorer_ref="judge:faithfulness")
    assert is_genai_spec(spec) is True


def test_is_genai_spec_no_scorer_ref() -> None:
    spec = _make_spec(scorer_ref=None)
    assert is_genai_spec(spec) is False


# ---------------------------------------------------------------------------
# compute_dataset_hash
# ---------------------------------------------------------------------------


def test_run_custom_eval_dataset_hash_passthrough() -> None:
    valid_hash = "sha256:" + "b" * 64
    result = compute_dataset_hash(spec_dataset_version=valid_hash, dataset_path=None)
    assert result == valid_hash


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("sha256:" + "a" * 64, "sha256:" + "a" * 64),
        ("sha256:" + "0" * 64, "sha256:" + "0" * 64),
        ("sha256:" + "A" * 64, None),
        ("sha256:" + "a" * 63, None),
        ("sha256:" + "a" * 65, None),
        ("a" * 64, None),
        (" latest ", None),
        (None, None),
    ],
)
def test_parse_sha256_dataset_version(value: object, expected: str | None) -> None:
    assert parse_sha256_dataset_version(value) == expected


def test_format_sha256_dataset_version_rejects_noncanonical_hex() -> None:
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        format_sha256_dataset_version("A" * 64)


def test_run_custom_eval_dataset_hash_computed_from_path(tmp_path) -> None:
    rows = [{"input": "a", "output": "1"}, {"input": "b", "output": "2"}]
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    result = compute_dataset_hash(spec_dataset_version=None, dataset_path=str(dataset_file))
    assert result.startswith("sha256:")
    assert re.match(r"^sha256:[0-9a-f]{64}$", result)

    # Verify determinism: shuffled rows → same hash
    shuffled = [rows[1], rows[0]]
    dataset_file2 = tmp_path / "data_shuffled.json"
    dataset_file2.write_text(json.dumps(shuffled), encoding="utf-8")
    result2 = compute_dataset_hash(spec_dataset_version=None, dataset_path=str(dataset_file2))
    assert result == result2


def test_dataset_hash_stable_across_row_order(tmp_path) -> None:
    rows = [{"x": i} for i in range(5)]
    shuffled = list(reversed(rows))

    f1 = tmp_path / "ordered.json"
    f2 = tmp_path / "shuffled.json"
    f1.write_text(json.dumps(rows), encoding="utf-8")
    f2.write_text(json.dumps(shuffled), encoding="utf-8")

    h1 = compute_dataset_hash(spec_dataset_version=None, dataset_path=str(f1))
    h2 = compute_dataset_hash(spec_dataset_version=None, dataset_path=str(f2))
    assert h1 == h2


def test_dataset_hash_raises_when_unresolvable() -> None:
    with pytest.raises(DatasetHashUnresolvableError):
        compute_dataset_hash(spec_dataset_version=None, dataset_path=None)


def test_dataset_hash_raises_when_path_not_sha256_and_remote() -> None:
    with pytest.raises(DatasetHashUnresolvableError):
        compute_dataset_hash(spec_dataset_version="v1.2.3", dataset_path=None)


# ---------------------------------------------------------------------------
# run_custom_eval — dispatch routing
# ---------------------------------------------------------------------------


def test_run_custom_eval_dispatches_to_mlflow_evaluate_without_scorer_refs(tmp_path) -> None:
    """Non-GenAI specs without scorer refs keep the mlflow.evaluate fallback."""
    rows = [{"input": "x"}]
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    spec = _make_benchmark_spec(scorer_ref=None)
    spec["dataset_reference"] = str(dataset_file)
    spec["dataset_version"] = None

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.9})

    with patch("src.evaluation.custom_eval._dispatch_genai") as mock_genai:
        result = run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    mock_genai.assert_not_called()
    assert fake_mlflow.evaluate_kwargs is not None
    assert fake_mlflow.evaluate_kwargs["model"] == "models:/model-a"
    assert result["status"] == "success"


def test_run_custom_eval_dispatches_remote_s3_dataset_with_canonical_hash() -> None:
    dataset_version = "sha256:" + "c" * 64
    spec = _make_benchmark_spec(scorer_ref="pass_rate")
    spec["dataset_reference"] = "s3://bucket/data.json"
    spec["dataset_version"] = dataset_version

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.9})

    result = run_custom_eval(
        model_id="model-a",
        benchmark_spec=spec,
        benchmark_spec_id="spec-001",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    assert result["status"] == "success"
    assert fake_mlflow.evaluate_kwargs is not None
    assert fake_mlflow.evaluate_kwargs["data"] == "s3://bucket/data.json"
    assert fake_mlflow.tags[DATASET_HASH_TAG] == dataset_version


def test_run_custom_eval_dispatches_to_mlflow_genai_evaluate(tmp_path) -> None:
    """GenAI spec → mlflow.genai.evaluate called, mlflow.evaluate NOT called."""

    def _quality_scorer(values: list[float]) -> float:
        return 0.0

    register_scorer(
        "quality_judge",
        callable_=_quality_scorer,
        version="1.0.0",
        input_schema={"type": "array"},
        output_metric_keys=("quality_judge",),
        metric_family=MetricFamily.QUALITY,
        aggregation=Aggregation.MEAN,
    )

    rows = [{"input": "x"}]
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    spec = _make_benchmark_spec(scorer_ref="quality_judge")
    spec["dataset_reference"] = str(dataset_file)
    spec["dataset_version"] = None

    fake_mlflow = _FakeMlflow()
    mock_result = SimpleNamespace(metrics={"accuracy": 0.7})

    with patch("src.evaluation.custom_eval._dispatch_deterministic") as mock_det:
        with patch("src.evaluation.custom_eval._dispatch_genai", return_value=mock_result):
            result = run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=None,
                seed=None,
                temperature=None,
            )

    mock_det.assert_not_called()
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# run_custom_eval — tag emission
# ---------------------------------------------------------------------------


def test_run_custom_eval_emits_all_canonical_tags(tmp_path) -> None:
    rows = [{"input": "x"}]
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    spec = _make_benchmark_spec(scorer_ref=None)
    spec["dataset_reference"] = str(dataset_file)
    spec["dataset_version"] = None

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.9})

    run_custom_eval(
        model_id="model-a",
        benchmark_spec=spec,
        benchmark_spec_id="spec-001",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    tags = fake_mlflow.tags
    assert PRIMARY_METRIC_TAG in tags
    assert tags[PRIMARY_METRIC_TAG] == "accuracy"
    assert MLFLOW_NAME_TAG in tags
    assert DATASET_HASH_TAG in tags
    assert re.match(r"^sha256:[0-9a-f]{64}$", tags[DATASET_HASH_TAG])
    assert SCORER_REF_TAG in tags
    assert MEASUREMENT_POLICY_TAG in tags
    assert STATUS_TAG in tags
    assert tags[STATUS_TAG] == "succeeded"


# ---------------------------------------------------------------------------
# run_custom_eval — error paths
# ---------------------------------------------------------------------------


def test_run_custom_eval_inactive_spec_raises() -> None:
    spec = _make_benchmark_spec(is_active=False)
    fake_mlflow = _FakeMlflow()

    with pytest.raises(CustomEvalError, match="spec_not_found_or_inactive"):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    # No run should have been started
    assert not fake_mlflow.tags


def test_run_custom_eval_unknown_scorer_raises() -> None:
    spec = _make_benchmark_spec(scorer_ref="nonexistent_scorer_xyz")

    fake_mlflow = _FakeMlflow()

    with pytest.raises(ScorerLoadError, match="scorer_load_failed"):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    # Pre-run abort: no tags written
    assert not fake_mlflow.tags


def test_run_custom_eval_remote_dataset_requires_canonical_hash() -> None:
    spec = _make_benchmark_spec(scorer_ref="pass_rate")
    spec["dataset_reference"] = "s3://bucket/data.json"
    spec["dataset_version"] = "latest"

    fake_mlflow = _FakeMlflow()

    with pytest.raises(
        DatasetHashUnresolvableError,
        match=r"Remote dataset_reference 's3://bucket/data.json' requires dataset_version",
    ):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    assert not fake_mlflow.tags


def test_all_scorer_refs_includes_guardrail_refs() -> None:
    """_all_scorer_refs must include scorer refs from guardrails."""
    spec = _make_spec(
        scorer_ref="pass_rate",
        guardrail_scorer_refs=["sales:unsubscribe_rate", None, "sales:spam_complaint_rate"],
    )
    refs = _all_scorer_refs(spec)
    assert "pass_rate" in refs
    assert "sales:unsubscribe_rate" in refs
    assert "sales:spam_complaint_rate" in refs
    assert None not in refs
    assert len(refs) == 3


def test_all_scorer_refs_guardrail_only() -> None:
    """_all_scorer_refs collects guardrail refs when primary has no scorer_ref."""
    spec = _make_spec(
        scorer_ref=None,
        guardrail_scorer_refs=["sales:spam_complaint_rate"],
    )
    refs = _all_scorer_refs(spec)
    assert refs == ["sales:spam_complaint_rate"]


def test_run_custom_eval_guardrail_scorer_ref_validated(tmp_path) -> None:
    """An unknown guardrail scorer_ref raises ScorerLoadError before starting an MLflow run."""
    spec = _make_benchmark_spec(
        scorer_ref=None,
        guardrails=[
            {
                "name": "my_guardrail",
                "direction": "lower_is_better",
                "threshold": 0.1,
                "scorer_ref": "nonexistent_guardrail_scorer_xyz",
            }
        ],
    )
    fake_mlflow = _FakeMlflow()
    with pytest.raises(ScorerLoadError, match="scorer_load_failed"):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )
    assert not fake_mlflow.tags


def test_run_custom_eval_guardrail_scorer_ref_in_tag(tmp_path) -> None:
    """Guardrail scorer_refs are included in the hokusai.scorer_ref MLflow tag."""
    rows = _sales_rows()
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    spec = _make_benchmark_spec(
        scorer_ref=None,
        guardrails=[
            {
                "name": "sales:unsubscribe_rate",
                "direction": "lower_is_better",
                "threshold": 0.03,
                "scorer_ref": "sales:unsubscribe_rate",
            }
        ],
    )
    spec["dataset_reference"] = str(dataset_file)
    spec["dataset_version"] = None

    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.9})

    run_custom_eval(
        model_id="model-a",
        benchmark_spec=spec,
        benchmark_spec_id="spec-001",
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    scorer_ref_tag = fake_mlflow.tags.get(SCORER_REF_TAG, "")
    assert "sales:unsubscribe_rate" in scorer_ref_tag


def test_run_custom_eval_mlflow_failure_tags(tmp_path) -> None:
    rows = [{"input": "x"}]
    dataset_file = tmp_path / "data.json"
    dataset_file.write_text(json.dumps(rows), encoding="utf-8")

    spec = _make_benchmark_spec(scorer_ref=None)
    spec["dataset_reference"] = str(dataset_file)
    spec["dataset_version"] = None

    fake_mlflow = _FakeMlflow(raise_on_evaluate=True)

    with pytest.raises(CustomEvalRuntimeError, match="mlflow_evaluate_error"):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    assert fake_mlflow.tags.get(STATUS_TAG) == "failed"
    assert fake_mlflow.tags.get(FAILURE_REASON_TAG) == "mlflow_evaluate_error"


def test_run_custom_eval_remote_deterministic_dataset_succeeds_for_s3_sales_rows() -> None:
    spec = _make_benchmark_spec(scorer_ref="sales:unsubscribe_rate")
    spec["dataset_reference"] = "s3://bucket/sales.json"
    spec["dataset_version"] = "sha256:" + "b" * 64

    fake_mlflow = _FakeMlflow()

    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps(_sales_rows()).encode("utf-8"),
    ):
        result = run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    assert result["status"] == "success"
    assert fake_mlflow.tags.get(STATUS_TAG) == "succeeded"
    assert fake_mlflow.tags.get(FAILURE_REASON_TAG) is None
    assert result["metrics"]["accuracy"] == pytest.approx(0.0)


def test_run_custom_eval_remote_sales_dataset_does_not_raise_access_not_implemented() -> None:
    spec = _make_benchmark_spec(scorer_ref="sales:unsubscribe_rate")
    spec["dataset_reference"] = "s3://bucket/sales.json"
    spec["dataset_version"] = "sha256:" + "d" * 64

    fake_mlflow = _FakeMlflow()

    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps(_sales_rows()).encode("utf-8"),
    ):
        try:
            run_custom_eval(
                model_id="model-a",
                benchmark_spec=spec,
                benchmark_spec_id="spec-001",
                mlflow_module=fake_mlflow,
                mlflow_client=None,
                cli_max_cost=None,
                seed=None,
                temperature=None,
            )
        except DatasetAccessNotImplementedError as exc:
            pytest.fail(f"unexpected DatasetAccessNotImplementedError: {exc}")


def test_load_sales_outcome_rows_from_remote_json_object() -> None:
    row = _sales_rows()[0]
    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps(row).encode("utf-8"),
    ):
        rows = _load_sales_outcome_rows("s3://bucket/sales.json")
    assert rows == [row]


def test_load_sales_outcome_rows_from_remote_json_array() -> None:
    rows = _sales_rows() * 2
    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps(rows).encode("utf-8"),
    ):
        loaded = _load_sales_outcome_rows("s3://bucket/sales.json")
    assert loaded == rows


def test_load_sales_outcome_rows_from_remote_jsonl() -> None:
    rows = _sales_rows() * 2
    payload = ("\n\n" + "\n".join(json.dumps(row) for row in rows) + "\n").encode("utf-8")
    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=payload,
    ):
        loaded = _load_sales_outcome_rows("s3://bucket/sales.jsonl")
    assert loaded == rows


def test_load_sales_outcome_rows_rejects_unsupported_suffix() -> None:
    with patch("src.evaluation.custom_eval._load_s3_object_bytes", return_value=b"ignored"):
        with pytest.raises(
            DatasetLoadError,
            match="unsupported deterministic sales dataset format",
        ):
            _load_sales_outcome_rows("s3://bucket/sales.csv")


def test_load_sales_outcome_rows_rejects_empty_remote_dataset() -> None:
    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps([]).encode("utf-8"),
    ):
        with pytest.raises(DatasetLoadError, match="must contain at least one row"):
            _load_sales_outcome_rows("s3://bucket/sales.json")


def test_load_sales_outcome_rows_rejects_malformed_remote_json() -> None:
    with patch("src.evaluation.custom_eval._load_s3_object_bytes", return_value=b"{not-json"):
        with pytest.raises(DatasetLoadError, match="invalid JSON dataset"):
            _load_sales_outcome_rows("s3://bucket/sales.json")


def test_load_sales_outcome_rows_rejects_invalid_row_schema() -> None:
    invalid_rows = [{"row_id": "row-1", "schema_version": "sales_outcome_row/v2"}]
    with patch(
        "src.evaluation.custom_eval._load_s3_object_bytes",
        return_value=json.dumps(invalid_rows).encode("utf-8"),
    ):
        with pytest.raises(DatasetLoadError, match="unsupported schema_version"):
            _load_sales_outcome_rows("s3://bucket/sales.json")


def test_load_sales_outcome_rows_rejects_unsupported_remote_scheme() -> None:
    with pytest.raises(DatasetAccessNotImplementedError, match="does not support remote"):
        _load_sales_outcome_rows("gs://bucket/sales.json")


def test_run_custom_eval_duplicate_canonical_metric_names_raise(tmp_path) -> None:
    dataset_file = tmp_path / "sales.json"
    dataset_file.write_text(
        json.dumps(
            [
                {
                    "row_id": "row-1",
                    "unit_id": "unit-1",
                    "schema_version": "sales_outcome_row/v1",
                    "delivered_count": 1,
                    "unsubscribe": False,
                    "spam_complaint": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    spec = {
        "spec_id": "spec-001",
        "model_id": "model-a",
        "is_active": True,
        "dataset_reference": str(dataset_file),
        "dataset_version": None,
        "dataset_id": "dataset-x",
        "eval_split": "test",
        "metric_name": "sales:unsubscribe_rate",
        "metric_direction": "higher_is_better",
        "eval_spec": {
            "primary_metric": {
                "name": "sales:unsubscribe_rate",
                "direction": "higher_is_better",
                "scorer_ref": "sales:unsubscribe_rate",
            },
            "secondary_metrics": [],
            "guardrails": [
                {
                    "name": "sales_unsubscribe_rate",
                    "direction": "lower_is_better",
                    "threshold": 0.1,
                    "scorer_ref": "sales:spam_complaint_rate",
                }
            ],
        },
    }

    fake_mlflow = _FakeMlflow()

    with pytest.raises(MetricNameCollisionError, match="metric_name_collision"):
        run_custom_eval(
            model_id="model-a",
            benchmark_spec=spec,
            benchmark_spec_id="spec-001",
            mlflow_module=fake_mlflow,
            mlflow_client=None,
            cli_max_cost=None,
            seed=None,
            temperature=None,
        )

    assert fake_mlflow.tags.get(STATUS_TAG) == "failed"
    assert fake_mlflow.tags.get(FAILURE_REASON_TAG) == "mlflow_evaluate_error"
