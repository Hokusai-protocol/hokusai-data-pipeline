"""Unit tests for src/events/api_schema.py.

MLflow calls are fully mocked; no live MLflow tracking URI or
MLFLOW_TRACKING_TOKEN is required for these unit tests.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from events.api_schema import (
    _mlflow_type_to_jsonschema,
    _schema_to_jsonschema,
    derive_api_schema,
    derive_api_schema_from_uri,
)


def _make_colspec(name: str, mlflow_type_str: str, optional: bool = False):
    """Build a ColSpec. optional=True maps to required=False in the ColSpec API."""
    from mlflow.types import ColSpec, DataType

    type_map = {
        "string": DataType.string,
        "integer": DataType.integer,
        "long": DataType.long,
        "float": DataType.float,
        "double": DataType.double,
        "boolean": DataType.boolean,
        "binary": DataType.binary,
        "datetime": DataType.datetime,
    }
    dtype = type_map[mlflow_type_str]
    col = ColSpec(type=dtype, name=name, required=not optional)
    return col


def _make_schema(*colspecs):
    """Build an MLflow Schema from ColSpec instances."""
    from mlflow.types import Schema

    return Schema(list(colspecs))


def _make_tensor_schema():
    """Build a tensor-based MLflow Schema (no column names)."""
    import numpy as np
    from mlflow.types import Schema, TensorSpec

    return Schema([TensorSpec(np.dtype("float32"), (-1, 4))])


class TestMlflowTypeToJsonschema:
    def test_string(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.string) == {"type": "string"}

    def test_integer(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.integer) == {"type": "integer"}

    def test_long(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.long) == {"type": "integer"}

    def test_float(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.float) == {"type": "number"}

    def test_double(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.double) == {"type": "number"}

    def test_boolean(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.boolean) == {"type": "boolean"}

    def test_binary(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.binary) == {
            "type": "string",
            "format": "byte",
        }

    def test_datetime(self):
        from mlflow.types import DataType

        assert _mlflow_type_to_jsonschema(DataType.datetime) == {
            "type": "string",
            "format": "date-time",
        }

    def test_unknown_type_returns_none(self):
        assert _mlflow_type_to_jsonschema("nonexistent_type") is None


class TestSchemaToJsonschema:
    def test_mixed_types_required_cols(self):
        schema = _make_schema(
            _make_colspec("text", "string"),
            _make_colspec("count", "integer"),
            _make_colspec("score", "double"),
            _make_colspec("active", "boolean"),
        )
        result = _schema_to_jsonschema(schema)
        assert result is not None
        assert result["type"] == "object"
        assert result["properties"]["text"] == {"type": "string"}
        assert result["properties"]["count"] == {"type": "integer"}
        assert result["properties"]["score"] == {"type": "number"}
        assert result["properties"]["active"] == {"type": "boolean"}
        assert set(result["required"]) == {"text", "count", "score", "active"}

    def test_optional_columns_excluded_from_required(self):
        schema = _make_schema(
            _make_colspec("required_field", "string", optional=False),
            _make_colspec("optional_field", "double", optional=True),
        )
        result = _schema_to_jsonschema(schema)
        assert result is not None
        assert "required_field" in result["properties"]
        assert "optional_field" in result["properties"]
        assert "required_field" in result["required"]
        assert "optional_field" not in result["required"]

    def test_all_optional_produces_no_required_key(self):
        schema = _make_schema(
            _make_colspec("a", "string", optional=True),
            _make_colspec("b", "integer", optional=True),
        )
        result = _schema_to_jsonschema(schema)
        assert result is not None
        assert "required" not in result

    def test_tensor_schema_returns_none(self):
        schema = _make_tensor_schema()
        assert _schema_to_jsonschema(schema) is None

    def test_none_schema_returns_none(self):
        assert _schema_to_jsonschema(None) is None

    def test_empty_inputs_returns_none(self):
        """A schema whose .inputs is an empty list returns None."""
        mock_schema = MagicMock()
        mock_schema.inputs = []
        assert _schema_to_jsonschema(mock_schema) is None


class TestDeriveApiSchema:
    def test_colspec_signature_returns_dict(self):
        from mlflow.models import ModelSignature

        inputs = _make_schema(
            _make_colspec("text", "string"),
            _make_colspec("num", "double"),
        )
        outputs = _make_schema(_make_colspec("label", "string"))
        sig = ModelSignature(inputs=inputs, outputs=outputs)

        result = derive_api_schema(sig)
        assert result is not None
        assert "inputSchema" in result
        assert "outputSchema" in result
        assert result["inputSchema"]["properties"]["text"] == {"type": "string"}
        assert result["outputSchema"]["properties"]["label"] == {"type": "string"}

    def test_none_signature_returns_none(self):
        assert derive_api_schema(None) is None

    def test_tensor_signature_returns_none(self):
        from mlflow.models import ModelSignature

        tensor = _make_tensor_schema()
        sig = ModelSignature(inputs=tensor, outputs=tensor)
        assert derive_api_schema(sig) is None

    def test_only_inputs_present(self):
        from mlflow.models import ModelSignature

        inputs = _make_schema(_make_colspec("x", "float"))
        sig = ModelSignature(inputs=inputs)
        result = derive_api_schema(sig)
        assert result is not None
        assert "inputSchema" in result
        assert "outputSchema" not in result

    def test_only_outputs_present(self):
        from mlflow.models import ModelSignature

        outputs = _make_schema(_make_colspec("pred", "double"))
        sig = ModelSignature(outputs=outputs)
        result = derive_api_schema(sig)
        assert result is not None
        assert "outputSchema" in result
        assert "inputSchema" not in result

    def test_required_reflects_non_optional_cols(self):
        from mlflow.models import ModelSignature

        inputs = _make_schema(
            _make_colspec("required_col", "string", optional=False),
            _make_colspec("optional_col", "integer", optional=True),
        )
        sig = ModelSignature(inputs=inputs)
        result = derive_api_schema(sig)
        assert result["inputSchema"]["required"] == ["required_col"]


class TestDeriveApiSchemaFromUri:
    def test_happy_path(self):
        from mlflow.models import ModelSignature

        inputs = _make_schema(_make_colspec("x", "double"))
        outputs = _make_schema(_make_colspec("y", "double"))
        sig = ModelSignature(inputs=inputs, outputs=outputs)

        mock_info = MagicMock()
        mock_info.signature = sig

        with patch("mlflow.models.get_model_info", return_value=mock_info):
            result = derive_api_schema_from_uri("models:/mymodel/1")

        assert result is not None
        assert "inputSchema" in result

    def test_get_model_info_raises_returns_none(self):
        with patch(
            "mlflow.models.get_model_info",
            side_effect=Exception("not found"),
        ):
            result = derive_api_schema_from_uri("models:/bad/999")

        assert result is None

    def test_signature_is_none_returns_none(self):
        mock_info = MagicMock()
        mock_info.signature = None

        with patch("mlflow.models.get_model_info", return_value=mock_info):
            result = derive_api_schema_from_uri("models:/nosig/1")

        assert result is None

    def test_none_uri_returns_none(self):
        assert derive_api_schema_from_uri(None) is None

    def test_empty_string_uri_returns_none(self):
        assert derive_api_schema_from_uri("") is None
