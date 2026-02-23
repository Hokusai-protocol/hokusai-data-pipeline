"""Session-level conversation scorer exploration using MLflow judges."""

from __future__ import annotations

from typing import Any

from .base import JudgeConfig, create_judge


def create_session_scorer(config: JudgeConfig | None = None) -> Any:
    """Create a trace/session-level scorer for multi-turn conversations.

    MLflow 3.4 does not expose a distinct ``create_session_scorer`` API, but
    ``make_judge`` supports ``{{ trace }}`` templates, which can evaluate full
    multi-turn conversations captured in traces.
    """
    instructions = (
        "You are an expert multi-turn conversation evaluator.\n"
        "Evaluate the full conversation TRACE={{ trace }}.\n"
        "Assess turn-level coherence, instruction following over time, factual consistency, "
        "and whether the final user intent was satisfied.\n"
        "Return:\n"
        "1) Session quality score from 1-5.\n"
        "2) Concise rationale covering strengths and the most important failure mode."
    )
    return create_judge(
        base_name="session_conversation_quality",
        instructions=instructions,
        config=config,
    )
