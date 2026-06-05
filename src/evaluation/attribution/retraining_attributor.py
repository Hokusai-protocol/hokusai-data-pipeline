"""Deterministic retraining-based cohort attribution for evaluation reports."""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any, TypeAlias

TrainFn: TypeAlias = Callable[[frozenset[str], int], Any]
EvalFn: TypeAlias = Callable[[Any, int], float]


@dataclass(frozen=True)
class Cohort:
    """Attribution cohort used as a unit of retraining."""

    cohort_id: str
    wallet: str | None
    submission_ids: tuple[str, ...]
    row_count: int


@dataclass(frozen=True)
class RetrainingConfig:
    """Deterministic controls for LOCO / Shapley attribution."""

    tau: float = 0.10
    budget: int = 64
    max_groups: int = 12
    rng_seed: int = 0
    eval_seeds: tuple[int, ...] = (0, 1, 2)
    enable_add_one_in: bool = False
    min_examples: int = 0
    noise_floor_factor: float = 0.25


@dataclass(frozen=True)
class _Group:
    group_id: str
    cohorts: tuple[Cohort, ...]


def attribute(
    *,
    cohorts: Sequence[Cohort],
    train_fn: TrainFn,
    eval_fn: EvalFn,
    model_id: str,
    baseline_run_id: str,
    candidate_run_id: str,
    created_at: str,
    dataset_hash: str,
    manifest_hash: str,
    total_rows_evaluated: int,
    config: RetrainingConfig = RetrainingConfig(),
) -> dict[str, Any]:
    """Compute deterministic attribution weights from retraining marginals."""
    ordered_cohorts = _normalize_cohorts(cohorts)
    if not ordered_cohorts:
        raise ValueError("at least one cohort is required")

    groups = _build_groups(ordered_cohorts, max_groups=config.max_groups)
    if config.budget < len(groups) + 2:
        raise ValueError("retrain budget too small for LOCO")

    evaluator = _SubsetEvaluator(
        train_fn=train_fn,
        eval_fn=eval_fn,
        rng_seed=config.rng_seed,
        eval_seed=config.eval_seeds[0] if config.eval_seeds else 0,
        budget=config.budget,
    )
    all_group_ids = frozenset(group.group_id for group in groups)
    all_wallets = sorted({cohort.wallet for cohort in ordered_cohorts if cohort.wallet is not None})
    group_plan = [
        {
            "group_id": group.group_id,
            "member_cohort_ids": [cohort.cohort_id for cohort in group.cohorts],
        }
        for group in groups
    ]

    baseline_handle = train_fn(all_group_ids, config.rng_seed)
    baseline_eval_seeds = config.eval_seeds or (0,)
    baseline_scores = [float(eval_fn(baseline_handle, seed)) for seed in baseline_eval_seeds]
    evaluator.prime(all_group_ids, float(eval_fn(baseline_handle, baseline_eval_seeds[0])))
    v_full = fmean(baseline_scores) if baseline_scores else 0.0
    v_empty = evaluator.value(frozenset())
    total_lift = v_full - v_empty
    gap_undefined = math.isclose(total_lift, 0.0, abs_tol=1e-12)
    noise_floor_std = pstdev(baseline_scores) if len(baseline_scores) > 1 else 0.0
    baseline_examples_ok = config.min_examples <= 0 or total_rows_evaluated >= config.min_examples
    noise_threshold = config.noise_floor_factor * config.tau * max(abs(total_lift), 1e-12)
    noise_floor_ok = (
        baseline_examples_ok and not gap_undefined and noise_floor_std < noise_threshold
    )

    loco_values: dict[str, float] = {}
    for group in groups:
        without_group = all_group_ids - {group.group_id}
        loco_values[group.group_id] = v_full - evaluator.value(without_group)
    active_values = dict(loco_values)
    tier = "loco"
    efficiency_gap = _efficiency_gap(active_values, total_lift)
    sample_plan: dict[str, Any] = {"groups": group_plan}

    can_try_add_one = config.enable_add_one_in and evaluator.remaining_budget >= len(groups)
    if noise_floor_ok and can_try_add_one:
        add_one_values = {
            group.group_id: evaluator.value(frozenset({group.group_id})) - v_empty
            for group in groups
        }
        averaged_values = {
            group.group_id: (loco_values[group.group_id] + add_one_values[group.group_id]) / 2.0
            for group in groups
        }
        averaged_gap = _efficiency_gap(averaged_values, total_lift)
        if averaged_gap <= config.tau or efficiency_gap <= config.tau:
            active_values = averaged_values
            tier = "loco+addone"
            efficiency_gap = averaged_gap

    if tier == "loco" and noise_floor_ok and efficiency_gap > config.tau:
        if len(groups) <= 12 and (1 << len(groups)) <= config.budget:
            active_values = _exact_shapley(groups=groups, evaluator=evaluator)
            tier = "shapley_exact"
            efficiency_gap = _efficiency_gap(active_values, total_lift)
        else:
            active_values, tmc_plan = _tmc_shapley(
                groups=groups,
                evaluator=evaluator,
                total_lift=total_lift,
                tau=config.tau,
                noise_floor_factor=config.noise_floor_factor,
                rng_seed=config.rng_seed,
            )
            sample_plan.update(tmc_plan)
            tier = "shapley_tmc"
            efficiency_gap = _efficiency_gap(active_values, total_lift)

    contributors, fallback = _build_contributors(
        cohorts=ordered_cohorts,
        groups=groups,
        group_values=active_values,
        wallets=all_wallets,
    )

    method_details: dict[str, Any] = {
        "tier": tier,
        "efficiency_gap": efficiency_gap,
        "total_lift": total_lift,
        "seed": config.rng_seed,
        "eval_seeds": list(config.eval_seeds),
        "tau": config.tau,
        "budget": config.budget,
        "retrain_count": evaluator.retrain_count,
        "noise_floor_ok": noise_floor_ok,
        "noise_floor_std": noise_floor_std,
        "dataset_hash": dataset_hash,
        "manifest_hash": manifest_hash,
        "sample_plan": sample_plan,
        "weight_kind": "retraining_marginal_lift",
    }
    if fallback is not None:
        method_details["fallback"] = fallback
    if gap_undefined:
        method_details["gap_undefined"] = True

    return {
        "schema_version": "attribution_report/v1",
        "model_id": model_id,
        "method": "loco_shapley",
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "created_at": created_at,
        "total_rows_evaluated": total_rows_evaluated,
        "rows_improved": 0,
        "contributors": contributors,
        "weight_bps_total": int(sum(item["weight_bps"] for item in contributors)),
        "method_details": method_details,
    }


