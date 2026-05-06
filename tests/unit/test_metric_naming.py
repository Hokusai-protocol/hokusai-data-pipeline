"""Unit tests for src/utils/metric_naming.py."""

from __future__ import annotations

import pytest

from src.utils.metric_naming import derive_mlflow_name, validate_mlflow_metric_key


class TestDerivemlflowName:
    def test_colon_replaced_with_underscore(self) -> None:
        assert (
            derive_mlflow_name("workflow:success_rate_under_budget")
            == "workflow_success_rate_under_budget"
        )

    def test_multiple_colons(self) -> None:
        assert derive_mlflow_name("a:b:c") == "a_b_c"

    def test_already_safe_name_unchanged(self) -> None:
        assert derive_mlflow_name("already_safe") == "already_safe"

    def test_override_returned_when_non_empty(self) -> None:
        assert derive_mlflow_name("name", override="custom_key") == "custom_key"

    def test_empty_override_falls_back_to_derived(self) -> None:
        assert derive_mlflow_name("my:metric", override="") == "my_metric"

    def test_none_override_falls_back_to_derived(self) -> None:
        assert derive_mlflow_name("my:metric", override=None) == "my_metric"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert derive_mlflow_name("  spaced  ") == "spaced"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError):
            derive_mlflow_name("")

    def test_whitespace_only_name_raises(self) -> None:
        with pytest.raises(ValueError):
            derive_mlflow_name("   ")

    def test_invalid_override_raises(self) -> None:
        with pytest.raises(ValueError, match="colon"):
            derive_mlflow_name("name", override="bad:key")


class TestValidateMlflowMetricKey:
    def test_valid_key_returns_none(self) -> None:
        assert validate_mlflow_metric_key("ok_key") is None

    def test_key_with_colon_raises(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_mlflow_metric_key("bad:key")
        assert "colon" in str(exc_info.value).lower() or ":" in str(exc_info.value)

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            validate_mlflow_metric_key("")

    def test_key_with_allowed_special_chars(self) -> None:
        validate_mlflow_metric_key("metric-name.v1/score")

    def test_key_with_space_allowed(self) -> None:
        validate_mlflow_metric_key("my metric")


class TestSalesMetricNaming:
    """Verify canonical sales:* metric names derive to valid, collision-free MLflow keys."""

    _CANONICAL_TO_DERIVED = {
        "sales:qualified_meeting_rate": "sales_qualified_meeting_rate",
        "sales:revenue_per_1000_messages": "sales_revenue_per_1000_messages",
        "sales:spam_complaint_rate": "sales_spam_complaint_rate",
        "sales:unsubscribe_rate": "sales_unsubscribe_rate",
    }

    def test_canonical_names_derive_to_expected_mlflow_keys(self) -> None:
        for canonical, expected in self._CANONICAL_TO_DERIVED.items():
            assert derive_mlflow_name(canonical) == expected

    def test_derived_names_are_valid_mlflow_keys(self) -> None:
        for canonical in self._CANONICAL_TO_DERIVED:
            derived = derive_mlflow_name(canonical)
            validate_mlflow_metric_key(derived)

    def test_derived_names_are_unique(self) -> None:
        derived = [derive_mlflow_name(k) for k in self._CANONICAL_TO_DERIVED]
        assert len(derived) == len(set(derived))

    def test_canonical_names_rejected_directly_by_validate(self) -> None:
        for canonical in self._CANONICAL_TO_DERIVED:
            with pytest.raises(ValueError):
                validate_mlflow_metric_key(canonical)
