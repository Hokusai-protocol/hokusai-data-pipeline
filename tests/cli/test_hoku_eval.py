"""Unit tests for hokusai eval CLI commands."""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

import src.cli.hoku_eval as hoku_eval


class _FakeRun:
    def __init__(self, run_id: str = "run-123", status: str = "RUNNING", tags=None) -> None:
        tag_payload = tags if tags is not None else {}
        self.info = SimpleNamespace(run_id=run_id, status=status)
        self.data = SimpleNamespace(tags=tag_payload, metrics={}, params={})


class _FakeClient:
    def __init__(self, model_exists: bool = True, matching_runs=None) -> None:
        self._model_exists = model_exists
        self._matching_runs = matching_runs or []

    def search_model_versions(self, _query: str):
        return [SimpleNamespace(name="model-a")] if self._model_exists else []

    def get_registered_model(self, _name: str):
        if not self._model_exists:
            raise ValueError("missing")
        return SimpleNamespace(name="model-a")

    def search_experiments(self):
        return [SimpleNamespace(experiment_id="0")]

    def search_runs(self, **_kwargs):
        return self._matching_runs

    def get_run(self, run_id: str):
        return _FakeRun(run_id=run_id, status="RUNNING", tags={"hoku_eval.status": "running"})


class _FakeMlflow:
    def __init__(self, metrics=None, raise_on_evaluate: bool = False) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self._metrics = metrics if metrics is not None else {"accuracy": 0.91}
        self._raise = raise_on_evaluate
        self.logged_params: list[tuple[str, object]] = []
        self.logged_metrics: list[tuple[str, float]] = []
        self.tags: list[tuple[str, str]] = []
        self.evaluate_kwargs = None

    def start_run(self, run_id: str | None = None, run_name: str | None = None):
        run_identifier = run_id or "run-123"
        run = _FakeRun(run_id=run_identifier)

        class _Ctx:
            def __enter__(self):
                return run

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Ctx()

    def set_tag(self, key: str, value: str) -> None:
        self.tags.append((key, value))

    def log_param(self, key: str, value) -> None:
        self.logged_params.append((key, value))

    def log_metric(self, key: str, value: float) -> None:
        self.logged_metrics.append((key, value))

    def log_dict(self, _payload: dict, _path: str) -> None:
        return None

    def evaluate(self, **kwargs):
        if self._raise:
            raise RuntimeError("boom")
        self.evaluate_kwargs = kwargs
        return SimpleNamespace(metrics=self._metrics)


def test_help_lists_eval_group() -> None:
    runner = CliRunner()
    result = runner.invoke(hoku_eval.eval_group, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output


def test_eval_run_help_lists_required_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(hoku_eval.eval_group, ["run", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--provider",
        "--seed",
        "--temperature",
        "--max-cost",
        "--dry-run",
        "--resume",
        "--attest",
        "--output",
    ):
        assert flag in result.output


def test_dry_run_success_json(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(hoku_eval, "_load_mlflow_client", lambda: _FakeClient(model_exists=True))

    result = runner.invoke(
        hoku_eval.eval_group,
        ["run", "model-a", "dataset-v1", "--dry-run", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "valid"
    assert payload["validation"]["model_exists"] is True


def test_dry_run_validation_error(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(hoku_eval, "_load_mlflow_client", lambda: _FakeClient(model_exists=False))

    result = runner.invoke(
        hoku_eval.eval_group,
        ["run", "missing-model", "dataset-v1", "--dry-run", "--output", "json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "invalid"
    assert payload["validation"]["errors"]


def test_eval_run_success_with_attestation(monkeypatch) -> None:
    runner = CliRunner()
    fake_mlflow = _FakeMlflow(metrics={"accuracy": 0.93, "cost_usd": 0.2})

    monkeypatch.setattr(hoku_eval, "_load_mlflow", lambda: fake_mlflow)
    monkeypatch.setattr(hoku_eval, "_load_mlflow_client", lambda: _FakeClient(model_exists=True))

    result = runner.invoke(
        hoku_eval.eval_group,
        [
            "run",
            "model-a",
            "dataset-v1",
            "--provider",
            "openai",
            "--seed",
            "42",
            "--temperature",
            "0.7",
            "--attest",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["attestation_hash"]
    assert payload["metrics"]["accuracy"] == 0.93
    assert fake_mlflow.evaluate_kwargs["evaluator_config"]["provider"] == "openai"
    assert fake_mlflow.evaluate_kwargs["evaluator_config"]["temperature"] == 0.7


def test_eval_run_skips_when_matching_completed_run_found(monkeypatch) -> None:
    runner = CliRunner()
    fake_mlflow = _FakeMlflow()
    completed_run = _FakeRun(
        run_id="run-complete",
        status="FINISHED",
        tags={"hoku_eval.status": "completed"},
    )

    monkeypatch.setattr(hoku_eval, "_load_mlflow", lambda: fake_mlflow)
    monkeypatch.setattr(
        hoku_eval,
        "_load_mlflow_client",
        lambda: _FakeClient(model_exists=True, matching_runs=[completed_run]),
    )

    result = runner.invoke(
        hoku_eval.eval_group,
        ["run", "model-a", "dataset-v1", "--resume", "auto", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "skipped"
    assert payload["run_id"] == "run-complete"


def test_eval_run_runtime_error_returns_exit_code_2(monkeypatch) -> None:
    runner = CliRunner()
    fake_mlflow = _FakeMlflow(raise_on_evaluate=True)

    monkeypatch.setattr(hoku_eval, "_load_mlflow", lambda: fake_mlflow)
    monkeypatch.setattr(hoku_eval, "_load_mlflow_client", lambda: _FakeClient(model_exists=True))

    result = runner.invoke(
        hoku_eval.eval_group,
        ["run", "model-a", "dataset-v1", "--output", "json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "error"


def test_benchmark_register_success(monkeypatch) -> None:
    runner = CliRunner()

    def _fake_request(**_kwargs):
        return {"spec_id": "spec-123", "model_id": "model-a"}

    monkeypatch.setattr(hoku_eval, "_benchmark_api_request", _fake_request)

    result = runner.invoke(
        hoku_eval.benchmark_group,
        [
            "register",
            "--model-id",
            "model-a",
            "--dataset-id",
            "kaggle/mmlu",
            "--dataset-version",
            "sha256:" + "a" * 64,
            "--metric-name",
            "accuracy",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["item"]["spec_id"] == "spec-123"


def test_benchmark_list_success(monkeypatch) -> None:
    runner = CliRunner()

    def _fake_request(**_kwargs):
        return {"count": 1, "items": [{"spec_id": "spec-123"}]}

    monkeypatch.setattr(hoku_eval, "_benchmark_api_request", _fake_request)

    result = runner.invoke(
        hoku_eval.benchmark_group,
        ["list", "--model-id", "model-a", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["count"] == 1
