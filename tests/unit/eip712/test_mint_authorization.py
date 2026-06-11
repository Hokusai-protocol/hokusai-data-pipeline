from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from src.eip712 import (
    BENCHMARK_ANCHORS_TYPES,
    CONTRIBUTOR_TYPES,
    DOMAIN_NAME,
    DOMAIN_VERSION,
    MINT_REQUEST_PAYLOAD_TYPES,
    MINT_REQUEST_TYPES,
    InvalidSignatureError,
    MintRequestSigningConfig,
    SignatureRegistryError,
    build_typed_data,
    compute_digest,
    recover_signer,
    render_for_human,
    sort_signatures_by_signer,
    validate_signatures_against_registry,
    verify_signature,
)
from src.events.schemas import MintRequest

FIXTURES = Path(__file__).with_name("fixtures") / "mint_request_kav.json"
PRIVATE_KEY_A = "0x" + "11" * 32
PRIVATE_KEY_B = "0x" + "22" * 32
PRIVATE_KEY_C = "0x" + "33" * 32
ADDRESS_A = Account.from_key(PRIVATE_KEY_A).address
ADDRESS_B = Account.from_key(PRIVATE_KEY_B).address
ADDRESS_C = Account.from_key(PRIVATE_KEY_C).address


def _load_vectors() -> list[dict]:
    return json.loads(FIXTURES.read_text())["vectors"]


def _vector(name: str) -> dict:
    return next(vector for vector in _load_vectors() if vector["name"] == name)


def _make_config(vector: dict, **overrides) -> MintRequestSigningConfig:
    values = {
        "chain_id": vector["chain_id"],
        "verifying_contract": vector["verifying_contract"],
    }
    values.update(overrides)
    return MintRequestSigningConfig(**values)


def _make_mint_request(vector_name: str = "single_contributor", **overrides) -> MintRequest:
    data = copy.deepcopy(_vector(vector_name)["wire_message"])
    data.update(overrides)
    return MintRequest.model_validate(data)


def _sign_typed_data(typed_data: dict, private_key: str) -> str:
    signed = Account.sign_message(encode_typed_data(full_message=typed_data), private_key)
    signature = signed.signature.hex()
    return signature if signature.startswith("0x") else f"0x{signature}"


def test_build_typed_data_matches_contract_schema() -> None:
    vector = _vector("single_contributor")
    typed_data = build_typed_data(_make_mint_request(), _make_config(vector))

    assert typed_data["primaryType"] == "MintRequest"
    assert typed_data["types"]["MintRequest"] == MINT_REQUEST_TYPES
    assert typed_data["types"]["MintRequestPayload"] == MINT_REQUEST_PAYLOAD_TYPES
    assert typed_data["types"]["BenchmarkAnchors"] == BENCHMARK_ANCHORS_TYPES
    assert typed_data["types"]["Contributor"] == CONTRIBUTOR_TYPES
    assert typed_data["domain"] == {
        "name": DOMAIN_NAME,
        "version": DOMAIN_VERSION,
        "chainId": vector["chain_id"],
        "verifyingContract": vector["verifying_contract"],
    }
    assert list(typed_data["message"].keys()) == ["modelId", "payload", "contributors"]


def test_benchmark_spec_hash_matches_consumer_derivation() -> None:
    mint_request = _make_mint_request()
    typed_data = build_typed_data(mint_request, _make_config(_vector("single_contributor")))

    assert typed_data["message"]["payload"]["anchors"]["benchmarkSpecHash"] == (
        f"0x{keccak(text=mint_request.benchmark_spec_id).hex()}"
    )


@pytest.mark.parametrize("name", ["single_contributor", "multi_contributor"])
def test_compute_digest_matches_known_answer_vector(name: str) -> None:
    vector = _vector(name)
    typed_data = build_typed_data(
        MintRequest.model_validate(vector["wire_message"]),
        _make_config(vector),
    )

    assert f"0x{compute_digest(typed_data).hex()}" == vector["expected_digest"]
    assert compute_digest(typed_data) == compute_digest(typed_data)


