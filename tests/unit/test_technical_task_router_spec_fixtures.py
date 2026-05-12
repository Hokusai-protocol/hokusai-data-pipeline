"""Schema validation for technical task router fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"
EXAMPLES_DIR = SCHEMA_DIR / "examples"

VALID_EXAMPLES = [
    "technical_task_router_row.valid_success.v1.json",
    "technical_task_router_row.valid_failed_completion.v1.json",
    "technical_task_router_row.valid_over_budget.v1.json",
    "technical_task_router_row.valid_disallowed_model.v1.json",
]

INVALID_EXAMPLES = [
    "technical_task_router_row.invalid_negative_cost.v1.json",
]


@pytest.fixture(scope="module")
def row_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / "technical_task_router_row.v1.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("filename", VALID_EXAMPLES)
def test_valid_router_row_examples_pass_schema(
    filename: str, row_validator: Draft202012Validator
) -> None:
    payload = json.loads((EXAMPLES_DIR / filename).read_text())
    assert list(row_validator.iter_errors(payload)) == []


@pytest.mark.parametrize("filename", INVALID_EXAMPLES)
def test_invalid_router_row_examples_fail_schema(
    filename: str, row_validator: Draft202012Validator
) -> None:
    payload = json.loads((EXAMPLES_DIR / filename).read_text())
    assert list(row_validator.iter_errors(payload))
