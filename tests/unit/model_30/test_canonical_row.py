"""HOK-3413: canonical Model 30 rows reprice v4 contributions from tokens."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.model_30.executed_route import route_economics
from src.model_30 import canonical_row as cr
from src.model_30.model_identity import (
    hokusai_price_snapshot,
    price_table_version,
    resolve_price,
)
from src.model_30.usage_cost import price_usage_by_model, usage_from_task_cost_segments

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads(
    (REPO_ROOT / "tests/fixtures/contribution_v4/sdk_contribution_v4_fixtures.v1.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]
V3_ROW = json.loads(
    (REPO_ROOT / "tests/fixtures/routing_outcome/sdk_routing_outcome_fixtures.v1.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]["followedRecommendation"]


def fixture(name: str) -> dict[str, Any]:
    return copy.deepcopy(FIXTURES[name])


def _independent_cost(row: dict[str, Any]) -> float:
    total = 0.0
    for stage in row["stage_executions"]:
        usage = usage_from_task_cost_segments(stage["task_cost"]["model_segments"])
        priced = price_usage_by_model(usage, hokusai_price_snapshot(), reprice="always")
        total += sum(bucket["cost"] for bucket in priced.per_model.values())
    return total


def _build(row: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "submission_id": "sub-1",
        "row_index": 0,
        "fidelity_tier": "training_eligible",
        "routing_join": None,
        "contributor_id": "user-1",
    }
    kwargs.update(overrides)
    return cr.build_canonical_row(row, **kwargs)


def test_reported_cost_is_evidence_and_cost_comes_from_tokens() -> None:
    row = fixture("singleHarness")
    row["actual_cost_usd"] = 10 * row["actual_cost_usd"]
    record = _build(row)
    assert record["cost_status"] == cr.COST_PRICED
    assert record["cost_usd"] == pytest.approx(_independent_cost(row))
    assert record["contributor_reported_cost_usd"] == row["actual_cost_usd"]
    assert record["cost_usd"] != pytest.approx(record["contributor_reported_cost_usd"])
    assert record["price_table_version"] == price_table_version()


def test_roles_carry_executed_model_tokens_and_cost() -> None:
    record = _build(fixture("singleHarness"))
    coder = record["roles"]["coder"]
    assert coder["executed_model"] == "claude-sonnet-5"
    assert coder["model_evidence"] == "session_telemetry"
    assert coder["harness"] == "claude-code"
    # The coding stage switched opus -> sonnet: both segments' tokens count.
    assert coder["tokens"] == {
        "input": 10000.0,
        "output": 3900.0,
        "cache_read": 0.0,
        "cache_write": 0.0,
    }
    assert sum(role["cost_usd"] for role in record["roles"].values()) == pytest.approx(
        record["cost_usd"]
    )


def test_v3_row_has_no_token_evidence_but_keeps_its_outcome() -> None:
    record = _build(V3_ROW)
    assert record["cost_status"] == cr.COST_NO_TOKEN_EVIDENCE
    assert record["cost_usd"] is None
    assert record["success"] is True
    assert record["contributor_reported_cost_usd"] == V3_ROW["actual_cost_usd"]
    assert {role["cost_status"] for role in record["roles"].values()} == {cr.COST_NO_TOKEN_EVIDENCE}


def test_unknown_model_is_unpriced_never_free() -> None:
    record = _build(fixture("challengeChallenger"))  # coder: gpt-5-codex, not priced
    assert record["cost_status"] == cr.COST_UNPRICED_MODEL
    assert record["cost_usd"] is None
    assert record["roles"]["coder"]["cost_usd"] is None
    assert record["unpriced_models"] == ["gpt-5-codex"]
    assert record["roles"]["reviewer"]["cost_status"] == cr.COST_PRICED


def test_partial_coverage_is_a_lower_bound_not_a_cost() -> None:
    row = fixture("singleHarness")
    row["stage_executions"][0]["task_cost"]["coverage"] = "partial"
    record = _build(row)
    assert record["cost_status"] == cr.COST_COVERAGE_PARTIAL
    assert record["cost_usd"] is None
    assert record["roles"]["planner"]["cost_status"] == cr.COST_COVERAGE_PARTIAL


def test_unmeasured_stage_has_no_token_evidence() -> None:
    row = fixture("singleHarness")
    task_cost = row["stage_executions"][2]["task_cost"]
    task_cost.update(coverage="unavailable", model_segments=[])
    record = _build(row)
    assert record["roles"]["reviewer"]["cost_status"] == cr.COST_NO_TOKEN_EVIDENCE
    assert record["cost_status"] == cr.COST_NO_TOKEN_EVIDENCE


def test_requested_only_evidence_never_counts_as_execution() -> None:
    row = fixture("singleHarness")
    row["stage_executions"][1]["model_evidence"] = "requested_only"
    coder = _build(row)["roles"]["coder"]
    assert coder["executed_model"] is None
    assert coder["requested_model"] == "claude-sonnet-5"
    assert coder["model_evidence"] == "requested_only"


def test_repair_stage_is_kept_and_counted_in_the_total() -> None:
    row = fixture("ciFixRepair")
    record = _build(row)
    (repair,) = record["repair_stages"]
    assert repair["stage"] == "ci-fix"
    assert repair["executed_model"] == "gpt-5-codex"
    assert set(record["roles"]) == {"coder", "reviewer"}


def test_comparison_group_and_source_are_carried() -> None:
    record = _build(fixture("challengePrimary"))
    assert record["comparison_group"] == {
        "id": "01a1a6d0-0000-7000-8000-000000000001",
        "role_varied": "coder",
    }
    assert record["source"] == {"kind": "contribution", "harness": "wavemill", "sdk_version": None}


def test_haiku_is_priced_server_side_at_its_v10_training_rate() -> None:
    """Models v10 priced only from Wavemill record snapshots need Hokusai's own rate."""
    price = resolve_price("claude-haiku-4-5", hokusai_price_snapshot())
    assert price is not None
    assert price.input_per_token == pytest.approx(0.8e-6)
    assert price.cache_read_per_token == pytest.approx(0.08e-6)
    assert price.source == "record_pricing_snapshot"


def test_server_pricing_equals_the_collector_on_the_same_usage() -> None:
    """One pricing implementation: the collector's ``route_economics`` agrees."""
    row = fixture("singleHarness")
    stage = row["stage_executions"][1]
    usage = usage_from_task_cost_segments(stage["task_cost"]["model_segments"])
    record = {"workflowTokenUsage": usage, "pricingSnapshot": hokusai_price_snapshot()}
    route = {"planner": "claude-opus-4-8", "coder": "claude-sonnet-5", "reviewer": "none"}
    collector = route_economics(record, route)
    assert collector.total_cost_usd == pytest.approx(cr.price_stage(stage).cost_usd)


def test_canonical_rows_have_no_pricing_of_their_own() -> None:
    source = inspect.getsource(cr)
    assert "price_usage_by_model(" in source
    for private_pricing in ("priced_usage_cost", "resolve_price", "input_per_token"):
        assert private_pricing not in source
