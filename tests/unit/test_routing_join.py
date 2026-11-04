"""HOK-3365: one outcome-to-inference join, and the evidence split it drives.

Fixtures are the SDK's golden routing-outcome rows (HOK-3364), copied verbatim
into ``tests/fixtures/routing_outcome``. They reproduce the 2026-10-30
incident shapes: HOK-3315 (challenge program ran haiku instead of the
recommended opus) and HOK-3329 (Wavemill escalation ran glm instead of the
recommended haiku at confidence 0.334).
"""

from __future__ import annotations

import ast
import copy
import json
from collections.abc import Collection
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from scripts.model_30.assemble_training_set import attach_routing_join
from scripts.model_30.routing_feedback_report import build_routing_feedback_report
from src.api.schemas.contribution import ContributionRequest
from src.api.schemas.inference_log import OutcomeSubmission
from src.api.services.contribution_fidelity import FidelityTier, classify_row
from src.api.services.contribution_service import ContributionService, StoredContributionRecord
from src.api.services.contributor_logger import ContributorLogger
from src.api.services.routing_join import (
    EvidenceClass,
    InferenceRecord,
    LinkStatus,
    resolve_routing_joins,
    routing_outcome_from_row,
)
from src.evaluation.scorers.builtin import (
    _task_router_benchmark_score_v2,
    _task_router_success_under_budget,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads(
    (REPO_ROOT / "tests/fixtures/routing_outcome/sdk_routing_outcome_fixtures.v1.json").read_text(
        encoding="utf-8"
    )
)["fixtures"]

TOKEN = "22222222-2222-2222-2222-222222222222"
AUTH = {"user_id": "u-1", "api_key_id": TOKEN, "service_id": None}

# What Model 30 recommended for each routed fixture, as its inference log holds it.
LOG_RECOMMENDATIONS: dict[str, tuple[dict[str, str], float]] = {
    "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a70": (
        {
            "planner": "claude-sonnet-4-6",
            "coder": "claude-sonnet-4-6",
            "reviewer": "claude-sonnet-4-6",
        },
        0.82,
    ),
    # HOK-3329: haiku at confidence 0.334; escalation ran glm.
    "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a71": (
        {"coder": "claude-haiku-4-5", "reviewer": "claude-sonnet-4-6"},
        0.334,
    ),
    # HOK-3315: opus; the challenge program ran haiku.
    "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a72": (
        {"coder": "claude-opus-4-7", "reviewer": "claude-sonnet-4-6"},
        0.71,
    ),
    "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a73": (
        {"coder": "claude-sonnet-4-6", "reviewer": "claude-haiku-4-5"},
        0.65,
    ),
    "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a74": (
        {"coder": "claude-sonnet-4-6", "reviewer": "claude-sonnet-4-6"},
        0.9,
    ),
}


class FakeLookup:
    """In-memory inference logs; records every fetch."""

    def __init__(self, records: dict[str, InferenceRecord] | None = None) -> None:
        self.records = (
            records
            if records is not None
            else {
                log_id: InferenceRecord(
                    api_token_id=TOKEN,
                    recommended=recommended,
                    confidence=confidence,
                    estimated_success_under_budget=confidence,
                )
                for log_id, (recommended, confidence) in LOG_RECOMMENDATIONS.items()
            }
        )
        self.fetches: list[set[str]] = []

    def fetch(self, ids: Collection[str]) -> dict[str, InferenceRecord]:
        self.fetches.append(set(ids))
        return {log_id: self.records[log_id] for log_id in ids if log_id in self.records}


class FailingLookup:
    def fetch(self, ids: Collection[str]) -> dict[str, InferenceRecord]:
        raise ConnectionError("database unreachable")


class InMemoryStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StoredContributionRecord] = {}

    def get(self, *, model_id: str, submission_id: str) -> StoredContributionRecord | None:
        return self.records.get((model_id, submission_id))

    def create(self, *, record: StoredContributionRecord) -> StoredContributionRecord:
        self.records[(record.model_id, record.submission_id)] = record
        return record

    def put_canonical_rows(self, *, submission_id: str, rows: list[dict]) -> str:
        self.canonical_rows = {**getattr(self, "canonical_rows", {}), submission_id: rows}
        return f"memory://model_30/canonical/v1/{submission_id}.jsonl"


