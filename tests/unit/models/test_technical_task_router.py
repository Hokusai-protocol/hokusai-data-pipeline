"""Unit coverage for the callable Technical Task Router pyfunc model.

Remote registry auth is supplied by ``MLFLOW_TRACKING_TOKEN`` in integration
paths; these unit tests use local file-backed MLflow.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import mlflow.pyfunc
import pandas as pd
import pytest

from scripts.model_30.clean_router_dataset import clean_router_datasets
from scripts.model_30.register_technical_task_router import (
    _attribution_per_row_frame,
    register_model,
    validate_router_dataset_model_ids,
)
from src.lineage.weight_commitment import compute_weight_commitment
from src.models.technical_task_router import (
    ROUTER_DATASET_ARTIFACT,
    TechnicalTaskRouterModel,
)

FIXTURE = Path(__file__).with_name("technical_task_router_fixture.csv")
REAL_MLFLOW_LOAD_MODEL = mlflow.pyfunc.load_model


def _loaded_model(k_neighbors: int = 2) -> TechnicalTaskRouterModel:
    model = TechnicalTaskRouterModel(k_neighbors=k_neighbors)
    model.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(FIXTURE)}))
    return model


def _feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "schema_version": "technical_task_router_inputs/v2",
                "task_descriptor": "{}",
                "task_description": "Refactor a FastAPI billing webhook with tests",
                "task_type": "refactor",
                "language": "python",
                "allowed_models": '["gpt-5.4","claude-sonnet-4-6"]',
                "preferred_models": '["claude-sonnet-4-6"]',
                "max_cost_usd": 1.0,
                "domain": "payments",
                "repo_size_bucket": "large",
                "requires_tests": True,
                "risk_level": "medium",
                "file_count": 6,
                "estimated_complexity": "medium",
                "expected_cost_usd": 0.5,
            }
        ]
    )


def _registration_args(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "router_dataset": str(FIXTURE),
        "tracking_uri": None,
        "experiment_name": "technical-task-router-test",
        "run_name": "test-run",
        "k_neighbors": 2,
        "smoke": False,
        "holdout_dataset": None,
        "evaluation_objectives": "all",
        "benchmark_version": "v2",
        "primary_metric": None,
        "benchmark_spec_id": None,
        "in_pool_coverage_gate": "warn",
        "min_in_pool_evidence_coverage": 0.70,
        "min_group_in_pool_evidence_coverage": 0.50,
        "launch_priority_models": "",
        "launch_priority_gate": "warn",
        "training_manifest": None,
        "model_id_uint": 30,
        "baseline_artifact_uri": "models:/Technical Task Router/4",
        "eth_rpc_url": "https://rpc.example",
        "delta_verifier_address": "0x" + "11" * 20,
        "model_registry_address": "0x" + "22" * 20,
        "onchain_timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _artifact_dir(tmp_path: Path, name: str, content: str) -> Path:
    artifact_dir = tmp_path / name
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "model.bin").write_text(content, encoding="utf-8")
    (artifact_dir / "MLmodel").write_text("ignored", encoding="utf-8")
    return artifact_dir


def test_load_context_loads_router_dataset_artifact() -> None:
    model = _loaded_model()

    result = model.predict(None, _feature_frame())

    assert list(result.columns) == [
        "selected_model",
        "selected_models",
        "confidence",
        "rationale",
        "estimated_cost_usd",
        "recommended_strategy",
        "alternatives",
        "tradeoffs",
        "nearest_neighbors",
        "neighbor_provenance",
    ]
    assert result.iloc[0]["selected_model"] == "claude-sonnet-4-6"
    assert result.iloc[0]["selected_models"] == ["claude-sonnet-4-6"]
    assert 0.0 <= result.iloc[0]["confidence"] <= 1.0
    assert result.iloc[0]["estimated_cost_usd"] > 0
    assert "nearest Wavemill router row" in result.iloc[0]["rationale"]
    assert result.iloc[0]["recommended_strategy"]["objective"] == "highest_reliability"
    assert result.iloc[0]["nearest_neighbors"]["count"] == 2
    assert len(result.iloc[0]["neighbor_provenance"]) == 2


def test_predict_emits_neighbor_provenance_sorted_by_distance(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [10, 20, 30])
    out = _predict_duration_scenario(tmp_path, rows)

    provenance = out["neighbor_provenance"]

    assert [entry["training_row_index"] for entry in provenance] == [0, 1, 2]
    assert provenance == sorted(
        provenance,
        key=lambda entry: (entry["distance"], entry["training_row_index"]),
    )
    assert all(entry["weight"] >= 0 for entry in provenance)


def test_attribution_per_row_frame_projects_outcomes_and_json_provenance() -> None:
    report = {
        "benchmark_rows": [
            {
                "row_id": "r0",
                "completed_successfully": True,
                "neighbor_provenance": [
                    {"training_row_index": 0, "weight": 1.0, "account_id": "user-a"}
                ],
            },
            {"row_id": "r1", "completed_successfully": False},
        ]
    }

    frame = _attribution_per_row_frame(report)

    assert list(frame.columns) == ["row_id", "completed_successfully", "neighbor_provenance"]
    assert frame["completed_successfully"].tolist() == [True, False]
    neighbors = json.loads(frame.iloc[0]["neighbor_provenance"])
    assert neighbors[0]["account_id"] == "user-a"
    # Rows with no neighbors serialize to an empty list, not null.
    assert frame.iloc[1]["neighbor_provenance"] == "[]"


def test_attribution_per_row_frame_handles_empty_report() -> None:
    frame = _attribution_per_row_frame({})
    assert list(frame.columns) == ["row_id", "completed_successfully", "neighbor_provenance"]
    assert frame.empty


def test_predict_neighbor_provenance_caps_at_dataset_size(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [10, 20])
    df = pd.DataFrame(rows)
    csv_path = tmp_path / "router.csv"
    df.to_csv(csv_path, index=False)
    router = TechnicalTaskRouterModel(k_neighbors=10)
    router.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(csv_path)}))

    out = router.predict(None, pd.DataFrame([{"task_type": "feature", "language": "py"}])).iloc[0]

    assert len(out["neighbor_provenance"]) == 2


def test_predict_neighbor_provenance_tie_breaks_by_training_row_index(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [10, 10, 10])
    out = _predict_duration_scenario(tmp_path, rows)

    assert [entry["training_row_index"] for entry in out["neighbor_provenance"]] == [0, 1, 2]


def test_strategy_router_respects_available_models_and_requested_stages() -> None:
    model = _loaded_model()
    features = _feature_frame()
    features.loc[0, "available_planner_models"] = '["gpt-5.4"]'
    features.loc[0, "available_coder_models"] = '["gpt-5.4"]'
    features.loc[0, "available_reviewer_models"] = '["claude-sonnet-4-6"]'
    features.loc[0, "workflow_stages"] = '["code"]'
    features.loc[0, "routing_objective"] = "lowest_cost"

    result = model.predict(None, features)
    strategy = result.iloc[0]["recommended_strategy"]

    assert strategy["objective"] == "lowest_cost"
    assert strategy["stages"] == ["code"]
    assert strategy["planner_model"] is None
    assert strategy["reviewer_model"] is None
    assert strategy["coder_model"] == "gpt-5.4"
    assert set(result.iloc[0]["selected_models"]) <= {"gpt-5.4"}
    assert strategy["estimated_cost_usd"] >= 0
    assert 0 <= strategy["estimated_success_under_budget"] <= 1
    assert 0 <= strategy["confidence"] <= 1
    assert set(result.iloc[0]["tradeoffs"]) == {
        "lowest_cost",
        "fastest_completion",
        "highest_reliability",
    }


def test_registration_dataset_validation_accepts_public_model_ids() -> None:
    summary = validate_router_dataset_model_ids(FIXTURE)

    assert summary.row_count == 3
    assert len(summary.sha256) == 64
    assert summary.selected_model_distribution == {
        "planner_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
        "coder_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
        "reviewer_model": {"claude-sonnet-4-6": 2, "gpt-5.4": 1},
    }
    assert summary.selected_model_distribution_by_group["task_type"]["feature"]["coder_model"] == {
        "claude-sonnet-4-6": 1
    }
    assert summary.in_pool_evidence_coverage["overall"]["coder"]["in_pool_fraction"] == 1.0


def test_registration_dataset_validation_reports_stale_label_in_pool_coverage(
    tmp_path: Path,
) -> None:
    stale_dataset = tmp_path / "stale-router-dataset.csv"
    stale_dataset.write_text(
        "\n".join(
            [
                "task_type,domain,complexity,"
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                'feature,backend,high,"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,claude-sonnet-4-5-20250929,gpt-5.4",
                'bugfix,frontend,low,"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,gpt-5.4,gpt-5.4",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = validate_router_dataset_model_ids(stale_dataset)
    coverage = summary.in_pool_evidence_coverage

    assert coverage["overall"]["coder"] == {
        "selected_rows": 2,
        "in_pool_rows": 1,
        "out_of_pool_rows": 1,
        "in_pool_fraction": 0.5,
    }
    assert coverage["excluded_selected_model_distribution"]["coder"] == {
        "claude-sonnet-4-5-20250929": 1
    }
    assert summary.selected_model_distribution_by_group["task_type"]["feature"]["coder_model"] == {
        "claude-sonnet-4-5-20250929": 1
    }
    assert summary.selected_model_distribution_by_group["domain"]["frontend"]["coder_model"] == {
        "gpt-5.4": 1
    }
    assert summary.to_mlflow_dict()["selected_model_distribution_by_group"]["complexity"]["high"][
        "coder_model"
    ] == {"claude-sonnet-4-5-20250929": 1}
    assert coverage["by_group"]["domain"]["backend"]["coder"]["in_pool_fraction"] == 0.0
    assert coverage["by_group"]["task_type"]["bugfix"]["coder"]["in_pool_fraction"] == 1.0


def test_registration_dataset_validation_reports_launch_priority_model_gaps() -> None:
    priority_set = {
        "schema_version": "model_30_launch_priority_models/v1",
        "source": {"name": "test", "url": "test", "snapshot_date": "2026-06-15"},
        "models": [
            {
                "model_id": "openai/gpt-5.4",
                "aliases": ["gpt-5.4"],
                "provider": "openai",
                "family": "gpt",
                "role_eligibility": ["coder"],
                "priority_tier": "anchor",
                "status": "active",
                "minimum_direct_evidence_target": 1,
            },
            {
                "model_id": "qwen/qwen3.7-max",
                "aliases": ["qwen3.7-max"],
                "provider": "qwen",
                "family": "qwen",
                "role_eligibility": ["coder"],
                "priority_tier": "low_cost_challenger",
                "status": "active",
                "minimum_direct_evidence_target": 2,
            },
        ],
    }

    summary = validate_router_dataset_model_ids(FIXTURE, launch_priority_models=priority_set)
    priority_coverage = summary.launch_priority_coverage

    assert priority_coverage is not None
    assert priority_coverage["priority_models"]["openai/gpt-5.4"]["roles"]["coder"] == {
        "direct_evidence_rows": 1,
        "available_pool_rows": 3,
        "minimum_direct_evidence_target": 1,
        "direct_evidence_gap": 0,
        "zero_direct_evidence": False,
    }
    qwen_role = priority_coverage["priority_models"]["qwen/qwen3.7-max"]["roles"]["coder"]
    assert qwen_role["direct_evidence_rows"] == 0
    assert qwen_role["available_pool_rows"] == 0
    assert qwen_role["direct_evidence_gap"] == 2
    assert priority_coverage["gap_summary"]["zero_direct_evidence_count"] == 1
    assert priority_coverage["gap_summary"]["below_target"][0]["model_id"] == "qwen/qwen3.7-max"


def test_registration_dataset_validation_rejects_fake_model_ids(tmp_path: Path) -> None:
    bad_dataset = tmp_path / "bad-router-dataset.csv"
    bad_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                '"[""gpt-5.4""]","[""deep-coder-v2""]","[""<synthetic>""]",'
                "gpt-5.4,fast-coder-v1,deep",
                "",
            ]
        ),
        encoding="utf-8",
    )

    try:
        validate_router_dataset_model_ids(bad_dataset)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected fake model ids to be rejected")

    assert "deep-coder-v2" in message
    assert "<synthetic>" in message
    assert "fast-coder-v1" in message
    assert "reviewer_model='deep'" in message


def test_registration_fails_before_mlflow_logging_for_invalid_model_ids(tmp_path: Path) -> None:
    bad_dataset = tmp_path / "bad-router-dataset.csv"
    bad_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                '"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",gpt-5.4,gpt-5.4,deep',
                "",
            ]
        ),
        encoding="utf-8",
    )
    args = _registration_args(
        router_dataset=str(bad_dataset),
    )

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment") as set_exp,
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
    ):
        try:
            register_model(args)
        except ValueError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected invalid dataset to fail registration")

    assert "reviewer_model='deep'" in message
    set_exp.assert_not_called()
    start_run.assert_not_called()


def test_registration_in_pool_coverage_gate_can_fail_before_mlflow(
    tmp_path: Path,
) -> None:
    stale_dataset = tmp_path / "stale-router-dataset.csv"
    stale_dataset.write_text(
        "\n".join(
            [
                "task_type,domain,complexity,"
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model",
                'feature,backend,high,"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,claude-sonnet-4-5-20250929,gpt-5.4",
                "",
            ]
        ),
        encoding="utf-8",
    )
    args = _registration_args(
        router_dataset=str(stale_dataset),
        in_pool_coverage_gate="fail",
        min_in_pool_evidence_coverage=0.99,
        min_group_in_pool_evidence_coverage=0.99,
    )

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment") as set_exp,
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
    ):
        with pytest.raises(ValueError, match="in-pool evidence coverage gate violated") as exc:
            register_model(args)

    assert "coder overall in-pool coverage 0/1=0.000 below 0.990" in str(exc.value)
    assert "claude-sonnet-4-5-20250929" not in str(exc.value)
    set_exp.assert_not_called()
    start_run.assert_not_called()


def test_registration_launch_priority_gate_can_fail_before_mlflow(tmp_path: Path) -> None:
    priority_path = tmp_path / "priority.json"
    priority_path.write_text(
        json.dumps(
            {
                "schema_version": "model_30_launch_priority_models/v1",
                "source": {"name": "test", "url": "test", "snapshot_date": "2026-06-15"},
                "generated_at": "2026-06-15T00:00:00Z",
                "models": [
                    {
                        "model_id": "qwen/qwen3.7-max",
                        "aliases": ["qwen3.7-max"],
                        "provider": "qwen",
                        "family": "qwen",
                        "role_eligibility": ["coder"],
                        "priority_tier": "low_cost_challenger",
                        "status": "active",
                        "minimum_direct_evidence_target": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = _registration_args(
        launch_priority_models=str(priority_path),
        launch_priority_gate="fail",
        in_pool_coverage_gate="off",
    )

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment") as set_exp,
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
    ):
        with pytest.raises(ValueError, match="launch-priority evidence gate violated") as exc:
            register_model(args)

    assert "qwen/qwen3.7-max role=coder direct evidence 0/2" in str(exc.value)
    set_exp.assert_not_called()
    start_run.assert_not_called()


def test_registration_logs_dataset_provenance_to_mlflow(tmp_path: Path) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = _registration_args()
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    candidate_dir = _artifact_dir(tmp_path, "candidate", "candidate")
    baseline_dir = _artifact_dir(tmp_path, "baseline", "baseline")
    baseline_commitment = f"0x{compute_weight_commitment(baseline_dir).root}"

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param") as log_param,
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            side_effect=[str(candidate_dir), str(baseline_dir)],
        ),
        patch(
            "scripts.model_30.register_technical_task_router.read_model_weight_head",
            return_value=baseline_commitment,
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        result = register_model(args)

    assert result["registered_model_version"] == "7"
    logged_params = {call.args[0]: call.args[1] for call in log_param.call_args_list}
    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert logged_params["router_dataset_rows"] == 3
    assert str(logged_params["router_dataset_sha256"]).startswith("sha256:")
    assert "claude-sonnet-4-6" in logged_params["router_dataset_model_distribution"]
    assert logged_params["in_pool_coverage_gate"] == "warn"
    assert logged_params["min_in_pool_evidence_coverage"] == 0.70
    assert logged_params["min_group_in_pool_evidence_coverage"] == 0.50
    assert logged_params["launch_priority_gate"] == "warn"
    assert logged_params["launch_priority_models"] == ""
    assert logged_tags["hokusai.dataset.id"] == "wavemill-hokusai-router-dataset-v1"
    assert logged_tags["hokusai.dataset.num_samples"] == "3"
    assert logged_tags["hokusai.model_30.in_pool_coverage_gate_violations"] == "[]"
    assert logged_tags["hokusai.model_30.launch_priority_gap_count"] == "0"
    assert logged_tags["hokusai.weight_commitment.baseline"] == baseline_commitment
    assert logged_tags["hokusai.weight_commitment.candidate"] == (
        f"0x{compute_weight_commitment(candidate_dir).root}"
    )
    log_dict.assert_called_once()


def test_registration_logs_holdout_evaluation_metrics_to_mlflow(tmp_path: Path) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = _registration_args(
        holdout_dataset=str(FIXTURE),
        evaluation_objectives="highest_reliability",
    )
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    candidate_dir = _artifact_dir(tmp_path, "candidate", "candidate")
    baseline_dir = _artifact_dir(tmp_path, "baseline", "baseline")
    baseline_commitment = f"0x{compute_weight_commitment(baseline_dir).root}"

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_metric") as log_metric,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            side_effect=[str(candidate_dir), str(baseline_dir)],
        ),
        patch(
            "scripts.model_30.register_technical_task_router.read_model_weight_head",
            return_value=baseline_commitment,
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        result = register_model(args)

    logged_metrics = {call.args[0]: call.args[1] for call in log_metric.call_args_list}
    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert result["evaluation_report"]["row_counts"]["evaluated_rows"] == 3
    assert (
        result["evaluation_report"]["primary_metric"] == "technical_task_router.benchmark_score_v2"
    )
    assert "technical_task_router.benchmark_score_v1" in logged_metrics
    assert "technical_task_router.benchmark_score_v2" in logged_metrics
    assert logged_tags["hokusai.primary_metric"] == "technical_task_router.benchmark_score/v2"
    assert logged_tags["hokusai.mlflow_name"] == "technical_task_router.benchmark_score_v2"
    assert logged_tags["hokusai.scorer_ref"] == "technical_task_router.benchmark_score/v2"
    assert logged_tags["hokusai.benchmark_spec_id"] == "technical_task_router.benchmark_score/v2"
    assert logged_tags["hokusai.metric_family"] == "continuous"
    assert logged_tags["hokusai.model_id_uint"] == "30"
    assert logged_tags["hokusai.model_30.benchmark_version"] == "v2"
    assert logged_tags["hokusai.model_30.primary_metric"] == (
        "technical_task_router.benchmark_score_v2"
    )
    assert logged_tags["hokusai.model_30.holdout_rows"] == "3"
    assert logged_tags["hokusai.model_30.benchmark_rows"] == "15"
    assert logged_tags["hokusai.model_30.quarantined_rows"] == "0"
    component_summary = json.loads(logged_tags["hokusai.model_30.component_summary"])
    assert sorted(component_summary) == [
        "technical_task_router.candidate_pool_robustness_v2",
        "technical_task_router.cost_efficiency_v2",
        "technical_task_router.sparse_cell_generalization_v2",
        "technical_task_router.success_under_budget_v1",
    ]
    assert log_dict.call_count == 2


def test_registration_logs_training_manifest_report_to_mlflow(tmp_path: Path) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    manifest_report = tmp_path / "report.json"
    manifest_report.write_text(
        json.dumps(
            {
                "dataset_hash": "sha256:" + "a" * 64,
                "manifest_digest": "sha256:" + "b" * 64,
                "as_of": "2026-06-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    args = _registration_args(
        training_manifest=str(manifest_report),
    )
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    candidate_dir = _artifact_dir(tmp_path, "candidate", "candidate")
    baseline_dir = _artifact_dir(tmp_path, "baseline", "baseline")
    baseline_commitment = f"0x{compute_weight_commitment(baseline_dir).root}"

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            side_effect=[str(candidate_dir), str(baseline_dir)],
        ),
        patch(
            "scripts.model_30.register_technical_task_router.read_model_weight_head",
            return_value=baseline_commitment,
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        register_model(args)

    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert logged_tags["training_dataset_hash"] == "sha256:" + "a" * 64
    assert logged_tags["training_manifest_digest"] == "sha256:" + "b" * 64
    assert logged_tags["training_as_of"] == "2026-06-01T00:00:00Z"
    assert any(call.args[1] == "training_manifest_report.json" for call in log_dict.call_args_list)


def test_registration_logs_split_report_manifest_to_mlflow(tmp_path: Path) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    split_report = tmp_path / "split-report.json"
    split_report.write_text(
        json.dumps(
            {
                "input_dataset_sha256": "sha256:" + "1" * 64,
                "train_dataset_sha256": "sha256:" + "2" * 64,
                "holdout_dataset_sha256": "sha256:" + "3" * 64,
                "quarantine_dataset_sha256": "sha256:" + "4" * 64,
            }
        ),
        encoding="utf-8",
    )
    args = _registration_args(
        training_manifest=str(split_report),
    )
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    candidate_dir = _artifact_dir(tmp_path, "candidate", "candidate")
    baseline_dir = _artifact_dir(tmp_path, "baseline", "baseline")
    baseline_commitment = f"0x{compute_weight_commitment(baseline_dir).root}"

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict") as log_dict,
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            side_effect=[str(candidate_dir), str(baseline_dir)],
        ),
        patch(
            "scripts.model_30.register_technical_task_router.read_model_weight_head",
            return_value=baseline_commitment,
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        register_model(args)

    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert logged_tags["training_dataset_hash"] == "sha256:" + "2" * 64
    assert "training_manifest_digest" not in logged_tags
    assert "training_as_of" not in logged_tags
    assert logged_tags["hokusai.model_30.input_dataset_hash"] == "sha256:" + "1" * 64
    assert logged_tags["hokusai.model_30.holdout_dataset_hash"] == "sha256:" + "3" * 64
    assert logged_tags["hokusai.model_30.quarantine_dataset_hash"] == "sha256:" + "4" * 64
    assert any(call.args[1] == "training_manifest_report.json" for call in log_dict.call_args_list)


def test_registration_warns_on_baseline_drift_and_keeps_onchain_value(
    tmp_path: Path, caplog
) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = _registration_args()
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    candidate_dir = _artifact_dir(tmp_path, "candidate", "candidate")
    baseline_dir = _artifact_dir(tmp_path, "baseline", "baseline")
    onchain_commitment = "0x" + "ab" * 32

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag") as set_tag,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict"),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            side_effect=[str(candidate_dir), str(baseline_dir)],
        ),
        patch(
            "scripts.model_30.register_technical_task_router.read_model_weight_head",
            return_value=onchain_commitment,
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        with caplog.at_level(logging.WARNING):
            register_model(args)

    assert "weight_commitment_baseline_drift" in caplog.text
    logged_tags = {call.args[0]: call.args[1] for call in set_tag.call_args_list}
    assert logged_tags["hokusai.weight_commitment.baseline"] == onchain_commitment


def test_registration_raises_when_candidate_artifact_has_no_committable_files(
    tmp_path: Path,
) -> None:
    class RunContext:
        def __enter__(self: RunContext) -> SimpleNamespace:
            return SimpleNamespace(info=SimpleNamespace(run_id="run-123"))

        def __exit__(self: RunContext, *args: Any) -> None:
            return None

    args = _registration_args()
    model_info = SimpleNamespace(model_uri="runs:/run-123/model", registered_model_version="7")
    empty_candidate_dir = tmp_path / "candidate"
    empty_candidate_dir.mkdir()

    with (
        patch("scripts.model_30.register_technical_task_router.mlflow.set_experiment"),
        patch("scripts.model_30.register_technical_task_router.mlflow.start_run") as start_run,
        patch("scripts.model_30.register_technical_task_router.mlflow.log_param"),
        patch("scripts.model_30.register_technical_task_router.mlflow.set_tag"),
        patch("scripts.model_30.register_technical_task_router.mlflow.log_dict"),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.artifacts.download_artifacts",
            return_value=str(empty_candidate_dir),
        ),
        patch(
            "scripts.model_30.register_technical_task_router.mlflow.pyfunc.log_model",
            return_value=model_info,
        ),
    ):
        start_run.return_value = RunContext()
        with pytest.raises(ValueError, match="no files to commit"):
            register_model(args)


def test_clean_router_dataset_merges_removes_available_fakes_and_drops_bad_labels(
    tmp_path: Path,
) -> None:
    dirty_dataset = tmp_path / "dirty-router-dataset.csv"
    clean_dataset = tmp_path / "clean-router-dataset.csv"
    report_path = tmp_path / "clean-router-dataset.report.json"
    dirty_dataset.write_text(
        "\n".join(
            [
                "available_planner_models,available_coder_models,available_reviewer_models,"
                "planner_model,coder_model,reviewer_model,task_type,completed_successfully,score",
                '"[""gpt-5.4"",""<synthetic>""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,gpt-5.4,gpt-5.4,feature,true,0.9",
                '"[""gpt-5.4""]","[""gpt-5.4""]","[""gpt-5.4""]",'
                "gpt-5.4,gpt-5.4,deep,feature,true,0.9",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = clean_router_datasets([dirty_dataset, dirty_dataset], clean_dataset, report_path)
    summary = validate_router_dataset_model_ids(clean_dataset)

    assert report["input_rows"] == 4
    assert report["output_rows"] == 1
    assert report["duplicate_rows_skipped"] == 1
    assert report["dropped_rows"] == 2
    assert report["removed_available_model_ids"] == {"<synthetic>": 2}
    assert report["drop_reasons"] == {"reviewer_model:invalid:deep": 2}
    assert summary.row_count == 1
    assert "<synthetic>" not in clean_dataset.read_text(encoding="utf-8")
    assert json.loads(report_path.read_text(encoding="utf-8"))["output_rows"] == 1


def test_predict_honors_unseen_allowed_model_when_history_has_no_match() -> None:
    model = _loaded_model()
    features = _feature_frame()
    features.loc[0, "allowed_models"] = '["gpt-5.5"]'
    features.loc[0, "preferred_models"] = '["gpt-5.5"]'

    result = model.predict(None, features)

    assert result.iloc[0]["selected_model"] == "gpt-5.5"
    assert result.iloc[0]["selected_models"] == ["gpt-5.5"]


def test_predict_borrows_retired_sonnet_evidence_for_current_allowed_sonnet(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "task_type": "feature",
            "language": "python",
            "domain": "backend",
            "completed_successfully": True,
            "score": 0.98,
            "planner_model": "gpt-5.4",
            "coder_model": "claude-sonnet-4-5-20250929",
            "reviewer_model": "gpt-5.4",
            "expected_cost_usd": 0.3,
            "actual_cost_usd": 0.3,
        },
        {
            "task_type": "feature",
            "language": "python",
            "domain": "backend",
            "completed_successfully": True,
            "score": 0.94,
            "planner_model": "gpt-5.4",
            "coder_model": "claude-sonnet-4-5-20250929",
            "reviewer_model": "gpt-5.4",
            "expected_cost_usd": 0.4,
            "actual_cost_usd": 0.4,
        },
        {
            "task_type": "feature",
            "language": "python",
            "domain": "backend",
            "completed_successfully": False,
            "score": 0.10,
            "planner_model": "gpt-5.4",
            "coder_model": "gpt-5.4",
            "reviewer_model": "gpt-5.4",
            "expected_cost_usd": 0.2,
            "actual_cost_usd": 0.2,
        },
    ]
    csv_path = tmp_path / "router.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    router = TechnicalTaskRouterModel(k_neighbors=len(rows))
    router.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(csv_path)}))
    features = pd.DataFrame(
        [
            {
                "task_type": "feature",
                "language": "python",
                "domain": "backend",
                "workflow_stages": '["code"]',
                "routing_objective": "highest_reliability",
                "available_coder_models": '["claude-sonnet-4-6","gpt-5.4"]',
                "available_planner_models": '["gpt-5.4"]',
                "available_reviewer_models": '["gpt-5.4"]',
            }
        ]
    )

    out = router.predict(None, features).iloc[0]
    strategy = out["recommended_strategy"]
    coder_evidence = strategy["role_evidence"]["coder"]

    assert strategy["coder_model"] == "claude-sonnet-4-6"
    assert out["selected_model"] == "claude-sonnet-4-6"
    assert out["selected_models"] == ["claude-sonnet-4-6"]
    assert coder_evidence["direct_support"] == 0
    assert coder_evidence["borrowed_support"] == 2
    assert coder_evidence["borrowed_from"] == {"claude-sonnet-4-5-20250929": 2}


def test_mlflow_pyfunc_save_load_and_predict_smoke(tmp_path: Path) -> None:
    model_path = tmp_path / "technical-task-router-model"
    mlflow.pyfunc.save_model(
        path=str(model_path),
        python_model=TechnicalTaskRouterModel(k_neighbors=2),
        artifacts={ROUTER_DATASET_ARTIFACT: str(FIXTURE)},
        input_example=_feature_frame(),
    )

    loaded = REAL_MLFLOW_LOAD_MODEL(str(model_path))
    result = loaded.predict(_feature_frame())

    assert result.iloc[0]["selected_model"] == "claude-sonnet-4-6"
    assert result.iloc[0]["selected_models"] == ["claude-sonnet-4-6"]


# ─────────────────────────────────────────────────────────────────────────────
# HOK-1928: duration evidence filtering — ignore nonpositive/missing durations
# ─────────────────────────────────────────────────────────────────────────────


def _dur_rows(
    model: str,
    durations: list,
    *,
    include_duration_column: bool = True,
) -> list[dict]:
    """Build minimal router dataset rows for one model with given duration values.

    Pass ``include_duration_column=False`` to produce rows without the
    ``actual_time_seconds`` column (simulates a dataset that never recorded it).
    When the flag is True, ``None`` items become ``NaN`` in the resulting
    DataFrame, simulating blank/missing duration cells in an otherwise-present
    column.
    """
    rows = []
    for dur in durations:
        row: dict = {
            "task_type": "feature",
            "language": "py",
            "domain": "backend",
            "repo_size_bucket": "medium",
            "files_touched_bucket": "2_5",
            "description_length_bucket": "medium",
            "risk_level": "low",
            "completed_successfully": True,
            "score": 0.9,
            "planner_model": model,
            "coder_model": model,
            "reviewer_model": model,
            "expected_cost_usd": 0.1,
            "actual_cost_usd": 0.1,
        }
        if include_duration_column:
            row["actual_time_seconds"] = dur
        rows.append(row)
    return rows


def _predict_duration_scenario(
    tmp_path: Path,
    rows: list[dict],
    *,
    routing_objective: str = "highest_reliability",
    workflow_stages: list[str] | None = None,
    available_coder_models: list[str] | None = None,
) -> dict:
    """Load a router model from ``rows`` and run a single prediction."""
    df = pd.DataFrame(rows)
    csv_path = tmp_path / "test-router-dataset.csv"
    df.to_csv(csv_path, index=False)

    router = TechnicalTaskRouterModel(k_neighbors=len(rows))
    router.load_context(SimpleNamespace(artifacts={ROUTER_DATASET_ARTIFACT: str(csv_path)}))

    feature_row: dict = {
        "task_type": "feature",
        "language": "py",
        "domain": "backend",
        "repo_size_bucket": "medium",
        "description_length_bucket": "medium",
        "risk_level": "low",
        "routing_objective": routing_objective,
    }
    if workflow_stages is not None:
        feature_row["workflow_stages"] = json.dumps(workflow_stages)
    if available_coder_models is not None:
        feature_row["available_coder_models"] = json.dumps(available_coder_models)

    result = router.predict(None, pd.DataFrame([feature_row]))
    return result.iloc[0].to_dict()


def test_duration_all_zero_produces_null(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [0, 0, 0])
    out = _predict_duration_scenario(tmp_path, rows)

    assert out["recommended_strategy"]["estimated_duration_seconds"] is None
    assert out["nearest_neighbors"]["mean_duration_seconds"] is None


def test_duration_mixed_zero_and_positive_uses_positive_values_only(tmp_path: Path) -> None:
    # Positives: [10, 20, 30] → median = 20.0, mean = 20.0
    rows = _dur_rows("model-a", [0, 0, 10, 20, 30])
    out = _predict_duration_scenario(tmp_path, rows)

    assert out["recommended_strategy"]["estimated_duration_seconds"] == 20.0
    assert out["nearest_neighbors"]["mean_duration_seconds"] == 20.0


def test_duration_nonpositive_and_missing_produces_null(tmp_path: Path) -> None:
    # Zero, negative, and NaN durations — all should be ignored.
    rows = _dur_rows("model-a", [0, -5, None])
    out = _predict_duration_scenario(tmp_path, rows)

    assert out["recommended_strategy"]["estimated_duration_seconds"] is None
    assert out["nearest_neighbors"]["mean_duration_seconds"] is None


def test_duration_missing_column_produces_null(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [1, 2, 3], include_duration_column=False)
    out = _predict_duration_scenario(tmp_path, rows)

    assert out["recommended_strategy"]["estimated_duration_seconds"] is None
    assert out["nearest_neighbors"]["mean_duration_seconds"] is None


def test_fastest_completion_prefers_known_duration_over_null(tmp_path: Path) -> None:
    # model-null has only zero durations → None; model-fast has positive durations.
    # With workflow_stages=["code"], only coder role is active, so strategy
    # separation is clean: each model's rows map to exactly one strategy.
    rows = _dur_rows("model-null", [0, 0, 0]) + _dur_rows("model-fast", [50, 50, 50])
    out = _predict_duration_scenario(
        tmp_path,
        rows,
        routing_objective="fastest_completion",
        workflow_stages=["code"],
        available_coder_models=["model-null", "model-fast"],
    )

    strategy = out["recommended_strategy"]
    assert strategy["coder_model"] == "model-fast"
    assert strategy["estimated_duration_seconds"] == 50.0


def test_fastest_completion_returns_null_duration_when_all_unknown(tmp_path: Path) -> None:
    rows = _dur_rows("model-a", [0, 0]) + _dur_rows("model-b", [0, 0])
    out = _predict_duration_scenario(
        tmp_path,
        rows,
        routing_objective="fastest_completion",
        workflow_stages=["code"],
        available_coder_models=["model-a", "model-b"],
    )

    strategy = out["recommended_strategy"]
    assert strategy["estimated_duration_seconds"] is None
    tradeoff = out["tradeoffs"]["fastest_completion"]
    assert tradeoff is not None
    assert tradeoff["estimated_duration_seconds"] is None
