"""Unit coverage for technical task router deterministic scorers."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.evaluation.scorers import resolve_scorer

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "schema" / "examples"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _load_v2_golden() -> dict:
    return _load_example("technical_task_router_benchmark_score.v2.golden.json")


def _valid_fixture_rows() -> list[dict]:
    return [
        _load_example("technical_task_router_row.success.v1.json"),
        _load_example("technical_task_router_row.over_budget.v1.json"),
        _load_example("technical_task_router_row.disallowed_model.v1.json"),
        _load_example("technical_task_router_row.failed.v1.json"),
    ]


def _score(ref: str, rows: list[dict]) -> float:
    return float(resolve_scorer(ref).callable_(rows))


def test_task_router_scorers_against_all_outcome_fixtures() -> None:
    rows = _valid_fixture_rows()

    assert _score("technical_task_router.feasibility/v1", rows) == pytest.approx(0.5)
    assert _score("technical_task_router.success_under_budget/v1", rows) == pytest.approx(0.25)
    assert _score("technical_task_router.benchmark_score/v1", rows) == pytest.approx(0.25)
    assert _score("technical_task_router.invalid_selection_rate/v1", rows) == pytest.approx(0.25)


def test_task_router_exact_budget_is_feasible_and_successful() -> None:
    row = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    row["actual_cost_usd"] = row["max_cost_usd"]

    assert _score("technical_task_router.feasibility/v1", [row]) == pytest.approx(1.0)
    assert _score("technical_task_router.benchmark_score/v1", [row]) == pytest.approx(1.0)


def test_task_router_empty_selected_models_are_allowed() -> None:
    row = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    row["selected_models"] = []

    assert _score("technical_task_router.feasibility/v1", [row]) == pytest.approx(1.0)
    assert _score("technical_task_router.benchmark_score/v1", [row]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "mutations,expected_feasibility,expected_success",
    [
        ({}, 1.0, 1.0),
        ({"actual_cost_usd": 999.0}, 0.0, 0.0),
        ({"selected_models": ["not-allowed-model"]}, 0.0, 0.0),
        ({"completed_successfully": False}, 1.0, 0.0),
    ],
)
def test_task_router_all_four_outcome_classes(
    mutations: dict,
    expected_feasibility: float,
    expected_success: float,
) -> None:
    row = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    row.update(mutations)

    assert _score("technical_task_router.feasibility/v1", [row]) == pytest.approx(
        expected_feasibility
    )
    assert _score("technical_task_router.success_under_budget/v1", [row]) == pytest.approx(
        expected_success
    )


def test_task_router_scorers_return_zero_for_empty_rows() -> None:
    for ref in [
        "technical_task_router.feasibility/v1",
        "technical_task_router.success_under_budget/v1",
        "technical_task_router.benchmark_score/v1",
        "technical_task_router.invalid_selection_rate/v1",
        "technical_task_router.cost_mae_usd/v1",
        "technical_task_router.duration_mae_seconds/v1",
        "technical_task_router.reliability_brier_score/v1",
        "technical_task_router.lowest_cost_success_under_budget/v1",
        "technical_task_router.fastest_completion_success_under_budget/v1",
        "technical_task_router.highest_reliability_success_under_budget/v1",
    ]:
        assert _score(ref, []) == 0.0


def test_task_router_v2_cost_efficiency_returns_zero_for_empty_rows() -> None:
    assert _score("technical_task_router.cost_efficiency/v2", []) == 0.0


def test_task_router_negative_or_zero_budget_is_infeasible() -> None:
    row = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    row["max_cost_usd"] = 0

    assert _score("technical_task_router.feasibility/v1", [row]) == 0.0
    assert _score("technical_task_router.benchmark_score/v1", [row]) == 0.0


def test_task_router_scorers_are_deterministic() -> None:
    rows = _valid_fixture_rows()
    values = [
        _score("technical_task_router.benchmark_score/v1", copy.deepcopy(rows)) for _ in range(100)
    ]

    assert values == [pytest.approx(0.25)] * 100


def test_task_router_prediction_error_diagnostics() -> None:
    success = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    failure = copy.deepcopy(_load_example("technical_task_router_row.failed.v1.json"))
    success.update(
        {
            "estimated_cost_usd": 0.8,
            "actual_time_seconds": 110.0,
            "estimated_duration_seconds": 100.0,
            "estimated_success_under_budget": 0.9,
        }
    )
    failure.update(
        {
            "estimated_cost_usd": 0.4,
            "actual_time_seconds": 80.0,
            "estimated_duration_seconds": 100.0,
            "estimated_success_under_budget": 0.2,
        }
    )
    rows = [success, failure]

    assert _score("technical_task_router.cost_mae_usd/v1", rows) == pytest.approx(0.3)
    assert _score("technical_task_router.duration_mae_seconds/v1", rows) == pytest.approx(15.0)
    assert _score("technical_task_router.reliability_brier_score/v1", rows) == pytest.approx(0.025)


def test_task_router_prediction_error_diagnostics_skip_missing_prediction_fields() -> None:
    row = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))

    assert _score("technical_task_router.cost_mae_usd/v1", [row]) == 0.0
    assert _score("technical_task_router.duration_mae_seconds/v1", [row]) == 0.0
    assert _score("technical_task_router.reliability_brier_score/v1", [row]) == 0.0


def test_task_router_duration_diagnostic_skips_null_and_zero_actual_labels() -> None:
    null_duration = copy.deepcopy(_load_example("technical_task_router_row.null_duration.v1.json"))
    zero_duration = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    zero_duration["actual_time_seconds"] = 0.0
    zero_duration["estimated_duration_seconds"] = 100.0

    assert (
        _score("technical_task_router.duration_mae_seconds/v1", [null_duration, zero_duration])
        == 100.0
    )


def test_task_router_objective_specific_success_rates() -> None:
    lowest_success = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    lowest_failure = copy.deepcopy(_load_example("technical_task_router_row.failed.v1.json"))
    fastest_success = copy.deepcopy(_load_example("technical_task_router_row.success.v1.json"))
    reliability_over_budget = copy.deepcopy(
        _load_example("technical_task_router_row.over_budget.v1.json")
    )
    lowest_success["routing_objective"] = "lowest_cost"
    lowest_failure["routing_objective"] = "lowest_cost"
    fastest_success["routing_objective"] = "fastest_completion"
    reliability_over_budget["routing_objective"] = "highest_reliability"
    rows = [lowest_success, lowest_failure, fastest_success, reliability_over_budget]

    assert _score("technical_task_router.lowest_cost_success_under_budget/v1", rows) == (
        pytest.approx(0.5)
    )
    assert _score("technical_task_router.fastest_completion_success_under_budget/v1", rows) == (
        pytest.approx(1.0)
    )
    assert _score("technical_task_router.highest_reliability_success_under_budget/v1", rows) == (
        pytest.approx(0.0)
    )


def test_task_router_v2_golden_fixture_scores_match_spec() -> None:
    golden = _load_v2_golden()
    rows = golden["rows"]
    expected = golden["expected"]["components"]

    assert _score("technical_task_router.success_under_budget/v1", rows) == pytest.approx(
        expected["success_under_budget"]
    )
    assert _score("technical_task_router.cost_efficiency/v2", rows) == pytest.approx(
        expected["cost_efficiency"]
    )
    assert _score("technical_task_router.sparse_cell_generalization/v2", rows) == pytest.approx(
        expected["sparse_cell_generalization"]
    )
    assert _score("technical_task_router.candidate_pool_robustness/v2", rows) == pytest.approx(
        expected["candidate_pool_robustness"]
    )
    assert _score("technical_task_router.benchmark_score/v2", rows) == pytest.approx(
        golden["expected"]["final_score"]
    )


def test_task_router_v2_benchmark_score_is_bounded() -> None:
    row = copy.deepcopy(_load_v2_golden()["rows"][0])
    row["scenario"] = "sparse_cell"
    row["actual_cost_usd"] = 0.0
    rows = [
        row,
        {**copy.deepcopy(row), "scenario": "challenger_present"},
        {**copy.deepcopy(row), "scenario": "dominant_model_removed"},
        {**copy.deepcopy(row), "scenario": "low_budget"},
    ]

    assert _score("technical_task_router.benchmark_score/v2", rows) == pytest.approx(1.0)


def test_task_router_v2_missing_required_scenario_slice_fails() -> None:
    rows = [row for row in _load_v2_golden()["rows"] if row["scenario"] != "sparse_cell"]

    with pytest.raises(ValueError, match="missing scenario rows: sparse_cell"):
        _score("technical_task_router.benchmark_score/v2", rows)
