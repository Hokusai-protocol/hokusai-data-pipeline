"""EIP-712 helpers for DeltaVerifier MintRequest attester signing."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data
from eth_utils import keccak

from src.events.schemas import MintRequest

_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")

DOMAIN_NAME = "HokusaiDeltaVerifier"
DOMAIN_VERSION = "1"
PRIMARY_TYPE = "MintRequest"
DOMAIN_TYPES = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
BENCHMARK_ANCHORS_TYPES = [
    {"name": "benchmarkSpecHash", "type": "bytes32"},
    {"name": "datasetHash", "type": "bytes32"},
    {"name": "attestationHash", "type": "bytes32"},
    {"name": "idempotencyKey", "type": "bytes32"},
    {"name": "metricName", "type": "string"},
    {"name": "metricFamily", "type": "string"},
]
CONTRIBUTOR_TYPES = [
    {"name": "walletAddress", "type": "address"},
    {"name": "weight", "type": "uint256"},
]
MINT_REQUEST_PAYLOAD_TYPES = [
    {"name": "pipelineRunId", "type": "string"},
    {"name": "baselineScoreBps", "type": "uint256"},
    {"name": "candidateScoreBps", "type": "uint256"},
    {"name": "maxCostUsdMicro", "type": "uint256"},
    {"name": "actualCostUsdMicro", "type": "uint256"},
    {"name": "totalSamples", "type": "uint256"},
    {"name": "anchors", "type": "BenchmarkAnchors"},
    {"name": "baselineCommitment", "type": "bytes32"},
    {"name": "candidateCommitment", "type": "bytes32"},
]
MINT_REQUEST_TYPES = [
    {"name": "modelId", "type": "uint256"},
    {"name": "payload", "type": "MintRequestPayload"},
    {"name": "contributors", "type": "Contributor[]"},
]


class MintRequestSigningError(ValueError):
    """Base error for MintRequest typed-data/signature validation."""


class InvalidSignatureError(MintRequestSigningError):
    """Raised when a signature cannot be parsed or recovered."""


@dataclass(frozen=True)
class MintRequestSigningConfig:
    """Runtime configuration for the DeltaVerifier EIP-712 signing domain."""

    chain_id: int
    verifying_contract: str
    attester_address: str

    @classmethod
    def from_env(cls: type[MintRequestSigningConfig]) -> MintRequestSigningConfig:
        raw_chain_id = os.getenv("MINT_CHAIN_ID")
        verifying_contract = os.getenv("MINT_VERIFYING_CONTRACT")
        attester_address = os.getenv("MINT_ATTESTER_ADDRESS")

        missing = [
            name
            for name, value in (
                ("MINT_CHAIN_ID", raw_chain_id),
                ("MINT_VERIFYING_CONTRACT", verifying_contract),
                ("MINT_ATTESTER_ADDRESS", attester_address),
            )
            if value is None or not str(value).strip()
        ]
        if missing:
            raise MintRequestSigningError(
                "Mint request signing config missing required environment variables: "
                + ", ".join(sorted(missing))
            )

        try:
            chain_id = int(str(raw_chain_id))
        except (TypeError, ValueError) as exc:
            raise MintRequestSigningError(
                f"MINT_CHAIN_ID must be an integer, got {raw_chain_id!r}"
            ) from exc
        if chain_id <= 0:
            raise MintRequestSigningError(f"MINT_CHAIN_ID must be positive, got {chain_id}")

        return cls(
            chain_id=chain_id,
            verifying_contract=_normalize_address(
                str(verifying_contract), field_name="MINT_VERIFYING_CONTRACT"
            ),
            attester_address=_normalize_address(
                str(attester_address), field_name="MINT_ATTESTER_ADDRESS"
            ),
        )


def build_typed_data(mint_request: MintRequest, config: MintRequestSigningConfig) -> dict[str, Any]:
    """Build the contract-canonical MintRequest EIP-712 payload."""
    if mint_request.baseline_commitment is None:
        raise MintRequestSigningError(
            "MintRequest.baseline_commitment is required for MintRequest signing"
        )
    if mint_request.candidate_commitment is None:
        raise MintRequestSigningError(
            "MintRequest.candidate_commitment is required for MintRequest signing"
        )
    if not mint_request.contributors:
        raise MintRequestSigningError("MintRequest.contributors must be non-empty for signing")

    evaluation = mint_request.evaluation
    anchors = {
        "benchmarkSpecHash": _benchmark_spec_hash(mint_request.benchmark_spec_id),
        "datasetHash": _normalize_bytes32(mint_request.dataset_hash, field_name="datasetHash"),
        "attestationHash": _normalize_bytes32(
            mint_request.attestation_hash, field_name="attestationHash"
        ),
        "idempotencyKey": _normalize_bytes32(
            mint_request.idempotency_key, field_name="idempotencyKey"
        ),
        "metricName": _require_non_empty(evaluation.metric_name, field_name="metricName"),
        "metricFamily": _require_non_empty(evaluation.metric_family, field_name="metricFamily"),
    }
    message = {
        "modelId": int(mint_request.model_id_uint),
        "payload": {
            "pipelineRunId": _require_non_empty(mint_request.eval_id, field_name="pipelineRunId"),
            "baselineScoreBps": int(evaluation.baseline_score_bps),
            "candidateScoreBps": int(evaluation.new_score_bps),
            "maxCostUsdMicro": int(evaluation.max_cost_usd_micro),
            "actualCostUsdMicro": int(evaluation.actual_cost_usd_micro),
            "totalSamples": int(mint_request.total_samples),
            "anchors": anchors,
            "baselineCommitment": _normalize_bytes32(
                mint_request.baseline_commitment, field_name="baselineCommitment"
            ),
            "candidateCommitment": _normalize_bytes32(
                mint_request.candidate_commitment, field_name="candidateCommitment"
            ),
        },
        "contributors": [
            {
                "walletAddress": _normalize_address(
                    contributor.wallet_address, field_name=f"contributors[{index}].walletAddress"
                ),
                "weight": int(contributor.weight_bps),
            }
            for index, contributor in enumerate(mint_request.contributors)
        ],
    }

    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            "MintRequest": list(MINT_REQUEST_TYPES),
            "MintRequestPayload": list(MINT_REQUEST_PAYLOAD_TYPES),
            "BenchmarkAnchors": list(BENCHMARK_ANCHORS_TYPES),
            "Contributor": list(CONTRIBUTOR_TYPES),
        },
        "primaryType": PRIMARY_TYPE,
        "domain": {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": config.chain_id,
            "verifyingContract": _normalize_address(
                config.verifying_contract, field_name="verifyingContract"
            ),
        },
        "message": message,
    }


def compute_digest(typed_data: dict[str, Any]) -> bytes:
    """Compute the exact digest verified by DeltaVerifier.hashMintRequest()."""
    normalized = _normalize_typed_data(typed_data)
    return bytes(_hash_eip191_message(encode_typed_data(full_message=normalized)))


def render_for_human(typed_data: dict[str, Any]) -> str:
    """Render normalized typed data and the final digest."""
    normalized = _normalize_typed_data(typed_data)
    digest_hex = f"0x{compute_digest(normalized).hex()}"
    return f"{json.dumps(normalized, indent=2)}\n\ndigest: {digest_hex}"


def verify_signature(
    typed_data: dict[str, Any],
    signature_hex: str,
    expected_address: str,
) -> bool:
    """Verify a signature against typed data, raising typed errors for malformed input."""
    recovered = recover_signer(typed_data, signature_hex)
    return (
        recovered.lower()
        == _normalize_address(expected_address, field_name="expected_address").lower()
    )


def recover_signer(typed_data: dict[str, Any], signature_hex: str) -> str:
    """Recover the signer address for a typed-data signature."""
    signable_message = encode_typed_data(full_message=_normalize_typed_data(typed_data))
    normalized_signature = _normalize_signature_hex(signature_hex)
    try:
        recovered = Account.recover_message(
            signable_message,
            signature=bytes.fromhex(normalized_signature.removeprefix("0x")),
        )
    except Exception as exc:  # noqa: BLE001
        raise InvalidSignatureError("signature could not be recovered") from exc
    return _normalize_address(recovered, field_name="recovered_signer")


def sort_signatures_by_signer(typed_data: dict[str, Any], signatures: list[str]) -> list[str]:
    """Sort signatures by strictly ascending recovered signer address and reject duplicates."""
    recovered_pairs = [
        (recover_signer(typed_data, signature).lower(), _normalize_signature_hex(signature))
        for signature in signatures
    ]
    recovered_pairs.sort(key=lambda item: item[0])
    ordered_addresses = [address for address, _ in recovered_pairs]
    if len(set(ordered_addresses)) != len(ordered_addresses):
        raise InvalidSignatureError("duplicate recovered signer addresses are not allowed")
    return [signature for _, signature in recovered_pairs]


def _normalize_typed_data(typed_data: dict[str, Any]) -> dict[str, Any]:
    domain = typed_data.get("domain") or {}
    message = typed_data.get("message") or {}
    payload = message.get("payload") or {}
    anchors = payload.get("anchors") or {}
    contributors = message.get("contributors") or []

    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            "MintRequest": list(MINT_REQUEST_TYPES),
            "MintRequestPayload": list(MINT_REQUEST_PAYLOAD_TYPES),
            "BenchmarkAnchors": list(BENCHMARK_ANCHORS_TYPES),
            "Contributor": list(CONTRIBUTOR_TYPES),
        },
        "primaryType": PRIMARY_TYPE,
        "domain": {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": int(domain["chainId"]),
            "verifyingContract": _normalize_address(
                str(domain["verifyingContract"]), field_name="verifyingContract"
            ),
        },
        "message": {
            "modelId": int(message["modelId"]),
            "payload": {
                "pipelineRunId": _require_non_empty(
                    str(payload["pipelineRunId"]), field_name="pipelineRunId"
                ),
                "baselineScoreBps": int(payload["baselineScoreBps"]),
                "candidateScoreBps": int(payload["candidateScoreBps"]),
                "maxCostUsdMicro": int(payload["maxCostUsdMicro"]),
                "actualCostUsdMicro": int(payload["actualCostUsdMicro"]),
                "totalSamples": int(payload["totalSamples"]),
                "anchors": {
                    "benchmarkSpecHash": _normalize_bytes32(
                        str(anchors["benchmarkSpecHash"]), field_name="benchmarkSpecHash"
                    ),
                    "datasetHash": _normalize_bytes32(
                        str(anchors["datasetHash"]), field_name="datasetHash"
                    ),
                    "attestationHash": _normalize_bytes32(
                        str(anchors["attestationHash"]), field_name="attestationHash"
                    ),
                    "idempotencyKey": _normalize_bytes32(
                        str(anchors["idempotencyKey"]), field_name="idempotencyKey"
                    ),
                    "metricName": _require_non_empty(
                        str(anchors["metricName"]), field_name="metricName"
                    ),
                    "metricFamily": _require_non_empty(
                        str(anchors["metricFamily"]), field_name="metricFamily"
                    ),
                },
                "baselineCommitment": _normalize_bytes32(
                    str(payload["baselineCommitment"]), field_name="baselineCommitment"
                ),
                "candidateCommitment": _normalize_bytes32(
                    str(payload["candidateCommitment"]), field_name="candidateCommitment"
                ),
            },
            "contributors": [
                {
                    "walletAddress": _normalize_address(
                        str(contributor["walletAddress"]),
                        field_name=f"contributors[{index}].walletAddress",
                    ),
                    "weight": int(contributor["weight"]),
                }
                for index, contributor in enumerate(contributors)
            ],
        },
    }


def _benchmark_spec_hash(benchmark_spec_id: str) -> str:
    benchmark_spec = _require_non_empty(benchmark_spec_id, field_name="benchmarkSpecId")
    return f"0x{keccak(text=benchmark_spec).hex()}"


def _require_non_empty(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise MintRequestSigningError(f"{field_name} must be non-empty")
    return stripped


def _normalize_address(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    lowered = stripped.lower()
    if not _ETH_ADDRESS_RE.match(lowered):
        raise MintRequestSigningError(
            f"{field_name} must be a 0x-prefixed 40-hex address, got {value!r}"
        )
    return lowered


def _normalize_bytes32(value: str, *, field_name: str) -> str:
    lowered = value.strip().lower()
    if not _BYTES32_RE.match(lowered):
        raise MintRequestSigningError(
            f"{field_name} must be a 0x-prefixed lowercase 64-hex value, got {value!r}"
        )
    return lowered


def _normalize_signature_hex(signature_hex: str) -> str:
    stripped = signature_hex.strip()
    if not stripped.startswith("0x"):
        raise InvalidSignatureError("signature must be 0x-prefixed hex")
    body = stripped.removeprefix("0x")
    if len(body) != 130:
        raise InvalidSignatureError(f"signature must be 65 bytes (130 hex chars), got {len(body)}")
    try:
        bytes.fromhex(body)
    except ValueError as exc:
        raise InvalidSignatureError("signature must be valid hexadecimal") from exc
    return f"0x{body.lower()}"
