"""Unit coverage for server-side contribution fidelity tiering.

Mirrors the service-level tests in ``test_contributions_endpoint.py``: a
training-eligible harness row is accepted and normalized, a partial harness row
is accepted but excluded from training, an invalid row is rejected, and existing
rich v1/v2 rows plus legacy compact Wavemill rows are unaffected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from src.api.schemas.contribution import ContributionRequest
from src.api.services.contribution_fidelity import (
    FidelityTier,
    classify_batch,
    classify_row,
)
from src.api.services.contribution_service import (
    ContributionService,
    ContributionValidationError,
    StoredContributionRecord,
)
from src.evaluation.scorers.builtin import _task_router_row_is_feasible

VALID_AUTH = {
    "user_id": "11111111-1111-1111-1111-111111111111",
    "api_key_id": "22222222-2222-2222-2222-222222222222",
    "service_id": "svc-1",
}


class InMemoryContributionStore:
    """Small in-memory store mirroring the endpoint test double."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], StoredContributionRecord] = {}

    def get(self, *, model_id: str, submission_id: str) -> StoredContributionRecord | None:
        return self.records.get((model_id, submission_id))

    def create(self, *, record: StoredContributionRecord) -> StoredContributionRecord:
        self.records[(record.model_id, record.submission_id)] = record
        return record


def _harness_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema_version": "harness_outcome_row/v1",
        "task_descriptor": {"task_type": "bugfix", "language": "python"},
        "allowed_models": ["gpt-5.4", "claude-sonnet-4-6"],
        "selected_models": {"coder": "gpt-5.4", "reviewer": "claude-sonnet-4-6"},
        "budget_usd": 2.0,
        "actual_cost_usd": 0.8,
        "wall_clock_seconds": 42.0,
        "success_under_budget": True,
        "completion_result": "success",
        "observed_at": "2026-06-01T00:00:00Z",
        "task_id": "task-abc",
        "harness": "claude-code",
        "harness_metadata": {"harness": "claude-code", "sdk_version": "0.1.3"},
    }
    row.update(overrides)
    return row


def _canonical_v1_row() -> dict[str, Any]:
    return {
        "schema_version": "technical_task_router_row/v1",
        "row_id": "r-1",
        "benchmark_spec_id": "bench-1",
        "eval_id": "eval-1",
        "model_id": "30",
        "task_descriptor": {"task_type": "bugfix"},
        "allowed_models": ["gpt-5.4"],
        "selected_models": ["gpt-5.4"],
        "max_cost_usd": 1.0,
        "actual_cost_usd": 0.5,
        "completed_successfully": True,
        "scorer_ref": "technical_task_router.success_under_budget/v1",
        "observed_at": "2026-06-01T00:00:00Z",
    }


def _service() -> tuple[ContributionService, InMemoryContributionStore]:
    store = InMemoryContributionStore()
    return ContributionService(store=store), store


def _accept(service: ContributionService, rows: list[dict[str, Any]], key: str) -> Any:
    payload = ContributionRequest.model_validate(
        {"rows": rows, "metadata": {"idempotency_key": key}}
    )
    return service.accept_contribution(
        model_id="30", request=payload, idempotency_key=None, auth=VALID_AUTH
    )


