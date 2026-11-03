"""HOK-3401: token-price cost, cheap lowest_cost candidates, 60% floor, exploration flag."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.models import technical_task_router as ttr

FRONTIER = "claude-opus-4-7"
CODER = "gpt-5.4"
CHEAP = "deepseek-v4-flash"


def _dataset(tmp_path: Path) -> Path:
    rows = []
    for i in range(8):
        rows.append(
            {
                "task_type": "feature",
                "language": "python",
                "domain": "backend",
                "complexity": 3,
                "max_cost_usd": 25,
                "available_planner_models": json.dumps([FRONTIER, CODER]),
                "available_coder_models": json.dumps([FRONTIER, CODER]),
                "available_reviewer_models": json.dumps([FRONTIER, CODER]),
                "planner_model": FRONTIER,
                "coder_model": CODER,
                "reviewer_model": FRONTIER,
                "completed_successfully": "true" if i % 4 else "false",
                "score": 0.85,
                "under_budget": "true",
                "actual_cost_usd": 12.0 + i,
                "planner_input_tokens": 1000,
                "planner_cache_tokens": 0,
                "planner_output_tokens": 500,
                "coder_input_tokens": 200_000,
                "coder_cache_tokens": 1_000_000,
                "coder_output_tokens": 30_000,
                "reviewer_input_tokens": 100_000,
                "reviewer_cache_tokens": 0,
                "reviewer_output_tokens": 5_000,
                "aux_cost_usd": 1.0,
            }
        )
    path = tmp_path / "router.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _prices(tmp_path: Path) -> Path:
    prices = {
        FRONTIER: {
            "input_per_token": 5e-6,
            "output_per_token": 25e-6,
            "cache_read_per_token": 0.5e-6,
        },
        CODER: {
            "input_per_token": 2.5e-6,
            "output_per_token": 15e-6,
            "cache_read_per_token": 0.25e-6,
        },
        CHEAP: {"input_per_token": 0.1e-6, "output_per_token": 0.2e-6},
    }
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps({"schema_version": "model_30_router_model_prices/v1", "prices": prices})
    )
    return path


def _model(tmp_path: Path, *, prices: bool) -> ttr.TechnicalTaskRouterModel:
    artifacts = {ttr.ROUTER_DATASET_ARTIFACT: str(_dataset(tmp_path))}
    if prices:
        artifacts[ttr.ROUTER_PRICES_ARTIFACT] = str(_prices(tmp_path))
    model = ttr.TechnicalTaskRouterModel(k_neighbors=8)
    model.load_context(type("C", (), {"artifacts": artifacts})())
    return model


def _features(objective: str) -> pd.DataFrame:
    pool = json.dumps([FRONTIER, CODER, CHEAP])
    return pd.DataFrame(
        [
            {
                "schema_version": "technical_task_router_inputs/v2",
                "task_descriptor": "{}",
                "task_description": "add an endpoint",
                "task_type": "feature",
                "language": "python",
                "domain": "backend",
                "allowed_models": pool,
                "available_planner_models": pool,
                "available_coder_models": pool,
                "available_reviewer_models": pool,
                "max_cost_usd": 100.0,
                "workflow_stages": '["plan","code","review"]',
                "routing_objective": objective,
            }
        ]
    )


def _strategy(model, objective: str) -> dict:
    return model.predict(None, _features(objective)).iloc[0]["recommended_strategy"]


def test_lowest_cost_recommends_cheap_model_when_priced(tmp_path: Path) -> None:
    strategy = _strategy(_model(tmp_path, prices=True), "lowest_cost")
    assert CHEAP in {strategy["coder_model"], strategy["reviewer_model"]}
    assert "Exploratory" in strategy["rationale"]
    assert strategy["estimated_success_under_budget"] >= ttr.LOWEST_COST_SUCCESS_FLOOR
    evidence = strategy["role_evidence"]
    assert any(e.get("exploratory") for e in evidence.values())


def test_without_prices_cheap_models_are_not_added(tmp_path: Path) -> None:
    strategy = _strategy(_model(tmp_path, prices=False), "lowest_cost")
    assert CHEAP not in {
        strategy["planner_model"],
        strategy["coder_model"],
        strategy["reviewer_model"],
    }


def test_floor_blocks_cheap_route_when_prior_is_below_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ttr, "EXPLORATION_SUCCESS_PRIOR", 0.2)
    strategy = _strategy(_model(tmp_path, prices=True), "lowest_cost")
    # The floor is route-level: a route may keep one low-prior cheap role if the
    # whole route still clears 60%, but a cheap coder (with an equally cheap
    # reviewer) would fall below it and must not be chosen.
    assert strategy["estimated_success_under_budget"] >= ttr.LOWEST_COST_SUCCESS_FLOOR
    assert not (strategy["coder_model"] == CHEAP and strategy["reviewer_model"] == CHEAP)


def test_token_price_cost_is_sum_of_role_tokens_times_price(tmp_path: Path) -> None:
    model = _model(tmp_path, prices=True)
    features = ttr._normalize_serving_features_with_counts(
        _features("lowest_cost").iloc[0].to_dict()
    ).features
    neighbors = model._nearest_neighbors(features)
    coder_cost = model._price_role_cost("coder", CHEAP, neighbors)
    # 200k input x 0.1e-6 + 1M cache x (0.1 x 0.1e-6 fallback) + 30k output x 0.2e-6
    assert coder_cost == pytest.approx(200_000 * 0.1e-6 + 1_000_000 * 0.01e-6 + 30_000 * 0.2e-6)


def test_highest_reliability_is_unaffected_by_cheap_candidates(tmp_path: Path) -> None:
    with_prices = _strategy(_model(tmp_path, prices=True), "highest_reliability")
    without = _strategy(_model(tmp_path, prices=False), "highest_reliability")
    assert with_prices["coder_model"] == without["coder_model"]


def test_price_state_survives_pickling(tmp_path: Path) -> None:
    import cloudpickle

    model = _model(tmp_path, prices=True)
    restored = cloudpickle.loads(cloudpickle.dumps(model))
    assert restored._prices == model._prices


def test_single_aux_outlier_does_not_inflate_token_priced_routes(tmp_path: Path) -> None:
    """One neighbor with a large aux cost must not add it to every priced route."""
    model = _model(tmp_path, prices=True)
    features = ttr._normalize_serving_features_with_counts(
        _features("lowest_cost").iloc[0].to_dict()
    ).features
    neighbors = model._nearest_neighbors(features).copy()
    neighbors["aux_cost_usd"] = [21.8] + [None] * (len(neighbors) - 1)
    # Fewer than MIN_TOKEN_PROFILE_ROWS aux values: fall back to the dataset median ($1).
    assert model._typical_aux_cost(neighbors) == pytest.approx(1.0)
    choices = {
        role: model._evidence_or_prior_choice(role, CHEAP, neighbors, features)
        for role in ("planner", "coder", "reviewer")
    }
    route_cost = model._price_route_cost(choices, neighbors)
    token_cost = sum(model._price_role_cost(r, CHEAP, neighbors) for r in choices)
    assert route_cost == pytest.approx(token_cost + 1.0, abs=1e-6)


def test_token_profile_memo_is_per_neighbors_object(tmp_path: Path) -> None:
    """The memo must not serve one request's profile to another (id() reuse)."""
    model = _model(tmp_path, prices=True)
    features = ttr._normalize_serving_features_with_counts(
        _features("lowest_cost").iloc[0].to_dict()
    ).features
    first = model._nearest_neighbors(features).copy()
    assert model._role_token_profile("coder", first)[0] == pytest.approx(200_000)
    del first
    second = model._nearest_neighbors(features).copy()
    second["coder_input_tokens"] = 50_000
    assert model._role_token_profile("coder", second)[0] == pytest.approx(50_000)
