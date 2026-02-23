"""Classification-oriented LLM-as-a-judge templates."""

from __future__ import annotations

from typing import Any

from .base import JudgeConfig, create_judge


def create_classification_judge(task_description: str, config: JudgeConfig | None = None) -> Any:
    """Create a reusable classification correctness judge."""
    instructions = (
        "You are an expert classification evaluator.\n"
        f"Task description: {task_description}\n\n"
        "Given INPUTS={{ inputs }}, model OUTPUTS={{ outputs }}, and "
        "EXPECTATIONS={{ expectations }}, "
        "determine whether the output label(s) are correct for the task. "
        "Support binary, multi-class, and multi-label cases.\n"
        "Respond with:\n"
        "1) A verdict: CORRECT or INCORRECT.\n"
        "2) A numeric score from 1-5 where 5 is fully correct and 1 is fully incorrect.\n"
        "3) A concise rationale focusing on label correctness and task constraints."
    )
    return create_judge(
        base_name="classification_correctness",
        instructions=instructions,
        config=config,
    )
