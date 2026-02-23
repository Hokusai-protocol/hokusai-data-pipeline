"""Exploration helpers for DeepEval-style judge resolution in MLflow.

Authentication for any remote MLflow lookup should be provided through
``MLFLOW_TRACKING_TOKEN`` or equivalent environment-based auth configuration.
"""

from __future__ import annotations

from typing import Any


def is_deepeval_judge_api_available() -> bool:
    """Return whether MLflow exposes a module-level ``get_judge`` API."""
    try:
        from mlflow import genai
    except Exception:
        return False

    return hasattr(genai, "get_judge")


def get_deepeval_judge(metric_name: str) -> Any:
    """Try to resolve a DeepEval judge through MLflow."""
    if not is_deepeval_judge_api_available():
        raise NotImplementedError(
            "DeepEval judge lookup is unavailable in this MLflow runtime. "
            "Expected API: mlflow.genai.get_judge('deepeval://<metric>')."
        )

    from mlflow import genai

    return genai.get_judge(f"deepeval://{metric_name}")


def get_faithfulness_judge() -> Any:
    """Resolve the DeepEval faithfulness judge if supported."""
    return get_deepeval_judge("faithfulness")


def get_answer_relevancy_judge() -> Any:
    """Resolve the DeepEval answer relevancy judge if supported."""
    return get_deepeval_judge("answer_relevancy")


def get_contextual_precision_judge() -> Any:
    """Resolve the DeepEval contextual precision judge if supported."""
    return get_deepeval_judge("contextual_precision")
