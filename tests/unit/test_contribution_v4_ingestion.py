"""HOK-3413: the contributions endpoint accepts v4 rows and stores canonical rows."""

from __future__ import annotations

import copy
import json
from collections.abc import Collection
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from src.api.schemas.contribution import ContributionRequest
from src.api.services.contribution_fidelity import FidelityTier, classify_row
from src.api.services.contribution_service import (
    ContributionPersistenceUnavailableError,
    ContributionService,
    StoredContributionRecord,
)
from src.api.services.routing_join import InferenceRecord
from src.model_30.canonical_row import price_row
from src.model_30.model_identity import price_table_version

REPO_ROOT = Path(__file__).resolve().parents[2]
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
CANONICAL_V1_SCHEMA = json.loads(
    (REPO_ROOT / "schema/technical_task_router_row.v1.json").read_text(encoding="utf-8")
)
AUTH = {"user_id": "user-1", "api_key_id": "token-1", "service_id": "svc-1"}


class EmptyLookup:
    def fetch(self, ids: Collection[str]) -> dict[str, InferenceRecord]:
        return {}


class Store:
    def __init__(self, *, fail_canonical: bool = False) -> None:
        self.records: dict[tuple[str, str], StoredContributionRecord] = {}
        self.canonical: dict[str, list[dict[str, Any]]] = {}
        self.fail_canonical = fail_canonical

    def get(self, *, model_id: str, submission_id: str) -> StoredContributionRecord | None:
        return self.records.get((model_id, submission_id))

    def create(self, *, record: StoredContributionRecord) -> StoredContributionRecord:
        self.records[(record.model_id, record.submission_id)] = record
        return record

    def put_canonical_rows(self, *, submission_id: str, rows: list[dict[str, Any]]) -> str:
        if self.fail_canonical:
            raise ContributionPersistenceUnavailableError("s3 down")
        self.canonical[submission_id] = rows
        return f"memory://model_30/canonical/v1/{submission_id}.jsonl"


def fixture(name: str) -> dict[str, Any]:
    return copy.deepcopy(FIXTURES[name])


def _submit(rows: list[dict[str, Any]], store: Store | None = None) -> tuple[Any, Store]:
    store = store or Store()
    service = ContributionService(store=store, inference_log_lookup=EmptyLookup())
    service._get_lifecycle_session_factory = lambda: None  # type: ignore[method-assign]
    accepted = service.accept_contribution(
        model_id="30",
        request=ContributionRequest(rows=rows),
        idempotency_key="k-1",
        auth=AUTH,
    )
    return accepted, store


def test_every_sdk_v4_fixture_is_accepted() -> None:
    accepted, store = _submit([fixture(name) for name in FIXTURES])
    response = accepted.response
    assert response.rows_accepted == len(FIXTURES)
    assert response.rejected_rows == []
    assert response.row_cost_status == [
        "priced",  # singleHarness
        "priced",  # mixedHarness (haiku priced from Hokusai's table)
        "priced",  # challengePrimary
        "unpriced_model",  # challengeChallenger (gpt-5-codex)
        "unpriced_model",  # ciFixRepair
    ]
    assert response.row_fidelity_tiers == [
        "training_eligible",
        "training_eligible",
        "training_eligible",
        "partial",
        "partial",
    ]
    assert response.cost_summary.priced == 3
    assert response.cost_summary.unpriced_model == 2
    assert response.cost_summary.price_table_version == price_table_version()
    (record,) = store.records.values()
    assert record.metadata["canonical_rows"] == {
        "location": "memory://model_30/canonical/v1/k-1.jsonl",
        "count": len(FIXTURES),
    }
    assert [row["canonical_row_id"] for row in store.canonical["k-1"]] == [
        f"k-1:{index}" for index in range(len(FIXTURES))
    ]
    assert all(row["contributor_id"] == "user-1" for row in store.canonical["k-1"])


