"""Reusable MLflow judge templates with lazy imports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "JudgeConfig",
    "create_judge",
    "register_judge",
    "list_registered_judges",
    "create_classification_judge",
    "create_generation_judge",
    "create_ranking_judge",
    "create_session_scorer",
    "is_deepeval_judge_api_available",
    "get_deepeval_judge",
    "get_faithfulness_judge",
    "get_answer_relevancy_judge",
    "get_contextual_precision_judge",
]

_MODULE_MAP: dict[str, tuple[str, str]] = {
    "JudgeConfig": ("src.evaluation.judges.base", "JudgeConfig"),
    "create_judge": ("src.evaluation.judges.base", "create_judge"),
    "register_judge": ("src.evaluation.judges.base", "register_judge"),
    "list_registered_judges": ("src.evaluation.judges.base", "list_registered_judges"),
    "create_classification_judge": (
        "src.evaluation.judges.classification",
        "create_classification_judge",
    ),
    "create_generation_judge": ("src.evaluation.judges.generation", "create_generation_judge"),
    "create_ranking_judge": ("src.evaluation.judges.ranking", "create_ranking_judge"),
    "create_session_scorer": (
        "src.evaluation.judges.session_scorer",
        "create_session_scorer",
    ),
    "is_deepeval_judge_api_available": (
        "src.evaluation.judges.deepeval_integration",
        "is_deepeval_judge_api_available",
    ),
    "get_deepeval_judge": ("src.evaluation.judges.deepeval_integration", "get_deepeval_judge"),
    "get_faithfulness_judge": (
        "src.evaluation.judges.deepeval_integration",
        "get_faithfulness_judge",
    ),
    "get_answer_relevancy_judge": (
        "src.evaluation.judges.deepeval_integration",
        "get_answer_relevancy_judge",
    ),
    "get_contextual_precision_judge": (
        "src.evaluation.judges.deepeval_integration",
        "get_contextual_precision_judge",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve judge APIs on first attribute access."""
    try:
        module_path, attr_name = _MODULE_MAP[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = __import__(module_path, fromlist=[attr_name])
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes for introspection and auto-complete."""
    return sorted(set(globals()) | set(__all__))
