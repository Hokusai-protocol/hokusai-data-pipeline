"""Shared provider-evidence validation and executed-endpoint economic projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.model_30.model_identity import hokusai_price_snapshot
from src.model_30.usage_cost import (
    finite_number,
    price_usage_by_model,
    usage_from_task_cost_segments,
)

FAULT_CLASSES = {
    "model-fault",
    "provider-fault",
    "harness-fault",
    "selection-fault",
    "unknown-fault",
}


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    """Mirror the owning SDK schema; conformance fixtures pin both consumers."""
    return Draft202012Validator(
        json.loads(Path(__file__).with_name("provider-execution.v1.schema.json").read_text())
    )


def _failure_errors(value: Any) -> list[str]:
    if (
        isinstance(value, dict)
        and set(value) == {"fault_class"}
        and isinstance(value["fault_class"], str)
        and value["fault_class"] in FAULT_CLASSES
    ):
        return []
    return ["failure must carry a valid fault class"]


def _entry_failure_errors(entry: Mapping[str, Any]) -> list[str]:
    return _failure_errors(entry["failure"]) if "failure" in entry else []


def execution_metadata_errors(entry: Mapping[str, Any]) -> list[str]:
    """Validate optional facts without broadening the stage's other allowed fields."""
    errors = _entry_failure_errors(entry)
    if "provider_executions" not in entry:
        return errors
    rows = entry["provider_executions"]
    if not isinstance(rows, list):
        return [*errors, "provider_executions must be an array"]
    seen: set[tuple[str, str, str]] = set()
    observations: set[str] = set()
    summary = entry.get("task_cost") if isinstance(entry.get("task_cost"), dict) else {}
    sessions = summary.get("session_ids", [])
    for index, row in enumerate(rows):
        violations = list(_validator().iter_errors(row))
        errors.extend(f"provider_executions[{index}]: {item.message}" for item in violations)
        if violations:
            continue
        if row.get("observationId"):
            if row["observationId"] in observations:
                errors.append("duplicate provider observation")
            observations.add(row["observationId"])
        if row["sessionRef"] not in sessions:
            errors.append("provider execution must belong to a stage session")
        if row["responseId"] is not None:
            key = (row["sessionRef"], row["transport"], row["responseId"])
            if key in seen:
                errors.append("duplicate provider response")
            seen.add(key)
    return errors


def provider_economics(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    """Preserve billed zeros and reprice unbilled turns through the existing price owner."""
    rows = entry.get("provider_executions")
    if not rows or execution_metadata_errors(entry):
        return None
    summary = entry.get("task_cost") or {}
    charges = [finite_number((row.get("generation") or {}).get("totalCostUsd")) for row in rows]
    billed = [charge for charge in charges if charge is not None]
    result = {
        "billed_cost_usd": round(sum(billed), 10) if billed else None,
        "charge_trust": "contributor_reported",
        "billing_coverage": "complete"
        if len(billed) == len(rows)
        else "partial"
        if billed
        else "unavailable",
        "cost_basis": "model_reference",
    }
    # Partial observations cannot allocate the entire stage or justify a total.
    if summary.get("harness") != "native" or len(rows) != summary.get("turn_count"):
        return {**result, "resolved_cost_usd": None, "cost_basis": "incomplete"}
    resolved: list[float] = []
    sources: set[str] = set()
    for row, charge in zip(rows, charges):
        if charge is not None and row["transport"] == "openrouter":
            resolved.append(charge)
            sources.add("provider_reported")
            continue
        usage = row.get("usage")
        if (
            not isinstance(usage, dict)
            or usage.get("input_tokens") is None
            or usage.get("output_tokens") is None
        ):
            return {**result, "resolved_cost_usd": None, "cost_basis": "incomplete"}
        model = row.get("responseModel") or entry.get("executed_model")
        snapshot = row.get("pricingSnapshot") or {}
        endpoint = snapshot.get("scope") == "endpoint"
        prices = {model: snapshot} if endpoint else hokusai_price_snapshot()
        priced = price_usage_by_model(
            usage_from_task_cost_segments([{"model": model, "usage": usage}]),
            prices,
            reprice="always",
        )
        if priced.unpriced or priced.partial:
            return {**result, "resolved_cost_usd": None, "cost_basis": "incomplete"}
        resolved.append(sum(bucket["cost"] for bucket in priced.per_model.values()))
        sources.add("endpoint_estimate" if endpoint else "model_reference")
    return {
        **result,
        "resolved_cost_usd": round(sum(resolved), 10),
        "cost_basis": next(iter(sources)) if len(sources) == 1 else "mixed",
    }
