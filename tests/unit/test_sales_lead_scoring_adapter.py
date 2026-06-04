"""Unit tests for model 27 MLflow adapter behavior.

Production MLflow auth relies on environment wiring such as
`MLFLOW_TRACKING_TOKEN`; these tests patch the SDK locally.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pandas as pd
import pytest

from src.api.endpoints import sales_lead_scoring_adapter as adapter
from src.api.endpoints.model_30_adapter import Model30FailurePhase, Model30InferenceError


def _valid_inputs() -> dict[str, object]:
    return {
        "Customer ID": "CG-12520",
        "first_industry": "Technology",
        "first_segment": "Enterprise",
        "first_region": "North America",
        "first_subregion": "US East",
        "first_country": "United States",
        "first_product": "Analytics Suite",
        "first_sales": 12500.0,
        "first_quantity": 25.0,
        "first_discount": 0.1,
        "total_profit": 3200.0,
    }


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    adapter.reset_model_27_cache()


def test_validate_sales_lead_inputs_accepts_public_schema() -> None:
    validated = adapter.validate_sales_lead_scoring_inputs(_valid_inputs())

    assert validated.customer_id == "CG-12520"
    assert validated.first_sales == 12500.0


def test_validate_sales_lead_inputs_rejects_extra_fields() -> None:
    payload = dict(_valid_inputs())
    payload["unexpected"] = True

    with pytest.raises(Exception) as excinfo:
        adapter.validate_sales_lead_scoring_inputs(payload)

    assert "Extra inputs are not permitted" in str(excinfo.value)


def test_sales_lead_inputs_to_features_preserves_public_column_order() -> None:
    validated = adapter.validate_sales_lead_scoring_inputs(_valid_inputs())

    features = adapter.sales_lead_scoring_inputs_to_features(validated)

    assert isinstance(features, pd.DataFrame)
    assert list(features.columns) == list(adapter.MODEL_27_FEATURE_COLUMNS)
    assert features.iloc[0]["Customer ID"] == "CG-12520"


def test_normalize_model_27_output_from_probability_mapping() -> None:
    validated = adapter.validate_sales_lead_scoring_inputs(_valid_inputs())

    normalized = adapter.normalize_model_27_output(
        {"probability": 0.82, "confidence": 0.91},
        validated,
    )

    assert normalized == {
        "lead_score": 82,
        "conversion_probability": 0.82,
        "recommendation": "Hot",
        "confidence": 0.91,
    }


def test_normalize_model_27_output_from_probability_array() -> None:
    validated = adapter.validate_sales_lead_scoring_inputs(_valid_inputs())

    normalized = adapter.normalize_model_27_output([0.18, 0.82], validated)

    assert normalized["lead_score"] == 82
    assert normalized["conversion_probability"] == 0.82
    assert normalized["recommendation"] == "Hot"
    assert normalized["confidence"] == 0.82


def test_normalize_model_27_output_rejects_empty_result() -> None:
    validated = adapter.validate_sales_lead_scoring_inputs(_valid_inputs())

    with pytest.raises(Model30InferenceError) as excinfo:
        adapter.normalize_model_27_output([], validated)

    assert excinfo.value.phase == Model30FailurePhase.RESPONSE_NORMALIZATION


def test_call_mlflow_model_27_caches_loaded_model() -> None:
    class _Model:
        def predict(self, features):
            return [{"probability": 0.77}]

    with patch(
        "src.api.endpoints.sales_lead_scoring_adapter.mlflow.pyfunc.load_model"
    ) as load_mock:
        load_mock.return_value = _Model()
        timings: dict[str, float] = {}
        first = adapter.call_mlflow_model_27(
            "models:/Sales Lead Scoring@production", object(), timings
        )
        second = adapter.call_mlflow_model_27(
            "models:/Sales Lead Scoring@production", object(), timings
        )

    assert first == [{"probability": 0.77}]
    assert second == [{"probability": 0.77}]
    assert load_mock.call_count == 1
    assert timings["artifact_load_ms"] >= 0.0


def test_call_mlflow_model_27_maps_connectivity_failure_phase() -> None:
    with patch(
        "src.api.endpoints.sales_lead_scoring_adapter.mlflow.pyfunc.load_model",
        side_effect=OSError("connection refused"),
    ):
        with pytest.raises(Model30InferenceError) as excinfo:
            adapter.call_mlflow_model_27("models:/Sales Lead Scoring@production", object(), {})

    assert excinfo.value.phase == Model30FailurePhase.MLFLOW_CONNECTIVITY


def test_call_mlflow_model_27_rejects_concurrent_cold_load() -> None:
    gate = threading.Event()
    release = threading.Event()

    class _Model:
        def predict(self, features):
            del features
            return [{"probability": 0.7}]

    def fake_load_model(_uri: str) -> _Model:
        gate.set()
        release.wait(timeout=1)
        return _Model()

    with patch(
        "src.api.endpoints.sales_lead_scoring_adapter.mlflow.pyfunc.load_model",
        side_effect=fake_load_model,
    ):
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                adapter.call_mlflow_model_27("models:/Sales Lead Scoring@production", object(), {})
            except BaseException as exc:  # noqa: BLE001 - test helper
                errors.append(exc)

        first = threading.Thread(target=_worker)
        second = threading.Thread(target=_worker)
        first.start()
        gate.wait(timeout=1)
        second.start()
        second.join(timeout=1)
        release.set()
        first.join(timeout=1)

    assert any(isinstance(exc, adapter.Model27LoadInProgressError) for exc in errors)
