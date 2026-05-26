from __future__ import annotations

import logging

from src.api.endpoints.latency_trace import Model30LatencyTrace


def test_latency_trace_emits_expected_structured_fields(caplog) -> None:
    trace = Model30LatencyTrace("req-123", "models:/Technical Task Router/1")
    trace.set_path_type(cached=False)
    trace.run_id = "run-456"
    trace.record_ms("request_validation", 3.2)
    trace.record_ms("model_cache_lookup", 1.1)
    trace.record_ms("artifact_load", 12.3)
    trace.record_ms("preprocessor_setup", 0.4)
    trace.record_ms("feature_transformation", 4.8)
    trace.record_ms("model_inference", 7.7)
    trace.record_ms("postprocessing_serialization", 1.5)
    trace.deadline_boundary_ms = 20.0

    with caplog.at_level(logging.INFO):
        trace.emit(logging.getLogger("test.model_30_latency_trace"))

    record = next(record for record in caplog.records if record.msg == "model_30_latency_trace")
    assert record.event == "model_30_latency_trace"
    assert record.request_id == "req-123"
    assert record.model_id == "30"
    assert record.model_uri == "models:/Technical Task Router/1"
    assert record.path_type == "cold"
    assert record.outcome == "success"
    assert record.run_id == "run-456"
    assert record.dominant_phase == "timeout_deadline_boundary"
    assert record.total_ms == 31.0
    assert record.request_validation_ms == 3.2
    assert record.model_cache_lookup_ms == 1.1
    assert record.artifact_load_ms == 12.3
    assert record.preprocessor_setup_ms == 0.4
    assert record.feature_transformation_ms == 4.8
    assert record.model_inference_ms == 7.7
    assert record.postprocessing_serialization_ms == 1.5
    assert record.timeout_deadline_boundary_ms == 20.0


def test_latency_trace_marks_warm_path() -> None:
    trace = Model30LatencyTrace("req-123", "models:/Technical Task Router/1")

    trace.set_path_type(cached=True)

    assert trace.path_type == "warm"


def test_latency_trace_dominant_phase_prefers_largest_model_phase(caplog) -> None:
    trace = Model30LatencyTrace("req-123", "models:/Technical Task Router/1")
    trace.record_ms("request_validation", 1.0)
    trace.record_ms("artifact_load", 25.0)
    trace.record_ms("model_inference", 5.0)
    trace.deadline_boundary_ms = 10.0

    with caplog.at_level(logging.INFO):
        trace.emit(logging.getLogger("test.model_30_latency_trace"))

    record = next(record for record in caplog.records if record.msg == "model_30_latency_trace")
    assert record.dominant_phase == "artifact_load"
