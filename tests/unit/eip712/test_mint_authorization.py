from __future__ import annotations

import copy

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from src.eip712 import (
    MintAuthorizationConfig,
    build_typed_data,
    compute_digest,
    render_for_human,
    verify_signature,
)
from src.events.schemas import MintRequest, MintRequestContributor, MintRequestEvaluation

_PRIVATE_KEY = "0x" + "11" * 32
_OTHER_PRIVATE_KEY = "0x" + "22" * 32
_EXPECTED_ADDRESS = Account.from_key(_PRIVATE_KEY).address.lower()


def _make_mint_request(**overrides) -> MintRequest:
    data = {
        "message_id": "msg-1",
        "timestamp": "2026-06-10T12:00:00+00:00",
        "model_id": "model-a",
        "model_id_uint": "12345678901234567890",
        "eval_id": "eval-1",
        "benchmark_spec_id": "spec-1",
        "dataset_hash": "0x" + "ab" * 32,
        "attestation_hash": "0x" + "cd" * 32,
        "idempotency_key": "0x" + "ef" * 32,
        "baseline_commitment": "0x" + "34" * 32,
        "candidate_commitment": "0x" + "56" * 32,
        "attester_signatures": ["0x" + "90" * 65],
        "totalSamples": 321,
        "evaluation": MintRequestEvaluation(
            metric_name="accuracy",
            metric_family="proportion",
            baseline_score_bps=7800,
            new_score_bps=8100,
            max_cost_usd_micro=5_000_000,
            actual_cost_usd_micro=2_500_000,
            sample_size_candidate=321,
        ),
        "contributors": [
            MintRequestContributor(
                wallet_address="0x742d35cc6634c0532925a3b844bc9e7595f62341",
                weight_bps=10000,
            )
        ],
    }
    data.update(overrides)
    return MintRequest.model_validate(data)


def _make_config(**overrides) -> MintAuthorizationConfig:
    values = {
        "chain_id": 1,
        "verifying_contract": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC",
        "attester_address": _EXPECTED_ADDRESS,
    }
    values.update(overrides)
    return MintAuthorizationConfig(**values)


def _sign_typed_data(typed_data: dict) -> str:
    signed = Account.sign_message(encode_typed_data(full_message=typed_data), _PRIVATE_KEY)
    signature_hex = signed.signature.hex()
    return signature_hex if signature_hex.startswith("0x") else f"0x{signature_hex}"


def test_build_typed_data_deterministic() -> None:
    mint_request = _make_mint_request()
    config = _make_config()

    assert build_typed_data(mint_request, config) == build_typed_data(mint_request, config)


def test_compute_digest_known_vector() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())

    assert (
        compute_digest(typed_data).hex()
        == "36adde27f0fc956f0477a8c96af9f28750112e832e20f76350c86f311769e901"
    )


def test_build_typed_data_matches_contract_field_mapping() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    payload = typed_data["message"]["payload"]
    anchors = payload["anchors"]

    assert typed_data["message"]["modelId"] == 12345678901234567890
    assert payload["pipelineRunId"] == "eval-1"
    assert payload["baselineScoreBps"] == 7800
    assert payload["candidateScoreBps"] == 8100
    assert payload["baselineCommitment"] == "0x" + "34" * 32
    assert payload["candidateCommitment"] == "0x" + "56" * 32
    assert anchors["benchmarkSpecHash"] == f"0x{keccak(text='spec-1').hex()}"
    assert anchors["datasetHash"] == "0x" + "ab" * 32


def test_compute_digest_changes_on_field_mutation() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    mutated = copy.deepcopy(typed_data)
    mutated["message"]["payload"]["totalSamples"] += 1

    assert compute_digest(typed_data) != compute_digest(mutated)


def test_domain_is_bound_to_digest() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    mutated = copy.deepcopy(typed_data)
    mutated["domain"]["chainId"] = 10

    assert compute_digest(typed_data) != compute_digest(mutated)


def test_verify_signature_roundtrip() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    signature = _sign_typed_data(typed_data)

    assert verify_signature(typed_data, signature, _EXPECTED_ADDRESS) is True


def test_verify_signature_wrong_address() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    signature = _sign_typed_data(typed_data)
    wrong_address = Account.from_key(_OTHER_PRIVATE_KEY).address

    assert verify_signature(typed_data, signature, wrong_address) is False


def test_verify_signature_mutated_typed_data() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    mutated = copy.deepcopy(typed_data)
    mutated["message"]["payload"]["candidateCommitment"] = "0x" + "99" * 32

    assert verify_signature(mutated, _sign_typed_data(typed_data), _EXPECTED_ADDRESS) is False


def test_verify_signature_malformed_hex() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())

    with pytest.raises(ValueError, match="signature"):
        verify_signature(typed_data, "not-hex", _EXPECTED_ADDRESS)


def test_render_for_human_contains_digest() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    digest = f"0x{compute_digest(typed_data).hex()}"

    assert digest in render_for_human(typed_data)


def test_render_no_truncated_hex() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    rendered = render_for_human(typed_data)

    assert "..." not in rendered
    for value in (
        typed_data["message"]["payload"]["baselineCommitment"],
        typed_data["message"]["payload"]["candidateCommitment"],
        typed_data["message"]["payload"]["anchors"]["attestationHash"],
        typed_data["message"]["payload"]["anchors"]["benchmarkSpecHash"],
    ):
        assert value in rendered


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINT_CHAIN_ID", "8453")
    monkeypatch.setenv("MINT_VERIFYING_CONTRACT", "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC")
    monkeypatch.setenv("MINT_ATTESTER_ADDRESS", _EXPECTED_ADDRESS.upper())

    config = MintAuthorizationConfig.from_env()

    assert config.chain_id == 8453
    assert config.verifying_contract == "0xcccccccccccccccccccccccccccccccccccccccc"
    assert config.attester_address == _EXPECTED_ADDRESS
