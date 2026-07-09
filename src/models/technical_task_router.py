"""Callable MLflow pyfunc model for the Wavemill Technical Task Router.

Registry authentication is handled outside this artifact by MLflow SDK
environment such as ``MLFLOW_TRACKING_TOKEN``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import product
from typing import Any

import mlflow.pyfunc
import pandas as pd

ROUTER_DATASET_ARTIFACT = "router_dataset"
MODEL_NAME = "Technical Task Router"
BORROWED_EVIDENCE_WEIGHT = 0.75

ROLE_COLUMNS = {
    "planner": "planner_model",
    "coder": "coder_model",
    "reviewer": "reviewer_model",
}

AVAILABLE_COLUMNS = {
    "planner": ("available_planner_models", "planner_models", "allowed_models"),
    "coder": ("available_coder_models", "coder_models", "allowed_models"),
    "reviewer": ("available_reviewer_models", "reviewer_models", "allowed_models"),
}

ROLE_STAGES = {
    "planner": "plan",
    "coder": "code",
    "reviewer": "review",
}

STRATEGY_OBJECTIVES = ("lowest_cost", "fastest_completion", "highest_reliability")

MODEL_SUCCESSOR_MAP = {
    "claude-sonnet-4-5-20250929": (
        "claude-sonnet-4-6",
        "anthropic/claude-sonnet-4.6",
    ),
    "claude-sonnet-4-5-20251001": (
        "claude-sonnet-4-6",
        "anthropic/claude-sonnet-4.6",
    ),
    "claude-sonnet-4.5": (
        "claude-sonnet-4-6",
        "anthropic/claude-sonnet-4.6",
    ),
    "gpt-5.3-codex": (
        "gpt-5.4",
        "openai/gpt-5.4",
        "gpt-5.2-codex",
        "openai/gpt-5.2-codex",
    ),
    "gpt-5.1-codex": (
        "gpt-5.2-codex",
        "openai/gpt-5.2-codex",
        "gpt-5.4",
        "openai/gpt-5.4",
    ),
}

FEATURE_DEFAULTS = {
    "task_type": "unknown",
    "language": "unknown",
    "domain": "backend",
    "repo_size_bucket": "medium",
    "files_touched_bucket": "2_5",
    "description_length_bucket": "medium",
    "risk_level": "low",
}


@dataclass(frozen=True)
class RoleChoice:
    """Selected model and quality estimates for one workflow role."""

    model_id: str
    score: float
    support: int
    expected_success: float
    estimated_cost_usd: float | None
    direct_support: int = 0
    borrowed_support: int = 0
    borrowed_from: dict[str, int] | None = None


@dataclass(frozen=True)
class StrategyCandidate:
    """Estimated workflow route for one candidate strategy."""

    objective: str
    planner_model: str | None
    coder_model: str | None
    reviewer_model: str | None
    stages: list[str]
    estimated_success_under_budget: float
    estimated_cost_usd: float
    estimated_duration_seconds: float | None
    confidence: float
    support: int
    rationale: str
    role_evidence: dict[str, dict[str, Any]]

    def to_dict(self: StrategyCandidate) -> dict[str, Any]:
        """Return a public response-friendly strategy mapping."""
        return {
            "objective": self.objective,
            "planner_model": self.planner_model,
            "coder_model": self.coder_model,
            "reviewer_model": self.reviewer_model,
            "stages": self.stages,
            "estimated_success_under_budget": self.estimated_success_under_budget,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_duration_seconds": self.estimated_duration_seconds,
            "confidence": self.confidence,
            "support": self.support,
            "rationale": self.rationale,
            "role_evidence": self.role_evidence,
        }


class TechnicalTaskRouterModel(mlflow.pyfunc.PythonModel):
    """Route technical tasks to the historically best Wavemill model set.

    The model is intentionally artifact-backed: ``load_context`` reads the
    Wavemill router dataset CSV and ``predict`` performs deterministic
    nearest-neighbor ranking over that learned history. This makes the MLflow
    artifact a callable inference model rather than a wrapper around raw data.
    Internal evaluation paths also consume per-neighbor provenance that is not
    exposed through the public Model 30 adapter response.
    """

    def __init__(self: TechnicalTaskRouterModel, *, k_neighbors: int = 40) -> None:
        self.k_neighbors = k_neighbors
        self._dataset: pd.DataFrame | None = None
        self._global_defaults: dict[str, RoleChoice] = {}

    def __getstate__(self: TechnicalTaskRouterModel) -> dict[str, Any]:
        """Return a deterministic serializer state for cloudpickle round-trips."""
        dataset_state: dict[str, Any] | None = None
        if self._dataset is not None:
            dataset_state = {
                "columns": list(self._dataset.columns),
                "data": self._dataset.to_dict(orient="split")["data"],
            }

        defaults_state = {
            role: {
                "model_id": choice.model_id,
                "score": choice.score,
                "support": choice.support,
                "expected_success": choice.expected_success,
                "estimated_cost_usd": choice.estimated_cost_usd,
                "direct_support": choice.direct_support,
                "borrowed_support": choice.borrowed_support,
                "borrowed_from": choice.borrowed_from,
            }
            for role, choice in self._global_defaults.items()
        }

        return {
            "k_neighbors": self.k_neighbors,
            "dataset_state": dataset_state,
            "global_defaults_state": defaults_state,
        }

    def __setstate__(self: TechnicalTaskRouterModel, state: dict[str, Any]) -> None:
        """Restore the deterministic serializer state from cloudpickle."""
        self.k_neighbors = int(state.get("k_neighbors", 40))

        if "dataset_state" in state:
            dataset_state = state["dataset_state"]
            if dataset_state is None:
                self._dataset = None
            else:
                self._dataset = pd.DataFrame(
                    data=dataset_state["data"],
                    columns=dataset_state["columns"],
                )
        else:
            # Older MLflow artifacts were pickled before the deterministic
            # serializer existed. Preserve any embedded dataset if present;
            # otherwise MLflow will populate it via load_context().
            self._dataset = state.get("_dataset")

        if "global_defaults_state" in state:
            self._global_defaults = {
                role: RoleChoice(**choice_state)
                for role, choice_state in state["global_defaults_state"].items()
            }
        else:
            self._global_defaults = state.get("_global_defaults") or {}

    def load_context(
        self: TechnicalTaskRouterModel,
        context: mlflow.pyfunc.PythonModelContext,
    ) -> None:
        """Load the Wavemill router CSV artifact required for inference."""
        dataset_path = context.artifacts.get(ROUTER_DATASET_ARTIFACT)
        if not dataset_path:
            raise ValueError(f"Missing required MLflow artifact: {ROUTER_DATASET_ARTIFACT}")

        dataset = pd.read_csv(dataset_path)
        self._dataset = _prepare_dataset(dataset)
        self._global_defaults = {
            role: self._rank_role(role, self._dataset, {}, [])[0] for role in ROLE_COLUMNS
        }

    def predict(
        self: TechnicalTaskRouterModel,
        context: Any,
        model_input: Any,
        params: dict[str, Any] | None = None,
    ) -> pd.DataFrame:
        """Return route predictions for the serving feature frame."""
        del context, params
        if self._dataset is None:
            raise RuntimeError("TechnicalTaskRouterModel.load_context() has not been called")

        frame = _coerce_input_frame(model_input)
        predictions = [self._predict_row(row.to_dict()) for _, row in frame.iterrows()]
        return pd.DataFrame(predictions)

    def _predict_row(
        self: TechnicalTaskRouterModel,
        raw_row: dict[str, Any],
    ) -> dict[str, Any]:
        features = _normalize_serving_features(raw_row)
        neighbors = self._nearest_neighbors(features)
        strategies = self._rank_strategies(neighbors, features)
        recommended_strategy = _recommended_strategy(strategies, features["routing_objective"])
        alternatives = _strategy_alternatives(strategies, recommended_strategy)
        tradeoffs = {
            objective: strategies[objective][0].to_dict() if strategies[objective] else None
            for objective in STRATEGY_OBJECTIVES
        }
        nearest_neighbors = _nearest_neighbors_summary(neighbors)

        role_choices = {
            role: self._strategy_role_choice(recommended_strategy, role, neighbors, features)
            for role in ROLE_COLUMNS
        }
        selected_models = _unique_ordered(
            [role_choices[role].model_id for role in ROLE_COLUMNS if role_choices[role] is not None]
        )
        selected_model = recommended_strategy.coder_model or _first_nonempty(selected_models)
        estimated_cost = recommended_strategy.estimated_cost_usd
        confidence = recommended_strategy.confidence

        rationale = (
            f"Selected coder {selected_model} from {len(neighbors)} nearest Wavemill "
            f"router row(s); planner={recommended_strategy.planner_model}, "
            f"reviewer={recommended_strategy.reviewer_model}, estimated_cost_usd="
            f"{estimated_cost:.6f}."
        )

        return {
            "selected_model": selected_model,
            "selected_models": selected_models,
            "confidence": confidence,
            "rationale": rationale,
            "estimated_cost_usd": estimated_cost,
            "recommended_strategy": recommended_strategy.to_dict(),
            "alternatives": [strategy.to_dict() for strategy in alternatives],
            "tradeoffs": tradeoffs,
            "nearest_neighbors": nearest_neighbors,
            "neighbor_provenance": _neighbor_provenance(neighbors),
        }

    def _rank_strategies(
        self: TechnicalTaskRouterModel,
        neighbors: pd.DataFrame,
        features: dict[str, Any],
    ) -> dict[str, list[StrategyCandidate]]:
        candidates = self._strategy_candidates(neighbors, features)
        return {
            objective: sorted(
                (candidate for candidate in candidates if candidate.objective == objective),
                key=lambda candidate: _strategy_sort_key(candidate, objective),
            )
            for objective in STRATEGY_OBJECTIVES
        }

    def _strategy_candidates(
        self: TechnicalTaskRouterModel,
        neighbors: pd.DataFrame,
        features: dict[str, Any],
    ) -> list[StrategyCandidate]:
        stages = features["workflow_stages"]
        role_options: dict[str, list[RoleChoice | None]] = {}
        for role in ROLE_COLUMNS:
            if ROLE_STAGES[role] not in stages:
                role_options[role] = [None]
                continue
            allowed_models = _role_allowed_models(role, features)
            ranked = self._rank_role(role, neighbors, features, allowed_models)
            if not ranked:
                ranked = self._rank_role(role, self._dataset, features, allowed_models)
            if not ranked:
                ranked = [self._fallback_role_choice(role, features, allowed_models)]
            role_options[role] = _apply_preference_bonus(
                ranked,
                _parse_json_list(features.get("preferred_models")),
            )[:3]

        candidates: list[StrategyCandidate] = []
        combinations = product(
            role_options["planner"],
            role_options["coder"],
            role_options["reviewer"],
        )
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for planner_choice, coder_choice, reviewer_choice in combinations:
            key = _strategy_key(planner_choice, coder_choice, reviewer_choice)
            if key in seen:
                continue
            seen.add(key)
            for objective in STRATEGY_OBJECTIVES:
                candidates.append(
                    _estimate_strategy(
                        objective,
                        stages,
                        neighbors,
                        features,
                        planner_choice,
                        coder_choice,
                        reviewer_choice,
                    )
                )
        return candidates

    def _fallback_role_choice(
        self: TechnicalTaskRouterModel,
        role: str,
        features: dict[str, Any],
        allowed_models: list[str],
    ) -> RoleChoice:
        preferred_models = _parse_json_list(features.get("preferred_models"))
        preferred_allowed = [model for model in preferred_models if model in set(allowed_models)]
        fallback_model = _first_nonempty(preferred_allowed + allowed_models + preferred_models)
        if fallback_model:
            return RoleChoice(
                model_id=fallback_model,
                score=0.35,
                support=0,
                expected_success=0.35,
                estimated_cost_usd=_feature_float(features, "expected_cost_usd"),
                direct_support=0,
                borrowed_support=0,
                borrowed_from={},
            )
        return self._global_defaults[role]

    def _strategy_role_choice(
        self: TechnicalTaskRouterModel,
        strategy: StrategyCandidate,
        role: str,
        neighbors: pd.DataFrame,
        features: dict[str, Any],
    ) -> RoleChoice | None:
        model_id = getattr(strategy, f"{role}_model")
        if model_id is None:
            return None
        ranked = self._rank_role(role, neighbors, features, [model_id])
        if ranked:
            return ranked[0]
        return RoleChoice(
            model_id=model_id,
            score=strategy.confidence,
            support=strategy.support,
            expected_success=strategy.estimated_success_under_budget,
            estimated_cost_usd=strategy.estimated_cost_usd,
            direct_support=0,
            borrowed_support=0,
            borrowed_from={},
        )

    def _nearest_neighbors(
        self: TechnicalTaskRouterModel,
        features: dict[str, Any],
    ) -> pd.DataFrame:
        if self._dataset is None:
            raise RuntimeError("TechnicalTaskRouterModel.load_context() has not been called")

        dataset = self._dataset.copy()
        dataset["_similarity"] = dataset.apply(
            lambda row: _similarity(features, row.to_dict()),
            axis=1,
        )
        neighbors = dataset.sort_values(
            by=["_similarity", "completed_successfully", "score"],
            ascending=[False, False, False],
        ).head(max(1, self.k_neighbors))
        return neighbors

    def _choose_role(
        self: TechnicalTaskRouterModel,
        role: str,
        neighbors: pd.DataFrame,
        features: dict[str, Any],
    ) -> RoleChoice:
        allowed_models = _role_allowed_models(role, features)
        preferred_models = _parse_json_list(features.get("preferred_models"))
        ranked = self._rank_role(role, neighbors, features, allowed_models)
        if not ranked:
            ranked = self._rank_role(role, self._dataset, features, allowed_models)

        if ranked:
            return _apply_preference_bonus(ranked, preferred_models)[0]

        preferred_allowed = [model for model in preferred_models if model in set(allowed_models)]
        fallback_model = _first_nonempty(preferred_allowed + allowed_models + preferred_models)
        if fallback_model:
            return RoleChoice(
                model_id=fallback_model,
                score=0.35,
                support=0,
                expected_success=0.35,
                estimated_cost_usd=_feature_float(features, "expected_cost_usd"),
                direct_support=0,
                borrowed_support=0,
                borrowed_from={},
            )

        return self._global_defaults[role]

    def _rank_role(
        self: TechnicalTaskRouterModel,
        role: str,
        rows: pd.DataFrame | None,
        features: dict[str, Any],
        allowed_models: list[str],
    ) -> list[RoleChoice]:
        if rows is None or rows.empty:
            return []

        role_column = ROLE_COLUMNS[role]
        candidates = rows.dropna(subset=[role_column]).copy()
        candidates = candidates[candidates[role_column].astype(str).str.len() > 0]
        candidates = _effective_role_evidence(candidates, role_column, allowed_models)
        if candidates.empty:
            return []

        max_cost = _feature_float(features, "max_cost_usd")
        choices: list[RoleChoice] = []
        for model_id, group in candidates.groupby("_effective_model_id"):
            weights = group["_evidence_weight"]
            success = _weighted_mean_bool(group["completed_successfully"], weights, default=0.5)
            quality = _weighted_mean_number(group["score"], weights, default=success)
            cost = _median_number(group["actual_cost_usd"])
            if cost is None:
                cost = _median_number(group["expected_cost_usd"])

            direct_support = int((group["_evidence_source"] == "direct").sum())
            borrowed = group[group["_evidence_source"] == "borrowed"]
            borrowed_support = int(len(borrowed))
            borrowed_from = {
                str(source): int(count)
                for source, count in borrowed["_source_model_id"]
                .value_counts()
                .sort_index()
                .items()
            }
            weighted_support = float(weights.sum())
            support = int(math.ceil(weighted_support))
            support_bonus = min(math.log1p(weighted_support) / 10.0, 0.2)
            cost_penalty = _cost_penalty(cost, max_cost)
            route_score = 0.55 * success + 0.30 * quality + support_bonus - cost_penalty
            choices.append(
                RoleChoice(
                    model_id=str(model_id),
                    score=_clamp(route_score, 0.0, 1.0),
                    support=support,
                    expected_success=_clamp((success + quality) / 2.0, 0.0, 1.0),
                    estimated_cost_usd=cost,
                    direct_support=direct_support,
                    borrowed_support=borrowed_support,
                    borrowed_from=borrowed_from,
                )
            )

        return sorted(choices, key=lambda choice: choice.score, reverse=True)


def _prepare_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"task_type", "completed_successfully", "score", *ROLE_COLUMNS.values()}
    missing = sorted(required_columns - set(dataset.columns))
    if missing:
        raise ValueError(f"Router dataset is missing required columns: {missing}")
    if dataset.empty:
        raise ValueError("Router dataset must contain at least one row")

    normalized = dataset.copy()
    for column, default in FEATURE_DEFAULTS.items():
        if column not in normalized.columns:
            normalized[column] = default
        normalized[column] = normalized[column].fillna(default).astype(str)

    for column in [
        "complexity",
        "max_cost_usd",
        "expected_cost_usd",
        "actual_cost_usd",
        "actual_time_seconds",
        "score",
        "intervention_count",
    ]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["completed_successfully"] = normalized["completed_successfully"].map(_coerce_bool)
    for role_column in ROLE_COLUMNS.values():
        normalized[role_column] = normalized[role_column].fillna("").astype(str)

    return normalized


def _coerce_input_frame(model_input: Any) -> pd.DataFrame:
    if isinstance(model_input, pd.DataFrame):
        return model_input
    if isinstance(model_input, pd.Series):
        return pd.DataFrame([model_input.to_dict()])
    if isinstance(model_input, Mapping):
        return pd.DataFrame([dict(model_input)])
    if isinstance(model_input, list):
        return pd.DataFrame(model_input)
    raise ValueError(f"Unsupported model input type: {type(model_input).__name__}")


def _normalize_serving_features(row: dict[str, Any]) -> dict[str, Any]:
    descriptor = _parse_json_object(row.get("task_descriptor"))
    context = _parse_json_object(descriptor.get("context"))
    workflow = _parse_json_object(descriptor.get("workflow"))

    task_description = str(row.get("task_description") or descriptor.get("description") or "")
    normalized = {
        "task_type": _first_nonempty(
            [row.get("task_type"), descriptor.get("task_type"), FEATURE_DEFAULTS["task_type"]]
        ),
        "language": _normalize_language(
            _first_nonempty(
                [row.get("language"), descriptor.get("language"), FEATURE_DEFAULTS["language"]]
            )
        ),
        "domain": _first_nonempty(
            [row.get("domain"), context.get("domain"), FEATURE_DEFAULTS["domain"]]
        ),
        "repo_size_bucket": _first_nonempty(
            [
                row.get("repo_size_bucket"),
                context.get("repo_size_bucket"),
                FEATURE_DEFAULTS["repo_size_bucket"],
            ]
        ),
        "files_touched_bucket": _first_nonempty(
            [row.get("files_touched_bucket"), _files_bucket(row.get("file_count"))]
        ),
        "description_length_bucket": _first_nonempty(
            [row.get("description_length_bucket"), _description_bucket(task_description)]
        ),
        "risk_level": _first_nonempty(
            [row.get("risk_level"), context.get("risk_level"), FEATURE_DEFAULTS["risk_level"]]
        ),
        "requires_tests": _coerce_bool(row.get("requires_tests")),
        "is_migration": _coerce_bool(row["is_migration"])
        if "is_migration" in row
        else _contains_any(task_description, ["migration", "schema", "alembic"]),
        "ui_heavy": _coerce_bool(row["ui_heavy"])
        if "ui_heavy" in row
        else _contains_any(task_description, ["ui", "frontend", "component"]),
        "cross_service": _coerce_bool(row["cross_service"])
        if "cross_service" in row
        else _contains_any(task_description, ["service", "integration", "api"]),
        "allowed_models": row.get("allowed_models"),
        "preferred_models": row.get("preferred_models"),
        "available_planner_models": row.get("available_planner_models"),
        "available_coder_models": row.get("available_coder_models"),
        "available_reviewer_models": row.get("available_reviewer_models"),
        "planner_models": workflow.get("planner_models"),
        "coder_models": workflow.get("coder_models"),
        "reviewer_models": workflow.get("reviewer_models"),
        "workflow_stages": row.get("workflow_stages") or workflow.get("stages"),
        "routing_objective": row.get("routing_objective"),
        "max_cost_usd": row.get("max_cost_usd"),
        "expected_cost_usd": row.get("expected_cost_usd"),
    }

    normalized["complexity"] = _complexity_number(
        row.get("complexity")
        or row.get("estimated_complexity")
        or context.get("estimated_complexity")
    )
    normalized["workflow_stages"] = _normalize_workflow_stages(normalized["workflow_stages"])
    normalized["routing_objective"] = _normalize_objective(normalized["routing_objective"])
    return normalized


def _similarity(features: dict[str, Any], row: dict[str, Any]) -> float:
    score = 0.0
    total = 0.0

    categorical_weights = {
        "task_type": 2.0,
        "language": 1.0,
        "domain": 1.2,
        "repo_size_bucket": 0.7,
        "files_touched_bucket": 0.5,
        "description_length_bucket": 0.4,
        "risk_level": 0.8,
    }
    for key, weight in categorical_weights.items():
        total += weight
        if str(features.get(key, "")).lower() == str(row.get(key, "")).lower():
            score += weight

    for key, weight in {
        "requires_tests": 0.5,
        "is_migration": 0.5,
        "ui_heavy": 0.5,
        "cross_service": 0.4,
    }.items():
        total += weight
        if _coerce_bool(features.get(key)) == _coerce_bool(row.get(key)):
            score += weight

    total += 1.0
    feature_complexity = _feature_float(features, "complexity", default=5.0)
    row_complexity = _feature_float(row, "complexity", default=5.0)
    score += 1.0 - min(abs(feature_complexity - row_complexity) / 10.0, 1.0)

    return score / total if total else 0.0


def _role_allowed_models(role: str, features: dict[str, Any]) -> list[str]:
    for column in AVAILABLE_COLUMNS[role]:
        values = _parse_json_list(features.get(column))
        if values:
            return values
    return []


def _parse_json_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, (tuple, set)):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [stripped]
        return _parse_json_list(parsed)
    return [str(value)]


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _apply_preference_bonus(
    ranked: list[RoleChoice],
    preferred_models: list[str],
) -> list[RoleChoice]:
    if not preferred_models:
        return ranked
    preferred = set(preferred_models)
    return sorted(
        ranked,
        key=lambda choice: choice.score + (0.08 if choice.model_id in preferred else 0.0),
        reverse=True,
    )


def _normalize_workflow_stages(raw_value: Any) -> list[str]:
    values = _parse_json_list(raw_value)
    stages = [stage for stage in values if stage in set(ROLE_STAGES.values())]
    return stages or list(ROLE_STAGES.values())


def _normalize_objective(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    return value if value in STRATEGY_OBJECTIVES else "highest_reliability"


def _strategy_key(
    planner_choice: RoleChoice | None,
    coder_choice: RoleChoice | None,
    reviewer_choice: RoleChoice | None,
) -> tuple[str | None, str | None, str | None]:
    return (
        planner_choice.model_id if planner_choice else None,
        coder_choice.model_id if coder_choice else None,
        reviewer_choice.model_id if reviewer_choice else None,
    )


def _estimate_strategy(
    objective: str,
    stages: list[str],
    neighbors: pd.DataFrame,
    features: dict[str, Any],
    planner_choice: RoleChoice | None,
    coder_choice: RoleChoice | None,
    reviewer_choice: RoleChoice | None,
) -> StrategyCandidate:
    role_choices = {
        "planner": planner_choice,
        "coder": coder_choice,
        "reviewer": reviewer_choice,
    }
    matched = _matching_strategy_rows(neighbors, role_choices)
    support = int(len(matched))
    evidence = matched if not matched.empty else neighbors
    success = _estimate_success_under_budget(evidence, role_choices)
    cost = _estimate_strategy_cost(evidence, role_choices, features)
    duration = _estimate_strategy_duration(evidence)
    confidence = _estimate_strategy_confidence(neighbors, role_choices, support)
    rationale = (
        f"Estimated {objective} strategy from {support} exact route match(es) "
        f"across {len(neighbors)} nearest Wavemill router row(s)."
    )
    return StrategyCandidate(
        objective=objective,
        planner_model=planner_choice.model_id if planner_choice else None,
        coder_model=coder_choice.model_id if coder_choice else None,
        reviewer_model=reviewer_choice.model_id if reviewer_choice else None,
        stages=stages,
        estimated_success_under_budget=success,
        estimated_cost_usd=cost,
        estimated_duration_seconds=duration,
        confidence=confidence,
        support=support,
        rationale=rationale,
        role_evidence=_strategy_role_evidence(role_choices),
    )


def _matching_strategy_rows(
    rows: pd.DataFrame,
    role_choices: dict[str, RoleChoice | None],
) -> pd.DataFrame:
    if rows.empty:
        return rows
    mask = pd.Series(True, index=rows.index)
    for role, choice in role_choices.items():
        if choice is None:
            continue
        selected_model_id = choice.model_id
        mask &= rows[ROLE_COLUMNS[role]].map(
            lambda model_id, selected_model_id=selected_model_id: _role_row_matches_choice(
                model_id,
                selected_model_id,
            )
        )
    return rows[mask]


def _strategy_role_evidence(
    role_choices: dict[str, RoleChoice | None],
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for role, choice in role_choices.items():
        if choice is None:
            continue
        evidence[role] = {
            "model_id": choice.model_id,
            "support": choice.support,
            "direct_support": choice.direct_support,
            "borrowed_support": choice.borrowed_support,
            "borrowed_from": choice.borrowed_from or {},
        }
    return evidence


def _role_row_matches_choice(value: Any, selected_model_id: str) -> bool:
    source_model_id = str(value or "")
    if source_model_id == selected_model_id:
        return True
    return selected_model_id in _successor_candidates(source_model_id)


def _estimate_success_under_budget(
    rows: pd.DataFrame,
    role_choices: dict[str, RoleChoice | None],
) -> float:
    if not rows.empty:
        success_values = rows["completed_successfully"].map(_coerce_bool)
        if "under_budget" in rows.columns:
            budget_values = rows["under_budget"].map(_coerce_bool)
            success_values = success_values & budget_values
        success = float(success_values.mean()) if len(success_values) else 0.5
        quality = _mean_number(rows["score"], default=success)
        return round(_clamp(0.7 * success + 0.3 * quality, 0.0, 1.0), 6)

    choices = [choice for choice in role_choices.values() if choice is not None]
    if not choices:
        return 0.35
    success = sum(choice.expected_success for choice in choices) / len(choices)
    return round(_clamp(success, 0.0, 1.0), 6)


def _estimate_strategy_cost(
    rows: pd.DataFrame,
    role_choices: dict[str, RoleChoice | None],
    features: dict[str, Any],
) -> float:
    if not rows.empty:
        cost = _median_number(rows["actual_cost_usd"])
        if cost is None:
            cost = _median_number(rows["expected_cost_usd"])
        if cost is not None:
            return round(max(0.0, float(cost)), 6)

    costs = [
        choice.estimated_cost_usd
        for choice in role_choices.values()
        if choice is not None and choice.estimated_cost_usd is not None
    ]
    cost = sum(costs) / len(costs) if costs else _feature_float(features, "expected_cost_usd")
    return round(max(0.0, float(cost or 0.0)), 6)


def _estimate_strategy_duration(rows: pd.DataFrame) -> float | None:
    if rows.empty or "actual_time_seconds" not in rows.columns:
        return None
    positives = _positive_duration_values(rows["actual_time_seconds"])
    if not positives:
        return None
    median = _median_number(positives)
    return round(median, 6) if median is not None else None


def _estimate_strategy_confidence(
    neighbors: pd.DataFrame,
    role_choices: dict[str, RoleChoice | None],
    support: int,
) -> float:
    active_choices = [choice for choice in role_choices.values() if choice is not None]
    if not active_choices:
        return 0.35
    support_ratio = min(support / max(len(neighbors), 1), 1.0)
    role_support = sum(choice.support for choice in active_choices)
    role_support_ratio = min(role_support / max(len(neighbors) * len(active_choices), 1), 1.0)
    mean_score = sum(choice.score for choice in active_choices) / len(active_choices)
    confidence = 0.20 + 0.35 * support_ratio + 0.25 * role_support_ratio + 0.20 * mean_score
    return round(_clamp(confidence, 0.0, 0.99), 6)


def _strategy_sort_key(candidate: StrategyCandidate, objective: str) -> tuple[float, ...]:
    duration = candidate.estimated_duration_seconds
    duration_sort = duration if duration is not None else float("inf")
    if objective == "lowest_cost":
        return (
            candidate.estimated_cost_usd,
            -candidate.estimated_success_under_budget,
            -candidate.confidence,
        )
    if objective == "fastest_completion":
        return (
            duration_sort,
            candidate.estimated_cost_usd,
            -candidate.estimated_success_under_budget,
        )
    return (
        -candidate.estimated_success_under_budget,
        -candidate.confidence,
        candidate.estimated_cost_usd,
    )


def _recommended_strategy(
    strategies: dict[str, list[StrategyCandidate]],
    objective: str,
) -> StrategyCandidate:
    selected = strategies.get(objective) or strategies["highest_reliability"]
    if selected:
        return selected[0]
    raise ValueError("No feasible routing strategies could be generated")


def _strategy_alternatives(
    strategies: dict[str, list[StrategyCandidate]],
    recommended: StrategyCandidate,
) -> list[StrategyCandidate]:
    alternatives: list[StrategyCandidate] = []
    seen = {_public_strategy_key(recommended)}
    for objective in STRATEGY_OBJECTIVES:
        for candidate in strategies[objective][:3]:
            key = _public_strategy_key(candidate)
            if key in seen:
                continue
            alternatives.append(candidate)
            seen.add(key)
            break
    return alternatives[:3]


def _public_strategy_key(
    strategy: StrategyCandidate,
) -> tuple[str | None, str | None, str | None, tuple[str, ...]]:
    return (
        strategy.planner_model,
        strategy.coder_model,
        strategy.reviewer_model,
        tuple(strategy.stages),
    )


def _nearest_neighbors_summary(neighbors: pd.DataFrame) -> dict[str, Any]:
    success_rate = _mean_bool(neighbors["completed_successfully"], default=0.0)
    if "under_budget" in neighbors.columns:
        budget_rate = _mean_bool(neighbors["under_budget"], default=0.0)
        success_rate = (success_rate + budget_rate) / 2.0
    mean_cost = _mean_number(neighbors["actual_cost_usd"], default=0.0)
    if "actual_time_seconds" in neighbors.columns:
        duration_positives = _positive_duration_values(neighbors["actual_time_seconds"])
        mean_duration = (
            sum(duration_positives) / len(duration_positives) if duration_positives else None
        )
    else:
        mean_duration = None
    return {
        "count": int(len(neighbors)),
        "success_under_budget_rate": round(_clamp(success_rate, 0.0, 1.0), 6),
        "mean_cost_usd": round(max(0.0, mean_cost), 6),
        "mean_duration_seconds": round(mean_duration, 6) if mean_duration is not None else None,
    }


def _neighbor_provenance(neighbors: pd.DataFrame) -> list[dict[str, Any]]:
    """Return deterministic per-neighbor attribution metadata."""
    provenance: list[dict[str, Any]] = []
    for training_row_index, neighbor in neighbors.iterrows():
        similarity = float(neighbor.get("_similarity", 0.0) or 0.0)
        provenance.append(
            {
                "training_row_index": int(training_row_index),
                "distance": float(1.0 - similarity),
                "weight": similarity,
            }
        )
    provenance.sort(key=lambda item: (item["distance"], item["training_row_index"]))
    return provenance


def _estimate_route_cost(
    neighbors: pd.DataFrame,
    role_choices: dict[str, RoleChoice],
    features: dict[str, Any],
) -> float:
    selected = {choice.model_id for choice in role_choices.values()}
    matched = neighbors[neighbors[list(ROLE_COLUMNS.values())].isin(selected).any(axis=1)]
    cost = _median_number(matched["actual_cost_usd"]) if not matched.empty else None
    if cost is None:
        costs = [
            choice.estimated_cost_usd
            for choice in role_choices.values()
            if choice.estimated_cost_usd is not None
        ]
        cost = sum(costs) / len(costs) if costs else _feature_float(features, "expected_cost_usd")
    if cost is None:
        cost = 0.0
    return round(max(0.0, float(cost)), 6)


def _estimate_confidence(
    neighbors: pd.DataFrame,
    role_choices: dict[str, RoleChoice],
) -> float:
    if neighbors.empty:
        return 0.35
    support = sum(choice.support for choice in role_choices.values())
    support_ratio = min(support / max(len(neighbors) * len(role_choices), 1), 1.0)
    mean_score = sum(choice.score for choice in role_choices.values()) / len(role_choices)
    return round(_clamp(0.25 + 0.45 * support_ratio + 0.30 * mean_score, 0.0, 0.99), 6)


def _cost_penalty(cost: float | None, max_cost: float | None) -> float:
    if cost is None:
        return 0.0
    if max_cost is not None and max_cost > 0 and cost > max_cost:
        return min((cost - max_cost) / max(max_cost, 1.0), 0.35)
    return min(cost / 100.0, 0.1)


def _positive_duration_values(values: Iterable[Any]) -> list[float]:
    """Return finite numeric values that are strictly positive from a duration iterable."""
    return [float(v) for v in values if _is_finite_number(v) and float(v) > 0.0]


def _effective_role_evidence(
    rows: pd.DataFrame,
    role_column: str,
    allowed_models: list[str],
) -> pd.DataFrame:
    """Expand retired role labels into weighted evidence for allowed successors."""
    if rows.empty:
        return _empty_effective_evidence(rows)

    allowed = set(allowed_models)
    if not allowed:
        direct = rows.copy()
        direct["_effective_model_id"] = direct[role_column].astype(str)
        direct["_source_model_id"] = direct[role_column].astype(str)
        direct["_evidence_source"] = "direct"
        direct["_evidence_weight"] = 1.0
        return direct

    frames: list[pd.DataFrame] = []
    direct_mask = rows[role_column].isin(allowed)
    if direct_mask.any():
        direct = rows[direct_mask].copy()
        direct["_effective_model_id"] = direct[role_column].astype(str)
        direct["_source_model_id"] = direct[role_column].astype(str)
        direct["_evidence_source"] = "direct"
        direct["_evidence_weight"] = 1.0
        frames.append(direct)

    for source_model_id, group in rows[~direct_mask].groupby(role_column):
        successors = [
            successor
            for successor in _successor_candidates(str(source_model_id))
            if successor in allowed
        ]
        for successor in successors:
            borrowed = group.copy()
            borrowed["_effective_model_id"] = successor
            borrowed["_source_model_id"] = str(source_model_id)
            borrowed["_evidence_source"] = "borrowed"
            borrowed["_evidence_weight"] = BORROWED_EVIDENCE_WEIGHT
            frames.append(borrowed)

    if not frames:
        return _empty_effective_evidence(rows)
    return pd.concat(frames, ignore_index=True)


def _empty_effective_evidence(rows: pd.DataFrame) -> pd.DataFrame:
    empty = rows.iloc[0:0].copy()
    empty["_effective_model_id"] = pd.Series(dtype="object")
    empty["_source_model_id"] = pd.Series(dtype="object")
    empty["_evidence_source"] = pd.Series(dtype="object")
    empty["_evidence_weight"] = pd.Series(dtype="float64")
    return empty


def _successor_candidates(model_id: str) -> tuple[str, ...]:
    return MODEL_SUCCESSOR_MAP.get(str(model_id or ""), ())


def _mean_bool(values: Iterable[Any], *, default: float) -> float:
    coerced = [_coerce_bool(value) for value in values]
    return sum(coerced) / len(coerced) if coerced else default


def _mean_number(values: Iterable[Any], *, default: float) -> float:
    numbers = [float(value) for value in values if _is_finite_number(value)]
    return sum(numbers) / len(numbers) if numbers else default


def _weighted_mean_bool(
    values: Iterable[Any],
    weights: Iterable[Any],
    *,
    default: float,
) -> float:
    weighted_values = [
        (1.0 if _coerce_bool(value) else 0.0, float(weight))
        for value, weight in zip(values, weights)
        if _is_finite_number(weight) and float(weight) > 0
    ]
    total_weight = sum(weight for _, weight in weighted_values)
    if total_weight <= 0:
        return default
    return sum(value * weight for value, weight in weighted_values) / total_weight


def _weighted_mean_number(
    values: Iterable[Any],
    weights: Iterable[Any],
    *,
    default: float,
) -> float:
    weighted_values = [
        (float(value), float(weight))
        for value, weight in zip(values, weights)
        if _is_finite_number(value) and _is_finite_number(weight) and float(weight) > 0
    ]
    total_weight = sum(weight for _, weight in weighted_values)
    if total_weight <= 0:
        return default
    return sum(value * weight for value, weight in weighted_values) / total_weight


def _median_number(values: Iterable[Any]) -> float | None:
    numbers = sorted(float(value) for value in values if _is_finite_number(value))
    if not numbers:
        return None
    midpoint = len(numbers) // 2
    if len(numbers) % 2:
        return numbers[midpoint]
    return (numbers[midpoint - 1] + numbers[midpoint]) / 2.0


def _feature_float(
    values: Mapping[str, Any],
    key: str,
    default: float | None = None,
) -> float | None:
    value = values.get(key)
    if _is_finite_number(value):
        return float(value)
    return default


def _is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if _is_finite_number(value):
        return bool(float(value))
    return False


def _complexity_number(value: Any) -> float:
    if _is_finite_number(value):
        return float(value)
    text = str(value or "").strip().lower()
    return {
        "low": 3.0,
        "small": 3.0,
        "medium": 5.0,
        "moderate": 5.0,
        "high": 8.0,
        "large": 8.0,
        "very_high": 10.0,
        # Reasoning-depth spellings emitted by the Hokusai SDK's
        # deriveTaskDescriptor before it was corrected to send a numeric score.
        # Without these, every such row fell through to the 5.0 default and the
        # complexity feature was a constant. Kept so already-ingested rows and
        # any harness still on an older SDK carry their real signal.
        "shallow": 3.0,
        "standard": 5.0,
        "deep": 8.0,
    }.get(text, 5.0)


def _files_bucket(value: Any) -> str:
    if not _is_finite_number(value):
        return FEATURE_DEFAULTS["files_touched_bucket"]
    count = int(float(value))
    if count <= 1:
        return "1"
    if count <= 5:
        return "2_5"
    if count <= 15:
        return "6_15"
    return "16_plus"


def _description_bucket(description: str) -> str:
    words = len(description.split())
    if words < 25:
        return "short"
    if words < 120:
        return "medium"
    return "long"


def _normalize_language(value: Any) -> str:
    language = str(value or "").lower()
    if language in {"typescript", "javascript", "python"}:
        return {"typescript": "ts", "javascript": "js", "python": "py"}[language]
    return language or "unknown"


def _contains_any(value: str, needles: Iterable[str]) -> bool:
    lower = value.lower()
    return any(needle in lower for needle in needles)


def _first_nonempty(values: Iterable[Any]) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _unique_ordered(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
