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
    ]:
        assert _score(ref, []) == 0.0


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
