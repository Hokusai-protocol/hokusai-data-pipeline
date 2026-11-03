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
    role_output_tokens: dict[str, float | None] = field(default_factory=dict)
    role_cost_usd: dict[str, float | None] = field(default_factory=dict)
    aux_cost_usd: float | None = None
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

    evidence = record.get("challengeExecutionEvidence")
    if isinstance(evidence, dict) and evidence.get("validity") == "valid":
        route = _route_from_mapping(evidence.get("effectiveRoute"))
        if route:
            return RouteResolution(route, "challenge_execution_evidence")

    identity = record.get("modelIdentityAttribution")
    if isinstance(identity, dict):
        roles = identity.get("roles") if isinstance(identity.get("roles"), dict) else {}
        verified = {
            role: normalize_model_id(roles[role].get("providerId") or roles[role].get("alias"))
            for role in ROLES
            if isinstance(roles.get(role), dict) and roles[role].get("identityStatus") == "verified"
        }
        if verified:
            route = {**stage_route, **{role: model for role, model in verified.items() if model}}
            return RouteResolution(route, "model_identity_attribution")

    pair_id = record.get("challengePairId")
    if not pair_id:
        return RouteResolution(stage_route, "stages")

    side = record.get("challengeSide")
    intent = record.get("challengeIntent")
    if side in {"primary", "challenger"} and isinstance(intent, dict):
        route = _route_from_mapping(_dict(intent.get(side)).get("expectedRoute"))
        if route:
            return RouteResolution(route, "challenge_intent")

    pair = (challenge_records or {}).get(str(pair_id))
    if pair is None:
        return RouteResolution(stage_route, "stages_unverified_challenge")
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

    inferred = side if side in {"primary", "challenger"} else _infer_side(record, primary, challenger)
    if inferred is None:
        return RouteResolution(stage_route, "stages", "ambiguous_challenge_route")
    executed = challenger if inferred == "challenger" else primary
    if executed in stage_route.values():
        return RouteResolution(stage_route, f"challenge_record_{inferred}")
    stage = _challenge_role(record)
    route = {**stage_route, stage: executed}
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


def route_economics(record: dict[str, Any], route: dict[str, str]) -> RouteEconomics:
    """Recompute route cost per model from token usage; attribute cost to roles."""
    usage = record.get("workflowTokenUsage")
    if not isinstance(usage, dict) or not usage:
        return RouteEconomics(total_cost_usd=None, cost_status="no_token_usage")
    snapshot = record.get("pricingSnapshot") if isinstance(record.get("pricingSnapshot"), dict) else {}

    per_model: dict[str, dict[str, float]] = {}
    repriced: list[str] = []
    unpriced: list[str] = []
    for raw_model, model_usage in usage.items():
        if not isinstance(model_usage, dict) or is_junk_model_id(raw_model):
            continue
        model = normalize_model_id(raw_model)
        recorded = _number(model_usage.get("costUsd")) or 0.0
        tokens = sum(
            _number(model_usage.get(key)) or 0.0
            for key in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheCreationTokens")
        )
        cost: float | None = recorded
        if recorded <= 0 and tokens > 0:
            price = resolve_price(raw_model, snapshot)
            if price is None:
                cost = None
                unpriced.append(model)
            else:
                cost = priced_usage_cost(model_usage, price)
                repriced.append(model)
        bucket = per_model.setdefault(model, {"input": 0.0, "output": 0.0, "cost": 0.0, "unknown": 0.0})
        bucket["input"] += (_number(model_usage.get("inputTokens")) or 0.0) + (
            _number(model_usage.get("cacheReadTokens")) or 0.0
        ) + (_number(model_usage.get("cacheCreationTokens")) or 0.0)
        bucket["output"] += _number(model_usage.get("outputTokens")) or 0.0
        if cost is None:
            bucket["unknown"] = 1.0
        else:
            bucket["cost"] += cost

    role_models = {role: route.get(role, "") for role in ROLES}
    shared = {m for m in role_models.values() if list(role_models.values()).count(m) > 1}
    role_in: dict[str, float | None] = {}
    role_out: dict[str, float | None] = {}
    role_cost: dict[str, float | None] = {}
    for role, model in role_models.items():
        bucket = per_model.get(model)
        if bucket is None or model in shared:
            role_in[role] = role_out[role] = role_cost[role] = None
            continue
        role_in[role] = bucket["input"]
        role_out[role] = bucket["output"]
        role_cost[role] = None if bucket["unknown"] else bucket["cost"]
    role_set = set(role_models.values())
    aux = [b for m, b in per_model.items() if m not in role_set]
    aux_cost = None if any(b["unknown"] for b in aux) else sum(b["cost"] for b in aux)

    if unpriced:
        return RouteEconomics(
            total_cost_usd=None,
            cost_status="unpriced_model",
            role_input_tokens=role_in,
            role_output_tokens=role_out,
            role_cost_usd=role_cost,
            aux_cost_usd=aux_cost,
            repriced_models=sorted(set(repriced)),
            unpriced_models=sorted(set(unpriced)),
        )
    total = sum(b["cost"] for b in per_model.values())
    return RouteEconomics(
        total_cost_usd=total,
        cost_status="repriced" if repriced else "recorded",
        role_input_tokens=role_in,
        role_output_tokens=role_out,
        role_cost_usd=role_cost,
        aux_cost_usd=aux_cost,
        repriced_models=sorted(set(repriced)),
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None
