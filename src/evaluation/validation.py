"""Validation helpers for Hokusai Evaluation Manifest (HEM)."""

from __future__ import annotations

from jsonschema import Draft7Validator

from src.evaluation.schema import HEM_V1_SCHEMA


def validate_manifest(data: dict) -> list[str]:
    """Validate manifest data against HEM v1 and return error messages."""
    validator = Draft7Validator(HEM_V1_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.absolute_path))
    messages: list[str] = []
    for error in errors:
        location = ".".join(str(token) for token in error.absolute_path) or "<root>"
        messages.append(f"{location}: {error.message}")
    return messages
