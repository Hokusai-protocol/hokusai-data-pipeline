"""Economic guardrails for DeltaOne reward minting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RewardCapResult:
    """Computed reward metadata for a single accepted evaluation."""

    reward_tokens: float
    capped: bool


@dataclass(frozen=True)
class BudgetConfig:
    """Economic guardrail settings loaded from Model 30 budget config."""

    tokens_per_delta_one: float | None = None
    max_reward_per_eval: float | None = None
    mint_paused: bool = False

    @classmethod
    def from_yaml(cls: type[BudgetConfig], path: str | Path) -> BudgetConfig:
        """Load economic guardrail settings from YAML."""
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        if not isinstance(raw, dict):
            raise ValueError("budget config must deserialize to a mapping")
        return cls(
            tokens_per_delta_one=_coerce_optional_float(raw.get("tokensPerDeltaOne")),
            max_reward_per_eval=_coerce_optional_float(raw.get("maxRewardPerEval")),
            mint_paused=_coerce_bool(raw.get("mint_paused", False)),
        )

    @classmethod
    def from_yaml_safe(cls: type[BudgetConfig], path: str | Path) -> BudgetConfig:
        """Load config with fail-closed semantics on any parse or validation error."""
        try:
            return cls.from_yaml(path)
        except Exception:
            logger.exception("event=budget_config_load_failed path=%s", path)
            return cls(mint_paused=True)


def compute_reward(
    delta_one: float,
    *,
    tokens_per_delta_one: float | None = None,
    max_reward_per_eval: float | None = None,
) -> RewardCapResult:
    """Compute capped token reward for a DeltaOne improvement."""
    delta = max(0.0, float(delta_one))
    if tokens_per_delta_one is None:
        return RewardCapResult(reward_tokens=delta, capped=False)

    raw_reward = delta * tokens_per_delta_one
    if max_reward_per_eval is not None and raw_reward > max_reward_per_eval:
        return RewardCapResult(reward_tokens=max_reward_per_eval, capped=True)
    return RewardCapResult(reward_tokens=raw_reward, capped=False)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    coerced = float(value)
    if coerced < 0:
        raise ValueError("budget config floats must be non-negative")
    return coerced


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("mint_paused must be a boolean")
