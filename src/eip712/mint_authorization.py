"""EIP-712 helpers for attester-authorized mint requests."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data

from src.events.schemas import MintRequest

_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")

DOMAIN_NAME = "HokusaiMintAuthority"
DOMAIN_VERSION = "1"
PRIMARY_TYPE = "MintAuthorization"
DOMAIN_TYPES = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
MESSAGE_TYPES = [
    {"name": "modelIdUint", "type": "uint256"},
    {"name": "baselineCommitment", "type": "bytes32"},
    {"name": "candidateCommitment", "type": "bytes32"},
    {"name": "baseline", "type": "bytes32"},
    {"name": "attestationHash", "type": "bytes32"},
    {"name": "totalSamples", "type": "uint256"},
]


@dataclass(frozen=True)
class MintAuthorizationConfig:
    """Runtime configuration for the MintAuthorization EIP-712 domain."""

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
    """Build the full EIP-712 typed-data dict from a MintRequest."""
    if mint_request.baseline_commitment is None:
        raise ValueError("MintRequest.baseline_commitment is required for mint authorization")
    if mint_request.candidate_commitment is None:
        raise ValueError("MintRequest.candidate_commitment is required for mint authorization")
    if mint_request.baseline is None:
        raise ValueError("MintRequest.baseline is required for mint authorization")

    message = {
        "modelIdUint": int(mint_request.model_id_uint),
        "baselineCommitment": _normalize_bytes32(
            mint_request.baseline_commitment, field_name="baselineCommitment"
        ),
        "candidateCommitment": _normalize_bytes32(
            mint_request.candidate_commitment, field_name="candidateCommitment"
        ),
        "baseline": _normalize_bytes32(mint_request.baseline, field_name="baseline"),
        "attestationHash": _normalize_bytes32(
            mint_request.attestation_hash, field_name="attestationHash"
        ),
        "totalSamples": mint_request.total_samples,
    }

    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            PRIMARY_TYPE: list(MESSAGE_TYPES),
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


def _normalize_typed_data(typed_data: dict[str, Any]) -> dict[str, Any]:
    domain = typed_data.get("domain") or {}
    message = typed_data.get("message") or {}
    return {
        "types": {
            "EIP712Domain": list(DOMAIN_TYPES),
            PRIMARY_TYPE: list(MESSAGE_TYPES),
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
            "modelIdUint": int(message["modelIdUint"]),
            "baselineCommitment": _normalize_bytes32(
                str(message["baselineCommitment"]), field_name="baselineCommitment"
            ),
            "candidateCommitment": _normalize_bytes32(
                str(message["candidateCommitment"]), field_name="candidateCommitment"
            ),
            "baseline": _normalize_bytes32(str(message["baseline"]), field_name="baseline"),
            "attestationHash": _normalize_bytes32(
                str(message["attestationHash"]), field_name="attestationHash"
            ),
            "totalSamples": int(message["totalSamples"]),
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
