"""HOK-3427: Model 30 serves the native models Wavemill is about to offer.

Wavemill will put certified OpenRouter models in its per-stage pools (HOK-3429).
Serving must resolve every spelling Wavemill sends, for every role, and the price
table baked into a registered model must price each one; an unknown or unpriced
id is dropped from the pool or never surfaces for lowest_cost.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.api.endpoints import model_30_adapter
from src.model_30 import model_identity
from src.models import technical_task_router as ttr

# Wavemill spelling -> Model 30 public id.
NATIVE_MODELS = {
    "kimi-k3": "kimi-k3",
    "kimi-k3.1-pro": "kimi-k3.1-pro",
    "kimi-k2.7-code": "kimi-k2.7-code",
    "glm-5.3": "glm-5.3",
    "glm-5.3-flash": "glm-5.3-flash",
    "qwen-3-coder": "qwen3-coder",
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
}
PROVIDER_IDS = {
    "moonshotai/kimi-k3": "kimi-k3",
    "moonshotai/kimi-k3.1-pro": "kimi-k3.1-pro",
    "z-ai/glm-5.3": "glm-5.3",
    "z-ai/glm-5.3-flash": "glm-5.3-flash",
    "qwen/qwen3-coder": "qwen3-coder",
}
ROLES = ("planner", "coder", "reviewer")
FRONTIER = "claude-opus-4-7"


def _inputs(pool: list[str], role: str | None = None, objective: str = "lowest_cost") -> dict:
    routing: dict = {"objective": objective, "max_cost_usd": 25}
    if role is None:
        routing["available_models"] = pool
    else:
        routing[f"available_{role}_models"] = pool
    return {
        "task": {"description": "Add retry handling to the webhook worker", "task_type": "feature"},
        "routing": routing,
    }


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    ("spelling", "public_id"), sorted({**NATIVE_MODELS, **PROVIDER_IDS}.items())
)
def test_every_native_spelling_resolves_for_every_role(
    spelling: str, public_id: str, role: str
) -> None:
    validated = model_30_adapter.validate_nested_model_30_inputs(_inputs([spelling], role))
    row = model_30_adapter.model_30_inputs_to_features(validated).iloc[0]

    assert row[f"available_{role}_models"] == [public_id]


@pytest.mark.parametrize("public_id", sorted(set(NATIVE_MODELS.values())))
def test_registration_price_table_prices_every_native_model(public_id: str) -> None:
    # The table ``build_router_corpus.py --prices-output`` writes for ``--router-prices``.
    table = model_identity.build_price_table([])

    price = table.get(public_id)
    assert price is not None, f"{public_id} would have no baked price, so lowest_cost never sees it"
    assert price["input_per_token"] and price["output_per_token"]


def _router(tmp_path: Path) -> ttr.TechnicalTaskRouterModel:
    """A router trained on frontier-only history, priced like a real registration."""
    rows = [
        {
            "task_type": "feature",
            "language": "python",
            "domain": "backend",
            "complexity": 3,
            "max_cost_usd": 25,
            "available_planner_models": json.dumps([FRONTIER]),
            "available_coder_models": json.dumps([FRONTIER]),
            "available_reviewer_models": json.dumps([FRONTIER]),
            "planner_model": FRONTIER,
            "coder_model": FRONTIER,
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
            "aux_cost_usd": 0.0,
        }
        for i in range(8)
    ]
    dataset = tmp_path / "router.csv"
    pd.DataFrame(rows).to_csv(dataset, index=False)
    prices = tmp_path / "prices.json"
    prices.write_text(
        json.dumps(
            {
                "schema_version": "model_30_router_model_prices/v1",
                "prices": model_identity.build_price_table([]),
            }
        )
    )
    model = ttr.TechnicalTaskRouterModel(k_neighbors=8)
    model.load_context(
        type(
            "C",
            (),
            {
                "artifacts": {
                    ttr.ROUTER_DATASET_ARTIFACT: str(dataset),
                    ttr.ROUTER_PRICES_ARTIFACT: str(prices),
                }
            },
        )()
    )
    return model


@pytest.mark.parametrize("objective", ["lowest_cost", "highest_reliability"])
def test_pool_of_wavemill_native_models_predicts_end_to_end(tmp_path: Path, objective: str) -> None:
    pool = [FRONTIER, *NATIVE_MODELS]
    validated = model_30_adapter.validate_nested_model_30_inputs(_inputs(pool, objective=objective))
    features = model_30_adapter.model_30_inputs_to_features(validated)

    strategy = _router(tmp_path).predict(None, features).iloc[0]["recommended_strategy"]

    assert strategy["objective"] == objective
    assert strategy["estimated_cost_usd"] > 0
    if objective == "lowest_cost":
        chosen = {strategy["planner_model"], strategy["coder_model"], strategy["reviewer_model"]}
        assert chosen & set(NATIVE_MODELS.values()), chosen