def test_mutating_any_signed_field_changes_digest() -> None:
    typed_data = build_typed_data(
        _make_mint_request("multi_contributor"),
        _make_config(_vector("multi_contributor")),
    )
    original = compute_digest(typed_data)

    mutators = [
        lambda td: td["message"].__setitem__("modelId", td["message"]["modelId"] + 1),
        lambda td: td["message"]["payload"].__setitem__("pipelineRunId", "eval-2026-mutated"),
        lambda td: td["message"]["payload"].__setitem__("baselineScoreBps", 6401),
        lambda td: td["message"]["payload"].__setitem__("candidateScoreBps", 6556),
        lambda td: td["message"]["payload"].__setitem__("maxCostUsdMicro", 1200001),
        lambda td: td["message"]["payload"].__setitem__("actualCostUsdMicro", 1100001),
        lambda td: td["message"]["payload"].__setitem__("totalSamples", 322),
        lambda td: td["message"]["payload"]["anchors"].__setitem__(
            "benchmarkSpecHash", f"0x{keccak(text='spec-multi-v3').hex()}"
        ),
        lambda td: td["message"]["payload"]["anchors"].__setitem__("datasetHash", "0x" + "44" * 32),
        lambda td: td["message"]["payload"]["anchors"].__setitem__(
            "attestationHash", "0x" + "55" * 32
        ),
        lambda td: td["message"]["payload"]["anchors"].__setitem__(
            "idempotencyKey", "0x" + "66" * 32
        ),
        lambda td: td["message"]["payload"]["anchors"].__setitem__("metricName", "sales_margin_v2"),
        lambda td: td["message"]["payload"]["anchors"].__setitem__("metricFamily", "proportion"),
        lambda td: td["message"]["payload"].__setitem__("baselineCommitment", "0x" + "77" * 32),
        lambda td: td["message"]["payload"].__setitem__("candidateCommitment", "0x" + "88" * 32),
        lambda td: td["message"]["contributors"][0].__setitem__("walletAddress", ADDRESS_A.lower()),
        lambda td: td["message"]["contributors"][0].__setitem__("weight", 6999),
        lambda td: td["message"]["contributors"].reverse(),
    ]

    for mutate in mutators:
        mutated = copy.deepcopy(typed_data)
        mutate(mutated)
        assert compute_digest(mutated) != original


def test_mutating_unsigned_wire_fields_does_not_change_digest() -> None:
    vector = _vector("single_contributor")
    wire_message = copy.deepcopy(vector["wire_message"])
    original = build_typed_data(MintRequest.model_validate(wire_message), _make_config(vector))

    wire_message["message_id"] = "different"
    wire_message["timestamp"] = "2026-01-01T00:00:00+00:00"
    wire_message["schema_version"] = "1.0"
    wire_message["attester_signatures"] = ["0x" + "90" * 65]
    mutated = build_typed_data(MintRequest.model_validate(wire_message), _make_config(vector))

    assert compute_digest(mutated) == compute_digest(original)


def test_render_for_human_uses_same_typed_data_and_ends_with_digest() -> None:
    typed_data = build_typed_data(
        _make_mint_request(),
        _make_config(_vector("single_contributor")),
    )
    digest_hex = f"0x{compute_digest(typed_data).hex()}"
    rendered = render_for_human(typed_data)

    assert json.loads(rendered.split("\n\ndigest:", 1)[0]) == typed_data
    assert rendered.endswith(f"digest: {digest_hex}")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("message", "modelId"), 999),
        (("message", "payload", "pipelineRunId"), "eval-mutated"),
        (("message", "payload", "baselineScoreBps"), 100),
        (("message", "payload", "candidateScoreBps"), 101),
        (("message", "payload", "maxCostUsdMicro"), 1),
        (("message", "payload", "actualCostUsdMicro"), 2),
        (("message", "payload", "totalSamples"), 3),
        (("message", "payload", "anchors", "benchmarkSpecHash"), "0x" + "11" * 32),
        (("message", "payload", "anchors", "datasetHash"), "0x" + "22" * 32),
        (("message", "payload", "anchors", "attestationHash"), "0x" + "33" * 32),
        (("message", "payload", "anchors", "idempotencyKey"), "0x" + "44" * 32),
        (("message", "payload", "anchors", "metricName"), "metric-2"),
        (("message", "payload", "anchors", "metricFamily"), "continuous"),
        (("message", "payload", "baselineCommitment"), "0x" + "55" * 32),
        (("message", "payload", "candidateCommitment"), "0x" + "66" * 32),
    ],
)
def test_mutating_signed_field_changes_render_and_digest(
    path: tuple[str, ...], value: object
) -> None:
    typed_data = build_typed_data(
        _make_mint_request(),
        _make_config(_vector("single_contributor")),
    )
    original_render = render_for_human(typed_data)
    original_digest = compute_digest(typed_data)
    mutated = copy.deepcopy(typed_data)

    target = mutated
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    assert render_for_human(mutated) != original_render
    assert compute_digest(mutated) != original_digest


