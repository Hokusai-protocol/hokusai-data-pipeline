"""Generation-quality LLM-as-a-judge templates."""

from __future__ import annotations

from typing import Any

from .base import JudgeConfig, create_judge

_DEFAULT_DIMENSIONS = ["fluency", "relevance", "coherence", "faithfulness"]


def create_generation_judge(metrics: list[str], config: JudgeConfig | None = None) -> Any:
    """Create a generation quality judge with configurable dimensions."""
    dimensions = metrics or _DEFAULT_DIMENSIONS
    dimensions_text = ", ".join(dimensions)
    instructions = (
        "You are an expert text-generation evaluator.\n"
        f"Evaluate the following dimensions: {dimensions_text}.\n\n"
        "Given INPUTS={{ inputs }}, model OUTPUTS={{ outputs }}, and "
        "EXPECTATIONS={{ expectations }}, "
        "rate each requested dimension from 1-5 (5 is best).\n"
        "Return:\n"
        "1) Per-dimension score.\n"
        "2) Overall score from 1-5 as an aggregate quality signal.\n"
        "3) Short rationale that calls out strengths and failures.\n"
        "Emphasize factual alignment and user intent satisfaction."
    )
    return create_judge(
        base_name="generation_quality",
        instructions=instructions,
        config=config,
    )