def test_v4_row_reported_10x_off_trains_on_the_repriced_cost() -> None:
    row = fixture("singleHarness")
    repriced = price_row(row).cost_usd
    row["actual_cost_usd"] = round(10 * row["actual_cost_usd"], 6)
    accepted, store = _submit([row])
    (stored,) = store.records.values()
    (training_row,) = stored.rows
    jsonschema.validate(training_row, CANONICAL_V1_SCHEMA)
    assert training_row["actual_cost_usd"] == pytest.approx(repriced)
    assert training_row["metadata"]["contributor_reported_cost_usd"] == row["actual_cost_usd"]
    (canonical,) = store.canonical["k-1"]
    assert canonical["cost_usd"] == pytest.approx(repriced)
    assert canonical["contributor_reported_cost_usd"] == row["actual_cost_usd"]


def test_unpriced_v4_row_is_partial_not_free() -> None:
    result = classify_row(fixture("challengeChallenger"))
    assert result.tier is FidelityTier.PARTIAL
    assert result.cost is not None and result.cost.cost_usd is None


def test_v3_row_keeps_its_tier_and_is_stored_without_token_evidence() -> None:
    accepted, store = _submit([copy.deepcopy(V3_ROW)])
    assert accepted.response.row_fidelity_tiers == ["training_eligible"]
    assert accepted.response.row_cost_status == ["no_token_evidence"]
    (canonical,) = store.canonical["k-1"]
    assert canonical["cost_status"] == "no_token_evidence"
    assert canonical["success"] is True


def test_legacy_compact_row_gets_no_cost_status_or_canonical_row() -> None:
    legacy = {"inputs": {"task_type": "bugfix"}, "success_under_budget": True}
    accepted, store = _submit([legacy])
    assert accepted.response.row_cost_status == [None]
    assert store.canonical == {}
    (record,) = store.records.values()
    assert "canonical_rows" not in record.metadata


def test_canonical_write_failure_stores_nothing() -> None:
    store = Store(fail_canonical=True)
    with pytest.raises(ContributionPersistenceUnavailableError):
        _submit([fixture("singleHarness")], store=store)
    assert store.records == {}


def _mutated(mutate: Any) -> dict[str, Any]:
    row = fixture("singleHarness")
    mutate(row)
    return row


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (
            _mutated(lambda r: r["stage_executions"][1].update(executed_model="claude-opus-4-8")),
            "the last coding stage's executed_model must equal selected_models.coder",
        ),
        (
            _mutated(lambda r: r["stage_executions"][0]["task_cost"].update(cwd="/home/me")),
            "forbidden field at stage_executions[0].task_cost.cwd",
        ),
        (
            _mutated(lambda r: r["stage_executions"][0]["task_cost"].update(task_id="other")),
            "stage_executions[0].task_cost.task_id must equal the row's task_id",
        ),
        (
            _mutated(lambda r: r["stage_executions"][0].update(model_evidence="guess")),
            "stage_executions[0].model_evidence must be one of",
        ),
        (
            _mutated(lambda r: r.update(stage_executions=[])),
            "stage_executions must be a non-empty array",
        ),
        (
            _mutated(lambda r: r.update(comparison_group={"id": "pair-1", "role_varied": "coder"})),
            "comparison_group.id must be a minted pair id",
        ),
        (
            _mutated(lambda r: r.update(integration={"merged": True})),
            "integration is reserved",
        ),
        (
            _mutated(
                lambda r: r["stage_executions"][0]["task_cost"]["model_segments"][0][
                    "usage"
                ].update(input_tokens=-5)
            ),
            "usage.input_tokens must be a count or null",
        ),
    ],
)
def test_invalid_stage_executions_are_rejected(row: dict[str, Any], reason: str) -> None:
    result = classify_row(row)
    assert result.tier is FidelityTier.INVALID
    assert result.reason is not None
    assert result.reason.startswith("invalid_stage_executions:")
    assert reason in result.reason