def test_training_eligible_harness_row_accepted_and_normalized() -> None:
    service, store = _service()

    accepted = _accept(service, [_harness_row()], "batch-h1")

    assert accepted.status_code == 201
    assert accepted.response.rows_accepted == 1
    assert accepted.response.submitted_rows == 1

    record = store.records[("30", "batch-h1")]
    assert record.metadata["row_fidelity_tiers"] == ["training_eligible"]

    normalized = record.rows[0]
    assert normalized["schema_version"] == "technical_task_router_row/v1"
    assert normalized["selected_models"] == ["gpt-5.4", "claude-sonnet-4-6"]
    assert normalized["allowed_models"] == ["gpt-5.4", "claude-sonnet-4-6"]
    assert normalized["max_cost_usd"] == 2.0
    assert normalized["actual_cost_usd"] == 0.8
    assert normalized["completed_successfully"] is True
    assert normalized["scorer_ref"] == "technical_task_router.success_under_budget/v1"

    # The normalized row validates against the canonical training schema and the
    # authoritative reward scorer treats it as feasible (train-usable).
    schema = json.loads(
        Path("schema/technical_task_router_row.v1.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(normalized, schema)
    assert _task_router_row_is_feasible(normalized) is True


def test_partial_harness_row_accepted_but_excluded_from_training() -> None:
    service, store = _service()
    row = _harness_row()
    del row["actual_cost_usd"]  # no numeric cost -> success-under-budget uncomputable

    accepted = _accept(service, [row], "batch-h2")

    assert accepted.status_code == 201
    assert accepted.response.rows_accepted == 1

    record = store.records[("30", "batch-h2")]
    assert record.metadata["row_fidelity_tiers"] == ["partial"]
    assert record.metadata["fidelity_summary"]["partial"] == 1
    # Persisted for telemetry in its original shape, never normalized to training.
    assert record.rows[0]["schema_version"] == "harness_outcome_row/v1"


def test_partial_only_submission_reason_is_excluded_from_training() -> None:
    row = _harness_row()
    del row["budget_usd"]  # no budget -> success-under-budget uncomputable
    classification = classify_batch([row], model_id="30")

    assert classification.partial_count == 1
    assert classification.training_eligible_count == 0
    assert classification.has_only_partial is True
    assert ContributionService._lifecycle_reason_for(classification) == "excluded_from_training"


def test_invalid_harness_row_rejected() -> None:
    service, store = _service()
    row = _harness_row()
    del row["selected_models"]
    del row["allowed_models"]

    with pytest.raises(ContributionValidationError) as excinfo:
        _accept(service, [row], "batch-h3")

    assert excinfo.value.detail["error"] == "no_acceptable_rows"
    assert store.records == {}


def test_mixed_batch_accepts_valid_and_records_rejected() -> None:
    service, store = _service()
    good = _harness_row(task_id="good")
    bad = _harness_row(task_id="bad")
    del bad["selected_models"]
    del bad["allowed_models"]

    accepted = _accept(service, [good, bad], "batch-h4")

    assert accepted.response.rows_accepted == 1
    assert accepted.response.submitted_rows == 2

    record = store.records[("30", "batch-h4")]
    assert len(record.rows) == 1
    assert record.metadata["row_fidelity_tiers"] == ["training_eligible"]
    summary = record.metadata["fidelity_summary"]
    assert summary["invalid"] == 1
    assert summary["rejected"][0]["index"] == 1


def test_existing_v1_row_unchanged_and_training_eligible() -> None:
    service, store = _service()
    v1_row = _canonical_v1_row()

    accepted = _accept(service, [v1_row], "batch-v1")

    assert accepted.response.rows_accepted == 1
    record = store.records[("30", "batch-v1")]
    # Rich rows keep their exact contract and shape, byte-for-byte.
    assert record.rows[0] == v1_row
    assert record.metadata["row_fidelity_tiers"] == ["training_eligible"]


def test_legacy_compact_wavemill_row_passthrough_unchanged() -> None:
    service, store = _service()
    compact = {
        "task_id": "redacted-task",
        "harness": "wavemill",
        "actual_cost_usd": 1.25,
        "success_under_budget": True,
        "inputs": {"coder_model": "gpt-5.4", "reviewer_model": "claude-sonnet-4-6"},
    }

    accepted = _accept(service, [compact], "batch-legacy")

    assert accepted.response.rows_accepted == 1
    record = store.records[("30", "batch-legacy")]
    # Legacy compact shape is neither rejected nor reclassified; assembler decides.
    assert record.rows[0] == compact
    assert record.metadata["row_fidelity_tiers"] == ["passthrough"]


def test_forbidden_field_in_harness_row_is_rejected() -> None:
    service, store = _service()
    row = _harness_row()
    row["task_descriptor"]["prompt"] = "raw user prompt text"

    with pytest.raises(ContributionValidationError):
        _accept(service, [row], "batch-forbidden")

    assert store.records == {}


def test_classify_row_tiers_directly() -> None:
    assert classify_row(_harness_row()).tier is FidelityTier.TRAINING_ELIGIBLE

    partial = _harness_row()
    del partial["budget_usd"]
    assert classify_row(partial).tier is FidelityTier.PARTIAL

    invalid = _harness_row()
    del invalid["selected_models"]
    del invalid["allowed_models"]
    assert classify_row(invalid).tier is FidelityTier.INVALID

    assert classify_row({"task_id": "row-1"}).tier is FidelityTier.PASSTHROUGH


# --- Fidelity tiers surfaced in the contribution response (HOK-2494) ----------
#
# The classification is computed server-side and stored in record metadata. It is
# also returned to the submitting client so a contributor can tell a row that
# trains from a row that is merely accepted.


def test_response_reports_training_eligible_tier() -> None:
    service, _ = _service()

    accepted = _accept(service, [_harness_row()], "batch-tier-1")

    assert accepted.response.row_fidelity_tiers == ["training_eligible"]
    assert accepted.response.fidelity_summary.training_eligible == 1
    assert accepted.response.fidelity_summary.partial == 0
    assert accepted.response.rejected_rows == []


def test_response_reports_partial_tier_when_cost_missing() -> None:
    service, _ = _service()
    row = _harness_row()
    del row["actual_cost_usd"]

    accepted = _accept(service, [row], "batch-tier-2")

    # Accepted, but visibly not training data.
    assert accepted.response.accepted is True
    assert accepted.response.rows_accepted == 1
    assert accepted.response.row_fidelity_tiers == ["partial"]
    assert accepted.response.fidelity_summary.partial == 1
    assert accepted.response.fidelity_summary.training_eligible == 0


def test_fidelity_summary_counts_sum_to_submitted_rows() -> None:
    service, _ = _service()
    partial = _harness_row()
    del partial["actual_cost_usd"]
    invalid = _harness_row()
    del invalid["selected_models"]
    del invalid["allowed_models"]

    accepted = _accept(
        service,
        [_harness_row(task_id="a"), partial, invalid, {"task_id": "legacy"}],
        "batch-tier-3",
    )

    summary = accepted.response.fidelity_summary
    total = summary.training_eligible + summary.partial + summary.passthrough + summary.invalid
    assert total == accepted.response.submitted_rows == 4
    assert summary.training_eligible == 1
    assert summary.partial == 1
    assert summary.passthrough == 1
    assert summary.invalid == 1
    # Tiers align by index to the accepted rows only; the invalid row is absent.
    assert accepted.response.row_fidelity_tiers == ["training_eligible", "partial", "passthrough"]


def test_response_reports_rejected_row_reasons() -> None:
    service, _ = _service()
    invalid = _harness_row()
    del invalid["selected_models"]
    del invalid["allowed_models"]

    accepted = _accept(service, [_harness_row(task_id="a"), invalid], "batch-tier-4")

    assert len(accepted.response.rejected_rows) == 1
    assert accepted.response.rejected_rows[0].index == 1
    assert accepted.response.rejected_rows[0].reason


def test_idempotent_replay_returns_stored_tiers_without_reclassifying() -> None:
    service, store = _service()
    rows = [_harness_row()]

    first = _accept(service, rows, "batch-replay")
    assert first.status_code == 201

    # Mutating the stored classification proves the replay reads it back rather
    # than recomputing: a reclassification would still say training_eligible.
    store.records[("30", "batch-replay")].response_payload["rowFidelityTiers"] = ["partial"]

    replay = _accept(service, rows, "batch-replay")

    assert replay.status_code == 200
    assert replay.response.idempotent_replay is True
    assert replay.response.row_fidelity_tiers == ["partial"]


def test_replay_of_legacy_record_omits_tiers_rather_than_fabricating() -> None:
    service, store = _service()
    rows = [_harness_row()]

    _accept(service, rows, "batch-legacy-replay")

    # Simulate a record persisted before the tier fields existed.
    payload = store.records[("30", "batch-legacy-replay")].response_payload
    payload.pop("rowFidelityTiers")
    payload.pop("fidelitySummary")
    payload.pop("rejectedRows")

    replay = _accept(service, rows, "batch-legacy-replay")

    assert replay.status_code == 200
    assert replay.response.row_fidelity_tiers is None
    assert replay.response.fidelity_summary is None
    assert replay.response.rejected_rows == []
