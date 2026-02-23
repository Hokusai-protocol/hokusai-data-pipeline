"""End-to-end tests for DeltaOne webhook notification triggering."""

from __future__ import annotations

# Auth-hook note: detect_delta_one is exercised with mocked MLflow client only.
# Production MLflow auth relies on Authorization / MLFLOW_TRACKING_TOKEN env wiring.
from types import SimpleNamespace
from unittest.mock import patch

from src.evaluation.deltaone_evaluator import detect_delta_one


def test_detect_delta_one_triggers_webhook_with_expected_payload() -> None:
    latest = SimpleNamespace(
        version="4",
        run_id="run-latest",
        tags={"benchmark_metric": "accuracy"},
    )
    baseline = SimpleNamespace(
        version="3",
        run_id="run-baseline",
        tags={"benchmark_metric": "accuracy", "benchmark_value": "0.84"},
    )

    run = SimpleNamespace(data=SimpleNamespace(metrics={"accuracy": 0.86}))

    class _Client:
        def search_model_versions(self, _filter: str):
            return [latest, baseline]

        def get_run(self, _run_id: str):
            return run

    with patch("src.evaluation.deltaone_evaluator.MlflowClient", return_value=_Client()):
        with patch("src.evaluation.deltaone_evaluator.send_deltaone_webhook") as mock_webhook:
            accepted = detect_delta_one("model-a", webhook_url="https://hooks.example.com/delta")

    assert accepted is True
    mock_webhook.assert_called_once()
    call_args = mock_webhook.call_args
    assert call_args.args[0] == "https://hooks.example.com/delta"

    payload = call_args.args[1]
    assert payload["model_name"] == "model-a"
    assert payload["baseline_version"] == "3"
    assert payload["new_version"] == "4"
    assert payload["metric_name"] == "accuracy"