def _service(lookup: Any) -> tuple[ContributionService, InMemoryStore]:
    store = InMemoryStore()
    service = ContributionService(
        store=store,
        lifecycle_session_factory=None,
        inference_log_lookup=lookup,
    )
    service._get_lifecycle_session_factory = lambda: None  # type: ignore[method-assign]
    return service, store


def _submit(rows: list[dict[str, Any]], lookup: Any = None, key: str = "k-1"):
    service, store = _service(lookup if lookup is not None else FakeLookup())
    accepted = service.accept_contribution(
        model_id="30",
        request=ContributionRequest(rows=rows),
        idempotency_key=key,
        auth=AUTH,
    )
    (record,) = store.records.values()
    return accepted, record


def _join_one(row: dict[str, Any], lookup: Any = None, token: str | None = TOKEN):
    (join,) = resolve_routing_joins(
        [routing_outcome_from_row(row)],
        api_token_id=token,
        lookup=lookup if lookup is not None else FakeLookup(),
        canonicalize=str.casefold,
    )
    return join


# ---------------------------------------------------------------------------
# Intake accepts the HOK-3364 rows without losing the routing-outcome block
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_sdk_golden_rows_are_accepted_and_keep_their_routing_block(name: str) -> None:
    row = FIXTURES[name]
    classification = classify_row(copy.deepcopy(row))

    assert classification.tier is FidelityTier.TRAINING_ELIGIBLE
    normalized = classification.row
    assert normalized["schema_version"] == "technical_task_router_row/v1"
    assert normalized["metadata"]["source_schema_version"] == row["schema_version"]
    routing = normalized["metadata"].get("routing_outcome")
    if "inference_log_id" in row:
        assert routing["inference_log_id"] == row["inference_log_id"]
        assert routing["overrides"] == row["overrides"]
        assert routing["selected_models"] == row["selected_models"]
    else:
        assert routing is None
    # eval_id is an identifier, never the join key.
    assert normalized["eval_id"] == normalized["row_id"]


def test_sdk_v2_router_row_is_normalized_not_mistaken_for_a_benchmark_row() -> None:
    row = copy.deepcopy(FIXTURES["unroutedTelemetry"])
    row["schema_version"] = "technical_task_router_row/v2"

    classification = classify_row(row)

    assert classification.tier is FidelityTier.TRAINING_ELIGIBLE
    assert isinstance(classification.row["selected_models"], list)
    assert "row_id" in classification.row


@pytest.mark.parametrize(
    ("mutate", "reason_prefix"),
    [
        (lambda row: row.pop("overrides"), "invalid_routing_outcome:a routed row must list"),
        (
            lambda row: row.pop("inference_log_id"),
            "invalid_routing_outcome:overrides require inference_log_id",
        ),
        (
            lambda row: row["overrides"][0].update({"to": "claude-sonnet-4-6"}),
            "invalid_routing_outcome:",
        ),
        (
            lambda row: row["overrides"][0].update({"source": "whim"}),
            "invalid_routing_outcome:overrides[0].source",
        ),
        (
            lambda row: row.update({"recommended_model": "claude-haiku-4-5"}),
            "recommendation_copy:recommended_model",
        ),
    ],
)
def test_invalid_routing_outcome_is_rejected(mutate: Any, reason_prefix: str) -> None:
    row = copy.deepcopy(FIXTURES["escalationOverride"])
    mutate(row)

    classification = classify_row(row)

    assert classification.tier is FidelityTier.INVALID
    assert classification.reason.startswith(reason_prefix)


