from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

# Auth-hook note: fake MLflow clients here intentionally avoid live
# Authorization headers and MLFLOW_TRACKING_TOKEN handling.
from src.evaluation.deltaone_evaluator import (
    DeltaOneEvaluator,
    _calculate_percentage_point_difference,
    _hem_to_array,
    _reconstruct_array,
)
from src.evaluation.hem import HEM, PerRowArtifact
from src.evaluation.tags import PER_ROW_ARTIFACT_URI_TAG


def _make_run(
    run_id: str,
    *,
    metric_name: str = "accuracy",
    metric_value: float = 0.87,
    n_examples: str = "1000",
    dataset_hash: str = "sha256:" + "a" * 64,
    model_id: str = "model-a",
    start_time: int = 1_700_000_000_000,
    experiment_id: str = "1",
    contributor_tags: dict[str, str] | None = None,
) -> SimpleNamespace:
    tags = {
        "hokusai.primary_metric": metric_name,
        "hokusai.dataset.num_samples": n_examples,
        "hokusai.dataset.hash": dataset_hash,
        "hokusai.model_id": model_id,
    }
    if contributor_tags:
        tags.update(contributor_tags)

    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=start_time, experiment_id=experiment_id),
        data=SimpleNamespace(
            metrics={metric_name: metric_value},
            tags=tags,
            params={},
        ),
    )


class _FakeMlflowClient:
    def __init__(
        self,
        runs: dict[str, SimpleNamespace],
        search_runs_result: list[SimpleNamespace] | None = None,
    ):
        self._runs = runs
        self._search_runs_result = search_runs_result or []
        self.tags_set: dict[str, dict[str, str]] = {}
        self.get_run_calls: list[str] = []

    def get_run(self, run_id: str) -> SimpleNamespace:
        self.get_run_calls.append(run_id)
        return self._runs[run_id]

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str,
        max_results: int,
        order_by: list[str],
    ) -> list[SimpleNamespace]:
        return self._search_runs_result

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags_set.setdefault(run_id, {})[key] = value


def test_extract_metrics_from_run_uses_single_mlflow_call() -> None:
    client = _FakeMlflowClient({"run-1": _make_run("run-1")})
    evaluator = DeltaOneEvaluator(mlflow_client=client)

    hem = evaluator._extract_metrics_from_run("run-1")

    assert hem.metric_name == "accuracy"
    assert hem.metric_value == pytest.approx(0.87)
    assert hem.sample_size == 1000
    assert hem.experiment_id == "1"
    assert client.get_run_calls == ["run-1"]


def test_percentage_point_calculation_uses_ratio_to_pp_conversion() -> None:
    assert _calculate_percentage_point_difference(0.85, 0.87) == pytest.approx(2.0)
    assert _calculate_percentage_point_difference(0.50, 0.51) == pytest.approx(1.0)


def test_confidence_interval_significance_known_case() -> None:
    evaluator = DeltaOneEvaluator(mlflow_client=_FakeMlflowClient({}))

    significant, ci_low, ci_high = evaluator._is_statistically_significant(
        baseline_metric=0.85,
        current_metric=0.87,
        baseline_n=10_000,
        current_n=10_000,
    )

    assert significant is True
    assert ci_low > 0.0
    assert ci_high > ci_low


def test_evaluate_rejects_when_cooldown_active() -> None:
    now = datetime.now(timezone.utc)
    previous_eval_run = SimpleNamespace(
        info=SimpleNamespace(run_id="older-run"),
        data=SimpleNamespace(
            tags={"hokusai.deltaone.evaluated_at": (now - timedelta(hours=1)).isoformat()}
        ),
    )

    runs = {
        "candidate": _make_run("candidate", metric_value=0.90, n_examples="2000"),
        "baseline": _make_run("baseline", metric_value=0.86, n_examples="2000"),
    }
    client = _FakeMlflowClient(runs, search_runs_result=[previous_eval_run])
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=24, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason.startswith("cooldown_active")


