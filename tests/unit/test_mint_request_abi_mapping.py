from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.event_payload import make_idempotency_key

REPO_ROOT = Path(__file__).parents[2]
EXAMPLE_FILE = REPO_ROOT / "schema" / "examples" / "mint_request.v1.json"


def _load_fixture() -> dict:
    with EXAMPLE_FILE.open() as fixture_file:
        return json.load(fixture_file)


def test_mint_request_fixture_matches_abi_contract_invariants() -> None:
    fixture = _load_fixture()
    contributors = fixture["contributors"]
    evaluation = fixture["evaluation"]

    assert fixture["benchmark_spec_id"]
    assert fixture["benchmark_spec_id"] == fixture["benchmark_spec_id"].strip()
    assert fixture["dataset_hash"].startswith("0x")
    assert fixture["dataset_hash"] != "0x" + "0" * 64
    if "baseline" in fixture:
        assert fixture["baseline"].startswith("0x")
        assert len(fixture["baseline"]) == 66
    assert fixture["attestation_hash"].startswith("0x")
    assert fixture["attestation_hash"] != "0x" + "0" * 64
    assert fixture["idempotency_key"] == make_idempotency_key(
        int(fixture["model_id_uint"]), fixture["attestation_hash"]
    )
    assert fixture["idempotency_key"] != "0x" + "0" * 64
    if "baselineCommitment" in fixture:
        assert fixture["baselineCommitment"].startswith("0x")
    if "candidateCommitment" in fixture:
        assert fixture["candidateCommitment"].startswith("0x")
    if "attesterSignature" in fixture:
        assert fixture["attesterSignature"].startswith("0x")
    if "signingDigest" in fixture:
        assert fixture["signingDigest"].startswith("0x")
        assert len(fixture["signingDigest"]) == 66
    assert sum(contributor["weight_bps"] for contributor in contributors) == 10000
    assert fixture["totalSamples"] >= 1
    assert fixture["totalSamples"] == evaluation["sample_size_candidate"]
    assert int(fixture["model_id_uint"]) < 2**256

    for key in (
        "baseline_score_bps",
        "new_score_bps",
        "ci_low_bps",
        "ci_high_bps",
        "effect_size_bps",
    ):
        value = evaluation[key]
        assert isinstance(value, int)
        assert 0 <= value <= 10000

    for key in ("max_cost_usd_micro", "actual_cost_usd_micro", "sample_size_baseline"):
        value = evaluation[key]
        assert isinstance(value, int)
        assert value >= 0
