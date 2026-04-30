"""JSON Schema definitions for Hokusai Evaluation Manifest (HEM)."""

from __future__ import annotations

from enum import Enum


class MetricFamily(str, Enum):
    """High-level category for the metric a scorer produces."""

    OUTCOME = "OUTCOME"
    QUALITY = "QUALITY"
    COST = "COST"
    LATENCY = "LATENCY"


HEM_V1_SCHEMA: dict[str, object] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Hokusai Evaluation Manifest v1",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "model_id",
        "eval_id",
        "dataset",
        "primary_metric",
        "metrics",
        "created_at",
        "mlflow_run_id",
    ],
    "properties": {
        "schema_version": {
            "type": "string",
            "enum": ["hokusai.eval.manifest/v1"],
        },
        "model_id": {"type": "string", "minLength": 1},
        "eval_id": {"type": "string", "minLength": 1},
        "mlflow_run_id": {"type": "string", "minLength": 1},
        "mlflow_dataset_id": {"type": "string", "minLength": 1},
        "created_at": {"type": "string", "format": "date-time"},
        "dataset": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "hash", "num_samples"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "hash": {"type": "string", "minLength": 1},
                "num_samples": {"type": "integer", "minimum": 0},
            },
        },
        "primary_metric": {"$ref": "#/definitions/metric"},
        "metrics": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/definitions/metric"},
        },
        "uncertainty": {
            "type": "object",
            "additionalProperties": False,
            "required": ["method", "ci95"],
            "properties": {
                "method": {"type": "string", "minLength": 1},
                "ci95": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        },
        "artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "path"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "hash": {"type": "string", "minLength": 1},
                    "type": {"type": "string", "minLength": 1},
                },
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["provider"],
            "properties": {
                "provider": {"type": "string", "minLength": 1},
                "provider_version": {"type": "string", "minLength": 1},
                "parameters": {"type": "object"},
            },
        },
        "scorer_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "version": {"type": "string"},
                    "kind": {"type": "string", "enum": ["custom", "builtin", "external"]},
                    "uri": {"type": "string"},
                },
            },
        },
        "scorer_source_hashes": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "measurement_policy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "aggregation": {"type": "string"},
                "thresholds": {"type": "object"},
                "sampling": {"type": "object"},
            },
        },
        "guardrail_results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "status"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "enum": ["pass", "fail", "skipped"]},
                    "details": {"type": "object"},
                },
            },
        },
        "eval_spec_version": {"type": "string", "minLength": 1},
        "input_dataset_hash": {"type": "string", "minLength": 1},
        "label_snapshot_hash": {"type": "string", "minLength": 1},
        "coverage": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "row_count": {"type": "integer"},
                "label_coverage": {"type": "number"},
                "notes": {"type": "string"},
            },
        },
    },
    "definitions": {
        "metric": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "value"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "value": {"type": "number"},
                "higher_is_better": {"type": "boolean"},
                "mlflow_name": {"type": "string", "minLength": 1},
            },
        }
    },
}