# ---------------------------------------------------------------------------
# One join; the evidence split (acceptance fixtures)
# ---------------------------------------------------------------------------


def test_incident_fixtures_split_into_recommendation_and_override_evidence() -> None:
    names = [
        "followedRecommendation",
        "challengeOverride",
        "escalationOverride",
        "operatorReroute",
        "unroutedTelemetry",
        "followedRecommendationHarnessRow",
    ]
    lookup = FakeLookup()

    accepted, record = _submit([copy.deepcopy(FIXTURES[name]) for name in names], lookup)

    joins = record.metadata["row_routing_joins"]
    assert len(joins) == len(record.rows) == len(names)
    by_name = dict(zip(names, joins, strict=True))
    # A followed recommendation counts toward recommendation accuracy.
    assert by_name["followedRecommendation"]["evidence"] == "recommendation"
    assert by_name["followedRecommendationHarnessRow"]["evidence"] == "recommendation"
    # HOK-3315 challenge and HOK-3329 escalation are override evidence, never
    # recommendation evidence.
    assert by_name["challengeOverride"]["evidence"] == "override"
    assert by_name["challengeOverride"]["override_sources"] == ["challenge"]
    assert by_name["challengeOverride"]["recommended"]["coder"] == "claude-opus-4-7"
    assert by_name["challengeOverride"]["executed"]["coder"] == "claude-haiku-4-5"
    assert by_name["escalationOverride"]["evidence"] == "override"
    assert by_name["escalationOverride"]["override_sources"] == ["escalation"]
    assert by_name["escalationOverride"]["confidence"] == 0.334
    # Strict: a reviewer-only override still disqualifies the whole row.
    assert by_name["operatorReroute"]["evidence"] == "override"
    # An unlinked row is counted as unlinked, and is executed-model evidence.
    assert by_name["unroutedTelemetry"]["link"] == "unlinked"
    assert by_name["unroutedTelemetry"]["evidence"] == "executed_only"
    # One batch query, only for rows that carry a join key.
    assert len(lookup.fetches) == 1
    assert len(lookup.fetches[0]) == 5

    summary = accepted.response.routing_summary
    assert summary.links["linked"] == 5
    assert summary.links["unlinked"] == 1
    assert summary.evidence["recommendation"] == 2
    assert summary.evidence["override"] == 3
    assert summary.overrides_by_source == {
        "escalation": 1,
        "launchability": 0,
        "challenge": 1,
        "operator": 1,
    }
    assert summary.linked_share == pytest.approx(5 / 6)
    assert record.metadata["routing_summary"]["linked_share"] == pytest.approx(5 / 6)


def test_task_id_never_links_a_row() -> None:
    row = copy.deepcopy(FIXTURES["unroutedTelemetry"])
    row["task_id"] = "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a70"  # equals a real inference id

    join = _join_one(row)

    assert join.link is LinkStatus.UNLINKED
    assert join.recommended == {}


def test_log_owned_by_another_token_does_not_link() -> None:
    join = _join_one(FIXTURES["followedRecommendation"], token="someone-else")

    assert join.link is LinkStatus.FOREIGN_TOKEN
    assert join.recommended == {}  # never exposes the other caller's recommendation
    assert join.evidence is EvidenceClass.EXECUTED_ONLY


def test_missing_log_is_counted_not_guessed() -> None:
    join = _join_one(FIXTURES["followedRecommendation"], lookup=FakeLookup(records={}))

    assert join.link is LinkStatus.LOG_MISSING
    assert join.evidence is EvidenceClass.EXECUTED_ONLY


def test_unreachable_log_store_never_fails_intake() -> None:
    accepted, record = _submit([copy.deepcopy(FIXTURES["followedRecommendation"])], FailingLookup())

    assert accepted.status_code == 201
    assert record.metadata["row_routing_joins"][0]["link"] == "unresolved"


