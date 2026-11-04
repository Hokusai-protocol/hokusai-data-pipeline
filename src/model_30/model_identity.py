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
then the serving catalog, then the pinned OpenRouter table
(``configs/model_30_openrouter_prices.v1.json``). A model with no price is
**unknown cost**, never free.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "configs" / "model_30_launch_priority_models.v1.json"
OPENROUTER_PRICES_PATH = REPO_ROOT / "configs" / "model_30_openrouter_prices.v1.json"
# Hokusai's own rates for server-side repricing (HOK-3413), in pricingSnapshot form.
TOKEN_PRICES_PATH = REPO_ROOT / "configs" / "model_30_token_prices.v1.json"

# Families whose models may appear in training data. A family prefix match is
# required for IDs that are not in the serving catalog.
MODEL_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
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
            "price": ModelPrice(
                input_per_token=_float(model.get("price_input_per_token")),
                output_per_token=_float(model.get("price_output_per_token")),
                source="serving_catalog",
            ),
        }
        for identifier in [provider_id, *aliases, _strip_routing_prefixes(provider_id)]:
            catalog.setdefault(identifier.casefold(), entry)
    return catalog


@lru_cache(maxsize=1)
def _openrouter_prices() -> dict[str, ModelPrice]:
    if not OPENROUTER_PRICES_PATH.exists():
        return {}
    payload = json.loads(OPENROUTER_PRICES_PATH.read_text(encoding="utf-8"))
    prices: dict[str, ModelPrice] = {}
    for provider_id, row in payload.get("models", {}).items():
        price = ModelPrice(
            input_per_token=_float(row.get("input_per_token")),
            output_per_token=_float(row.get("output_per_token")),
            cache_read_per_token=_float(row.get("cache_read_per_token")),
            cache_write_per_token=_float(row.get("cache_write_per_token")),
            source="openrouter_pinned",
        )
        prices[provider_id.casefold()] = price
        prices.setdefault(_strip_routing_prefixes(provider_id).casefold(), price)
    return prices


@lru_cache(maxsize=1)
def hokusai_price_snapshot() -> dict[str, dict[str, Any]]:
    """Hokusai's server-side price rows, keyed by model id (``pricingSnapshot`` form).

    Pass as the *snapshot* of ``resolve_price`` so it takes precedence over the
    serving catalog and the pinned OpenRouter table. Contributor-supplied price
    snapshots are never used server-side.
    """
    payload = json.loads(TOKEN_PRICES_PATH.read_text(encoding="utf-8"))
    return {str(model): dict(row) for model, row in payload.get("models", {}).items()}


@lru_cache(maxsize=1)
def price_table_version() -> str:
    """Identify every price input server repricing reads, for stamping on rows.

    ``<token price version>+sha256:<digest of the token, catalog and OpenRouter
    price files>``: any rate change in any of the three changes the stamp.
    """
    digest = hashlib.sha256()
    for path in (TOKEN_PRICES_PATH, CATALOG_PATH, OPENROUTER_PRICES_PATH):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    version = json.loads(TOKEN_PRICES_PATH.read_text(encoding="utf-8")).get("version", "unknown")
    return f"model_30_token_prices/{version}+sha256:{digest.hexdigest()[:16]}"


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
    """Return the price for *model_id*: record snapshot, catalog, then pinned OpenRouter."""
    snapshot = pricing_snapshot or {}
    keys = {k.casefold(): v for k, v in snapshot.items() if isinstance(v, dict)}
    for variant in [*_bare_variants(model_id), normalize_model_id(model_id).casefold()]:
        row = keys.get(variant)
        if row is not None:
            price = ModelPrice(
                input_per_token=_per_mtok(row.get("inputCostPerMTok")),
                output_per_token=_per_mtok(row.get("outputCostPerMTok")),
                cache_read_per_token=_per_mtok(row.get("cacheReadCostPerMTok")),
                cache_write_per_token=_per_mtok(row.get("cacheWriteCostPerMTok")),
                source="record_pricing_snapshot",
            )
            if price.input_per_token is not None and price.output_per_token is not None:
                return price
    for variant in _bare_variants(model_id):
        entry = _catalog().get(variant)
        if entry is not None:
            price = entry["price"]
            if price.input_per_token is not None and price.output_per_token is not None:
                return price
    for variant in _bare_variants(model_id):
        price = _openrouter_prices().get(variant)
        if price is not None and price.input_per_token is not None:
            return price
    return None


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


def priced_usage_cost(usage: dict[str, Any], price: ModelPrice) -> float:
    """Cost of one model's token usage.

    A missing cache-read rate defaults to DEFAULT_CACHE_READ_SHARE x input (full
    input price overstated Codex cost ~10x: tasks are mostly cache reads). A
    missing cache-write rate falls back to the input price.
    """
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
    price fall back to the serving catalog, then the pinned OpenRouter table.
    """
    table = _latest_snapshot_prices(snapshots)
    candidates = set(extra_model_ids or [])
    for entry in _catalog().values():
        candidates.add(str(entry["canonical_id"]))
    for provider_id in _openrouter_prices():
        candidates.add(normalize_model_id(provider_id))
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
