"""HOK-3401: catalog-based model identity, executed-route resolution, token repricing."""

from __future__ import annotations

import pytest

from scripts.model_30.executed_route import resolve_executed_route, route_economics
from src.model_30.model_identity import (
    is_junk_model_id,
    is_supported_model_id,
    model_family,
    normalize_model_id,
    resolve_price,
)

STAGES = {"planner": "claude-opus-4-7", "coder": "gpt-5.4", "reviewer": "claude-opus-4-7"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("openrouter:moonshotai/kimi-k2.7-code", "kimi-k2.7-code"),
        ("moonshotai/kimi-k2.7-code", "kimi-k2.7-code"),
        ("qwen-3-coder", "qwen3-coder"),
        ("qwen/qwen3-coder", "qwen3-coder"),
        ("z-ai/glm-5.2", "glm-5.2"),
        ("claude-opus-4-7", "claude-opus-4-7"),
    ],
)
def test_normalize_model_id(raw: str, expected: str) -> None:
    assert normalize_model_id(raw) == expected


@pytest.mark.parametrize(
    "model_id",
    [
        "kimi-k2.7-code",
        "qwen3-coder",
        "glm-5.3-flash",
        "deepseek-v4-flash",
        "gpt-5.5",
        "claude-haiku-4-5",
    ],
)
def test_cheap_and_frontier_families_are_supported(model_id: str) -> None:
    """The former vendor allow-list dropped Kimi/Qwen/GLM; they must now pass."""
    assert is_supported_model_id(model_id)
    assert model_family(model_id)


@pytest.mark.parametrize(
    "model_id", ["<synthetic>", "scripted:launch-planning-success-1", "deep", "", None]
)
def test_junk_ids_are_rejected(model_id) -> None:
    assert is_junk_model_id(model_id)
    assert not is_supported_model_id(model_id)


def test_price_resolution_prefers_record_snapshot_then_falls_back() -> None:
    snapshot = {"qwen3-coder": {"inputCostPerMTok": 0.35, "outputCostPerMTok": 1.05}}
    from_snapshot = resolve_price("qwen/qwen3-coder", snapshot)
    assert from_snapshot is not None and from_snapshot.source == "record_pricing_snapshot"
    assert from_snapshot.input_per_token == pytest.approx(0.35e-6)
    fallback = resolve_price("openrouter:moonshotai/kimi-k2.7-code")
    assert fallback is not None and fallback.input_per_token > 0


def test_unpriced_tokens_are_repriced_not_free() -> None:
    record = {
        "workflowTokenUsage": {
            "openrouter:moonshotai/kimi-k2.7-code": {
                "inputTokens": 1_000_000,
                "outputTokens": 100_000,
                "costUsd": 0,
            },
            "gpt-5.4": {"inputTokens": 10, "outputTokens": 10, "costUsd": 2.5},
        }
    }
    econ = route_economics(
        record, {"planner": "gpt-5.4", "coder": "kimi-k2.7-code", "reviewer": "gpt-5.4"}
    )
    assert econ.cost_status == "repriced"
    assert econ.total_cost_usd is not None and econ.total_cost_usd > 2.5
    assert econ.role_cost_usd["coder"] > 0
    assert "kimi-k2.7-code" in econ.repriced_models


def test_model_with_no_price_anywhere_is_unknown_cost() -> None:
    record = {
        "workflowTokenUsage": {
            "devstral-small": {"inputTokens": 100, "outputTokens": 10, "costUsd": 0}
        }
    }
    econ = route_economics(
        record,
        {"planner": "devstral-small", "coder": "devstral-small", "reviewer": "devstral-small"},
    )
    assert econ.cost_status == "unpriced_model"
    assert econ.total_cost_usd is None


def test_valid_execution_evidence_overrides_stage_route() -> None:
    record = {
        "challengePairId": "HOK-1",
        "challengeExecutionEvidence": {
            "validity": "valid",
            "effectiveRoute": {
                "planner": "claude-opus-4-7",
                "coder": "glm-5.2",
                "reviewer": "claude-opus-4-7",
            },
        },
    }
    res = resolve_executed_route(record, STAGES)
    assert res.route["coder"] == "glm-5.2"
    assert res.source == "challenge_execution_evidence"
    assert res.exclusion_reason is None


def test_invalid_challenge_is_excluded() -> None:
    res = resolve_executed_route({"challengePairId": "HOK-1", "invalidChallenge": True}, STAGES)
    assert res.exclusion_reason == "invalid_challenge"


