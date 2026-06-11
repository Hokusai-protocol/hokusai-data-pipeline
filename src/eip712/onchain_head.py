"""Minimal JSON-RPC client for reading the on-chain MintRequest lineage head."""

from __future__ import annotations

import re

import requests
from eth_utils import keccak

_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_UINT_RE = re.compile(r"^[1-9]\d*$")
_CURRENT_MODEL_HEAD_SELECTOR = keccak(text="currentModelHead(uint256)")[:4].hex()


class BaselineUnavailableError(RuntimeError):
    """Raised when the canonical on-chain lineage head cannot be resolved safely."""


def read_current_model_head(
    rpc_url: str,
    *,
    contract_address: str,
    model_id_uint: str,
    timeout: float = 5.0,
) -> str:
    """Return DeltaVerifier.currentModelHead(modelId) as a lowercase 0x-prefixed bytes32."""
    normalized_contract = _normalize_address(contract_address)
    calldata = _build_current_model_head_calldata(model_id_uint)

    try:
        response = requests.post(
            rpc_url,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": normalized_contract, "data": calldata}, "latest"],
                "id": 1,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BaselineUnavailableError(
            f"failed to read currentModelHead({model_id_uint}) from {rpc_url}: {exc}"
        ) from exc

    error = payload.get("error")
    if error is not None:
        raise BaselineUnavailableError(f"RPC error while reading currentModelHead: {error}")

    result = payload.get("result")
    if not isinstance(result, str):
        raise BaselineUnavailableError("RPC response missing eth_call result")

    normalized = result.lower()
    if not _BYTES32_RE.match(normalized):
        raise BaselineUnavailableError(f"currentModelHead returned non-bytes32 value: {result!r}")
    if normalized == "0x" + "0" * 64:
        raise BaselineUnavailableError(
            f"currentModelHead({model_id_uint}) returned zero; model genesis is not seeded"
        )
    return normalized


def _build_current_model_head_calldata(model_id_uint: str) -> str:
    if not _UINT_RE.match(model_id_uint):
        raise BaselineUnavailableError(
            f"model_id_uint must be a positive decimal string, got {model_id_uint!r}"
        )
    encoded_model_id = f"{int(model_id_uint):064x}"
    return f"0x{_CURRENT_MODEL_HEAD_SELECTOR}{encoded_model_id}"


def _normalize_address(value: str) -> str:
    stripped = value.strip()
    lowered = stripped.lower()
    if not _ADDRESS_RE.match(lowered):
        raise BaselineUnavailableError(
            f"contract address must be a 0x-prefixed 40-hex address, got {value!r}"
        )
    return lowered
