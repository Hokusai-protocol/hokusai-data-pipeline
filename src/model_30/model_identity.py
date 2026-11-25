"""Model identity, family and price resolution for Model 30 training data (HOK-3401).

Replaces the vendor allow-list (``^(claude-|gpt-|deepseek-)``) that silently
dropped every Kimi, Qwen and GLM outcome. A model ID is accepted when it
resolves through the serving catalog or belongs to a known model family. Junk
identifiers (``<synthetic>``, ``scripted:*``, bare words such as ``deep``) are
still rejected.

Normalised IDs follow the serving catalog's public spelling (the first alias,
e.g. ``kimi-k2.7-code``, ``claude-opus-4-7``). IDs that are not in the catalog
keep their bare spelling with any ``openrouter:`` / ``vendor/`` prefix removed,
so ``openrouter:moonshotai/kimi-k2.7-code`` and ``kimi-k2.7-code`` are the same
model.

Prices are looked up in this order: the eval record's own ``pricingSnapshot``,
then the SDK-published ``configs/hokusai_token_prices.v1.json``. Catalog
metadata is used for identity only, never as a second live price table. A model with no price is
**unknown cost**, never free.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "configs" / "model_30_launch_priority_models.v1.json"
# SDK-published rates for new canonical rows (HOK-3421).
TOKEN_PRICES_PATH = REPO_ROOT / "configs" / "hokusai_token_prices.v1.json"

# Families whose models may appear in training data. A family prefix match is
# required for IDs that are not in the serving catalog.
MODEL_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("codex-", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("deepseek-", "deepseek"),
    ("kimi-", "moonshotai"),
    ("qwen", "qwen"),
    ("glm-", "z-ai"),
    ("minimax-", "minimax"),
    ("mimo-", "xiaomi"),
    ("kat-coder", "kwaipilot"),
    ("gemini-", "google"),
    ("mistral-", "mistralai"),
    ("devstral-", "mistralai"),
    ("codestral-", "mistralai"),
    ("grok-", "x-ai"),
    ("llama-", "meta-llama"),
)
_JUNK_PATTERNS = (re.compile(r"^<.*>$"), re.compile(r"^scripted:"), re.compile(r"^[a-z]+$"))


@dataclass(frozen=True)
class ModelPrice:
    """USD per token. ``None`` means the dimension is not priced."""

    input_per_token: float | None
    output_per_token: float | None
    cache_read_per_token: float | None = None
    cache_write_per_token: float | None = None
    source: str = ""
    long_context: dict[str, Any] | None = None


def _strip_routing_prefixes(model_id: str) -> str:
    value = model_id.strip()
    if value.lower().startswith("openrouter:"):
        value = value.split(":", 1)[1]
    if "/" in value:
        value = value.split("/", 1)[1]
    return value


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog: dict[str, dict[str, Any]] = {}
    for model in payload.get("models", []):
        aliases = [str(a).strip() for a in model.get("aliases", []) if str(a).strip()]
        provider_id = str(model.get("model_id", "")).strip()
        if not provider_id or not aliases:
            continue
        entry = {
            "canonical_id": aliases[0],
            "provider_id": provider_id,
            "family": str(model.get("family") or model.get("provider") or ""),
        }
        for identifier in [provider_id, *aliases, _strip_routing_prefixes(provider_id)]:
            catalog.setdefault(identifier.casefold(), entry)
    return catalog


@lru_cache(maxsize=1)
def _sdk_table() -> dict[str, Any]:
    payload = json.loads(TOKEN_PRICES_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "hokusai_token_prices/v1":
        raise ValueError("Unsupported SDK token price table")
    return payload


@lru_cache(maxsize=1)
def hokusai_price_snapshot() -> dict[str, dict[str, Any]]:
    """Compatibility projection of the SDK table; never contributor prices."""
    return {
        model: {
            "inputCostPerMTok": row["inputPerMTokUsd"],
            "outputCostPerMTok": row["outputPerMTokUsd"],
            "cacheReadCostPerMTok": row["cachedInputPerMTokUsd"],
            "cacheWriteCostPerMTok": row["cacheWritePerMTokUsd"],
            "source": "sdk_price_table",
            "long_context": row.get("long_context"),
        }
        for model, row in _sdk_table()["models"].items()
    }


@lru_cache(maxsize=1)
def price_table_version() -> str:
    """Version and full SHA-256 of the sole server-side rate source."""
    digest = hashlib.sha256(TOKEN_PRICES_PATH.read_bytes()).hexdigest()
    return f"hokusai_token_prices/{_sdk_table()['version']}+sha256:{digest}"


def _sdk_model_key(model_id: str) -> str:
    """Mirror the SDK's bounded known-prefix and snapshot normalization."""
    value = model_id.strip().lower()
    if value.startswith("openrouter:"):
        value = value[len("openrouter:") :]
    prefixes = (
        "openrouter/",
        "litellm/",
        "openai/",
        "anthropic/",
        "google/",
        "gemini/",
        "deepseek/",
        "meta-llama/",
        "meta/",
        "mistralai/",
        "moonshotai/",
        "qwen/",
        "x-ai/",
        "z-ai/",
    )
    for _ in range(5):
        prefix = next((p for p in prefixes if value.startswith(p)), None)
        if prefix is None:
            break
        value = value[len(prefix) :]
    if value.startswith("claude-"):
        value = value.replace(".", "-")
    value = _sdk_table().get("aliases", {}).get(value, value)
    if value in _sdk_table()["models"]:
        return value
    stripped = re.sub(r"-\d{8}$|-\d{4}-\d{2}-\d{2}$", "", value)
    if stripped == value and value.startswith("gemini-"):
        stripped = re.sub(r"-001$", "", value)
    return stripped


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bare_variants(model_id: str) -> list[str]:
    bare = _strip_routing_prefixes(model_id).casefold()
    variants = [model_id.strip().casefold(), bare]
    # Wavemill spells Qwen both "qwen-3-coder" and "qwen3-coder".
    variants.append(re.sub(r"^qwen-(\d)", r"qwen\1", bare))
    return list(dict.fromkeys(variants))


