"""HOK-3413: one token-usage pricing path for the collector and server ingestion."""

from __future__ import annotations

import pytest

from src.model_30.model_identity import resolve_price
from src.model_30.usage_cost import price_usage_by_model, usage_from_task_cost_segments

GPT = "gpt-5.4"  # catalog: $2.50 / $15 per MTok, no cache rate -> 0.1 x input


def _segment(model: str, **usage: float | None) -> dict:
    base = {
        "input_tokens": None,
        "output_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens": None,
    }
    return {
        "model": model,
        "turn_count": 1,
        "usage": {**base, **usage},
        "actual_cost_usd": None,
        "estimated_cost_usd": None,
        "cost_source": "none",
    }


def test_sdk_segments_are_exclusive_and_never_bill_reasoning() -> None:
    usage = usage_from_task_cost_segments(
        [
            _segment(
                GPT,
                input_tokens=100_000,
                output_tokens=20_000,
                cache_read_tokens=1_000_000,
                cache_write_tokens=0,
                reasoning_tokens=5_000,
            )
        ]
    )
    priced = price_usage_by_model(usage, reprice="always")
    price = resolve_price(GPT)
    assert price is not None
    # input already excludes cache (SDK contract): no subtraction; reasoning is in output.
    expected = (
        100_000 * price.input_per_token
        + 20_000 * price.output_per_token
        + 1_000_000 * 0.1 * price.input_per_token
    )
    assert priced.per_model[GPT]["cost"] == pytest.approx(expected)
    assert priced.per_model[GPT]["output"] == 20_000
    assert priced.repriced == [GPT]
    assert priced.partial == []


def test_always_ignores_contributor_reported_cost() -> None:
    segment = _segment(GPT, input_tokens=1_000, output_tokens=1_000, cache_read_tokens=0)
    segment["actual_cost_usd"] = 999.0
    usage = usage_from_task_cost_segments([segment])
    kept = price_usage_by_model(usage)
    repriced = price_usage_by_model(usage, reprice="always")
    assert kept.per_model[GPT]["cost"] == 999.0
    assert repriced.per_model[GPT]["cost"] == pytest.approx(1_000 * 2.5e-6 + 1_000 * 15e-6)


def test_segments_for_one_model_are_summed_across_spellings() -> None:
    usage = usage_from_task_cost_segments(
        [
            _segment("openai/gpt-5.4", input_tokens=10, output_tokens=1),
            _segment("gpt-5.4", input_tokens=5, output_tokens=2),
        ]
    )
    priced = price_usage_by_model(usage, reprice="always")
    assert set(priced.per_model) == {GPT}
    assert priced.per_model[GPT]["input"] == 15
    assert priced.per_model[GPT]["output"] == 3


def test_unreported_counter_marks_model_partial() -> None:
    usage = usage_from_task_cost_segments([_segment(GPT, input_tokens=1_000)])
    priced = price_usage_by_model(usage, reprice="always")
    assert priced.partial == [GPT]


def test_unpriced_model_is_unknown_not_free() -> None:
    usage = usage_from_task_cost_segments(
        [_segment("acme-coder-1", input_tokens=1_000, output_tokens=1_000)]
    )
    priced = price_usage_by_model(usage, reprice="always")
    assert priced.unpriced == ["acme-coder-1"]
    assert priced.per_model["acme-coder-1"]["unknown"] == 1.0
