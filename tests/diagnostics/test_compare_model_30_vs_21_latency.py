from __future__ import annotations

# MLflow auth in production comes from shared env such as MLFLOW_TRACKING_TOKEN.
from scripts.diagnostics import compare_model_30_vs_21_latency as harness


def test_aggregate_stats_correct_percentiles() -> None:
    stats = harness.aggregate_stats([1, 2, 3, 4, 5])

    assert stats == {"p50": 3.0, "p95": 5.0, "mean": 3.0, "min": 1.0, "max": 5.0, "n": 5}


def test_divergence_detected_when_phase_exceeds_2x() -> None:
    divergences = harness.analyze_divergence(
        {"model_inference": {"p50": 50.0}, "total": {"p50": 50.0}},
        {"model_inference": {"p50": 500.0}, "total": {"p50": 500.0}},
    )

    assert divergences[0]["phase"] == "model_inference"
    assert divergences[0]["ratio"] == 10.0


def test_divergence_detected_when_absolute_delta_100ms() -> None:
    divergences = harness.analyze_divergence(
        {"feature_transformation": {"p50": 80.0}, "total": {"p50": 80.0}},
        {"feature_transformation": {"p50": 190.0}, "total": {"p50": 190.0}},
    )

    assert divergences[0]["phase"] == "feature_transformation"
    assert divergences[0]["delta_ms"] == 110.0


def test_no_divergence_when_both_fast() -> None:
    divergences = harness.analyze_divergence(
        {"model_inference": {"p50": 40.0}, "total": {"p50": 40.0}},
        {"model_inference": {"p50": 50.0}, "total": {"p50": 50.0}},
    )

    assert divergences == [
        {
            "phase": "no_divergence",
            "model_21_p50_ms": 40.0,
            "model_30_p50_ms": 50.0,
            "delta_ms": 10.0,
            "ratio": 1.25,
        }
    ]


def test_error_run_excluded_from_aggregation() -> None:
    stats = harness.aggregate_phase_stats(
        [
            {"total_ms": 100.0, "model_inference_ms": 100.0},
            {"error": {"type": "RuntimeError", "message": "boom"}},
            {"total_ms": 200.0, "model_inference_ms": 200.0},
        ]
    )

    assert stats["total"]["n"] == 2
    assert stats["total"]["mean"] == 150.0
    assert stats["model_inference"]["n"] == 2


def test_report_rendering_contains_required_sections() -> None:
    model_template = {
        "warm": {
            "stats": {
                "total": {"p50": 10.0, "p95": 20.0, "mean": 12.0},
                "model_inference": {"p50": 9.0, "p95": 18.0, "mean": 11.0},
            }
        },
        "cold": {"stats": {"artifact_load": {"mean": 100.0}}},
        "artifact": {
            "size_bytes": 1024,
            "file_count": 1,
            "top_files": ["model.pkl (1024 bytes)"],
            "dependencies": ["numpy==1.0"],
            "runtime": ["python-3.11"],
        },
    }

    report = harness.render_report(
        model_template,
        model_template,
        [
            {
                "phase": "model_inference",
                "model_21_p50_ms": 9.0,
                "model_30_p50_ms": 18.0,
                "delta_ms": 9.0,
                "ratio": 2.0,
            }
        ],
        run_date="2026-05-26",
        mlflow_uri="https://mlflow.example",
    )

    assert "## Divergence Analysis" in report
    assert "| Phase |" in report
    assert "## Artifact Comparison" in report
    assert "## Preprocessing Complexity" in report