def test_evaluate_rejects_when_sample_size_too_small() -> None:
    runs = {
        "candidate": _make_run("candidate", metric_value=0.90, n_examples="400"),
        "baseline": _make_run("baseline", metric_value=0.86, n_examples="1200"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "insufficient_samples"


def test_evaluate_rejects_when_dataset_hash_mismatch() -> None:
    runs = {
        "candidate": _make_run(
            "candidate",
            metric_value=0.90,
            n_examples="2000",
            dataset_hash="sha256:" + "a" * 64,
        ),
        "baseline": _make_run(
            "baseline",
            metric_value=0.86,
            n_examples="2000",
            dataset_hash="sha256:" + "b" * 64,
        ),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(mlflow_client=client, cooldown_hours=0, min_examples=800)

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "dataset_hash_mismatch"


def test_evaluate_end_to_end_significant_improvement() -> None:
    runs = {
        "candidate": _make_run(
            "candidate",
            metric_value=0.87,
            n_examples="10000",
            contributor_tags={
                "contributor_id": "prompt-author-123",
                "hokusai.contributor.prompt_author_id": "prompt-author-123",
                "hokusai.contributor.training_data_uploader_id": "uploader-456",
                "hokusai.contributor.human_labeler_id": "labeler-789",
            },
        ),
        "baseline": _make_run("baseline", metric_value=0.85, n_examples="10000"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is True
    assert decision.reason == "accepted"
    assert decision.delta_percentage_points == pytest.approx(2.0)
    assert "hokusai.deltaone.accepted" in client.tags_set["candidate"]
    assert client.tags_set["candidate"]["hokusai.deltaone.contributor_id"] == "prompt-author-123"
    assert (
        client.tags_set["candidate"]["hokusai.deltaone.hokusai.contributor.prompt_author_id"]
        == "prompt-author-123"
    )
    assert (
        client.tags_set["candidate"][
            "hokusai.deltaone.hokusai.contributor.training_data_uploader_id"
        ]
        == "uploader-456"
    )
    assert (
        client.tags_set["candidate"]["hokusai.deltaone.hokusai.contributor.human_labeler_id"]
        == "labeler-789"
    )


def test_evaluate_end_to_end_not_significant() -> None:
    runs = {
        "candidate": _make_run("candidate", metric_value=0.87, n_examples="1000"),
        "baseline": _make_run("baseline", metric_value=0.85, n_examples="1000"),
    }
    client = _FakeMlflowClient(runs)
    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
    )

    decision = evaluator.evaluate("candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "not_statistically_significant"


def test_evaluate_for_model_uses_active_benchmark_spec() -> None:
    runs = {
        "candidate": _make_run("candidate", metric_value=0.87, n_examples="10000"),
        "baseline": _make_run("baseline", metric_value=0.85, n_examples="10000"),
    }
    client = _FakeMlflowClient(runs)

    class _Resolver:
        def get_active_spec_for_model(self, _model_id: str) -> dict[str, object]:
            return {
                "spec_id": "spec-1",
                "dataset_version": "sha256:" + "a" * 64,
                "metric_name": "accuracy",
                "tiebreak_rules": {"min_examples": 1000},
                "input_schema": {},
            }

    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
        benchmark_spec_resolver=_Resolver(),
    )

    decision = evaluator.evaluate_for_model("model-a", "candidate", "baseline")

    assert decision.accepted is True
    assert decision.reason == "accepted"


def test_extract_metrics_three_tier_fallback_normalized_name() -> None:
    """Tier-2: canonical colon name resolves via underscore-normalized key."""
    run = SimpleNamespace(
        info=SimpleNamespace(run_id="run-ns", start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            metrics={"workflow_success_rate_under_budget": 0.85},
            tags={
                "hokusai.primary_metric": "workflow:success_rate_under_budget",
                "hokusai.dataset.num_samples": "500",
                "hokusai.dataset.hash": "sha256:" + "c" * 64,
                "hokusai.model_id": "model-c",
            },
            params={},
        ),
    )
    client = _FakeMlflowClient({"run-ns": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client)

    hem = evaluator._extract_metrics_from_run(
        "run-ns", expected_metric_name="workflow:success_rate_under_budget"
    )

    assert hem.metric_value == pytest.approx(0.85)
    assert hem.metric_name == "workflow:success_rate_under_budget"


def test_extract_metrics_three_tier_fallback_literal() -> None:
    """Tier-3: when the metric key is already the literal canonical name."""
    run = SimpleNamespace(
        info=SimpleNamespace(run_id="run-lit", start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            metrics={"accuracy": 0.92},
            tags={
                "hokusai.primary_metric": "accuracy",
                "hokusai.dataset.num_samples": "500",
                "hokusai.dataset.hash": "sha256:" + "d" * 64,
                "hokusai.model_id": "model-d",
            },
            params={},
        ),
    )
    client = _FakeMlflowClient({"run-lit": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client)

    hem = evaluator._extract_metrics_from_run("run-lit", expected_metric_name="accuracy")

    assert hem.metric_value == pytest.approx(0.92)


def test_extract_metrics_raises_with_helpful_message_when_all_tiers_miss() -> None:
    """All three tiers miss → ValueError with tried keys listed."""
    run = SimpleNamespace(
        info=SimpleNamespace(run_id="run-miss", start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            metrics={"completely_different_metric": 0.5},
            tags={
                "hokusai.dataset.num_samples": "500",
                "hokusai.dataset.hash": "sha256:" + "e" * 64,
                "hokusai.model_id": "model-e",
            },
            params={},
        ),
    )
    client = _FakeMlflowClient({"run-miss": run})
    evaluator = DeltaOneEvaluator(mlflow_client=client)

    with pytest.raises(ValueError) as exc_info:
        evaluator._extract_metrics_from_run(
            "run-miss",
            expected_metric_name="workflow:my_metric",
            expected_mlflow_name="workflow_my_metric",
        )
    msg = str(exc_info.value)
    assert "workflow:my_metric" in msg
    assert "workflow_my_metric" in msg


def test_evaluate_for_model_resolves_namespaced_metric() -> None:
    """evaluate_for_model resolves metric when eval_spec carries mlflow_name."""
    namespaced_mlflow_key = "workflow_success_rate_under_budget"
    canonical_name = "workflow:success_rate_under_budget"
    dataset_hash = "sha256:" + "f" * 64

    run = SimpleNamespace(
        info=SimpleNamespace(run_id="cand", start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            metrics={namespaced_mlflow_key: 0.87},
            tags={
                "hokusai.primary_metric": canonical_name,
                "hokusai.dataset.num_samples": "10000",
                "hokusai.dataset.hash": dataset_hash,
                "hokusai.model_id": "model-f",
            },
            params={},
        ),
    )
    baseline_run = SimpleNamespace(
        info=SimpleNamespace(run_id="base", start_time=1_700_000_000_000, experiment_id="1"),
        data=SimpleNamespace(
            metrics={namespaced_mlflow_key: 0.85},
            tags={
                "hokusai.primary_metric": canonical_name,
                "hokusai.dataset.num_samples": "10000",
                "hokusai.dataset.hash": dataset_hash,
                "hokusai.model_id": "model-f",
            },
            params={},
        ),
    )
    client = _FakeMlflowClient({"cand": run, "base": baseline_run})

    class _Resolver:
        def get_active_spec_for_model(self, _model_id: str) -> dict[str, object]:
            return {
                "spec_id": "spec-ns",
                "dataset_version": dataset_hash,
                "metric_name": canonical_name,
                "tiebreak_rules": {"min_examples": 1000},
                "input_schema": {},
                "eval_spec": {
                    "primary_metric": {
                        "mlflow_name": namespaced_mlflow_key,
                    }
                },
            }

    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
        benchmark_spec_resolver=_Resolver(),
    )

    decision = evaluator.evaluate_for_model("model-f", "cand", "base")
    assert decision.accepted is True


def test_evaluate_for_model_rejects_dataset_not_in_spec() -> None:
    runs = {
        "candidate": _make_run(
            "candidate",
            metric_value=0.87,
            n_examples="1200",
            dataset_hash="sha256:" + "b" * 64,
        ),
        "baseline": _make_run(
            "baseline",
            metric_value=0.85,
            n_examples="1200",
            dataset_hash="sha256:" + "b" * 64,
        ),
    }
    client = _FakeMlflowClient(runs)

    class _Resolver:
        def get_active_spec_for_model(self, _model_id: str) -> dict[str, object]:
            return {
                "spec_id": "spec-1",
                "dataset_version": "sha256:" + "a" * 64,
                "metric_name": "accuracy",
                "tiebreak_rules": {"min_examples": 1000},
                "input_schema": {},
            }

    evaluator = DeltaOneEvaluator(
        mlflow_client=client,
        cooldown_hours=0,
        min_examples=800,
        delta_threshold_pp=1.0,
        benchmark_spec_resolver=_Resolver(),
    )

    decision = evaluator.evaluate_for_model("model-a", "candidate", "baseline")

    assert decision.accepted is False
    assert decision.reason == "dataset_hash_not_in_active_spec"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HASH = "sha256:" + "a" * 64


def _make_hem(
    *,
    metric_name: str = "accuracy",
    metric_value: float = 0.75,
    sample_size: int = 4,
    per_row_artifact: PerRowArtifact | None = None,
    unit_of_analysis: str | None = None,
) -> HEM:
    return HEM(
        metric_name=metric_name,
        metric_value=metric_value,
        sample_size=sample_size,
        dataset_hash=_HASH,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_mlflow_run_id="run-1",
        model_id="model-1",
        experiment_id="1",
        per_row_artifact=per_row_artifact,
        unit_of_analysis=unit_of_analysis,
    )


def _write_parquet(path: Path, df: pd.DataFrame) -> str:
    parquet_path = str(path / "per_row.parquet")
    df.to_parquet(parquet_path, index=False)
    return parquet_path


# ---------------------------------------------------------------------------
# _hem_to_array tests
# ---------------------------------------------------------------------------


class TestHemToArrayPerRowPath:
    def test_projects_mlflow_name_column_exactly(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"row_id": ["0", "1", "2", "3"], "accuracy": [1.0, 0.0, 1.0, 1.0]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(per_row_artifact=PerRowArtifact(uri=parquet_path))
        values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert np.allclose(values, [1.0, 0.0, 1.0, 1.0])
        assert unit_ids is None

    def test_drops_nans_and_preserves_unit_id_alignment(self, tmp_path: Path) -> None:
        df = pd.DataFrame(
            {
                "accuracy": [1.0, float("nan"), 0.0, 1.0],
                "unit_id": ["a", "b", "a", "b"],
            }
        )
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            per_row_artifact=PerRowArtifact(uri=parquet_path), unit_of_analysis="account_id"
        )
        values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 3
        assert np.allclose(values, [1.0, 0.0, 1.0])
        assert unit_ids is not None
        assert list(unit_ids) == ["a", "a", "b"]

    def test_runs_uri_downloads_via_mlflow_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        df = pd.DataFrame({"accuracy": [1.0, 0.0, 1.0]})
        parquet_path = _write_parquet(tmp_path, df)

        fake_mlflow = SimpleNamespace(
            artifacts=SimpleNamespace(download_artifacts=lambda artifact_uri: parquet_path)
        )
        monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow)

        hem = _make_hem(
            per_row_artifact=PerRowArtifact(uri="runs:/run-abc123/eval_results/per_row.parquet")
        )
        values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 3
        assert unit_ids is None

    def test_fallback_when_metric_column_absent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        df = pd.DataFrame({"row_id": ["0", "1"], "other_metric": [1.0, 0.0]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            metric_value=0.5, sample_size=2, per_row_artifact=PerRowArtifact(uri=parquet_path)
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="src.evaluation.deltaone_evaluator"):
            values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 2
        assert unit_ids is None
        assert any("absent" in r.message or "column" in r.message.lower() for r in caplog.records)

    def test_fallback_on_artifact_read_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        hem = _make_hem(
            metric_value=0.5,
            sample_size=10,
            per_row_artifact=PerRowArtifact(uri="/nonexistent/path/per_row.parquet"),
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="src.evaluation.deltaone_evaluator"):
            values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 10
        assert unit_ids is None
        assert any("failed to load" in r.message.lower() for r in caplog.records)

    def test_fallback_when_all_values_null(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        df = pd.DataFrame({"accuracy": [float("nan"), float("nan")]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            metric_value=0.5, sample_size=5, per_row_artifact=PerRowArtifact(uri=parquet_path)
        )
        import logging

        with caplog.at_level(logging.WARNING, logger="src.evaluation.deltaone_evaluator"):
            values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 5
        assert unit_ids is None


class TestHemToArrayFallbackPath:
    def test_proportion_reconstruction_matches_legacy_exactly(self) -> None:
        hem = _make_hem(metric_value=0.75, sample_size=1000)
        legacy_arr, _ = _hem_to_array(hem, "proportion")
        reconstructed = _reconstruct_array(hem, "proportion")
        assert np.allclose(legacy_arr, reconstructed)

    def test_proportion_fallback_bitfor_bit_no_per_row(self) -> None:
        hem = _make_hem(metric_value=0.6, sample_size=100)
        values, unit_ids = _hem_to_array(hem, "proportion")
        assert len(values) == 100
        assert float(np.mean(values)) == pytest.approx(0.6)
        assert unit_ids is None

    def test_continuous_fallback_is_constant_array(self) -> None:
        hem = _make_hem(metric_value=3.14, sample_size=50)
        values, unit_ids = _hem_to_array(hem, "continuous")
        assert len(values) == 50
        assert np.all(values == 3.14)
        assert unit_ids is None

    def test_zero_inflated_fallback_is_constant_array(self) -> None:
        hem = _make_hem(metric_value=2.5, sample_size=20)
        values, unit_ids = _hem_to_array(hem, "zero_inflated_continuous")
        assert len(values) == 20
        assert np.all(values == 2.5)


class TestHemToArrayUnitIds:
    def test_declared_column_name_used_for_unit_ids(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"accuracy": [1.0, 0.0, 1.0], "account_id": ["a1", "a2", "a1"]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            per_row_artifact=PerRowArtifact(uri=parquet_path), unit_of_analysis="account_id"
        )
        _, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert unit_ids is not None
        assert list(unit_ids) == ["a1", "a2", "a1"]

    def test_falls_back_to_unit_id_column_when_declared_name_absent(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"accuracy": [1.0, 0.0], "unit_id": ["u1", "u2"]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            per_row_artifact=PerRowArtifact(uri=parquet_path), unit_of_analysis="account_id"
        )
        _, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert unit_ids is not None
        assert list(unit_ids) == ["u1", "u2"]

    def test_returns_none_unit_ids_when_column_missing(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"accuracy": [1.0, 0.0, 1.0]})
        parquet_path = _write_parquet(tmp_path, df)

        hem = _make_hem(
            per_row_artifact=PerRowArtifact(uri=parquet_path), unit_of_analysis="account_id"
        )
        values, unit_ids = _hem_to_array(hem, "proportion", "accuracy")

        assert len(values) == 3
        assert unit_ids is None


# ---------------------------------------------------------------------------
# _extract_metrics_from_run: per_row_artifact population
# ---------------------------------------------------------------------------


class TestExtractMetricsPerRowArtifact:
    def _make_run(self, *, per_row_uri: str | None = None) -> SimpleNamespace:
        tags: dict[str, str] = {
            "hokusai.primary_metric": "accuracy",
            "hokusai.dataset.num_samples": "100",
            "hokusai.dataset.hash": _HASH,
            "hokusai.model_id": "model-x",
        }
        if per_row_uri is not None:
            tags[PER_ROW_ARTIFACT_URI_TAG] = per_row_uri
        return SimpleNamespace(
            info=SimpleNamespace(run_id="run-1", start_time=None, experiment_id="1"),
            data=SimpleNamespace(metrics={"accuracy": 0.8}, tags=tags, params={}),
        )

    def test_populates_per_row_artifact_from_tag(self) -> None:
        uri = "runs:/run-abc123/eval_results/per_row.parquet"
        run = self._make_run(per_row_uri=uri)
        client = _FakeMlflowClient({"run-1": run})
        evaluator = DeltaOneEvaluator(mlflow_client=client)

        hem = evaluator._extract_metrics_from_run("run-1")

        assert hem.per_row_artifact is not None
        assert hem.per_row_artifact.uri == uri

    def test_per_row_artifact_is_none_when_tag_absent(self) -> None:
        run = self._make_run(per_row_uri=None)
        client = _FakeMlflowClient({"run-1": run})
        evaluator = DeltaOneEvaluator(mlflow_client=client)

        hem = evaluator._extract_metrics_from_run("run-1")

        assert hem.per_row_artifact is None

    def test_unit_of_analysis_propagated(self) -> None:
        run = self._make_run()
        client = _FakeMlflowClient({"run-1": run})
        evaluator = DeltaOneEvaluator(mlflow_client=client)

        hem = evaluator._extract_metrics_from_run("run-1", unit_of_analysis="account_id")

        assert hem.unit_of_analysis == "account_id"
