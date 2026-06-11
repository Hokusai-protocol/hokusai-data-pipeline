"""EIP-712 helpers for attester-authorized MintRequest payloads."""

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
MESSAGE_TYPES = {
    "MintRequest": [
        {"name": "modelId", "type": "uint256"},
        {"name": "payload", "type": "MintRequestPayload"},
        {"name": "contributors", "type": "Contributor[]"},
    ],
    "MintRequestPayload": [
        {"name": "pipelineRunId", "type": "string"},
        {"name": "baselineScoreBps", "type": "uint256"},
        {"name": "candidateScoreBps", "type": "uint256"},
        {"name": "maxCostUsdMicro", "type": "uint256"},
        {"name": "actualCostUsdMicro", "type": "uint256"},
        {"name": "totalSamples", "type": "uint256"},
        {"name": "anchors", "type": "BenchmarkAnchors"},
        {"name": "baselineCommitment", "type": "bytes32"},
        {"name": "candidateCommitment", "type": "bytes32"},
    ],
    "BenchmarkAnchors": [
        {"name": "benchmarkSpecHash", "type": "bytes32"},
        {"name": "datasetHash", "type": "bytes32"},
        {"name": "attestationHash", "type": "bytes32"},
        {"name": "idempotencyKey", "type": "bytes32"},
        {"name": "metricName", "type": "string"},
        {"name": "metricFamily", "type": "string"},
    ],
    "Contributor": [
        {"name": "walletAddress", "type": "address"},
        {"name": "weight", "type": "uint256"},
    ],
}


@dataclass(frozen=True)
class MintAuthorizationConfig:
    """Runtime configuration for the MintRequest EIP-712 domain."""

    chain_id: int
    verifying_contract: str
    attester_address: str

    @classmethod
    def from_env(cls: type[MintAuthorizationConfig]) -> MintAuthorizationConfig:
        """Build configuration from required mint-authorization environment variables."""
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
            raise ValueError(
                "Mint authorization config missing required environment variables: "
                + ", ".join(sorted(missing))
            )

        try:
            chain_id = int(str(raw_chain_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MINT_CHAIN_ID must be an integer, got {raw_chain_id!r}") from exc
        if chain_id <= 0:
            raise ValueError(f"MINT_CHAIN_ID must be positive, got {chain_id}")

        return cls(
            chain_id=chain_id,
            verifying_contract=_normalize_address(
                str(verifying_contract), field_name="MINT_VERIFYING_CONTRACT"
            ),
            attester_address=_normalize_address(
                str(attester_address), field_name="MINT_ATTESTER_ADDRESS"
            ),
        )


def build_typed_data(mint_request: MintRequest, config: MintAuthorizationConfig) -> dict[str, Any]:
    """Build the exact typed-data dict the token contract verifies."""
    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            **{name: list(fields) for name, fields in MESSAGE_TYPES.items()},
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
        "message": _build_message(mint_request),
    }


def compute_digest(typed_data: dict[str, Any]) -> bytes:
    """Compute the 32-byte EIP-712 digest for a typed-data payload."""
    return bytes(_hash_eip191_message(encode_typed_data(full_message=typed_data)))


def render_for_human(typed_data: dict[str, Any]) -> str:
    """Render the exact typed data alongside the digest derived from it."""
    normalized = _normalize_typed_data(typed_data)
    digest_hex = f"0x{compute_digest(normalized).hex()}"
    exact_json = json.dumps(normalized, indent=2)
    return f"{exact_json}\n\ndigest: {digest_hex}"


def verify_signature(
    typed_data: dict[str, Any],
    signature_hex: str,
    expected_address: str,
) -> bool:
    """Verify that the signature signs the typed data and recovers the expected address."""
    signable_message = encode_typed_data(full_message=_normalize_typed_data(typed_data))
    normalized_signature = _normalize_signature_hex(signature_hex)
    recovered = Account.recover_message(
        signable_message,
        signature=bytes.fromhex(normalized_signature.removeprefix("0x")),
    )
    return (
        recovered.lower()
        == _normalize_address(expected_address, field_name="expected_address").lower()
    )


def _build_message(mint_request: MintRequest) -> dict[str, Any]:
    return {
        "modelId": int(mint_request.model_id_uint),
        "payload": {
            "pipelineRunId": mint_request.eval_id,
            "baselineScoreBps": mint_request.evaluation.baseline_score_bps,
            "candidateScoreBps": mint_request.evaluation.new_score_bps,
            "maxCostUsdMicro": mint_request.evaluation.max_cost_usd_micro,
            "actualCostUsdMicro": mint_request.evaluation.actual_cost_usd_micro,
            "totalSamples": mint_request.total_samples,
            "anchors": {
                "benchmarkSpecHash": f"0x{keccak(text=mint_request.benchmark_spec_id).hex()}",
                "datasetHash": _normalize_bytes32(
                    mint_request.dataset_hash, field_name="datasetHash"
                ),
                "attestationHash": _normalize_bytes32(
                    mint_request.attestation_hash, field_name="attestationHash"
                ),
                "idempotencyKey": _normalize_bytes32(
                    mint_request.idempotency_key, field_name="idempotencyKey"
                ),
                "metricName": mint_request.evaluation.metric_name,
                "metricFamily": mint_request.evaluation.metric_family,
            },
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
                    contributor.wallet_address, field_name="contributors.walletAddress"
                ),
                "weight": contributor.weight_bps,
            }
            for contributor in mint_request.contributors
        ],
    }


def _normalize_typed_data(typed_data: dict[str, Any]) -> dict[str, Any]:
    domain = typed_data.get("domain") or {}
    message = typed_data.get("message") or {}
    payload = message.get("payload") or {}
    anchors = payload.get("anchors") or {}
    contributors = message.get("contributors") or []

    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            **{name: list(fields) for name, fields in MESSAGE_TYPES.items()},
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
                "pipelineRunId": str(payload["pipelineRunId"]),
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
                    "metricName": str(anchors["metricName"]),
                    "metricFamily": str(anchors["metricFamily"]),
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
                        str(contributor["walletAddress"]), field_name="contributors.walletAddress"
                    ),
                    "weight": int(contributor["weight"]),
                }
                for contributor in contributors
            ],
        },
    }


def _normalize_address(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    lowered = stripped.lower()
    if not _ETH_ADDRESS_RE.match(lowered):
        raise ValueError(f"{field_name} must be a 0x-prefixed 40-hex address, got {value!r}")
    return lowered


def _normalize_bytes32(value: str, *, field_name: str) -> str:
    lowered = value.strip().lower()
    if not _BYTES32_RE.match(lowered):
        raise ValueError(
            f"{field_name} must be a 0x-prefixed lowercase 64-hex value, got {value!r}"
        )
    return lowered


def _normalize_signature_hex(signature_hex: str) -> str:
    stripped = signature_hex.strip()
    if not stripped.startswith("0x"):
        raise ValueError("signature must be 0x-prefixed hex")
    body = stripped.removeprefix("0x")
    if len(body) != 130:
        raise ValueError(f"signature must be 65 bytes (130 hex chars), got {len(body)}")
    try:
        bytes.fromhex(body)
    except ValueError as exc:
        raise ValueError("signature must be valid hexadecimal") from exc
    return f"0x{body.lower()}"
