from __future__ import annotations

from scripts.model_30 import profile_inference


def test_aggregate_stats_includes_p99() -> None:
    stats = profile_inference.aggregate_stats([1, 2, 3, 4, 5])

    assert stats == {
        "p50": 3.0,
        "p95": 5.0,
        "p99": 5.0,
        "mean": 3.0,
        "min": 1.0,
        "max": 5.0,
        "n": 5,
    }


def test_aggregate_trace_samples_groups_each_phase() -> None:
    sample = profile_inference.TraceSample(
        total_ms=10.0,
        request_validation_ms=1.0,
        model_cache_lookup_ms=1.0,
        artifact_load_ms=2.0,
        preprocessor_setup_ms=1.0,
        feature_transformation_ms=2.0,
        model_inference_ms=2.0,
        postprocessing_serialization_ms=1.0,
    )

    stats = profile_inference.aggregate_trace_samples([sample, sample])

    assert stats["total_ms"]["mean"] == 10.0
    assert stats["artifact_load_ms"]["p95"] == 2.0
    assert stats["model_inference_ms"]["n"] == 2
