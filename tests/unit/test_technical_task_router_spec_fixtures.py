"""JSON schema validation for technical task router benchmark fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "technical_task_router_row.v1.json"
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"


@pytest.fixture()
def row_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    "filename",
    [
        "technical_task_router_row.success.v1.json",
        "technical_task_router_row.over_budget.v1.json",
        "technical_task_router_row.disallowed_model.v1.json",
        "technical_task_router_row.failed.v1.json",
    ],
)
def test_valid_task_router_row_examples_pass(
    row_validator: Draft202012Validator, filename: str
) -> None:
    row = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
    row_validator.validate(row)


def test_invalid_negative_cost_fixture_fails(row_validator: Draft202012Validator) -> None:
    row = json.loads(
        (EXAMPLES_DIR / "technical_task_router_row.invalid_negative_cost.v1.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(ValidationError, match="less than the minimum"):
        row_validator.validate(row)


def test_schema_rejects_extra_top_level_properties(row_validator: Draft202012Validator) -> None:
    row = json.loads(
        (EXAMPLES_DIR / "technical_task_router_row.success.v1.json").read_text(encoding="utf-8")
    )
    row["unexpected"] = "not allowed"

    with pytest.raises(ValidationError, match="Additional properties"):
        row_validator.validate(row)