def test_claim_that_contradicts_the_log_is_unattributed() -> None:
    # The row says the recommendation was followed with sonnet, but the log
    # recommended haiku: the harness did not report an override it made.
    row = copy.deepcopy(FIXTURES["followedRecommendation"])
    row["inference_log_id"] = "0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a71"

    join = _join_one(row)

    assert join.link is LinkStatus.LINKED
    assert join.consistent is False
    assert join.evidence is EvidenceClass.UNATTRIBUTED


def test_v1_harness_row_with_join_key_but_no_overrides_is_unattributed() -> None:
    row = copy.deepcopy(FIXTURES["followedRecommendationHarnessRow"])
    row["schema_version"] = "harness_outcome_row/v1"
    del row["overrides"]

    join = _join_one(row)

    assert join.link is LinkStatus.LINKED
    assert join.evidence is EvidenceClass.UNATTRIBUTED


# ---------------------------------------------------------------------------
# The /outcomes intake path uses the same join
# ---------------------------------------------------------------------------


class _LogRow:
    def __init__(self, recommended: dict[str, str]) -> None:
        self.api_token_id = TOKEN
        self.output_payload = {
            "recommended_strategy": {
                **{f"{role}_model": model for role, model in recommended.items()},
                "confidence": 0.334,
            }
        }
        self.trace_metadata = {"latency_ms": 12}
        self.outcome_score = None
        self.outcome_type = None
        self.outcome_recorded_at = None


def _record_outcome(log_row: _LogRow, **kwargs: Any) -> dict[str, Any]:
    class Query:
        def filter_by(self, **_kwargs: Any) -> Query:
            return self

        def first(self) -> _LogRow:
            return log_row

    class Session:
        def query(self, _model: Any) -> Query:
            return Query()

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    logger = ContributorLogger(session_factory=lambda: Session())
    return logger.record_outcome(
        UUID("0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a71"), TOKEN, 0.0, "task_failed", **kwargs
    )


def test_outcome_submission_joins_through_the_same_function() -> None:
    escalation = FIXTURES["escalationOverride"]
    log_row = _LogRow({"coder": "claude-haiku-4-5", "reviewer": "claude-sonnet-4-6"})

    join = _record_outcome(
        log_row,
        selected_models=escalation["selected_models"],
        overrides=escalation["overrides"],
    )

    assert join["link"] == "linked"
    assert join["evidence"] == "override"
    assert join["override_sources"] == ["escalation"]
    assert log_row.trace_metadata["outcome_routing_join"] == join
    assert log_row.trace_metadata["latency_ms"] == 12


def test_outcome_without_routing_block_cannot_grade_the_recommendation() -> None:
    join = _record_outcome(_LogRow({"coder": "claude-haiku-4-5"}))

    assert join["link"] == "linked"
    assert join["evidence"] == "unattributed"


def test_outcome_submission_rejects_an_invalid_override_chain() -> None:
    with pytest.raises(ValueError, match="Invalid routing outcome"):
        OutcomeSubmission(
            inference_log_id="0f8e2c1a-5b3d-4e7f-9a1b-2c3d4e5f6a71",
            outcome_score=0.0,
            outcome_type="task_failed",
            selected_models={"coder": "claude-sonnet-4-6"},
            overrides=FIXTURES["escalationOverride"]["overrides"],
        )


# ---------------------------------------------------------------------------
# Reports: calibration from recommendation evidence only; coverage
# ---------------------------------------------------------------------------


