"""Unit tests for the technical task router deterministic scorer."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.evaluation.custom_eval import DatasetLoadError, _load_technical_task_router_rows
from src.evaluation.scorers.builtin import _score_technical_task_router_row
from src.evaluation.scorers.registry import resolve_scorer


def _base_row() -> dict:
    return {
        "schema_version": "technical_task_router_row/v1",
        "row_id": "router-row-001",
        "task_descriptor": {"task_type": "bug_fix"},
        "allowed_models": ["gpt-4.1", "o4-mini"],
        "max_cost_usd": 1.0,
        "selected_models": ["gpt-4.1"],
        "workflow_config": {"steps": [{"model": "gpt-4.1"}]},
        "actual_cost_usd": 0.8,
        "completed_successfully": True,
    }


def test_router_row_all_pass_scores_one() -> None:
    assert _score_technical_task_router_row(_base_row()) == 1.0


def test_router_row_disallowed_model_scores_zero() -> None:
    row = _base_row()
    row["selected_models"] = ["gpt-4.1", "gpt-5"]
    assert _score_technical_task_router_row(row) == 0.0


def test_router_row_over_budget_scores_zero() -> None:
    row = _base_row()
    row["actual_cost_usd"] = 1.01
    assert _score_technical_task_router_row(row) == 0.0


def test_router_row_failed_completion_scores_zero() -> None:
    row = _base_row()
    row["completed_successfully"] = False
    assert _score_technical_task_router_row(row) == 0.0


def test_router_row_equal_budget_boundary_scores_one() -> None:
    row = _base_row()
    row["actual_cost_usd"] = row["max_cost_usd"]
    assert _score_technical_task_router_row(row) == 1.0


def test_router_aggregate_returns_expected_mean() -> None:
    scorer = resolve_scorer("technical_task_router:success_within_budget")
    rows = [_base_row()]

    row = _base_row()
    row["selected_models"] = ["unsupported-model"]
    rows.append(row)

    row = _base_row()
    row["actual_cost_usd"] = 1.2
    rows.append(row)

    row = _base_row()
    row["completed_successfully"] = False
    rows.append(row)

    row = _base_row()
    row["selected_models"] = ["gpt-4.1", "outside-allowlist"]
    rows.append(row)

    result = scorer.callable_(rows)
    assert result == {"technical_task_router:success_within_budget": pytest.approx(0.2)}


def test_router_row_missing_required_field_raises_value_error() -> None:
    row = copy.deepcopy(_base_row())
    del row["actual_cost_usd"]
    with pytest.raises(ValueError, match="missing required fields"):
        _score_technical_task_router_row(row)


def test_load_technical_task_router_rows_empty_dataset_raises(tmp_path: Path) -> None:
    """Empty datasets raise DatasetLoadError (mirrors sales scorer behaviour)."""
    dataset_path = tmp_path / "empty.json"
    dataset_path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(DatasetLoadError, match="at least one row"):
        _load_technical_task_router_rows(str(dataset_path))
