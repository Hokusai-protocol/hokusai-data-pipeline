"""Output formatters for `hoku eval` command results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _to_ci_value(value: Any) -> str:
    """Convert arbitrary values to single-token CI-safe strings."""
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def format_json(payload: Mapping[str, Any]) -> str:
    """Format payload as pretty JSON."""
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ci(payload: Mapping[str, Any]) -> str:
    """Format payload as compact CI-friendly `key=value` output."""
    pairs: list[str] = []
    for key in sorted(payload):
        pairs.append(f"{key}={_to_ci_value(payload[key])}")
    return " ".join(pairs)


def format_human(payload: Mapping[str, Any]) -> str:
    """Format payload for terminal-readable output."""
    lines: list[str] = []
    status = payload.get("status", "unknown")
    lines.append(f"Status: {status}")

    if "run_id" in payload and payload["run_id"]:
        lines.append(f"Run ID: {payload['run_id']}")

    if "message" in payload and payload["message"]:
        lines.append(f"Message: {payload['message']}")

    if "cost_usd" in payload and payload["cost_usd"] is not None:
        lines.append(f"Cost (USD): {payload['cost_usd']}")

    if "attestation_hash" in payload and payload["attestation_hash"]:
        lines.append(f"Attestation: {payload['attestation_hash']}")

    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        lines.append("Metrics:")
        for key in sorted(metrics):
            lines.append(f"  - {key}: {metrics[key]}")

    plan = payload.get("plan")
    if isinstance(plan, Mapping):
        lines.append("Plan:")
        for key in sorted(plan):
            lines.append(f"  - {key}: {plan[key]}")

    return "\n".join(lines)


def format_output(output_format: str, payload: Mapping[str, Any]) -> str:
    """Render payload for one of the supported output formats."""
    if output_format == "json":
        return format_json(payload)
    if output_format == "ci":
        return format_ci(payload)
    return format_human(payload)
