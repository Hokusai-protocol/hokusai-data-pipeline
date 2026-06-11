from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from src.events.schemas import MintRequest

REPO_ROOT = Path(__file__).parents[2]
PIPELINE_SCHEMA_FILE = REPO_ROOT / "schema" / "mint_request.v1.json"
CONSUMER_SCHEMA_FILE = REPO_ROOT / "schema" / "mint_request.consumer.v1.json"
EXAMPLE_FILE = REPO_ROOT / "schema" / "examples" / "mint_request.v1.json"
TOKEN_FIXTURE_FILE = (
    Path("/Users/timothyogilvie/Dropbox/Hokusai/hokusai-token")
    / "services/contract-deployer/tests/fixtures/mint_request.v1.json"
)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_example_validates_against_pipeline_and_consumer_schemas() -> None:
    example = _load_json(EXAMPLE_FILE)
    pipeline_schema = _load_json(PIPELINE_SCHEMA_FILE)
    consumer_schema = _load_json(CONSUMER_SCHEMA_FILE)

    jsonschema.Draft202012Validator(pipeline_schema).validate(example)
    jsonschema.Draft202012Validator(consumer_schema).validate(example)


def test_example_round_trips_through_pydantic_without_legacy_keys() -> None:
    example = _load_json(EXAMPLE_FILE)
    message = MintRequest.model_validate(example)
    dumped = json.loads(message.model_dump_json(by_alias=True))

    assert dumped["baseline_commitment"] == example["baseline_commitment"]
    assert dumped["candidate_commitment"] == example["candidate_commitment"]
    assert dumped["attester_signatures"] == example["attester_signatures"]
    assert "baseline" not in dumped
    assert "baselineCommitment" not in dumped
    assert "candidateCommitment" not in dumped
    assert "attesterSignature" not in dumped
    assert "signingDigest" not in dumped


def test_pipeline_example_fixture_matches_token_fixture_bytes() -> None:
    assert EXAMPLE_FILE.read_bytes() == TOKEN_FIXTURE_FILE.read_bytes()
