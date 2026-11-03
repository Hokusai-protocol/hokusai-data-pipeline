"""Resolve which models actually executed a Wavemill task, and what each role cost (HOK-3401).

Wavemill eval records describe the route in ``taskDescriptor.stages``. For
challenge runs that field often shows the *primary* route even when the
challenger ran (``missing_challenge_stage``). Before HOK-3401 this mislabeled
Qwen and Kimi runs as gpt-5.4/gpt-5.5.

Resolution order (first that applies):

1. ``challengeExecutionEvidence.effectiveRoute`` with ``validity == "valid"``
2. ``modelIdentityAttribution.roles[*]`` with ``identityStatus == "verified"``
3. ``challengeIntent[<challengeSide>].expectedRoute`` when the side is known
4. challenge-records join (older challenge evals without intent metadata): the
   stage route is kept only when it contains the primary or the challenger model
   of the pair; otherwise the row is ambiguous and excluded
5. ``taskDescriptor.stages`` (non-challenge records)

Records flagged ``invalidChallenge`` are excluded.

Cost is recomputed per model from ``workflowTokenUsage`` × price (see
``model_identity.resolve_price``). Wavemill recorded $0 for models it had no
price for; those are re-priced here, and a model that still has no price makes
the route cost *unknown*, not zero.

Spend by models outside the executed route ("aux") is split (HOK-3404):

- challenge-partner spend: the other arm of a challenge pair, identified from the
  challenge record and ``challengeIntent``. It is excluded from the route cost.
- sub-agent spend: everything else (e.g. Opus/Fable sub-agents inside a Claude
  Code session, judge calls). It is harness overhead and stays in the route cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.model_30.model_identity import (
    is_junk_model_id,
    normalize_model_id,
    priced_usage_cost,
    resolve_price,
)

ROLES = ("planner", "coder", "reviewer")
CHALLENGE_RECORDS_FILENAME = "challenge-records.jsonl"


@dataclass
class RouteResolution:
    """Executed route for one eval record."""

    route: dict[str, str]
    source: str
    exclusion_reason: str | None = None


@dataclass
class RouteEconomics:
    """Token and cost breakdown for one executed route."""

    total_cost_usd: float | None
    cost_status: str
    role_input_tokens: dict[str, float | None] = field(default_factory=dict)
    role_cache_tokens: dict[str, float | None] = field(default_factory=dict)
    role_output_tokens: dict[str, float | None] = field(default_factory=dict)
    role_cost_usd: dict[str, float | None] = field(default_factory=dict)
    # aux = challenge partner + sub-agents (all spend by models outside the route).
    aux_cost_usd: float | None = None
    challenge_partner_cost_usd: float | None = None
    subagent_cost_usd: float | None = None
    repriced_models: list[str] = field(default_factory=list)
    unpriced_models: list[str] = field(default_factory=list)


def load_challenge_records(eval_dir: Path) -> dict[str, dict[str, Any]]:
    """Return challenge records in *eval_dir* keyed by ``challengePairId``."""
    path = eval_dir / CHALLENGE_RECORDS_FILENAME
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            pair_id = record.get("challengePairId")
            if isinstance(pair_id, str) and pair_id:
                records[pair_id] = record
    return records


def _route_from_mapping(mapping: Any) -> dict[str, str] | None:
    if not isinstance(mapping, dict):
        return None
    route = {role: normalize_model_id(mapping.get(role)) for role in ROLES}
    if not all(route.values()):
        return None
    return route


def resolve_executed_route(
    record: dict[str, Any],
    stage_route: dict[str, str],
    challenge_records: dict[str, dict[str, Any]] | None = None,
) -> RouteResolution:
    """Return the executed route for *record* (see module docstring for precedence)."""
    stage_route = {role: normalize_model_id(stage_route.get(role)) for role in ROLES}
    if record.get("invalidChallenge") is True:
        return RouteResolution(stage_route, "stages", "invalid_challenge")
    resolved = _resolve_from_metadata(record, stage_route)
    if resolved is not None:
        return resolved
    pair_id = record.get("challengePairId")
    if not pair_id:
        return RouteResolution(stage_route, "stages")
    pair = (challenge_records or {}).get(str(pair_id))
    if pair is None:
        return RouteResolution(stage_route, "stages_unverified_challenge")
    return _resolve_from_challenge_record(record, stage_route, pair)


def _resolve_from_metadata(
    record: dict[str, Any], stage_route: dict[str, str]
) -> RouteResolution | None:
    """Resolve from execution evidence, verified identity, then declared intent."""
    evidence = _dict(record.get("challengeExecutionEvidence"))
    if evidence.get("validity") == "valid":
        route = _route_from_mapping(evidence.get("effectiveRoute"))
        if route:
            return RouteResolution(route, "challenge_execution_evidence")
    roles = _dict(_dict(record.get("modelIdentityAttribution")).get("roles"))
    verified = {
        role: normalize_model_id(roles[role].get("providerId") or roles[role].get("alias"))
        for role in ROLES
        if _dict(roles.get(role)).get("identityStatus") == "verified"
    }
    verified = {role: model for role, model in verified.items() if model}
    if verified:
        return RouteResolution({**stage_route, **verified}, "model_identity_attribution")
    side = record.get("challengeSide")
    if record.get("challengePairId") and side in {"primary", "challenger"}:
        intent = _dict(record.get("challengeIntent"))
        route = _route_from_mapping(_dict(intent.get(side)).get("expectedRoute"))
        if route:
            return RouteResolution(route, "challenge_intent")
    return None


def _resolve_from_challenge_record(
    record: dict[str, Any], stage_route: dict[str, str], pair: dict[str, Any]
) -> RouteResolution:
    """Older challenge evals: join the pair record and infer which side ran."""
    primary = normalize_model_id(pair.get("primaryModel"))
    challenger = normalize_model_id(pair.get("challengerModel"))
    if not primary or not challenger or primary == challenger:
        # Wavemill recorded no distinct challenger (often the harness default for
        # both sides). The stage route is trustworthy unless the eval also shows
        # tokens from a model outside that route, in which case the executor is
        # unknown (e.g. an OpenRouter challenger that may or may not have run).
        if _foreign_token_models(record, stage_route):
            return RouteResolution(stage_route, "stages", "ambiguous_challenge_route")
        return RouteResolution(stage_route, "stages_same_model_challenge")
    side = record.get("challengeSide")
    inferred = (
        side if side in {"primary", "challenger"} else _infer_side(record, primary, challenger)
    )
    if inferred is None:
        return RouteResolution(stage_route, "stages", "ambiguous_challenge_route")
    executed = challenger if inferred == "challenger" else primary
    if executed in stage_route.values():
        return RouteResolution(stage_route, f"challenge_record_{inferred}")
    route = {**stage_route, _challenge_role(record): executed}
    return RouteResolution(route, f"challenge_record_{inferred}_corrected")


_AUXILIARY_FAMILIES = ("gemini-", "mistral-")


def _foreign_token_models(record: dict[str, Any], route: dict[str, str]) -> list[str]:
    """Models with recorded tokens that are not in *route* (ignoring auxiliary stages)."""
    usage = record.get("workflowTokenUsage")
    if not isinstance(usage, dict):
        return []
    in_route = set(route.values())
    foreign = []
    for raw, values in usage.items():
        if not isinstance(values, dict) or is_junk_model_id(raw):
            continue
        model = normalize_model_id(raw)
        if model in in_route or model.casefold().startswith(_AUXILIARY_FAMILIES):
            continue
        tokens = sum(
            _number(values.get(key)) or 0.0
            for key in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")
        )
        if tokens > 0:
            foreign.append(model)
    return foreign


def _model_tokens(record: dict[str, Any], model: str) -> float:
    usage = record.get("workflowTokenUsage")
    if not isinstance(usage, dict):
        return 0.0
    total = 0.0
    for raw, values in usage.items():
        if isinstance(values, dict) and normalize_model_id(raw) == model:
            total += sum(
                _number(values.get(key)) or 0.0
                for key in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")
            )
    return total


def _infer_side(record: dict[str, Any], primary: str, challenger: str) -> str | None:
    """Infer which side of a challenge pair an eval ran from whose tokens it recorded."""
    primary_tokens = _model_tokens(record, primary)
    challenger_tokens = _model_tokens(record, challenger)
    if challenger_tokens > 0 and primary_tokens == 0:
        return "challenger"
    if primary_tokens > 0 and challenger_tokens == 0:
        return "primary"
    return None


_STAGE_TO_ROLE = {"plan": "planner", "implementation": "coder", "review": "reviewer"}


def _challenge_role(record: dict[str, Any]) -> str:
    stage = record.get("challengeStage")
    if not isinstance(stage, str):
        stage = _dict(record.get("challengeIntent")).get("challengeStage")
    return _STAGE_TO_ROLE.get(str(stage), "coder")


def challenge_partner_models(
    record: dict[str, Any],
    route: dict[str, str],
    challenge_records: dict[str, dict[str, Any]] | None = None,
) -> set[str]:
    """Models from the *other* arm of this record's challenge pair (never in *route*)."""
    pair_id = record.get("challengePairId")
    if not pair_id:
        return set()
    models: set[str] = set()
    pair = (challenge_records or {}).get(str(pair_id)) or {}
    for key in ("primaryModel", "challengerModel"):
        models.add(normalize_model_id(pair.get(key)))
    intent = _dict(record.get("challengeIntent"))
    for side in ("primary", "challenger"):
        expected = _route_from_mapping(_dict(intent.get(side)).get("expectedRoute"))
        if expected:
            models.update(expected.values())
    return {model for model in models if model} - set(route.values())


