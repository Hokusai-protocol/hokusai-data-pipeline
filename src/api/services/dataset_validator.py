"""Dataset format validation for uploaded benchmark files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_MIN_ROWS = 50
DEFAULT_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass
class ValidationError:
    """A single validation issue found in a dataset."""

    code: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationResult:
    """Aggregated result of dataset validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def to_dict(self: ValidationResult) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [{"code": e.code, "message": e.message} for e in self.errors],
            "warnings": [{"code": w.code, "message": w.message} for w in self.warnings],
        }


class DatasetValidationError(ValueError):
    """Raised when dataset validation fails with structured error details."""

    def __init__(self: DatasetValidationError, result: ValidationResult) -> None:
        self.result = result
        messages = [e.message for e in result.errors]
        super().__init__("; ".join(messages))


class DatasetValidator:
    """Validates uploaded dataset files for benchmark evaluation.

    Checks:
    - File size within limits
    - Declared target_column and input_columns exist in the dataset
    - Minimum row count for statistical significance
    - No completely empty columns among declared columns
    - Basic type inference warnings for mismatched column types
    """

    def __init__(
        self: DatasetValidator,
        min_rows: int = DEFAULT_MIN_ROWS,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        self.min_rows = min_rows
        self.max_file_size_bytes = max_file_size_bytes

    def validate(
        self: DatasetValidator,
        df: pd.DataFrame,
        *,
        target_column: str,
        input_columns: list[str],
        file_size_bytes: int,
    ) -> ValidationResult:
        """Run all validations on a loaded DataFrame.

        Raises DatasetValidationError if any errors are found.
        Returns ValidationResult (may contain warnings even on success).
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # 1. File size check
        if file_size_bytes > self.max_file_size_bytes:
            errors.append(
                ValidationError(
                    code="file_too_large",
                    message=(
                        f"File size ({file_size_bytes:,} bytes) exceeds maximum "
                        f"allowed size ({self.max_file_size_bytes:,} bytes)"
                    ),
                )
            )

        available_columns = list(df.columns)

        # 2. Check target_column exists
        if target_column and target_column not in df.columns:
            errors.append(
                ValidationError(
                    code="target_column_not_found",
                    message=(
                        f"Column '{target_column}' not found in dataset. "
                        f"Available columns: {', '.join(available_columns)}"
                    ),
                )
            )

        # 3. Check input_columns exist
        if input_columns:
            missing = [col for col in input_columns if col not in df.columns]
            if missing:
                errors.append(
                    ValidationError(
                        code="input_columns_not_found",
                        message=(
                            f"Input column(s) not found in dataset: {', '.join(missing)}. "
                            f"Available columns: {', '.join(available_columns)}"
                        ),
                    )
                )

        # 4. Minimum row count
        if len(df) < self.min_rows:
            errors.append(
                ValidationError(
                    code="insufficient_rows",
                    message=(
                        f"Dataset has {len(df)} row(s), but at least {self.min_rows} "
                        f"are required for statistically significant evaluation"
                    ),
                )
            )

        # 5. Check for completely empty columns among declared columns
        declared_columns = []
        if target_column and target_column in df.columns:
            declared_columns.append(target_column)
        if input_columns:
            declared_columns.extend(col for col in input_columns if col in df.columns)

        empty_columns = [col for col in declared_columns if df[col].isna().all()]
        if empty_columns:
            errors.append(
                ValidationError(
                    code="empty_columns",
                    message=(
                        f"Declared column(s) are completely empty: {', '.join(empty_columns)}"
                    ),
                )
            )

        # 6. Type inference warnings
        warnings.extend(self._check_column_types(df, target_column, input_columns))

        result = ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

        if not result.valid:
            raise DatasetValidationError(result)

        return result

    def _check_column_types(
        self: DatasetValidator,
        df: pd.DataFrame,
        target_column: str,
        input_columns: list[str],
    ) -> list[ValidationError]:
        """Run basic type inference checks and return warnings."""
        warnings: list[ValidationError] = []

        # Warn if target column is non-numeric and non-categorical (object with high cardinality)
        if target_column and target_column in df.columns:
            col = df[target_column]
            if col.dtype == object:
                n_unique = col.nunique()
                n_rows = len(col.dropna())
                if n_rows > 0 and n_unique > 0.5 * n_rows and n_unique > 20:
                    warnings.append(
                        ValidationError(
                            code="target_high_cardinality",
                            message=(
                                f"Target column '{target_column}' has high cardinality "
                                f"({n_unique} unique values out of {n_rows} rows). "
                                "This may indicate it is not a classification target."
                            ),
                            severity="warning",
                        )
                    )

        # Warn about mixed types in input columns
        if input_columns:
            for col_name in input_columns:
                if col_name not in df.columns:
                    continue
                col = df[col_name]
                null_frac = col.isna().sum() / len(col) if len(col) > 0 else 0
                if null_frac > 0.5:
                    warnings.append(
                        ValidationError(
                            code="high_null_fraction",
                            message=(f"Input column '{col_name}' has {null_frac:.0%} null values"),
                            severity="warning",
                        )
                    )

        return warnings
