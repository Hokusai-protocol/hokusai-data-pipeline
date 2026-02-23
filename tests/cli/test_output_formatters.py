"""Unit tests for hoku eval output formatters."""

import json

from src.cli.output_formatters import format_ci, format_human, format_json, format_output


def test_format_json_produces_valid_json() -> None:
    payload = {"status": "success", "metrics": {"accuracy": 0.9}}
    rendered = format_json(payload)
    parsed = json.loads(rendered)
    assert parsed["status"] == "success"
    assert parsed["metrics"]["accuracy"] == 0.9


def test_format_ci_renders_key_values() -> None:
    payload = {"status": "success", "run_id": "run-123", "resumed": False}
    rendered = format_ci(payload)
    assert "status=success" in rendered
    assert "run_id=run-123" in rendered
    assert "resumed=false" in rendered


def test_format_human_renders_sections() -> None:
    payload = {
        "status": "success",
        "run_id": "run-123",
        "metrics": {"accuracy": 0.99},
        "plan": {"model_id": "model-a"},
    }
    rendered = format_human(payload)
    assert "Status: success" in rendered
    assert "Run ID: run-123" in rendered
    assert "Metrics:" in rendered
    assert "Plan:" in rendered


def test_format_output_routes_to_requested_formatter() -> None:
    payload = {"status": "ok"}
    assert json.loads(format_output("json", payload))["status"] == "ok"
    assert "status=ok" in format_output("ci", payload)
    assert "Status: ok" in format_output("human", payload)
