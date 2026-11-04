"""HOK-3400: one estimator scale for every route."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd
import pytest

from src.models import technical_task_router as ttr

STRONG = "claude-opus-4-7"
WEAK = "gpt-5.4"
POOL = json.dumps([STRONG, WEAK])


def _row(planner: str, coder: str, reviewer: str, *, success: bool, **extra: object) -> dict:
    return {
        "task_type": "feature",
        "language": "python",
        "domain": "backend",
        "complexity": 3,
        "max_cost_usd": 25,
        "available_planner_models": POOL,
        "available_coder_models": POOL,
        "available_reviewer_models": POOL,
        "planner_model": planner,
        "coder_model": coder,
        "reviewer_model": reviewer,
        "completed_successfully": "true" if success else "false",
        "score": 0.8 if success else 0.2,
        "actual_cost_usd": 10.0,
        **extra,
    }


def _model(tmp_path: Path, rows: list[dict], estimator: str) -> ttr.TechnicalTaskRouterModel:
    path = tmp_path / "router.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    model = ttr.TechnicalTaskRouterModel(estimator=estimator)
    model.load_context(type("C", (), {"artifacts": {ttr.ROUTER_DATASET_ARTIFACT: str(path)}})())
    return model


def _route_success(model: ttr.TechnicalTaskRouterModel, route: tuple[str, str, str]) -> float:
    features = ttr._normalize_serving_features(
        {
            "task_type": "feature",
            "language": "python",
            "complexity": 3,
            "available_planner_models": POOL,
            "available_coder_models": POOL,
            "available_reviewer_models": POOL,
        }
    )
    neighbors = model._nearest_neighbors(features)
    choices = [
        model._rank_role(role, neighbors, features, [model_id])[0]
        for role, model_id in zip(ttr.ROLE_COLUMNS, route, strict=True)
    ]
    return ttr._estimate_strategy(
        "highest_reliability",
        features["workflow_stages"],
        neighbors,
        features,
        *choices,
        estimator=model.estimator,
    ).estimated_success_under_budget


def _mixed_history() -> list[dict]:
    # STRONG-only routes succeed often; WEAK-only routes usually fail. One mixed
    # route (STRONG planner, WEAK coder, STRONG reviewer) has a single exact match
    # that happened to succeed.
    rows = [_row(STRONG, STRONG, STRONG, success=i % 5 != 0) for i in range(10)]
    rows += [_row(WEAK, WEAK, WEAK, success=i % 4 == 0) for i in range(8)]
    rows.append(_row(STRONG, WEAK, STRONG, success=True))
    return rows


def test_legacy_single_lucky_match_outranks_well_supported_route(tmp_path: Path) -> None:
    """The defect: one exact match puts a route on a different, extreme scale."""
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_LEGACY)
    lucky = _route_success(model, (STRONG, WEAK, STRONG))
    proven = _route_success(model, (STRONG, STRONG, STRONG))
    assert lucky > proven


def test_shrunk_single_lucky_match_stays_near_its_prior(tmp_path: Path) -> None:
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_SHRUNK)
    lucky = _route_success(model, (STRONG, WEAK, STRONG))
    proven = _route_success(model, (STRONG, STRONG, STRONG))
    assert proven > lucky


def test_shrunk_estimate_with_no_exact_match_is_the_role_prior(tmp_path: Path) -> None:
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_SHRUNK)
    route = (WEAK, STRONG, WEAK)  # never observed as a route
    features = ttr._normalize_serving_features({"task_type": "feature", "language": "python"})
    neighbors = model._nearest_neighbors(features)
    choices = [
        model._rank_role(role, neighbors, features, [m])[0]
        for role, m in zip(ttr.ROLE_COLUMNS, route, strict=True)
    ]
    expected = round(sum(c.route_success for c in choices) / len(choices), 6)
    assert _route_success(model, route) == pytest.approx(expected)


def test_shrunk_prior_uses_the_exact_route_success_definition(tmp_path: Path) -> None:
    """Over-budget successes are misses on both sides of the comparison."""
    rows = [_row(STRONG, STRONG, STRONG, success=True, under_budget="false") for _ in range(6)]
    model = _model(tmp_path, rows, ttr.ESTIMATOR_SHRUNK)
    choice = model._rank_role("coder", model._dataset, {}, [STRONG])[0]
    # success under budget 0 -> 0.7 * 0 + 0.3 * score(0.8)
    assert choice.route_success == pytest.approx(0.24)
    # Exact matches and prior agree, so the estimate equals both.
    assert _route_success(model, (STRONG, STRONG, STRONG)) == pytest.approx(0.24)


def test_legacy_state_has_no_estimator_key(tmp_path: Path) -> None:
    """Legacy artifacts keep byte-identical state, so their commitment is unchanged."""
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_LEGACY)
    assert "estimator" not in model.__getstate__()


def test_shrunk_estimator_round_trips_through_pickle(tmp_path: Path) -> None:
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_SHRUNK)
    restored = pickle.loads(pickle.dumps(model))
    assert restored.estimator == ttr.ESTIMATOR_SHRUNK


def test_state_without_estimator_restores_legacy(tmp_path: Path) -> None:
    model = _model(tmp_path, _mixed_history(), ttr.ESTIMATOR_SHRUNK)
    state = model.__getstate__()
    state.pop("estimator")
    restored = ttr.TechnicalTaskRouterModel.__new__(ttr.TechnicalTaskRouterModel)
    restored.__setstate__(state)
    assert restored.estimator == ttr.ESTIMATOR_LEGACY


def test_unknown_estimator_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown estimator"):
        ttr.TechnicalTaskRouterModel(estimator="bayes")