class _SubsetEvaluator:
    """Cache subset evaluations and enforce a hard retraining budget."""

    def __init__(
        self: _SubsetEvaluator,
        *,
        train_fn: TrainFn,
        eval_fn: EvalFn,
        rng_seed: int,
        eval_seed: int,
        budget: int,
    ) -> None:
        self._train_fn = train_fn
        self._eval_fn = eval_fn
        self._rng_seed = rng_seed
        self._eval_seed = eval_seed
        self._budget = budget
        self._cache: dict[frozenset[str], float] = {}

    @property
    def retrain_count(self: _SubsetEvaluator) -> int:
        return len(self._cache)

    @property
    def remaining_budget(self: _SubsetEvaluator) -> int:
        return self._budget - self.retrain_count

    def is_cached(self: _SubsetEvaluator, included_ids: frozenset[str]) -> bool:
        return frozenset(included_ids) in self._cache

    def value(self: _SubsetEvaluator, included_ids: frozenset[str]) -> float:
        subset = frozenset(included_ids)
        if subset in self._cache:
            return self._cache[subset]
        if self.retrain_count >= self._budget:
            raise ValueError("retrain budget exhausted")
        handle = self._train_fn(subset, self._rng_seed)
        score = float(self._eval_fn(handle, self._eval_seed))
        self._cache[subset] = score
        return score

    def prime(self: _SubsetEvaluator, included_ids: frozenset[str], score: float) -> None:
        subset = frozenset(included_ids)
        self._cache.setdefault(subset, float(score))


