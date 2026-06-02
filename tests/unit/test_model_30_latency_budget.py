from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.model_30 import latency_smoke_check as smoke


def test_load_budget_file_reads_required_metrics(tmp_path: Path) -> None:
    budget_path = tmp_path / "budget.yaml"
    budget_path.write_text(
        "\n".join(
            [
                "cold_readiness_ms: {soft: 30000, hard: 60000}",
                "artifact_load_ms: {soft: 15000, hard: 25000}",
                "warm_p50_ms: {soft: 300, hard: 600}",
                "warm_p95_ms: {soft: 800, hard: 1500}",
                "warm_p99_ms: {soft: 1500, hard: 3000}",
                "timeout_rate: {soft: 0.0, hard: 0.02}",
                "warm_memory_mb: {soft: 800, hard: 1200}",
                "cold_memory_mb: {soft: 1200, hard: 1800}",
                "extra_metric: {soft: 1, hard: 2}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    budget = smoke.load_budget_file(budget_path)

    assert set(budget) == set(smoke.REQUIRED_BUDGET_KEYS)
    assert budget["warm_p95_ms"] == {"soft": 800.0, "hard": 1500.0}


def test_load_budget_file_raises_for_missing_metric(tmp_path: Path) -> None:
    budget_path = tmp_path / "budget.yaml"
    budget_path.write_text(
        "\n".join(
            [
                "cold_readiness_ms: {soft: 30000, hard: 60000}",
                "artifact_load_ms: {soft: 15000, hard: 25000}",
                "warm_p50_ms: {soft: 300, hard: 600}",
                "warm_p95_ms: {soft: 800, hard: 1500}",
                "warm_p99_ms: {soft: 1500, hard: 3000}",
                "timeout_rate: {soft: 0.0, hard: 0.02}",
                "warm_memory_mb: {soft: 800, hard: 1200}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(smoke.BudgetValidationError, match="cold_memory_mb"):
        smoke.load_budget_file(budget_path)


def test_main_returns_setup_error_for_unreadable_budget_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_30_SMOKE_JWT", "token")

    exit_code = smoke.main(
        [
            "--api-url",
            "http://localhost:8001",
            "--budget-file",
            "missing.yaml",
        ]
    )

    assert exit_code == smoke.SETUP_ERROR


def test_main_missing_jwt_writes_infra_inconclusive_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MODEL_30_SMOKE_JWT", raising=False)
    budget_path = tmp_path / "budget.yaml"
    budget_path.write_text(
        "\n".join(
            [
                "cold_readiness_ms: {soft: 30000, hard: 60000}",
                "artifact_load_ms: {soft: 15000, hard: 25000}",
                "warm_p50_ms: {soft: 300, hard: 600}",
                "warm_p95_ms: {soft: 800, hard: 1500}",
                "warm_p99_ms: {soft: 1500, hard: 3000}",
                "timeout_rate: {soft: 0.0, hard: 0.02}",
                "warm_memory_mb: {soft: 800, hard: 1200}",
                "cold_memory_mb: {soft: 1200, hard: 1800}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"

    exit_code = smoke.main(
        [
            "--api-url",
            "http://localhost:8001",
            "--budget-file",
            str(budget_path),
            "--report-out",
            str(report_path),
        ]
    )

    assert exit_code == smoke.INFRA_INCONCLUSIVE
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["classification"] == "infra_inconclusive"
    assert report["exit_code"] == smoke.INFRA_INCONCLUSIVE
    assert "MODEL_30_SMOKE_JWT" in report["reason"]


def test_compute_percentiles_for_range() -> None:
    percentiles = smoke.compute_percentiles([float(value) for value in range(1, 101)])

    assert percentiles["warm_p50_ms"] == pytest.approx(50.5)
    assert percentiles["warm_p95_ms"] == pytest.approx(95.05)
    assert percentiles["warm_p99_ms"] == pytest.approx(99.01)


def test_compute_percentiles_for_single_sample() -> None:
    percentiles = smoke.compute_percentiles([12.34])

    assert percentiles == {
        "warm_p50_ms": 12.34,
        "warm_p95_ms": 12.34,
        "warm_p99_ms": 12.34,
    }


@pytest.mark.parametrize(
    ("status", "body", "error", "expected"),
    [
        (200, {"ok": True}, None, "success"),
        (401, {"detail": "nope"}, None, "infra_auth"),
        (403, {"detail": "nope"}, None, "infra_auth"),
        (502, None, None, "infra_upstream"),
        (504, {"detail": {"error": "timeout"}}, None, "model_30_timeout"),
        (
            422,
            {"detail": "Technical Task Router MLflow inference failed: invalid output"},
            None,
            "model_30_error",
        ),
        (None, None, RuntimeError("connection reset"), "infra_network"),
    ],
)
def test_classify_response(status: int | None, body: object, error: object, expected: str) -> None:
    assert smoke.classify_response(status=status, body=body, error=error) == expected


def _budget() -> dict[str, dict[str, float]]:
    return {
        "cold_readiness_ms": {"soft": 30000.0, "hard": 60000.0},
        "artifact_load_ms": {"soft": 15000.0, "hard": 25000.0},
        "warm_p50_ms": {"soft": 300.0, "hard": 600.0},
        "warm_p95_ms": {"soft": 800.0, "hard": 1500.0},
        "warm_p99_ms": {"soft": 1500.0, "hard": 3000.0},
        "timeout_rate": {"soft": 0.0, "hard": 0.02},
        "warm_memory_mb": {"soft": 800.0, "hard": 1200.0},
        "cold_memory_mb": {"soft": 1200.0, "hard": 1800.0},
    }


def _metrics(**overrides: float | None) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {
        "cold_readiness_ms": 1000.0,
        "artifact_load_ms": 100.0,
        "warm_p50_ms": 100.0,
        "warm_p95_ms": 200.0,
        "warm_p99_ms": 300.0,
        "timeout_rate": 0.0,
        "warm_memory_mb": 500.0,
        "cold_memory_mb": 700.0,
    }
    metrics.update(overrides)
    return metrics


def test_evaluate_budgets_clean_run() -> None:
    exit_code, classification, breaches, infra_summary, model_error_count = smoke.evaluate_budgets(
        metrics=_metrics(),
        budget=_budget(),
        samples=[{"classification": "success"} for _ in range(50)],
    )

    assert exit_code == 0
    assert classification == "pass"
    assert breaches == {"hard": [], "soft": []}
    assert infra_summary == {"auth": 0, "upstream": 0, "network": 0}
    assert model_error_count == 0


def test_evaluate_budgets_hard_latency_breach() -> None:
    exit_code, classification, breaches, _, _ = smoke.evaluate_budgets(
        metrics=_metrics(warm_p95_ms=2000.0),
        budget=_budget(),
        samples=[{"classification": "success"} for _ in range(50)],
    )

    assert exit_code == smoke.LATENCY_BREACH
    assert classification == "hard_breach"
    assert breaches["hard"] == ["warm_p95_ms"]


def test_evaluate_budgets_model_error_excess() -> None:
    exit_code, classification, _, _, model_error_count = smoke.evaluate_budgets(
        metrics=_metrics(),
        budget=_budget(),
        samples=[{"classification": "success"} for _ in range(49)]
        + [{"classification": "model_30_error"}],
    )

    assert exit_code == smoke.MODEL_30_ERROR_EXCESS
    assert classification == "model_30_error_excess"
    assert model_error_count == 1


def test_evaluate_budgets_soft_only_breach() -> None:
    exit_code, classification, breaches, _, _ = smoke.evaluate_budgets(
        metrics=_metrics(warm_p95_ms=1000.0),
        budget=_budget(),
        samples=[{"classification": "success"} for _ in range(50)],
    )

    assert exit_code == 0
    assert classification == "pass"
    assert breaches["soft"] == ["warm_p95_ms"]
    assert breaches["hard"] == []


def test_build_report_shape() -> None:
    report = smoke.build_report(
        metrics=_metrics(),
        budget=_budget(),
        breaches={"hard": [], "soft": []},
        classification="pass",
        exit_code=0,
        infra_summary={"auth": 0, "upstream": 0, "network": 0},
        samples=[{"latency_ms": 10.0, "status": 200, "classification": "success"}],
        model_30_error_count=0,
    )

    assert set(report) >= {
        "metrics",
        "budget",
        "breaches",
        "classification",
        "exit_code",
        "infra_summary",
        "samples",
    }
    assert report["breaches"] == {"hard": [], "soft": []}
    assert report["samples"][0] == {
        "latency_ms": 10.0,
        "status": 200,
        "classification": "success",
    }


def test_infra_inconclusive_gate_at_twenty_percent() -> None:
    exit_code, classification, breaches, infra_summary, _ = smoke.evaluate_budgets(
        metrics=_metrics(),
        budget=_budget(),
        samples=[{"classification": "infra_auth"} for _ in range(10)]
        + [{"classification": "success"} for _ in range(40)],
    )

    assert exit_code == smoke.INFRA_INCONCLUSIVE
    assert classification == "infra_inconclusive"
    assert breaches["hard"] == []
    assert infra_summary == {"auth": 10, "upstream": 0, "network": 0}


def test_infra_noise_below_twenty_percent_is_tolerated() -> None:
    exit_code, classification, _, infra_summary, _ = smoke.evaluate_budgets(
        metrics=_metrics(),
        budget=_budget(),
        samples=[{"classification": "infra_auth"} for _ in range(9)]
        + [{"classification": "success"} for _ in range(41)],
    )

    assert exit_code == 0
    assert classification == "pass"
    assert infra_summary == {"auth": 9, "upstream": 0, "network": 0}


def test_parse_json_body_returns_none_for_invalid_json() -> None:
    assert smoke.parse_json_body("{") is None


def test_write_report_persists_json(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report = smoke.build_report(
        metrics=_metrics(),
        budget=_budget(),
        breaches={"hard": [], "soft": []},
        classification="pass",
        exit_code=0,
        infra_summary={"auth": 0, "upstream": 0, "network": 0},
        samples=[],
        model_30_error_count=0,
    )

    smoke.write_report(report_path, report)

    assert json.loads(report_path.read_text(encoding="utf-8"))["classification"] == "pass"
