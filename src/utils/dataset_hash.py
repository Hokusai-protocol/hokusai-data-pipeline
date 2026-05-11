"""Helpers for canonical dataset hash and dataset_version handling."""

from __future__ import annotations

import re

SHA256_DATASET_VERSION_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def format_sha256_dataset_version(hex_digest: str) -> str:
    """Return canonical ``sha256:<hex>`` form for a lowercase 64-hex digest."""
    if not isinstance(hex_digest, str) or not _SHA256_HEX_RE.fullmatch(hex_digest):
        raise ValueError("sha256 hex digest must be 64 lowercase hexadecimal characters")
    return f"sha256:{hex_digest}"


def is_canonical_sha256_dataset_version(value: object) -> bool:
    """Return whether *value* is exactly ``sha256:<64 lowercase hex>``."""
    return isinstance(value, str) and SHA256_DATASET_VERSION_RE.fullmatch(value) is not None


def parse_sha256_dataset_version(value: object) -> str | None:
    """Return canonical dataset_version when valid, otherwise ``None``."""
    if not is_canonical_sha256_dataset_version(value):
        return None
    return value