def _normalize_cohorts(cohorts: Sequence[Cohort]) -> list[Cohort]:
    ordered = sorted(
        cohorts,
        key=lambda cohort: (cohort.cohort_id, cohort.wallet or "", cohort.row_count),
    )
    normalized: list[Cohort] = []
    seen_ids: set[str] = set()
    for cohort in ordered:
        if cohort.cohort_id in seen_ids:
            raise ValueError(f"duplicate cohort_id: {cohort.cohort_id}")
        seen_ids.add(cohort.cohort_id)
        normalized.append(
            Cohort(
                cohort_id=cohort.cohort_id,
                wallet=cohort.wallet,
                submission_ids=tuple(sorted(dict.fromkeys(cohort.submission_ids))),
                row_count=cohort.row_count,
            )
        )
    return normalized


def _build_groups(cohorts: Sequence[Cohort], *, max_groups: int) -> list[_Group]:
    if max_groups <= 0:
        raise ValueError("max_groups must be positive")
    if len(cohorts) <= max_groups:
        return [_Group(group_id=cohort.cohort_id, cohorts=(cohort,)) for cohort in cohorts]

    sortable = sorted(cohorts, key=lambda cohort: (cohort.row_count, cohort.cohort_id))
    pooled_size = len(cohorts) - max_groups + 1
    pooled = tuple(sortable[:pooled_size])
    pooled_id = "+".join(cohort.cohort_id for cohort in pooled)
    remaining = sorted(sortable[pooled_size:], key=lambda cohort: cohort.cohort_id)
    groups = [_Group(group_id=pooled_id, cohorts=pooled)]
    groups.extend(_Group(group_id=cohort.cohort_id, cohorts=(cohort,)) for cohort in remaining)
    return sorted(groups, key=lambda group: group.group_id)


def _efficiency_gap(group_values: dict[str, float], total_lift: float) -> float:
    if math.isclose(total_lift, 0.0, abs_tol=1e-12):
        return math.inf
    return abs(sum(group_values.values()) - total_lift) / abs(total_lift)


def _exact_shapley(*, groups: Sequence[_Group], evaluator: _SubsetEvaluator) -> dict[str, float]:
    n_groups = len(groups)
    factorials = [math.factorial(index) for index in range(n_groups + 1)]
    all_group_ids = tuple(group.group_id for group in groups)
    result = {group_id: 0.0 for group_id in all_group_ids}
    for subset_size in range(n_groups):
        for subset_tuple in itertools.combinations(all_group_ids, subset_size):
            subset = frozenset(subset_tuple)
            subset_value = evaluator.value(subset)
            weight = (
                factorials[subset_size]
                * factorials[n_groups - subset_size - 1]
                / factorials[n_groups]
            )
            for group_id in all_group_ids:
                if group_id in subset:
                    continue
                with_group = frozenset((*subset_tuple, group_id))
                marginal = evaluator.value(with_group) - subset_value
                result[group_id] += weight * marginal
    return result


