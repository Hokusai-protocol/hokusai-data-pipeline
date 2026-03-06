"""Unit tests for DatasetValidator service."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.api.services.dataset_validator import (
    DatasetValidationError,
    DatasetValidator,
)


def _make_df(n_rows: int = 100, columns: list[str] | None = None) -> pd.DataFrame:
    """Create a simple test DataFrame."""
    if columns is None:
        columns = ["input_a", "input_b", "target"]
    data = {col: list(range(n_rows)) for col in columns}
    return pd.DataFrame(data)


class TestColumnValidation:
    def test_valid_columns_pass(self) -> None:
        df = _make_df()
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=["input_a", "input_b"], file_size_bytes=1000
        )
        assert result.valid
        assert len(result.errors) == 0

    def test_missing_target_column_raises(self) -> None:
        df = _make_df()
        validator = DatasetValidator(min_rows=10)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(
                df, target_column="label", input_columns=["input_a"], file_size_bytes=1000
            )
        result = exc_info.value.result
        assert not result.valid
        error_codes = [e.code for e in result.errors]
        assert "target_column_not_found" in error_codes
        assert "label" in result.errors[0].message
        assert "input_a" in result.errors[0].message  # available columns listed

    def test_missing_input_columns_raises(self) -> None:
        df = _make_df()
        validator = DatasetValidator(min_rows=10)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(
                df,
                target_column="target",
                input_columns=["input_a", "missing_col"],
                file_size_bytes=1000,
            )
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "input_columns_not_found" in error_codes
        assert "missing_col" in str(exc_info.value)

    def test_empty_target_column_skips_check(self) -> None:
        df = _make_df()
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="", input_columns=["input_a"], file_size_bytes=1000
        )
        assert result.valid

    def test_empty_input_columns_skips_check(self) -> None:
        df = _make_df()
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=[], file_size_bytes=1000
        )
        assert result.valid


class TestMinRowCount:
    def test_sufficient_rows_pass(self) -> None:
        df = _make_df(n_rows=50)
        validator = DatasetValidator(min_rows=50)
        result = validator.validate(
            df, target_column="target", input_columns=[], file_size_bytes=1000
        )
        assert result.valid

    def test_insufficient_rows_raises(self) -> None:
        df = _make_df(n_rows=10)
        validator = DatasetValidator(min_rows=50)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(df, target_column="target", input_columns=[], file_size_bytes=1000)
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "insufficient_rows" in error_codes
        assert "10" in result.errors[0].message
        assert "50" in result.errors[0].message

    def test_custom_min_rows(self) -> None:
        df = _make_df(n_rows=5)
        validator = DatasetValidator(min_rows=3)
        result = validator.validate(
            df, target_column="target", input_columns=[], file_size_bytes=1000
        )
        assert result.valid


class TestEmptyColumns:
    def test_completely_empty_target_raises(self) -> None:
        df = _make_df(n_rows=100)
        df["target"] = np.nan
        validator = DatasetValidator(min_rows=10)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(
                df, target_column="target", input_columns=["input_a"], file_size_bytes=1000
            )
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "empty_columns" in error_codes
        assert "target" in result.errors[0].message

    def test_completely_empty_input_column_raises(self) -> None:
        df = _make_df(n_rows=100)
        df["input_a"] = None
        validator = DatasetValidator(min_rows=10)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(
                df, target_column="target", input_columns=["input_a"], file_size_bytes=1000
            )
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "empty_columns" in error_codes

    def test_partially_filled_column_passes(self) -> None:
        df = _make_df(n_rows=100)
        df.loc[0:49, "input_a"] = np.nan
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=["input_a"], file_size_bytes=1000
        )
        assert result.valid


class TestFileSizeValidation:
    def test_oversized_file_raises(self) -> None:
        df = _make_df(n_rows=100)
        validator = DatasetValidator(min_rows=10, max_file_size_bytes=1000)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(df, target_column="target", input_columns=[], file_size_bytes=2000)
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "file_too_large" in error_codes

    def test_within_size_limit_passes(self) -> None:
        df = _make_df(n_rows=100)
        validator = DatasetValidator(min_rows=10, max_file_size_bytes=10000)
        result = validator.validate(
            df, target_column="target", input_columns=[], file_size_bytes=5000
        )
        assert result.valid


class TestTypeInferenceWarnings:
    def test_high_cardinality_target_warning(self) -> None:
        df = pd.DataFrame(
            {
                "input": range(100),
                "target": [f"unique_value_{i}" for i in range(100)],
            }
        )
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=["input"], file_size_bytes=1000
        )
        assert result.valid  # warnings don't make it invalid
        warning_codes = [w.code for w in result.warnings]
        assert "target_high_cardinality" in warning_codes

    def test_low_cardinality_target_no_warning(self) -> None:
        df = pd.DataFrame(
            {
                "input": range(100),
                "target": ["cat", "dog"] * 50,
            }
        )
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=["input"], file_size_bytes=1000
        )
        assert result.valid
        warning_codes = [w.code for w in result.warnings]
        assert "target_high_cardinality" not in warning_codes

    def test_high_null_input_warning(self) -> None:
        df = _make_df(n_rows=100)
        df.loc[0:79, "input_a"] = np.nan  # 80% null
        validator = DatasetValidator(min_rows=10)
        result = validator.validate(
            df, target_column="target", input_columns=["input_a"], file_size_bytes=1000
        )
        assert result.valid
        warning_codes = [w.code for w in result.warnings]
        assert "high_null_fraction" in warning_codes


class TestMultipleErrors:
    def test_multiple_errors_collected(self) -> None:
        df = _make_df(n_rows=5, columns=["col_a"])
        validator = DatasetValidator(min_rows=50)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(
                df,
                target_column="missing_target",
                input_columns=["missing_input"],
                file_size_bytes=1000,
            )
        result = exc_info.value.result
        error_codes = [e.code for e in result.errors]
        assert "target_column_not_found" in error_codes
        assert "input_columns_not_found" in error_codes
        assert "insufficient_rows" in error_codes


class TestValidationResultSerialization:
    def test_to_dict(self) -> None:
        df = _make_df(n_rows=5)
        validator = DatasetValidator(min_rows=50)
        with pytest.raises(DatasetValidationError) as exc_info:
            validator.validate(df, target_column="target", input_columns=[], file_size_bytes=1000)
        result_dict = exc_info.value.result.to_dict()
        assert result_dict["valid"] is False
        assert len(result_dict["errors"]) > 0
        assert "code" in result_dict["errors"][0]
        assert "message" in result_dict["errors"][0]