def is_junk_model_id(model_id: Any) -> bool:
    """Return True for placeholder or scripted IDs that are never real models."""
    if not isinstance(model_id, str) or not model_id.strip():
        return True
    value = model_id.strip().casefold()
    return any(pattern.search(value) for pattern in _JUNK_PATTERNS)


def normalize_model_id(model_id: Any) -> str:
    """Return the public spelling of *model_id* (catalog alias, else bare ID)."""
    if not isinstance(model_id, str):
        return ""
    for variant in _bare_variants(model_id):
        entry = _catalog().get(variant)
        if entry is not None:
            return str(entry["canonical_id"])
    return re.sub(r"^qwen-(\d)", r"qwen\1", _strip_routing_prefixes(model_id))


def model_family(model_id: Any) -> str | None:
    """Return the provider family for a model ID, or None when unknown."""
    if is_junk_model_id(model_id):
        return None
    for variant in _bare_variants(str(model_id)):
        entry = _catalog().get(variant)
        if entry is not None:
            provider = str(entry["provider_id"]).split("/", 1)[0]
            return provider or entry["family"] or None
    bare = normalize_model_id(model_id).casefold()
    for prefix, family in MODEL_FAMILY_PREFIXES:
        if bare.startswith(prefix):
            return family
    return None


def is_supported_model_id(model_id: Any) -> bool:
    """Accept catalog models and known-family models; reject junk and unknown IDs."""
    return model_family(model_id) is not None


def resolve_price(
    model_id: str, pricing_snapshot: dict[str, Any] | None = None
) -> ModelPrice | None:
    """Explicit historical snapshot, else the SDK table. No catalog-rate fallback.

    Only offline historical callers supply record snapshots. Server ingestion
    passes ``hokusai_price_snapshot()`` and never contributor price metadata.
    """
    snapshot = pricing_snapshot or {}
    keys = {k.casefold(): v for k, v in snapshot.items() if isinstance(v, dict)}
    sdk_key = _sdk_model_key(model_id)
    for variant in [sdk_key, *_bare_variants(model_id), normalize_model_id(model_id).casefold()]:
        row = keys.get(variant)
        if row is not None:
            return ModelPrice(
                input_per_token=_per_mtok(row.get("inputCostPerMTok")),
                output_per_token=_per_mtok(row.get("outputCostPerMTok")),
                cache_read_per_token=_per_mtok(row.get("cacheReadCostPerMTok")),
                cache_write_per_token=_per_mtok(row.get("cacheWriteCostPerMTok")),
                source="sdk_price_table"
                if row.get("source") == "sdk_price_table"
                else "record_pricing_snapshot",
                long_context=row.get("long_context"),
            )
    row = hokusai_price_snapshot().get(sdk_key)
    if row is None:
        return None
    return ModelPrice(
        input_per_token=_per_mtok(row["inputCostPerMTok"]),
        output_per_token=_per_mtok(row["outputCostPerMTok"]),
        cache_read_per_token=_per_mtok(row["cacheReadCostPerMTok"]),
        cache_write_per_token=_per_mtok(row["cacheWriteCostPerMTok"]),
        source="sdk_price_table",
        long_context=row.get("long_context"),
    )


def _per_mtok(value: Any) -> float | None:
    number = _float(value)
    return None if number is None else number / 1_000_000


