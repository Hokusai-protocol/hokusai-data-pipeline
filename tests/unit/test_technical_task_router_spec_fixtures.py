"""JSON schema validation for technical task router benchmark fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "technical_task_router_row.v1.json"
SCHEMA_V2_PATH = REPO_ROOT / "schema" / "technical_task_router_row.v2.json"
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"


@pytest.fixture()
def row_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture()
def row_v2_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_V2_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    "filename",
    [
        "technical_task_router_row.success.v1.json",
        "technical_task_router_row.over_budget.v1.json",
        "technical_task_router_row.disallowed_model.v1.json",
        "technical_task_router_row.failed.v1.json",
        "technical_task_router_row.null_duration.v1.json",
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


def test_task_router_v2_golden_rows_pass_schema(
    row_v2_validator: Draft202012Validator,
) -> None:
    golden = json.loads(
        (EXAMPLES_DIR / "technical_task_router_benchmark_score.v2.golden.json").read_text(
            encoding="utf-8"
        )
    )

    for row in golden["rows"]:
        row_v2_validator.validate(row)


def test_task_router_v2_spec_fixture_defines_reward_contract() -> None:
    spec = json.loads(
        (EXAMPLES_DIR / "technical_task_router_spec.v2.json").read_text(encoding="utf-8")
    )
    policy = spec["measurement_policy"]

    assert spec["primary_metric"]["name"] == "technical_task_router.benchmark_score/v2"
    assert spec["metric_family"] == "continuous"
    assert policy["row_schema_version"] == "technical_task_router_row/v2"
    assert "Rewards are paid only for improving the predefined" in policy["reward_policy"]
    assert policy["components"]["success_under_budget"]["weight"] == 0.7
    assert policy["components"]["cost_efficiency"]["weight"] == 0.15
    assert policy["components"]["sparse_cell_generalization"]["weight"] == 0.1
    assert policy["components"]["candidate_pool_robustness"]["weight"] == 0.05


def test_task_router_v2_golden_scores_are_deterministic() -> None:
    golden = json.loads(
        (EXAMPLES_DIR / "technical_task_router_benchmark_score.v2.golden.json").read_text(
            encoding="utf-8"
        )
    )
    rows = golden["rows"]
    weights = golden["weights"]

    def success_under_budget(row: dict[str, object]) -> float:
        selected_models = row["selected_models"]
        allowed_models = set(row["allowed_models"])
        if not isinstance(selected_models, list) or not all(
            model in allowed_models for model in selected_models
        ):
            return 0.0
        if row["completed_successfully"] is not True:
            return 0.0
        return float(row["actual_cost_usd"] <= row["max_cost_usd"])

    def mean(values: list[float]) -> float:
        return sum(values) / len(values)

    successes = [success_under_budget(row) for row in rows]
    sparse_successes = [
        success_under_budget(row) for row in rows if row["scenario"] == "sparse_cell"
    ]
    robustness_successes = [
        success_under_budget(row)
        for row in rows
        if row["scenario"] in {"challenger_present", "dominant_model_removed", "low_budget"}
    ]
    cost_efficiencies = [
        success_under_budget(row)
        * (1.0 - min(max(float(row["actual_cost_usd"]) / float(row["max_cost_usd"]), 0.0), 1.0))
        for row in rows
    ]

    components = {
        "success_under_budget": mean(successes),
        "cost_efficiency": mean(cost_efficiencies),
        "sparse_cell_generalization": mean(sparse_successes),
        "candidate_pool_robustness": mean(robustness_successes),
    }
    final_score = sum(components[name] * weight for name, weight in weights.items())

    assert components == pytest.approx(golden["expected"]["components"])
    assert final_score == pytest.approx(golden["expected"]["final_score"])