def test_verify_signature_accepts_checksum_and_lowercase_expected_addresses() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config(_vector("single_contributor")))
    signature = _sign_typed_data(typed_data, PRIVATE_KEY_A)

    assert verify_signature(typed_data, signature, ADDRESS_A) is True
    assert verify_signature(typed_data, signature, ADDRESS_A.lower()) is True
    assert verify_signature(typed_data, signature, ADDRESS_B) is False


def test_verify_signature_malformed_hex_raises_typed_error() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config(_vector("single_contributor")))

    with pytest.raises(InvalidSignatureError, match="signature"):
        verify_signature(typed_data, "not-hex", ADDRESS_A)


def test_sort_signatures_orders_by_recovered_address_and_rejects_duplicates() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config(_vector("single_contributor")))
    sig_a = _sign_typed_data(typed_data, PRIVATE_KEY_A)
    sig_b = _sign_typed_data(typed_data, PRIVATE_KEY_B)
    sig_c = _sign_typed_data(typed_data, PRIVATE_KEY_C)

    shuffled = [sig_c, sig_a, sig_b]
    ordered = sort_signatures_by_signer(typed_data, shuffled)
    ordered_addresses = [recover_signer(typed_data, signature) for signature in ordered]

    assert ordered_addresses == sorted(
        address.lower() for address in [ADDRESS_A, ADDRESS_B, ADDRESS_C]
    )

    with pytest.raises(InvalidSignatureError, match="duplicate"):
        sort_signatures_by_signer(typed_data, [sig_a, sig_a])


def test_validate_signatures_against_registry_sorts_and_checks_threshold() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config(_vector("single_contributor")))
    sig_a = _sign_typed_data(typed_data, PRIVATE_KEY_A)
    sig_b = _sign_typed_data(typed_data, PRIVATE_KEY_B)

    ordered = validate_signatures_against_registry(
        typed_data,
        [sig_b, sig_a],
        registry_check=lambda address: address.lower() in {ADDRESS_A.lower(), ADDRESS_B.lower()},
        threshold=2,
    )

    assert [recover_signer(typed_data, signature).lower() for signature in ordered] == sorted(
        [ADDRESS_A.lower(), ADDRESS_B.lower()]
    )


def test_validate_signatures_against_registry_rejects_non_attester() -> None:
    typed_data = build_typed_data(_make_mint_request(), _make_config(_vector("single_contributor")))
    sig_a = _sign_typed_data(typed_data, PRIVATE_KEY_A)

    with pytest.raises(SignatureRegistryError, match="registered attester"):
        validate_signatures_against_registry(
            typed_data,
            [sig_a],
            registry_check=lambda _address: False,
            threshold=1,
        )


def test_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINT_CHAIN_ID", "8453")
    monkeypatch.setenv("MINT_VERIFYING_CONTRACT", "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC")

    config = MintRequestSigningConfig.from_env()

    assert config.chain_id == 8453
    assert config.verifying_contract == "0xcccccccccccccccccccccccccccccccccccccccc"
