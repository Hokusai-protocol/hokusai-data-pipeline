"""Callable MLflow pyfunc model for the Wavemill Technical Task Router.

Registry authentication is handled outside this artifact by MLflow SDK
environment such as ``MLFLOW_TRACKING_TOKEN``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import mlflow.pyfunc
import pandas as pd

ROUTER_DATASET_ARTIFACT = "router_dataset"
MODEL_NAME = "Technical Task Router"

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


class TechnicalTaskRouterModel(mlflow.pyfunc.PythonModel):
    """Route technical tasks to the historically best Wavemill model set.

    The model is intentionally artifact-backed: ``load_context`` reads the
    Wavemill router dataset CSV and ``predict`` performs deterministic
    nearest-neighbor ranking over that learned history. This makes the MLflow
    artifact a callable inference model rather than a wrapper around raw data.
    """

    def __init__(self: TechnicalTaskRouterModel, *, k_neighbors: int = 40) -> None:
        self.k_neighbors = k_neighbors
        self._dataset: pd.DataFrame | None = None
        self._global_defaults: dict[str, RoleChoice] = {}

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

        role_choices = {role: self._choose_role(role, neighbors, features) for role in ROLE_COLUMNS}
        selected_models = _unique_ordered(
            [
                role_choices["planner"].model_id,
                role_choices["coder"].model_id,
                role_choices["reviewer"].model_id,
            ]
        )
        selected_model = role_choices["coder"].model_id
        estimated_cost = _estimate_route_cost(neighbors, role_choices, features)
        confidence = _estimate_confidence(neighbors, role_choices)

        rationale = (
            f"Selected coder {selected_model} from {len(neighbors)} nearest Wavemill "
            f"router row(s); planner={role_choices['planner'].model_id}, "
            f"reviewer={role_choices['reviewer'].model_id}, estimated_cost_usd="
            f"{estimated_cost:.6f}."
        )

        return {
            "selected_model": selected_model,
            "selected_models": selected_models,
            "confidence": confidence,
            "rationale": rationale,
            "estimated_cost_usd": estimated_cost,
        }

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
        return neighbors.drop(columns=["_similarity"])

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

        fallback_model = _first_nonempty(preferred_models + allowed_models)
        if fallback_model:
            return RoleChoice(
                model_id=fallback_model,
                score=0.35,
                support=0,
                expected_success=0.35,
                estimated_cost_usd=_feature_float(features, "expected_cost_usd"),
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
        if allowed_models:
            candidates = candidates[candidates[role_column].isin(set(allowed_models))]
        if candidates.empty:
            return []

        max_cost = _feature_float(features, "max_cost_usd")
        choices: list[RoleChoice] = []
        for model_id, group in candidates.groupby(role_column):
            success = _mean_bool(group["completed_successfully"], default=0.5)
            quality = _mean_number(group["score"], default=success)
            cost = _median_number(group["actual_cost_usd"])
            if cost is None:
                cost = _median_number(group["expected_cost_usd"])

            support = int(len(group))
            support_bonus = min(math.log1p(support) / 10.0, 0.2)
            cost_penalty = _cost_penalty(cost, max_cost)
            route_score = 0.55 * success + 0.30 * quality + support_bonus - cost_penalty
            choices.append(
                RoleChoice(
                    model_id=str(model_id),
                    score=_clamp(route_score, 0.0, 1.0),
                    support=support,
                    expected_success=_clamp((success + quality) / 2.0, 0.0, 1.0),
                    estimated_cost_usd=cost,
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
        "files_touched_bucket": _files_bucket(row.get("file_count")),
        "description_length_bucket": _description_bucket(task_description),
        "risk_level": _first_nonempty(
            [row.get("risk_level"), context.get("risk_level"), FEATURE_DEFAULTS["risk_level"]]
        ),
        "requires_tests": _coerce_bool(row.get("requires_tests")),
        "is_migration": _contains_any(task_description, ["migration", "schema", "alembic"]),
        "ui_heavy": _contains_any(task_description, ["ui", "frontend", "component"]),
        "cross_service": _contains_any(task_description, ["service", "integration", "api"]),
        "allowed_models": row.get("allowed_models"),
        "preferred_models": row.get("preferred_models"),
        "available_planner_models": row.get("available_planner_models"),
        "available_coder_models": row.get("available_coder_models"),
        "available_reviewer_models": row.get("available_reviewer_models"),
        "planner_models": workflow.get("planner_models"),
        "coder_models": workflow.get("coder_models"),
        "reviewer_models": workflow.get("reviewer_models"),
        "max_cost_usd": row.get("max_cost_usd"),
        "expected_cost_usd": row.get("expected_cost_usd"),
    }

    normalized["complexity"] = _complexity_number(
        row.get("estimated_complexity") or context.get("estimated_complexity")
    )
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


def _mean_bool(values: Iterable[Any], *, default: float) -> float:
    coerced = [_coerce_bool(value) for value in values]
    return sum(coerced) / len(coerced) if coerced else default


def _mean_number(values: Iterable[Any], *, default: float) -> float:
    numbers = [float(value) for value in values if _is_finite_number(value)]
    return sum(numbers) / len(numbers) if numbers else default


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
