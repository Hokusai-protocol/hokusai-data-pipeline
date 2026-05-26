from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.diagnostics import reproduce_model_30_inference as harness
from src.api.endpoints import model_30_adapter

# MLflow auth is configured in production via shared env such as MLFLOW_TRACKING_TOKEN.
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data/test_fixtures"


def test_main_generates_json_report(monkeypatch, tmp_path, capsys) -> None:
    model_30_adapter.reset_model_30_cache()
    model_30_adapter._MLFLOW_CLIENT_CONFIGURED = False

    def fake_load_model(_uri: str) -> object:
        def predict(features):
            row = features.iloc[0]
            return {
                "selected_model": f"stub-{row['task_type']}",
                "confidence": 0.9,
            }

        return SimpleNamespace(predict=predict)

    monkeypatch.setattr(
        "src.api.endpoints.model_30_adapter.mlflow.pyfunc.load_model",
        fake_load_model,
    )

    report_path = tmp_path / "report.json"
    exit_code = harness.main(
        [
            "--model-uri",
            "models:/Technical Task Router/1",
            "--curated-payload",
            str(FIXTURE_DIR / "model_30_curated_payload.json"),
            "--minimal-payload",
            str(FIXTURE_DIR / "model_30_minimal_payload.json"),
            "--warm-iterations",
            "3",
            "--output",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""

    stdout_report = json.loads(captured.out)
    file_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert stdout_report == file_report

    expected_top_level = {
        "cold_load_seconds",
        "cold_result_preview",
        "mlflow_tracking_uri",
        "mlflow_version",
        "model_uri",
        "payloads",
        "python_version",
        "rss_after_inference_mb",
        "rss_after_load_mb",
        "rss_before_load_mb",
        "timing_source",
        "trace_timings_ms",
        "verdict",
        "verdict_reason",
    }
    assert expected_top_level.issubset(stdout_report)
    assert stdout_report["verdict"] in {"model_runtime", "api_or_cache", "inconclusive"}

    for payload_name in ("curated", "minimal"):
        payload_report = stdout_report["payloads"][payload_name]
        stats = payload_report["warm_seconds"]
        assert len(stats["samples"]) == 3
        assert stats["min"] <= stats["median"] <= stats["max"]
        assert payload_report["result_preview"] is not None
        assert payload_report["error"] is None


def test_main_exits_non_zero_for_invalid_payload(tmp_path, capsys) -> None:
    invalid_payload = tmp_path / "invalid.json"
    invalid_payload.write_text('{"routing": {"max_cost_usd": 0.5}}', encoding="utf-8")

    exit_code = harness.main(
        [
            "--model-uri",
            "models:/Technical Task Router/1",
            "--curated-payload",
            str(invalid_payload),
            "--minimal-payload",
            str(FIXTURE_DIR / "model_30_minimal_payload.json"),
            "--warm-iterations",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "curated payload validation failed" in captured.err
