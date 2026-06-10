"""Minimal JSON-RPC client for reading the on-chain mint baseline."""

from __future__ import annotations

import re
from typing import Any

import requests

_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")


class BaselineUnavailableError(RuntimeError):
    """Raised when the latest on-chain head cannot be resolved safely."""


def read_onchain_head(rpc_url: str, *, timeout: float = 5.0) -> str:
    """Return the latest block hash as a lowercase 0x-prefixed 64-hex string."""
    try:
        response = requests.post(
            rpc_url,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "method": "eth_getBlockByNumber",
                "params": ["latest", False],
                "id": 1,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BaselineUnavailableError(
            f"failed to read on-chain head from {rpc_url}: {exc}"
        ) from exc

    error = payload.get("error")
    if error is not None:
        raise BaselineUnavailableError(f"RPC error while reading on-chain head: {error}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise BaselineUnavailableError("RPC response missing latest block result object")

    return _extract_block_hash(result)


def _extract_block_hash(result: dict[str, Any]) -> str:
    block_hash = result.get("hash")
    if not isinstance(block_hash, str):
        raise BaselineUnavailableError("latest block response missing hash")
    normalized = block_hash.lower()
    if not _BYTES32_RE.match(normalized):
        raise BaselineUnavailableError(
            f"latest block hash must be 0x-prefixed 64-hex, got {block_hash!r}"
        )
    return normalized
