from __future__ import annotations

import copy

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

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
        "baseline": "0x" + "12" * 32,
        "baselineCommitment": "0x" + "34" * 32,
        "candidateCommitment": "0x" + "56" * 32,
        "signingDigest": "0x" + "78" * 32,
        "attesterSignature": "0x" + "90" * 65,
        "totalSamples": 321,
        "evaluation": MintRequestEvaluation(
            metric_name="accuracy",
            metric_family="proportion",
            baseline_score_bps=7800,
            new_score_bps=8100,
            max_cost_usd_micro=5_000_000,
            actual_cost_usd_micro=2_500_000,
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
        == "63210e4da17d33e7e36f652f87b694d7cfe994dfcd4510ab5d30db1921df52ab"
    )


def test_compute_digest_changes_on_field_mutation() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    mutated = copy.deepcopy(typed_data)
    mutated["message"]["totalSamples"] += 1

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
    mutated["message"]["baseline"] = "0x" + "99" * 32

    assert verify_signature(mutated, _sign_typed_data(typed_data), _EXPECTED_ADDRESS) is False


def test_verify_signature_malformed_hex() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())

    with pytest.raises(ValueError, match="signature"):
        verify_signature(typed_data, "not-hex", _EXPECTED_ADDRESS)


def test_render_for_human_contains_digest() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    digest = f"0x{compute_digest(typed_data).hex()}"

    assert digest in render_for_human(typed_data)


def test_render_and_digest_change_together() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    mutated = copy.deepcopy(typed_data)
    mutated["message"]["candidateCommitment"] = "0x" + "aa" * 32

    assert render_for_human(typed_data) != render_for_human(mutated)
    assert compute_digest(typed_data) != compute_digest(mutated)


def test_render_no_truncated_hex() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config())
    rendered = render_for_human(typed_data)

    assert "..." not in rendered
    for value in (
        typed_data["message"]["baselineCommitment"],
        typed_data["message"]["candidateCommitment"],
        typed_data["message"]["baseline"],
        typed_data["message"]["attestationHash"],
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
