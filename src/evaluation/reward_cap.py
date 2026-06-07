"""Economic guardrails for DeltaOne reward minting."""

from __future__ import annotations

import logging
import os
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
    per_eval_budget_ceiling_usd: float | None = None
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
            per_eval_budget_ceiling_usd=_coerce_optional_float(raw.get("perEvalBudgetCeilingUsd")),
            mint_paused=_coerce_bool(raw.get("mint_paused", False)),
        )

    @classmethod
    def from_env(cls: type[BudgetConfig]) -> BudgetConfig:
        """Load economic guardrail settings from environment variables."""
        return cls(
            tokens_per_delta_one=_coerce_optional_float_env("MINT_TOKENS_PER_DELTA_ONE"),
            max_reward_per_eval=_coerce_optional_float_env("MINT_MAX_REWARD"),
            per_eval_budget_ceiling_usd=_coerce_optional_float_env("MINT_PER_EVAL_BUDGET_CEILING"),
            mint_paused=_coerce_env_bool("MINT_PAUSED", default=False),
        )

    @classmethod
    def from_yaml_or_env(cls: type[BudgetConfig], path: str | Path) -> BudgetConfig:
        """Load config from YAML when present, otherwise from environment.

        Fails closed (mint_paused=True) if the YAML file exists but cannot be
        parsed — falling through to env in that case could silently disable
        every guardrail when env vars are unset.
        """
        config_path = Path(path)
        if config_path.exists():
            try:
                return cls.from_yaml(config_path)
            except Exception:
                logger.exception("event=budget_config_yaml_load_failed path=%s", config_path)
                return cls(mint_paused=True)
        return cls.from_env()

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


def _coerce_optional_float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return _coerce_optional_float(raw)


def _coerce_env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean string")