def route_economics(
    record: dict[str, Any],
    route: dict[str, str],
    partner_models: set[str] | None = None,
) -> RouteEconomics:
    """Recompute route cost per model from token usage; attribute cost to roles.

    *partner_models* (see ``challenge_partner_models``) are the other challenge
    arm; their spend is reported separately and excluded from the route total.
    """
    usage = record.get("workflowTokenUsage")
    if not isinstance(usage, dict) or not usage:
        return RouteEconomics(total_cost_usd=None, cost_status="no_token_usage")
    untrusted = _untrusted_usage_reason(usage, route)
    if untrusted is not None:
        return RouteEconomics(total_cost_usd=None, cost_status=f"untrusted:{untrusted}")
    per_model, repriced, unpriced = _aggregate_usage(usage, _dict(record.get("pricingSnapshot")))
    partners = set(partner_models or ()) - set(route.values())
    economics = _attribute_roles(per_model, route, partners)
    economics.repriced_models = sorted(set(repriced))
    if unpriced:
        economics.cost_status = "unpriced_model"
        economics.unpriced_models = sorted(set(unpriced))
        return economics
    economics.total_cost_usd = sum(b["cost"] for m, b in per_model.items() if m not in partners)
    economics.cost_status = "repriced" if repriced else "recorded"
    return economics