def test_feedback_report_calibrates_on_recommendation_evidence_only() -> None:
    names = [
        "followedRecommendation",
        "challengeOverride",
        "escalationOverride",
        "operatorReroute",
        "unroutedTelemetry",
    ]
    _, record = _submit([copy.deepcopy(FIXTURES[name]) for name in names])
    legacy = StoredContributionRecord(
        submission_id="legacy",
        model_id="30",
        idempotency_key="legacy",
        body_hash="",
        rows=[copy.deepcopy(record.rows[0])],
        metadata={},
        response_payload={},
        created_at="",
    )

    report = build_routing_feedback_report([record, legacy])

    bands = report["calibration"]["bands"]
    # Only the followed recommendation (confidence 0.82) is calibration data.
    # The HOK-3329 escalation at 0.334 failed, but that failure was glm's.
    assert bands["[0.8,1.0]"]["rows"] == 1
    assert bands["[0.8,1.0]"]["success_rate"] == 1.0
    assert bands["[0.0,0.4)"]["rows"] == 0
    overrides = report["overrides"]
    assert overrides["by_source"]["escalation"]["rows"] == 1
    assert overrides["by_source"]["escalation"]["success_rate"] == 0.0
    assert overrides["by_source"]["challenge"]["rows"] == 1
    assert overrides["escalation_vs_followed_by_band"]["[0.0,0.4)"]["escalation"]["rows"] == 1
    coverage = report["coverage"]
    assert coverage["links"]["linked"] == 4
    assert coverage["links"]["unlinked"] == 1
    assert coverage["linked_share"] == pytest.approx(4 / 5)
    assert coverage["overrides_by_source"]["operator"] == 1
    assert coverage["rows_without_routing_join"] == 1


# ---------------------------------------------------------------------------
# Scorers read the joined record
# ---------------------------------------------------------------------------


def test_router_scorers_read_selected_models_only_through_the_joined_route() -> None:
    source = (REPO_ROOT / "src/evaluation/scorers/builtin.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name != "_joined_route"
        and any(
            isinstance(child, ast.Constant) and child.value == "selected_models"
            for child in ast.walk(node)
        )
    ]
    assert offenders == [], f"read selected_models without the joined record: {offenders}"


def _benchmark_row(scenario: str, *, evidence: str, success: bool = True) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "selected_models": ["claude-sonnet-4-6"],
        "allowed_models": ["claude-sonnet-4-6", "gpt-5.4"],
        "actual_cost_usd": 0.5,
        "max_cost_usd": 1.0,
        "completed_successfully": success,
        "metadata": {"routing_join": {"evidence": evidence}},
    }


def test_counterfactual_labels_are_not_scored() -> None:
    rows = [
        _benchmark_row("production_pool", evidence="recommendation", success=False),
        _benchmark_row("production_pool", evidence="counterfactual", success=True),
    ]

    assert _task_router_success_under_budget(rows) == 0.0


def test_composite_drops_a_slice_with_no_label_evidence() -> None:
    rows = [
        _benchmark_row("production_pool", evidence="recommendation"),
        _benchmark_row("challenger_present", evidence="recommendation"),
        _benchmark_row("sparse_cell", evidence="counterfactual", success=False),
    ]

    # sparse_cell is unmeasured, so its 0.10 weight is dropped rather than
    # scored 0: the remaining components are all perfect successes at 50% cost.
    expected = (0.70 * 1.0 + 0.15 * 0.5 + 0.05 * 1.0) / 0.90
    assert _task_router_benchmark_score_v2(rows) == pytest.approx(expected)


def test_assembler_carries_the_join_into_canonical_rows_only() -> None:
    report = {"rows_without_routing_join": 0}
    join = {"evidence": "override", "link": "linked"}
    canonical = classify_row(copy.deepcopy(FIXTURES["challengeOverride"])).row

    attached = attach_routing_join(canonical, join, report)
    compact = attach_routing_join({"inputs": {}, "task_id": "t"}, join, report)
    legacy = attach_routing_join(canonical, None, report)

    assert attached["metadata"]["routing_join"] == join
    assert attached["metadata"]["routing_outcome"] == canonical["metadata"]["routing_outcome"]
    assert "routing_join" not in canonical["metadata"]  # input not mutated
    assert compact == {"inputs": {}, "task_id": "t"}
    assert legacy is canonical
    assert report["rows_without_routing_join"] == 1
