"""Integration coverage for diagnostic-only custom outcome eval flows.

Auth note: tests use fake MLflow clients only; no live MLflow requests are made.
Production auth relies on MLFLOW_TRACKING_TOKEN / Authorization env wiring.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

import src.evaluation.custom_eval as custom_eval
from src.api.schemas.token_mint import TokenMintResult
from src.evaluation.custom_eval import run_custom_eval
from src.evaluation.deltaone_evaluator import DeltaOneEvaluator
from src.evaluation.deltaone_mint_orchestrator import DeltaOneMintOrchestrator
from src.evaluation.guardrails import evaluate_guardrails
from src.evaluation.manifest import create_hem_from_mlflow_run
from src.evaluation.spec_translation import RuntimeGuardrailSpec
from src.evaluation.tags import (
    DATASET_HASH_TAG,
    PER_ROW_ARTIFACT_URI_TAG,
    PRIMARY_METRIC_TAG,
    STATUS_TAG,
)
from tests.integration.test_sales_custom_eval_dispatch import (
    MODEL_ID,
    RUN_ID,
    SPEC_ID,
    _build_sales_benchmark_spec,
    _FakeMlflow,
    _load_example,
    _PersistTempDir,
)

pytestmark = pytest.mark.integration


class _FakeMlflowClient:
    def __init__(self, runs: dict[str, SimpleNamespace]) -> None:
        self._runs = runs
        self.tags_set: dict[str, dict[str, str]] = {}

    def get_run(self, run_id: str) -> SimpleNamespace:
        return self._runs[run_id]

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str,
        max_results: int,
        order_by: list[str],
    ) -> list[SimpleNamespace]:
        return []

    def set_tag(self, run_id: str, key: str, value: str) -> None:
        self.tags_set.setdefault(run_id, {})[key] = value


def _make_run(
    run_id: str,
    *,
    metric_name: str,
    metric_value: float,
    dataset_hash: str,
    num_samples: int,
    tags: dict[str, str] | None = None,
    start_time: int = 1_700_000_000_000,
) -> SimpleNamespace:
    run_tags = {
        "hokusai.model_id": MODEL_ID,
        "hokusai.eval_id": SPEC_ID,
        "hokusai.primary_metric": metric_name,
        "hokusai.dataset.id": "diagnostic-only-sales-fixture",
        "hokusai.dataset.hash": dataset_hash,
        "hokusai.dataset.num_samples": str(num_samples),
        **(tags or {}),
    }
    return SimpleNamespace(
        info=SimpleNamespace(run_id=run_id, start_time=start_time, experiment_id="1"),
        data=SimpleNamespace(
            tags=run_tags,
            params={},
            metrics={metric_name: metric_value},
        ),
    )


def _guardrail_specs(eval_spec: dict) -> list[RuntimeGuardrailSpec]:
    return [
        RuntimeGuardrailSpec(
            name=guardrail["name"],
            direction=guardrail["direction"],
            threshold=float(guardrail["threshold"]),
            blocking=bool(guardrail.get("blocking", True)),
            scorer_ref=guardrail.get("scorer_ref"),
        )
        for guardrail in eval_spec["guardrails"]
    ]


def test_diagnostic_only_pipeline_full_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    eval_spec = _load_example("sales_eval_spec.diagnostic_only.v1.json")
    rows = [
        _load_example("sales_outcome_row.revenue.v1.json"),
        _load_example("sales_outcome_row.unsubscribe.v1.json"),
        _load_example("sales_outcome_row.spam_complaint.v1.json"),
    ]
    dataset_path = tmp_path / "rows.json"
    dataset_path.write_text(json.dumps(rows), encoding="utf-8")

    benchmark_spec = _build_sales_benchmark_spec(dataset_path, eval_spec)
    fake_mlflow = _FakeMlflow()
    result_df = pd.DataFrame(
        {
            "row_id": [row["row_id"] for row in rows],
            "unit_id": [row["unit_id"] for row in rows],
            "message_quality_score": [0.78, 0.78, 0.78],
        }
    )

    monkeypatch.setattr(
        "src.evaluation.custom_eval.tempfile.TemporaryDirectory",
        lambda: _PersistTempDir(tmp_path),
    )
    monkeypatch.setattr(
        "src.evaluation.custom_eval._has_direct_sales_scorer_refs",
        lambda runtime_spec: False,
    )

    def _fake_dispatch_deterministic(**kwargs: object) -> SimpleNamespace:
        result = SimpleNamespace(
            metrics={"message_quality_score": 0.78},
            result_df=result_df,
        )
        custom_eval._persist_per_row_artifact(
            mlflow_module=kwargs["mlflow_module"],
            result=result,
            runtime_spec=kwargs["runtime_spec"],
            run_id=kwargs["run_id"],
        )
        return result

    monkeypatch.setattr(
        "src.evaluation.custom_eval._dispatch_deterministic",
        _fake_dispatch_deterministic,
    )

    result = run_custom_eval(
        model_id=MODEL_ID,
        benchmark_spec=benchmark_spec,
        benchmark_spec_id=SPEC_ID,
        mlflow_module=fake_mlflow,
        mlflow_client=None,
        cli_max_cost=None,
        seed=None,
        temperature=None,
    )

    assert result["status"] == "success"
    assert fake_mlflow.tags[PRIMARY_METRIC_TAG] == "message_quality_score"
    assert fake_mlflow.tags[STATUS_TAG] == "succeeded"
    assert re.match(r"^sha256:[0-9a-f]{64}$", fake_mlflow.tags[DATASET_HASH_TAG])
    assert fake_mlflow.metrics_logged["message_quality_score"] == pytest.approx(0.78)
    assert (
        fake_mlflow.tags[PER_ROW_ARTIFACT_URI_TAG] == f"runs:/{RUN_ID}/eval_results/per_row.parquet"
    )

    parquet_path = tmp_path / "per_row.parquet"
    assert parquet_path.exists()

    hem_run = SimpleNamespace(
        info=SimpleNamespace(run_id=RUN_ID),
        data=SimpleNamespace(
            tags={
                **fake_mlflow.tags,
                "hokusai.model_id": MODEL_ID,
                "hokusai.eval_id": SPEC_ID,
            },
            params={},
            metrics=fake_mlflow.metrics_logged,
        ),
    )
    fake_mlflow_for_hem = SimpleNamespace(
        get_run=lambda _run_id: hem_run,
        artifacts=SimpleNamespace(download_artifacts=lambda *args, **kwargs: str(parquet_path)),
    )
    monkeypatch.setitem(sys.modules, "mlflow", fake_mlflow_for_hem)

    manifest = create_hem_from_mlflow_run(RUN_ID)

    assert manifest.primary_metric["name"] == "message_quality_score"
    assert manifest.dataset == {
        "id": str(dataset_path),
        "hash": fake_mlflow.tags[DATASET_HASH_TAG],
        "num_samples": 3,
    }

    candidate_run = _make_run(
        "candidate-run",
        metric_name="message_quality_score",
        metric_value=0.78,
        dataset_hash=fake_mlflow.tags[DATASET_HASH_TAG],
        num_samples=3,
        tags={PER_ROW_ARTIFACT_URI_TAG: fake_mlflow.tags[PER_ROW_ARTIFACT_URI_TAG]},
    )
    baseline_run = _make_run(
        "baseline-run",
        metric_name="message_quality_score",
        metric_value=0.74,
        dataset_hash=fake_mlflow.tags[DATASET_HASH_TAG],
        num_samples=3,
        start_time=1_699_999_000_000,
    )
    evaluator_client = _FakeMlflowClient(
        {"candidate-run": candidate_run, "baseline-run": baseline_run}
    )
    evaluator = DeltaOneEvaluator(
        mlflow_client=evaluator_client,
        min_examples=100,
        cooldown_hours=0,
    )

    decision = evaluator.evaluate("candidate-run", "baseline-run")

    assert decision.accepted is False
    assert decision.reason == "insufficient_samples"

    guardrail_specs = _guardrail_specs(eval_spec)
    observations = {
        "sales:unsubscribe_rate": 0.0,
        "sales:spam_complaint_rate": 0.0,
    }
    guardrail_result = evaluate_guardrails(observations, guardrail_specs)

    assert guardrail_result.passed is True

    mocked_evaluator = Mock()
    mocked_evaluator.evaluate_for_model.return_value = decision
    mocked_evaluator.delta_threshold_pp = 1.0
    publisher = Mock()
    mint_hook = Mock()
    mint_hook.mint.return_value = TokenMintResult(
        status="success",
        audit_ref="unused",
        timestamp=datetime.now(UTC),
    )
    orchestrator_client = _FakeMlflowClient(
        {"candidate-run": candidate_run, "baseline-run": baseline_run}
    )
    orchestrator = DeltaOneMintOrchestrator(
        evaluator=mocked_evaluator,
        mint_hook=mint_hook,
        mlflow_client=orchestrator_client,
        mint_request_publisher=publisher,
    )

    outcome = orchestrator.process_evaluation_with_spec(
        "candidate-run",
        "baseline-run",
        benchmark_spec,
    )

    assert outcome.status == "not_eligible"
    mint_hook.mint.assert_not_called()
    publisher.publish.assert_not_called()