_TOKEN_KEYS = ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")


def _aggregate_usage(
    usage: dict[str, Any], snapshot: dict[str, Any]
) -> tuple[dict[str, dict[str, float]], list[str], list[str]]:
    """Per-model token and cost buckets; models Wavemill recorded at $0 are re-priced."""
    per_model: dict[str, dict[str, float]] = {}
    repriced: list[str] = []
    unpriced: list[str] = []
    for raw_model, model_usage in usage.items():
        if not isinstance(model_usage, dict) or is_junk_model_id(raw_model):
            continue
        model = normalize_model_id(raw_model)
        cost: float | None = _number(model_usage.get("costUsd")) or 0.0
        tokens = sum(_number(model_usage.get(key)) or 0.0 for key in _TOKEN_KEYS)
        if cost <= 0 and tokens > 0:
            price = resolve_price(raw_model, snapshot)
            cost = None if price is None else priced_usage_cost(model_usage, price)
            (unpriced if price is None else repriced).append(model)
        bucket = per_model.setdefault(
            model, {"input": 0.0, "cache": 0.0, "output": 0.0, "cost": 0.0, "unknown": 0.0}
        )
        bucket["input"] += _number(model_usage.get("inputTokens")) or 0.0
        bucket["cache"] += (_number(model_usage.get("cacheReadTokens")) or 0.0) + (
            _number(model_usage.get("cacheCreationTokens")) or 0.0
        )
        bucket["output"] += _number(model_usage.get("outputTokens")) or 0.0
        if cost is None:
            bucket["unknown"] = 1.0
        else:
            bucket["cost"] += cost
    return per_model, repriced, unpriced


def _attribute_roles(
    per_model: dict[str, dict[str, float]],
    route: dict[str, str],
    partners: set[str] | None = None,
) -> RouteEconomics:
    """Assign each role its model's tokens and cost; models used by 2+ roles stay unattributed."""
    role_models = {role: route.get(role, "") for role in ROLES}
    used = list(role_models.values())
    economics = RouteEconomics(total_cost_usd=None, cost_status="")
    for role, model in role_models.items():
        bucket = per_model.get(model)
        attributable = bucket is not None and used.count(model) == 1
        economics.role_input_tokens[role] = bucket["input"] if attributable else None
        economics.role_cache_tokens[role] = bucket["cache"] if attributable else None
        economics.role_output_tokens[role] = bucket["output"] if attributable else None
        economics.role_cost_usd[role] = (
            None if not attributable or bucket["unknown"] else bucket["cost"]
        )
    partners = partners or set()
    outside = {m: b for m, b in per_model.items() if m not in set(used)}
    partner = [b for m, b in outside.items() if m in partners]
    subagent = [b for m, b in outside.items() if m not in partners]
    economics.challenge_partner_cost_usd = _bucket_cost(partner)
    economics.subagent_cost_usd = _bucket_cost(subagent)
    economics.aux_cost_usd = _bucket_cost(partner + subagent)
    return economics


def _bucket_cost(buckets: list[dict[str, float]]) -> float | None:
    """Return the summed cost of *buckets*, or None if any bucket cost is unknown."""
    if any(b["unknown"] for b in buckets):
        return None
    return sum(b["cost"] for b in buckets)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _untrusted_usage_reason(usage: dict[str, Any], route: dict[str, str]) -> str | None:
    """Why this record's token usage (and so its cost) can't be trusted, or None.

    From 2026-06-24 to ~2026-10-26 Wavemill's cost meter read native transcripts
    first, picking up leaked test fixtures (provider ``scripted``) and dropping
    the real Codex/Claude sessions. Those records show tokens for models that
    never ran the task and none for the coder that did (HOK-3402 forensics).
    """
    models = {
        normalize_model_id(raw): values for raw, values in usage.items() if isinstance(values, dict)
    }
    if any(str(raw).strip().casefold().startswith("scripted:") for raw in usage):
        return "scripted_fixture_tokens"
    coder = route.get("coder")
    coder_usage = models.get(coder or "")
    if not coder_usage or not (_number(coder_usage.get("outputTokens")) or 0.0) > 0:
        return "coder_tokens_missing"
    return None
