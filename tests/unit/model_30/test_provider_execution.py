"""Provider charges and attribution survive canonical intake and repricing."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.api.services.contribution_fidelity import stage_execution_errors
from src.api.services.routing_join import (
    resolve_routing_joins,
    routing_outcome_from_row,
)
from src.model_30.canonical_row import build_canonical_row, price_stage


def row():
    """Adapt an SDK-published valid row without using the implementation as an oracle."""
    fixture = (
        Path(__file__).resolve().parents[3]
        / "tests/fixtures/contribution_v4/sdk_contribution_v4_fixtures.v1.json"
    )
    value = copy.deepcopy(json.loads(fixture.read_text())["fixtures"]["singleHarness"])
    stage = value["stage_executions"][0]
    value["stage_executions"] = [stage]
    stage["harness"] = stage["task_cost"]["harness"] = "native"
    stage["task_cost"]["turn_count"] = 2
    session = stage["task_cost"]["session_ids"][0]
    stage["provider_executions"] = [
        {
            "sessionRef": session,
            "ownershipAttemptIds": ["attempt"],
            "responseId": f"response-{index}",
            "transport": "openrouter",
            "requestedModel": stage["executed_model"],
            "responseModel": stage["executed_model"],
            "generation": {"providerName": host, "totalCostUsd": charge},
            "usage": {
                "input_tokens": 100000,
                "output_tokens": 10000,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": None,
            },
            "pricingSnapshot": {
                "scope": "endpoint",
                "inputCostPerMTok": 0.2,
                "outputCostPerMTok": 1,
            },
        }
        for index, (host, charge) in enumerate([("Host A", 0.25), ("Host B", 0)])
    ]
    return value


def test_billed_zero_and_actual_charges_are_not_replaced_by_reference_prices():
    value = row()
    stage = value["stage_executions"][0]
    assert stage_execution_errors(value) == []
    cost = price_stage(stage)
    assert cost.cost_usd == 0.25
    assert cost.execution_evidence["billing_coverage"] == "complete"
    assert cost.execution_evidence["cost_basis"] == "provider_reported"
    canonical = build_canonical_row(
        value,
        submission_id="sub",
        row_index=0,
        fidelity_tier="training_eligible",
        routing_join=None,
        contributor_id="test",
    )
    assert canonical["cost_usd"] == 0.25
    assert canonical["execution_evidence"][0]["provider_executions"] == stage["provider_executions"]


def test_partial_billing_prices_only_the_unbilled_turn_at_its_endpoint_rates():
    value = row()
    stage = value["stage_executions"][0]
    stage["provider_executions"][1]["generation"] = None
    cost = price_stage(stage)
    assert cost.cost_usd == pytest.approx(0.28)
    assert cost.execution_evidence["billed_cost_usd"] == 0.25
    assert cost.execution_evidence["billing_coverage"] == "partial"
    assert cost.execution_evidence["cost_basis"] == "mixed"


def test_non_model_failure_is_kept_without_becoming_a_negative_quality_label():
    value = row()
    stage = value["stage_executions"][0]
    stage["failure"] = {"fault_class": "harness-fault"}
    value["completion_result"] = "failure"
    assert stage_execution_errors(value) == []
    canonical = build_canonical_row(
        value,
        submission_id="sub",
        row_index=0,
        fidelity_tier="partial",
        routing_join=None,
        contributor_id="test",
    )
    assert canonical["success"] is None
    assert canonical["cost_usd"] == 0.25
    assert canonical["execution_evidence"][0]["failure"] == stage["failure"]
    stage["failure"]["fault_class"] = "made-up-fault"
    assert stage_execution_errors(value)


def test_private_or_duplicate_evidence_is_rejected():
    value = row()
    records = value["stage_executions"][0]["provider_executions"]
    records.append(copy.deepcopy(records[0]))
    assert any("duplicate provider response" in item for item in stage_execution_errors(value))
    records.pop()
    records[0]["generation"]["prompt"] = "private"
    assert stage_execution_errors(value)


def test_missing_usage_and_billing_remain_unknown_instead_of_a_zero_total():
    value = row()
    stage = value["stage_executions"][0]
    stage["provider_executions"][1]["generation"] = None
    stage["provider_executions"][1].pop("usage")
    cost = price_stage(stage)
    assert cost.cost_usd is None
    assert cost.execution_evidence["billed_cost_usd"] == 0.25


def test_real_wavemill_producer_replay_survives_intake_and_canonical_storage():
    """The same wire bytes are generated/checked by Wavemill's SDK builder test."""
    fixture = (
        Path(__file__).resolve().parents[3]
        / "tests/fixtures/contribution_v4/provider_execution_replay.json"
    )
    value = json.loads(fixture.read_text())
    assert stage_execution_errors(value) == []
    routing_join = resolve_routing_joins(
        [routing_outcome_from_row(value)], api_token_id=None, lookup=None
    )[0].to_dict()
    canonical = build_canonical_row(
        value,
        submission_id="provider-replay",
        row_index=0,
        fidelity_tier="partial",
        routing_join=routing_join,
        contributor_id="test",
    )
    assert canonical["cost_usd"] == 0.02
    assert canonical["routing_join"]["inference_log_id"] == "replay-routing-decision"
    assert (
        canonical["execution_evidence"][0]["provider_executions"]
        == value["stage_executions"][0]["provider_executions"]
    )
    for fault in [
        "harness-fault",
        "provider-fault",
        "unknown-fault",
        "selection-fault",
    ]:
        value["stage_executions"][0]["failure"] = {"fault_class": fault}
        canonical = build_canonical_row(
            value,
            submission_id="provider-replay",
            row_index=0,
            fidelity_tier="partial",
            routing_join=None,
            contributor_id="test",
        )
        assert canonical["success"] is None
        assert canonical["cost_usd"] == 0.02
