"""Cross-language pricing parity against generated SDK outputs (HOK-3421)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.model_30.model_identity import (
    TOKEN_PRICES_PATH,
    price_table_version,
    priced_usage_cost,
    resolve_price,
)
from src.model_30.usage_cost import price_usage_by_model

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/token-prices"
CASES = json.loads((FIXTURES / "parity.v1.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["input"]["model"] + ":" + c["label"])
def test_prices_match_sdk_computation(case: dict) -> None:
    inputs = case["input"]
    price = resolve_price(inputs["model"])
    actual = None if price is None else priced_usage_cost(inputs, price)
    expected = case["expected_usd"]
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected, abs=1e-9)


def test_provenance_and_optional_sdk_checkout() -> None:
    manifest = json.loads((FIXTURES / "provenance.json").read_text())
    configured = os.environ.get("HOKUSAI_SDK_DIR")
    sdk = Path(configured) if configured else ROOT.parent / "hokusai-sdk"
    for relative, source in manifest["artifacts"].items():
        local = ROOT / relative
        assert hashlib.sha256(local.read_bytes()).hexdigest() == source["sha256"]
        original = sdk / source["sdk_path"]
        if configured or original.exists():
            assert original.read_bytes() == local.read_bytes(), "Re-vendor the SDK price artifacts"


def test_stamp_identifies_exact_published_table() -> None:
    digest = hashlib.sha256(TOKEN_PRICES_PATH.read_bytes()).hexdigest()
    version = json.loads(TOKEN_PRICES_PATH.read_text())["version"]
    assert price_table_version() == f"hokusai_token_prices/{version}+sha256:{digest}"


def test_unpriced_dimension_stays_unknown_without_fallback() -> None:
    result = price_usage_by_model(
        {
            "gemini-2.5-pro": {
                "inputTokens": 1000,
                "outputTokens": 100,
                "cacheCreationTokens": 500,
                "cacheSemantics": "exclusive",
            }
        },
        reprice="always",
    )
    assert result.unpriced == ["gemini-2.5-pro"]
    assert result.per_model["gemini-2.5-pro"]["unknown"] == 1


def test_subscription_metadata_does_not_change_resource_cost() -> None:
    tokens = {"inputTokens": 1000, "outputTokens": 200, "cacheSemantics": "exclusive"}
    ordinary = price_usage_by_model({"gpt-5-codex": tokens}, reprice="always")
    subscription = price_usage_by_model(
        {"gpt-5-codex": {**tokens, "cost_basis": "subscription"}}, reprice="always"
    )
    assert ordinary == subscription
    assert subscription.per_model["gpt-5-codex"]["cost"] > 0
