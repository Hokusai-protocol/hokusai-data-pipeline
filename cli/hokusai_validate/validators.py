"""Data validation modules for schema, PII, and quality checks."""

import re
from re import Pattern
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .exceptions import PIIDetectionError, SchemaValidationError


class SchemaValidator:
    """Validates data against schema definitions."""

    def validate(self, data: pd.DataFrame, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate DataFrame against schema.

        Args:
            data: DataFrame to validate
            schema: Schema definition dictionary

        Returns:
            Validation result dictionary

        """
        result = {
            "valid": True,
            "errors": [],
            "missing_columns": [],
            "type_errors": {},
            "value_errors": {},
        }

        try:
            # Check required columns
            if "required_columns" in schema:
                missing_cols = self._check_required_columns(data, schema["required_columns"])
                if missing_cols:
                    result["valid"] = False
                    result["missing_columns"] = missing_cols
                    result["errors"].append(f"Missing required columns: {missing_cols}")

            # Check column types
            if "column_types" in schema:
                type_errors = self._check_column_types(data, schema["column_types"])
                if type_errors:
                    result["valid"] = False
                    result["type_errors"] = type_errors
                    result["errors"].append(
                        f"Type validation failed for columns: {list(type_errors.keys())}",
                    )

            # Check value ranges/constraints
            if "value_ranges" in schema:
                value_errors = self._check_value_ranges(data, schema["value_ranges"])
                if value_errors:
                    result["valid"] = False
                    result["value_errors"] = value_errors
                    result["errors"].append(
                        f"Value validation failed for columns: {list(value_errors.keys())}",
                    )

            return result

        except Exception as e:
            raise SchemaValidationError(f"Schema validation failed: {e!s}")

    def _check_required_columns(self, data: pd.DataFrame, required: List[str]) -> List[str]:
        """Check for missing required columns."""
        return [col for col in required if col not in data.columns]

    def _check_column_types(self, data: pd.DataFrame, types: Dict[str, str]) -> Dict[str, str]:
        """Check column data types."""
        type_errors = {}

        for col, expected_type in types.items():
            if col in data.columns:
                actual_type = str(data[col].dtype)
                if not self._types_compatible(actual_type, expected_type):
                    type_errors[col] = f"Expected {expected_type}, got {actual_type}"

        return type_errors

    def _check_value_ranges(
        self, data: pd.DataFrame, ranges: Dict[str, Dict],
    ) -> Dict[str, List[str]]:
        """Check value ranges and constraints."""
        value_errors = {}

        for col, constraints in ranges.items():
            if col not in data.columns:
                continue

            errors = []

            if "min" in constraints:
                min_val = constraints["min"]
                if (data[col] < min_val).any():
                    errors.append(f"Values below minimum {min_val}")

            if "max" in constraints:
                max_val = constraints["max"]
                if (data[col] > max_val).any():
                    errors.append(f"Values above maximum {max_val}")

            if "values" in constraints:
                allowed_values = constraints["values"]
                invalid_values = data[col][~data[col].isin(allowed_values)]
                if not invalid_values.empty:
                    errors.append(f"Invalid values: {invalid_values.unique().tolist()}")

            if errors:
                value_errors[col] = errors

        return value_errors

    def _types_compatible(self, actual: str, expected: str) -> bool:
        """Check if data types are compatible."""
        type_mappings = {
            "object": ["object", "string"],
            "int64": ["int64", "int32", "int16", "int8"],
            "float64": ["float64", "float32", "int64", "int32"],
            "bool": ["bool"],
            "datetime64": ["datetime64"],
        }

        compatible_types = type_mappings.get(expected, [expected])
        return any(actual.startswith(t) for t in compatible_types)


class PIIDetector:
    """Detects and handles personally identifiable information."""

    def __init__(self) -> None:
        """Initialize with default PII patterns."""
        self.patterns = {
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "phone": re.compile(r"\b(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
            "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
            "zip_code": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
        }
        self.custom_patterns = {}

    def add_custom_patterns(self, patterns: Dict[str, str]) -> None:
        """Add custom PII patterns."""
        for name, pattern in patterns.items():
            self.custom_patterns[name] = re.compile(pattern)

    def scan(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Scan DataFrame for PII.

        Args:
            data: DataFrame to scan

        Returns:
            PII detection results

        """
        try:
            result = {
                "pii_found": False,
                "patterns_detected": [],
                "flagged_fields": [],
                "details": {},
            }

            all_patterns = {**self.patterns, **self.custom_patterns}

            for col in data.columns:
                if data[col].dtype == "object":  # Only scan text columns
                    col_result = self._scan_column(data[col], all_patterns)

                    if col_result["pii_found"]:
                        result["pii_found"] = True
                        result["flagged_fields"].append(col)
                        result["details"][col] = col_result

                        for pattern in col_result["patterns_detected"]:
                            if pattern not in result["patterns_detected"]:
                                result["patterns_detected"].append(pattern)

            return result

        except Exception as e:
            raise PIIDetectionError(f"PII detection failed: {e!s}")

    def redact(self, data: pd.DataFrame) -> pd.DataFrame:
        """Redact PII from DataFrame.

        Args:
            data: DataFrame to redact

        Returns:
            DataFrame with PII redacted

        """
        redacted_data = data.copy()
        all_patterns = {**self.patterns, **self.custom_patterns}

        for col in redacted_data.columns:
            if redacted_data[col].dtype == "object":
                redacted_data[col] = redacted_data[col].apply(
                    lambda x: self._redact_text(str(x), all_patterns) if pd.notna(x) else x,
                )

        return redacted_data

    def _scan_column(self, column: pd.Series, patterns: Dict[str, Pattern]) -> Dict[str, Any]:
        """Scan a single column for PII patterns."""
        result = {"pii_found": False, "patterns_detected": [], "match_count": 0, "matches": []}

        text_data = column.dropna().astype(str)

        for pattern_name, pattern in patterns.items():
            matches = []
            for idx, text in text_data.items():
                found_matches = pattern.findall(text)
                if found_matches:
                    matches.extend([(idx, match) for match in found_matches])

            if matches:
                result["pii_found"] = True
                result["patterns_detected"].append(pattern_name)
                result["match_count"] += len(matches)
                result["matches"].extend([(pattern_name, idx, match) for idx, match in matches])

        return result

    def _redact_text(self, text: str, patterns: Dict[str, Pattern]) -> str:
        """Redact PII patterns from text."""
        redacted_text = text

        for pattern_name, pattern in patterns.items():
            redacted_text = pattern.sub("[REDACTED]", redacted_text)

        return redacted_text


class DataQualityChecker:
    """Checks data quality metrics and issues."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize with quality check configuration."""
        self.config = config or {}
        self.max_missing_percentage = self.config.get("max_missing_percentage", 0.1)
        self.outlier_threshold = self.config.get("outlier_threshold", 1.5)  # Standard deviations

    def check(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Perform comprehensive data quality checks.

        Args:
            data: DataFrame to check

        Returns:
            Quality check results

        """
        result = {
            "quality_score": 1.0,
            "issues": [],
            "missing_values": {},
            "outliers": [],
            "duplicates": {},
            "consistency": {},
        }

        # Check missing values
        missing_result = self._check_missing_values(data)
        result["missing_values"] = missing_result
        if missing_result["percentage"] > self.max_missing_percentage:
            result["issues"].append(
                f"High missing value percentage: {missing_result['percentage']:.2%}",
            )
            result["quality_score"] -= 0.2

        # Check for outliers
        outlier_result = self._detect_outliers(data)
        result["outliers"] = outlier_result
        if outlier_result:
            result["issues"].append(f"Outliers detected in {len(outlier_result)} columns")
            result["quality_score"] -= 0.1

        # Check for duplicates
        duplicate_result = self._check_duplicates(data)
        result["duplicates"] = duplicate_result
        if duplicate_result["count"] > 0:
            result["issues"].append(f"Duplicate rows found: {duplicate_result['count']}")
            result["quality_score"] -= 0.1

        # Check data consistency
        consistency_result = self._check_consistency(data)
        result["consistency"] = consistency_result

        # Ensure quality score doesn't go below 0
        result["quality_score"] = max(0.0, result["quality_score"])

        return result

    def _check_missing_values(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Check for missing values."""
        total_cells = data.size
        missing_cells = data.isnull().sum().sum()

        by_column = {}
        for col in data.columns:
            missing_count = data[col].isnull().sum()
            if missing_count > 0:
                by_column[col] = {
                    "count": int(missing_count),
                    "percentage": missing_count / len(data),
                }

        return {
            "total": int(missing_cells),
            "percentage": missing_cells / total_cells if total_cells > 0 else 0,
            "by_column": by_column,
        }

    def _detect_outliers(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect outliers using Z-score method."""
        outliers = []

        numeric_columns = data.select_dtypes(include=[np.number]).columns

        for col in numeric_columns:
            col_data = data[col].dropna()
            if len(col_data) < 3:  # Need at least 3 points for outlier detection
                continue

            mean = col_data.mean()
            std = col_data.std()

            if std == 0:  # No variation
                continue

            z_scores = np.abs((col_data - mean) / std)
            outlier_mask = z_scores > self.outlier_threshold

            if outlier_mask.any():
                outlier_indices = col_data[outlier_mask].index.tolist()
                outlier_z_scores = z_scores[outlier_mask].tolist()

                outliers.append(
                    {
                        "column": col,
                        "indices": outlier_indices,
                        "values": data.loc[outlier_indices, col].tolist(),
                        "z_scores": outlier_z_scores,
                    },
                )

        return outliers

    def _check_duplicates(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Check for duplicate rows."""
        duplicates = data.duplicated()
        duplicate_count = duplicates.sum()

        return {
            "count": int(duplicate_count),
            "percentage": duplicate_count / len(data) if len(data) > 0 else 0,
            "indices": data[duplicates].index.tolist(),
        }

    def _check_consistency(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Check data consistency."""
        result = {
            "duplicate_rows": int(data.duplicated().sum()),
            "empty_strings": {},
            "whitespace_issues": {},
        }

        # Check for empty strings and whitespace issues in text columns
        text_columns = data.select_dtypes(include=["object"]).columns

        for col in text_columns:
            empty_strings = (data[col] == "").sum()
            if empty_strings > 0:
                result["empty_strings"][col] = int(empty_strings)

            # Check for leading/trailing whitespace
            has_whitespace = (
                data[col]
                .astype(str)
                .apply(lambda x: x != x.strip() if pd.notna(x) else False)
                .sum()
            )
            if has_whitespace > 0:
                result["whitespace_issues"][col] = int(has_whitespace)

        return result
