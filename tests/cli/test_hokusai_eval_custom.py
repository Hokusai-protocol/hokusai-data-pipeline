"""CLI-level tests for --benchmark-spec-id flag in hokusai eval run."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import src.cli.hokusai_eval as hokusai_eval
from src.cli._api import BenchmarkSpecLookupError
from src.evaluation.custom_eval import (
    CostGateExceeded,
    CustomEvalError,
    CustomEvalRuntimeError,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SPEC_ID = "spec-abc-123"
_MODEL_ID = "my-model"
_VALID_HASH = "sha256:" + "a" * 64

_VALID_SPEC: dict[str, Any] = {
    "spec_id": _SPEC_ID,
    "model_id": _MODEL_ID,
    "is_active": True,
    "dataset_reference": "s3://bucket/data.json",
    "dataset_version": _VALID_HASH,
    "eval_split": "test",
    "metric_name": "accuracy",
    "metric_direction": "higher_is_better",
    "eval_spec": {
        "primary_metric": {"name": "accuracy", "direction": "higher_is_better"},
        "secondary_metrics": [],
        "guardrails": [],
        "measurement_policy": None,
    },
}

_SUCCESS_RESULT = {
    "status": "success",
    "run_id": "run-xyz",
    "metrics": {"accuracy": 0.9},
    "benchmark_spec_id": _SPEC_ID,
}


def _run(args: list[str], env: dict[str, str] | None = None) -> Any:
    # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
    runner = CliRunner()
    return runner.invoke(
        hokusai_eval.eval_group,
        args,
        env=env or {"HOKUSAI_API_KEY": "test-key"},
        catch_exceptions=False,
    )


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


def test_eval_run_help_lists_benchmark_spec_id() -> None:
    runner = CliRunner()
    result = runner.invoke(hokusai_eval.eval_group, ["run", "--help"])
    assert result.exit_code == 0
    assert "--benchmark-spec-id" in result.output


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_run_with_benchmark_spec_id_invokes_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(hokusai_eval, "fetch_benchmark_spec", lambda *a, **kw: _VALID_SPEC)

    with patch("src.cli.hokusai_eval.run_custom_eval", return_value=_SUCCESS_RESULT) as mock_run:
        with (
            patch("src.cli.hokusai_eval._load_mlflow"),
            patch("src.cli.hokusai_eval._load_mlflow_client"),
        ):
            result = _run(["run", _MODEL_ID, "--benchmark-spec-id", _SPEC_ID, "--output", "json"])

    assert result.exit_code == 0
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["model_id"] == _MODEL_ID
    assert call_kwargs["benchmark_spec_id"] == _SPEC_ID
    assert call_kwargs["benchmark_spec"] == _VALID_SPEC

    payload = json.loads(result.output)
    assert payload["status"] == "success"


# ---------------------------------------------------------------------------
# Spec lookup errors
# ---------------------------------------------------------------------------


def test_run_benchmark_spec_not_found_exits_1_no_run(monkeypatch) -> None:
    monkeypatch.setattr(
        hokusai_eval,
        "fetch_benchmark_spec",
        lambda *a, **kw: (_ for _ in ()).throw(
            BenchmarkSpecLookupError(f"Benchmark spec '{_SPEC_ID}' not found")
        ),
    )

    with patch("src.cli.hokusai_eval._load_mlflow") as mock_mlflow:
        result = _run(["run", _MODEL_ID, "--benchmark-spec-id", _SPEC_ID, "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"
    assert _SPEC_ID in payload["message"]
    mock_mlflow.assert_not_called()


def test_run_inactive_benchmark_spec_exits_1(monkeypatch) -> None:
    inactive_spec = {**_VALID_SPEC, "is_active": False}
    monkeypatch.setattr(hokusai_eval, "fetch_benchmark_spec", lambda *a, **kw: inactive_spec)

    with patch("src.cli.hokusai_eval.run_custom_eval") as mock_run:
        mock_run.side_effect = CustomEvalError("spec_not_found_or_inactive")
        with (
            patch("src.cli.hokusai_eval._load_mlflow"),
            patch("src.cli.hokusai_eval._load_mlflow_client"),
        ):
            result = _run(["run", _MODEL_ID, "--benchmark-spec-id", _SPEC_ID, "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"


# ---------------------------------------------------------------------------
# Cost gate
# ---------------------------------------------------------------------------


def test_run_cost_gate_exceeds_exits_1(monkeypatch) -> None:
    monkeypatch.setattr(hokusai_eval, "fetch_benchmark_spec", lambda *a, **kw: _VALID_SPEC)

    with patch("src.cli.hokusai_eval.run_custom_eval") as mock_run:
        mock_run.side_effect = CostGateExceeded(
            "Projected cost $5.00 exceeds cap $1.00 (500 rows × 1 GenAI scorers × $0.01/call)"
        )
        with (
            patch("src.cli.hokusai_eval._load_mlflow"),
            patch("src.cli.hokusai_eval._load_mlflow_client"),
        ):
            result = _run(
                [
                    "run",
                    _MODEL_ID,
                    "--benchmark-spec-id",
                    _SPEC_ID,
                    "--max-cost",
                    "1.0",
                    "--output",
                    "json",
                ]
            )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"
    assert "cost" in payload["message"].lower() or "gate" in payload["message"].lower()


# ---------------------------------------------------------------------------
# Runtime error
# ---------------------------------------------------------------------------


def test_run_custom_eval_runtime_error_exits_2(monkeypatch) -> None:
    monkeypatch.setattr(hokusai_eval, "fetch_benchmark_spec", lambda *a, **kw: _VALID_SPEC)

    with patch("src.cli.hokusai_eval.run_custom_eval") as mock_run:
        mock_run.side_effect = CustomEvalRuntimeError("mlflow_evaluate_error: boom")
        with (
            patch("src.cli.hokusai_eval._load_mlflow"),
            patch("src.cli.hokusai_eval._load_mlflow_client"),
        ):
            result = _run(["run", _MODEL_ID, "--benchmark-spec-id", _SPEC_ID, "--output", "json"])

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------


def test_run_without_benchmark_spec_id_unchanged(monkeypatch) -> None:
    """Existing eval_spec positional arg path still works."""
    from types import SimpleNamespace

    fake_mlflow = MagicMock()
    fake_run = MagicMock()
    fake_run.__enter__ = lambda s: SimpleNamespace(info=SimpleNamespace(run_id="run-old"))
    fake_run.__exit__ = MagicMock(return_value=False)
    fake_mlflow.start_run.return_value = fake_run
    fake_mlflow.evaluate.return_value = SimpleNamespace(metrics={"accuracy": 0.85})

    monkeypatch.setattr(hokusai_eval, "_load_mlflow", lambda: fake_mlflow)
    monkeypatch.setattr(
        hokusai_eval,
        "_load_mlflow_client",
        lambda: MagicMock(
            search_model_versions=lambda q: [SimpleNamespace(name="model-a")],
            search_experiments=lambda: [],
            search_runs=lambda **kw: [],
        ),
    )

    runner = CliRunner()
    result = runner.invoke(
        hokusai_eval.eval_group,
        ["run", "model-a", "dataset-v1", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"


def test_run_eval_spec_without_benchmark_spec_id_missing_spec_exits_1() -> None:
    """Calling run with no eval_spec and no --benchmark-spec-id exits 1."""
    runner = CliRunner()
    result = runner.invoke(
        hokusai_eval.eval_group,
        ["run", "model-a", "--output", "json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"


def test_conflict_eval_spec_path_and_benchmark_spec_id(monkeypatch) -> None:
    """Combining a path eval_spec with --benchmark-spec-id should exit 1."""
    runner = CliRunner()
    result = runner.invoke(
        hokusai_eval.eval_group,
        [
            "run",
            "model-a",
            "/path/to/data.json",
            "--benchmark-spec-id",
            _SPEC_ID,
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"
    assert "Cannot specify both" in payload["message"]


# ---------------------------------------------------------------------------
# Dry-run with --benchmark-spec-id
# ---------------------------------------------------------------------------


def test_dry_run_with_benchmark_spec_id(monkeypatch) -> None:
    monkeypatch.setattr(hokusai_eval, "fetch_benchmark_spec", lambda *a, **kw: _VALID_SPEC)

    result = _run(
        ["run", _MODEL_ID, "--benchmark-spec-id", _SPEC_ID, "--dry-run", "--output", "json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert "plan" in payload
    assert payload["plan"]["benchmark_spec_id"] == _SPEC_ID