def test_challenger_side_inferred_from_tokens_corrects_route() -> None:
    records = {"HOK-2": {"primaryModel": "gpt-5.4", "challengerModel": "glm-5.3"}}
    record = {
        "challengePairId": "HOK-2",
        "challengeStage": "implementation",
        "workflowTokenUsage": {"z-ai/glm-5.3": {"inputTokens": 5, "outputTokens": 5}},
    }
    res = resolve_executed_route(record, STAGES, records)
    assert res.route["coder"] == "glm-5.3"
    assert res.source == "challenge_record_challenger_corrected"


def test_same_model_challenge_with_foreign_tokens_is_ambiguous() -> None:
    """gpt-5.5 -> gpt-5.5 records with Qwen tokens: executor unknown, so exclude."""
    records = {"HOK-3": {"primaryModel": "gpt-5.5", "challengerModel": "gpt-5.5"}}
    record = {
        "challengePairId": "HOK-3",
        "workflowTokenUsage": {"qwen/qwen3-coder": {"inputTokens": 15000, "outputTokens": 18}},
    }
    stages = {"planner": "claude-opus-4-7", "coder": "gpt-5.5", "reviewer": "claude-opus-4-7"}
    res = resolve_executed_route(record, stages, records)
    assert res.exclusion_reason == "ambiguous_challenge_route"


def test_same_model_challenge_without_foreign_tokens_keeps_stage_route() -> None:
    records = {"HOK-4": {"primaryModel": "gpt-5.5", "challengerModel": "gpt-5.5"}}
    record = {
        "challengePairId": "HOK-4",
        "workflowTokenUsage": {"gemini-2.5-pro": {"inputTokens": 1, "outputTokens": 1}},
    }
    stages = {"planner": "claude-opus-4-7", "coder": "gpt-5.5", "reviewer": "claude-opus-4-7"}
    res = resolve_executed_route(record, stages, records)
    assert res.exclusion_reason is None
    assert res.route["coder"] == "gpt-5.5"


def test_challenge_partner_spend_is_split_out_of_route_cost() -> None:
    """HOK-3404: the other challenge arm is not this route's cost; sub-agents are."""
    from scripts.model_30.executed_route import challenge_partner_models

    route = {"planner": "claude-opus-4-7", "coder": "gpt-5.4", "reviewer": "claude-sonnet-4-6"}
    record = {
        "challengePairId": "HOK-5",
        "workflowTokenUsage": {
            "claude-opus-4-7": {"inputTokens": 10, "outputTokens": 10, "costUsd": 1.0},
            "gpt-5.4": {"inputTokens": 10, "outputTokens": 20875, "costUsd": 13.75},
            "claude-sonnet-4-6": {"inputTokens": 10, "outputTokens": 10, "costUsd": 0.5},
            "gpt-5.5": {"inputTokens": 10, "outputTokens": 13017, "costUsd": 21.83},
            "claude-fable-5": {"inputTokens": 10, "outputTokens": 10, "costUsd": 2.0},
        },
    }
    pairs = {"HOK-5": {"primaryModel": "gpt-5.4", "challengerModel": "gpt-5.5"}}
    partners = challenge_partner_models(record, route, pairs)
    assert partners == {"gpt-5.5"}
    econ = route_economics(record, route, partners)
    assert econ.challenge_partner_cost_usd == pytest.approx(21.83)
    assert econ.subagent_cost_usd == pytest.approx(2.0)
    assert econ.aux_cost_usd == pytest.approx(23.83)
    assert econ.total_cost_usd == pytest.approx(1.0 + 13.75 + 0.5 + 2.0)


def test_partner_from_challenge_intent_and_never_a_route_model() -> None:
    from scripts.model_30.executed_route import challenge_partner_models

    route = {"planner": "claude-opus-4-7", "coder": "glm-5.3", "reviewer": "claude-opus-4-7"}
    record = {
        "challengePairId": "HOK-6",
        "challengeIntent": {
            "primary": {"expectedRoute": {**route, "coder": "gpt-5.5"}},
            "challenger": {"expectedRoute": route},
        },
    }
    assert challenge_partner_models(record, route) == {"gpt-5.5"}
    assert challenge_partner_models({"workflowTokenUsage": {}}, route) == set()


def test_non_challenge_aux_is_all_subagent() -> None:
    haiku = normalize_model_id("claude-haiku-4-5")
    route = {"planner": "claude-opus-4-7", "coder": haiku, "reviewer": "gpt-5.4"}
    record = {
        "workflowTokenUsage": {
            "claude-haiku-4-5": {"inputTokens": 10, "outputTokens": 408, "costUsd": 0.02},
            "claude-opus-4-6": {"inputTokens": 10, "outputTokens": 10, "costUsd": 9.26},
        }
    }
    econ = route_economics(record, route)
    assert econ.challenge_partner_cost_usd == 0.0
    assert econ.subagent_cost_usd == pytest.approx(9.26)
    assert econ.total_cost_usd == pytest.approx(9.28)
