"""Ranking-quality LLM-as-a-judge templates."""

from __future__ import annotations

from typing import Any

from .base import JudgeConfig, create_judge


def create_ranking_judge(config: JudgeConfig | None = None) -> Any:
    """Create a ranking judge for relevance-order quality.

    Expects ``{{ outputs }}`` to contain model-ranked candidates and
    ``{{ expectations }}`` to include ideal ordering or relevance targets.
    """
    instructions = (
        "You are an expert ranking evaluator.\n"
        "Given INPUTS={{ inputs }}, model-ranked OUTPUTS={{ outputs }}, and "
        "EXPECTATIONS={{ expectations }}, "
        "assess how well the ordering matches expected relevance.\n"
        "Use NDCG-style thinking: highly relevant items should appear earlier, and severe ordering "
        "mistakes should be penalized.\n"
        "Return:\n"
        "1) Ranking score from 1-5 (5 is best ordering).\n"
        "2) Brief rationale about top-of-list quality and major ordering errors."
    )
    return create_judge(
        base_name="ranking_quality",
        instructions=instructions,
        config=config,
    )
