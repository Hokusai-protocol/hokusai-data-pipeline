"""Verify the DeltaOne acceptance event maps to the on-chain DeltaVerifier struct.

The fixture in ``tests/fixtures/deltaone_acceptance_event_v1_contract_mapping.json``
captures the expected per-field mapping between the off-chain
``DeltaOneAcceptanceEvent`` and the on-chain ``DeltaVerifier`` struct in
``hokusai-token``.  Updating either side requires updating this fixture so
that drift is visible in code review.

The test only relies on the documented mapping so it does not require
``hokusai-token`` to be checked out alongside this repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.event_payload import DeltaOneAcceptanceEvent

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "deltaone_acceptance_event_v1_contract_mapping.json"
)


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_fixture_event_validates_against_pydantic_model(fixture_data: dict) -> None:
    """The fixture event must be a valid v1 acceptance event."""
    DeltaOneAcceptanceEvent(**fixture_data["event"])


def test_contract_struct_field_mapping(fixture_data: dict) -> None:
    """Each contract field maps to a documented event field with the same value."""
    event = fixture_data["event"]
    contract = fixture_data["expected_contract_struct"]

    assert contract["pipelineRunId"] == event["eval_id"]
    assert contract["modelId"] == event["model_id_uint"]
    assert contract["baselineMetrics"]["accuracy"] == event["baseline_score_bps"]
    assert contract["newMetrics"]["accuracy"] == event["candidate_score_bps"]

    # Other metric slots in the single-metric struct must default to 0 per
    # HOK-1269 §4.1: only the `accuracy` slot carries the primary score.
    for slot in ("latencyP50Ms", "latencyP99Ms", "samplesProcessed"):
        assert contract["baselineMetrics"][slot] == 0
        assert contract["newMetrics"][slot] == 0

    assert contract["maxCostUsd"] == event["max_cost_usd_micro"]
    assert contract["actualCostUsd"] == event["actual_cost_usd_micro"]
    assert contract["attestationHash"] == "0x" + event["attestation_hash"]
    assert contract["idempotencyKey"] == "0x" + event["idempotency_key"]


def test_field_mapping_documents_all_contract_fields(fixture_data: dict) -> None:
    """Documented field mapping must cover every non-zero contract field."""
    contract = fixture_data["expected_contract_struct"]
    mapped = set(fixture_data["field_mapping"].keys())
    expected = {
        "pipelineRunId",
        "modelId",
        "baselineMetrics.accuracy",
        "newMetrics.accuracy",
        "maxCostUsd",
        "actualCostUsd",
        "attestationHash",
        "idempotencyKey",
    }
    missing = expected - mapped
    assert not missing, f"field mapping missing entries: {missing}"
    # Sanity check: contract has the structural fields documented above.
    assert "baselineMetrics" in contract and "newMetrics" in contract