def exclusive_cache_usage(model_id: Any, usage: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return *usage* with ``inputTokens`` excluding cached reads, and whether it changed.

    OpenAI reports ``input_tokens`` *including* cached tokens; Anthropic and most
    OpenRouter providers report them separately. Wavemill priced OpenAI usage as
    if exclusive, charging cached tokens at the full input price on top of the
    cache price (~5x real cost for Codex, HOK-3402). Only OpenAI-family usage
    whose input covers its cache reads is treated as inclusive.
    """
    if usage.get("cacheSemantics") == "exclusive" or model_family(model_id) != "openai":
        return usage, False
    cache_read = _float(usage.get("cacheReadTokens")) or 0.0
    input_tokens = _float(usage.get("inputTokens")) or 0.0
    if cache_read <= 0 or input_tokens < cache_read:
        return usage, False
    return {**usage, "inputTokens": input_tokens - cache_read}, True


# Cache reads are billed at a discount by every provider we price (10% of input
# for OpenAI, Anthropic and Google; 10-50% elsewhere). When a price has no cache
# read rate, use this share of the input price, matching the router's estimate.
DEFAULT_CACHE_READ_SHARE = 0.1


def priced_usage_cost(usage: dict[str, Any], price: ModelPrice) -> float | None:
    """SDK rates preserve unpriced dimensions; historical snapshots keep legacy rules."""
    if price.source == "sdk_price_table":
        values = [
            _float(usage.get(key)) or 0.0
            for key in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")
        ]
        if any(not math.isfinite(value) or value < 0 for value in values):
            return None
        rates = [
            price.input_per_token,
            price.output_per_token,
            price.cache_read_per_token,
            price.cache_write_per_token,
        ]
        long = price.long_context
        if (
            usage.get("requestScoped") is True
            and long
            and sum((values[0], values[2], values[3])) > long["threshold_input_tokens"]
        ):
            rates = [
                _per_mtok(long[key])
                for key in (
                    "inputPerMTokUsd",
                    "outputPerMTokUsd",
                    "cachedInputPerMTokUsd",
                    "cacheWritePerMTokUsd",
                )
            ]
        if any(value > 0 and rate is None for value, rate in zip(values, rates)):
            return None
        # Match SDK operation order and per-million arithmetic at rounding ties.
        cost = sum(values[i] / 1_000_000 * ((rates[i] or 0.0) * 1_000_000) for i in (0, 3, 2, 1))
        return math.floor(cost * 1_000_000 + 0.5) / 1_000_000
    # Historical record snapshots are explicit, not the live server rate source.
    input_price = price.input_per_token or 0.0
    cache_read = (
        price.cache_read_per_token
        if price.cache_read_per_token is not None
        else DEFAULT_CACHE_READ_SHARE * input_price
    )
    cache_write = (
        price.cache_write_per_token if price.cache_write_per_token is not None else input_price
    )
    return (
        (_float(usage.get("inputTokens")) or 0.0) * input_price
        + (_float(usage.get("outputTokens")) or 0.0) * (price.output_per_token or 0.0)
        + (_float(usage.get("cacheReadTokens")) or 0.0) * cache_read
        + (_float(usage.get("cacheCreationTokens")) or 0.0) * cache_write
    )


def build_price_table(
    snapshots: list[tuple[str, dict[str, Any]]],
    extra_model_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``{public_model_id: price}`` for the router artifact.

    *snapshots* are ``(timestamp, pricingSnapshot)`` pairs from eval records; the
    most recent snapshot that prices a model wins. Models without a snapshot
    price fall back to the SDK-published table.
    """
    table = _latest_snapshot_prices(snapshots)
    candidates = set(extra_model_ids or [])
    for entry in _catalog().values():
        candidates.add(str(entry["canonical_id"]))
    candidates.update(hokusai_price_snapshot())
    for model in sorted(candidates):
        if not model or model in table or is_junk_model_id(model):
            continue
        price = resolve_price(model)
        if price is not None:
            table[normalize_model_id(model)] = _price_dict(price)
    return dict(sorted(table.items()))


def latest_snapshot(snapshots: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Merge ``pricingSnapshot`` dicts, keeping each model's most recent raw row.

    Used as a fallback snapshot: records whose real usage was recovered from
    sessions often carry a snapshot that priced only the leaked fixture models.
    """
    merged: dict[str, Any] = {}
    seen_at: dict[str, str] = {}
    for timestamp, snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        for raw_model, row in snapshot.items():
            if not isinstance(row, dict) or is_junk_model_id(raw_model):
                continue
            model = normalize_model_id(raw_model)
            if seen_at.get(model, "") > timestamp:
                continue
            seen_at[model] = timestamp
            merged[model] = row
    return merged


def _latest_snapshot_prices(
    snapshots: list[tuple[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Most recent record-snapshot price per public model id."""
    table: dict[str, dict[str, Any]] = {}
    seen_at: dict[str, str] = {}
    for timestamp, snapshot in snapshots:
        for raw_model in snapshot if isinstance(snapshot, dict) else {}:
            model = normalize_model_id(raw_model)
            price = None if is_junk_model_id(raw_model) else resolve_price(raw_model, snapshot)
            if price is None or price.source != "record_pricing_snapshot":
                continue
            if seen_at.get(model, "") > timestamp:
                continue
            seen_at[model] = timestamp
            table[model] = _price_dict(price)
    return table


def _price_dict(price: ModelPrice) -> dict[str, Any]:
    return {
        "input_per_token": price.input_per_token,
        "output_per_token": price.output_per_token,
        "cache_read_per_token": price.cache_read_per_token,
        "cache_write_per_token": price.cache_write_per_token,
        "source": price.source,
    }
