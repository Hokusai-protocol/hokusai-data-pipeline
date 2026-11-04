"""Price per-model token usage: the one answer to "what did this task cost?" (HOK-3413).

Used by the offline Wavemill collector (``scripts/model_30/executed_route.py``)
and, from HOK-3413 on, by server-side ingestion of ``technical_task_router_row/v4``
rows. Both read usage in one shape: ``{model_id: {inputTokens, outputTokens,
cacheReadTokens, cacheCreationTokens, costUsd?, cacheSemantics?}}``.

``usage_from_task_cost_segments`` maps the SDK's ``TaskCostSummaryV1.model_segments``
into that shape. The SDK contract (``@hokusai/core`` task-cost README) makes the
buckets disjoint: ``input_tokens`` excludes cache reads and writes, and
``reasoning_tokens`` is a reporting-only breakdown of ``output_tokens``, so it is
never billed on top.

A model with no price is **unknown cost**, never free.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from src.model_30.model_identity import (
    exclusive_cache_usage,
    is_junk_model_id,
    normalize_model_id,
    priced_usage_cost,
    resolve_price,
)

TOKEN_KEYS = ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")
# SDK TaskCostTokenUsage field -> collector usage key. reasoning_tokens is omitted on
# purpose: it is already inside output_tokens.
_SDK_TOKEN_FIELDS = {
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "cache_read_tokens": "cacheReadTokens",
    "cache_write_tokens": "cacheCreationTokens",
}
# Counters that must be reported for a model's cost to be complete.
_REQUIRED_SDK_FIELDS = ("input_tokens", "output_tokens")

RepricePolicy = Literal["unpriced_only", "always"]


@dataclass
class PricedUsage:
    """Per-model token buckets and cost for one task.

    ``per_model[model]`` has ``input``, ``cache`` (reads + writes), ``output``,
    ``cost`` and ``unknown`` (1.0 when the model's cost could not be priced).
    """

    per_model: dict[str, dict[str, float]] = field(default_factory=dict)
    repriced: list[str] = field(default_factory=list)
    unpriced: list[str] = field(default_factory=list)
    # Models with a required counter not reported (SDK ``null``): cost is a lower bound.
    partial: list[str] = field(default_factory=list)


def finite_number(value: Any) -> float | None:
    """Return *value* as a finite float, or None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def price_usage_by_model(
    usage: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None = None,
    *,
    reprice: RepricePolicy = "unpriced_only",
) -> PricedUsage:
    """Price each model's tokens; aggregate by public model id.

    ``reprice="unpriced_only"`` (the Wavemill collector) keeps a cost the record
    already carries and prices only usage recorded at $0, plus OpenAI usage whose
    cached input was double-counted (see ``exclusive_cache_usage``).
    ``reprice="always"`` (server ingestion) ignores any contributor-reported cost
    and prices every model from tokens with Hokusai's price table.
    """
    snapshot = dict(snapshot or {})
    result = PricedUsage()
    for raw_model, model_usage in usage.items():
        if not isinstance(model_usage, dict) or is_junk_model_id(raw_model):
            continue
        model = normalize_model_id(raw_model)
        model_usage, inclusive = exclusive_cache_usage(raw_model, model_usage)
        cost: float | None = finite_number(model_usage.get("costUsd")) or 0.0
        tokens = sum(finite_number(model_usage.get(key)) or 0.0 for key in TOKEN_KEYS)
        if (reprice == "always" or cost <= 0 or inclusive) and tokens > 0:
            price = resolve_price(raw_model, snapshot)
            cost = None if price is None else priced_usage_cost(model_usage, price)
            (result.unpriced if price is None else result.repriced).append(model)
        elif reprice == "always":
            cost = 0.0
        if model_usage.get("partial") is True:
            result.partial.append(model)
        bucket = result.per_model.setdefault(
            model, {"input": 0.0, "cache": 0.0, "output": 0.0, "cost": 0.0, "unknown": 0.0}
        )
        bucket["input"] += finite_number(model_usage.get("inputTokens")) or 0.0
        bucket["cache"] += (finite_number(model_usage.get("cacheReadTokens")) or 0.0) + (
            finite_number(model_usage.get("cacheCreationTokens")) or 0.0
        )
        bucket["output"] += finite_number(model_usage.get("outputTokens")) or 0.0
        if cost is None:
            bucket["unknown"] = 1.0
        else:
            bucket["cost"] += cost
    return result


def usage_from_task_cost_segments(
    segments: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map ``TaskCostSummaryV1.model_segments`` to the collector usage shape.

    Segments for the same model are summed. Buckets are exclusive by contract, so
    the result is marked ``cacheSemantics: "exclusive"``. A segment whose input or
    output counter is ``null`` (not reported) marks the model ``partial``.
    Contributor-reported costs are carried as ``costUsd`` for reference only;
    ingestion prices with ``reprice="always"``.
    """
    usage: dict[str, dict[str, Any]] = {}
    for segment in segments:
        model = segment.get("model")
        if not isinstance(model, str) or not model.strip():
            continue
        tokens = segment.get("usage") if isinstance(segment.get("usage"), Mapping) else {}
        entry = usage.setdefault(
            model,
            {**{key: 0.0 for key in _SDK_TOKEN_FIELDS.values()}, "cacheSemantics": "exclusive"},
        )
        for sdk_field, key in _SDK_TOKEN_FIELDS.items():
            entry[key] += finite_number(tokens.get(sdk_field)) or 0.0
        if any(finite_number(tokens.get(f)) is None for f in _REQUIRED_SDK_FIELDS):
            entry["partial"] = True
        reported = finite_number(segment.get("actual_cost_usd"))
        if reported is not None:
            entry["costUsd"] = (finite_number(entry.get("costUsd")) or 0.0) + reported
    return usage