def _tmc_shapley(
    *,
    groups: Sequence[_Group],
    evaluator: _SubsetEvaluator,
    total_lift: float,
    tau: float,
    noise_floor_factor: float,
    rng_seed: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    rng = random.Random(rng_seed)
    group_ids = [group.group_id for group in groups]
    contributions: dict[str, list[float]] = {group_id: [] for group_id in group_ids}
    permutations: list[list[str]] = []
    truncation_eps = noise_floor_factor * tau * max(abs(total_lift), 1e-12)
    previous_means: dict[str, float] | None = None

    while evaluator.remaining_budget > 0:
        permutation = list(group_ids)
        rng.shuffle(permutation)
        current_subset = frozenset()
        previous_value = evaluator.value(current_subset)
        marginals = {group_id: 0.0 for group_id in group_ids}
        for group_id in permutation:
            next_subset = frozenset((*current_subset, group_id))
            if evaluator.remaining_budget <= 0 and not evaluator.is_cached(next_subset):
                break
            next_value = evaluator.value(next_subset)
            marginal = next_value - previous_value
            marginals[group_id] = marginal
            current_subset = next_subset
            previous_value = next_value
            if abs(total_lift - previous_value) <= truncation_eps:
                break
        for group_id in group_ids:
            contributions[group_id].append(marginals[group_id])
        permutations.append(list(permutation))
        current_means = {
            group_id: fmean(values) if values else 0.0 for group_id, values in contributions.items()
        }
        if previous_means is not None and all(
            abs(current_means[group_id] - previous_means[group_id]) <= truncation_eps
            for group_id in group_ids
        ):
            break
        previous_means = current_means

    return (
        {group_id: fmean(values) if values else 0.0 for group_id, values in contributions.items()},
        {
            "method": "tmc",
            "permutations": permutations,
            "truncation_eps": truncation_eps,
        },
    )


def _build_contributors(
    *,
    cohorts: Sequence[Cohort],
    groups: Sequence[_Group],
    group_values: dict[str, float],
    wallets: Sequence[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not wallets:
        return [], None

    wallet_totals: dict[str, dict[str, Any]] = {
        wallet: {
            "wallet": wallet,
            "submission_ids": set(),
            "rows_credited": 0,
            "raw_score": 0.0,
        }
        for wallet in wallets
    }
    for cohort in cohorts:
        if cohort.wallet is None:
            continue
        aggregate = wallet_totals[cohort.wallet]
        aggregate["submission_ids"].update(cohort.submission_ids)
        aggregate["rows_credited"] += cohort.row_count
    for group in groups:
        raw_value = group_values.get(group.group_id, 0.0)
        attributable_rows = sum(
            cohort.row_count for cohort in group.cohorts if cohort.wallet is not None
        )
        for cohort in group.cohorts:
            if cohort.wallet is None:
                continue
            share = raw_value
            if len(group.cohorts) > 1 and attributable_rows > 0:
                share = raw_value * (cohort.row_count / attributable_rows)
            wallet_totals[cohort.wallet]["raw_score"] += share

    clamped = {wallet: max(0.0, float(wallet_totals[wallet]["raw_score"])) for wallet in wallets}
    fallback: str | None = None
    if all(math.isclose(value, 0.0, abs_tol=1e-12) for value in clamped.values()):
        fallback = "equal_weight"
        if wallets:
            clamped = {wallet: 1.0 for wallet in wallets}

    weight_bps = (
        _largest_remainder_bps(clamped)
        if any(clamped.values())
        else {wallet: 0 for wallet in wallets}
    )
    contributors = [
        {
            "wallet": wallet,
            "submission_ids": sorted(wallet_totals[wallet]["submission_ids"]),
            "rows_credited": int(wallet_totals[wallet]["rows_credited"]),
            "raw_score": round(clamped[wallet], 12),
            "weight_bps": int(weight_bps[wallet]),
        }
        for wallet in wallets
    ]
    contributors.sort(key=lambda item: (-item["weight_bps"], item["wallet"]))
    return contributors, fallback


def _largest_remainder_bps(raw_scores: dict[str, float]) -> dict[str, int]:
    ordered_wallets = sorted(raw_scores)
    total_raw = sum(raw_scores.values())
    if total_raw <= 0:
        return {wallet: 0 for wallet in ordered_wallets}
    exact_bps = {wallet: (raw_scores[wallet] / total_raw) * 10000.0 for wallet in ordered_wallets}
    floor_bps = {wallet: math.floor(value) for wallet, value in exact_bps.items()}
    deficit = 10000 - sum(floor_bps.values())
    if deficit > 0:
        remainders = sorted(
            ordered_wallets,
            key=lambda wallet: (-(exact_bps[wallet] - floor_bps[wallet]), wallet),
        )
        for wallet in remainders[:deficit]:
            floor_bps[wallet] += 1
    return floor_bps
