"""Unit coverage for budget config loading and reward cap behavior."""

from __future__ import annotations

from pathlib import Path

from src.evaluation.reward_cap import BudgetConfig, compute_reward


def test_budget_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MINT_MAX_REWARD", "42.5")
    monkeypatch.setenv("MINT_TOKENS_PER_DELTA_ONE", "12")
    monkeypatch.setenv("MINT_PER_EVAL_BUDGET_CEILING", "7.25")
    monkeypatch.setenv("MINT_PAUSED", "true")

    config = BudgetConfig.from_env()

    assert config.max_reward_per_eval == 42.5
    assert config.tokens_per_delta_one == 12.0
    assert config.per_eval_budget_ceiling_usd == 7.25
    assert config.mint_paused is True


def test_budget_config_from_yaml_safe_fail_closed(tmp_path: Path) -> None:
    bad_config = tmp_path / "budget.yaml"
    bad_config.write_text("mint_paused: nope\n", encoding="utf-8")

    config = BudgetConfig.from_yaml_safe(bad_config)

    assert config.mint_paused is True


def test_budget_config_from_yaml_or_env_fail_closed_on_corrupt_yaml(
    tmp_path: Path, monkeypatch
) -> None:
    # Existing-but-corrupt YAML must NOT silently fall through to env vars,
    # because empty env vars would disable every guardrail (fail-open).
    bad_config = tmp_path / "budget.yaml"
    bad_config.write_text("mint_paused: nope\n", encoding="utf-8")
    monkeypatch.delenv("MINT_MAX_REWARD", raising=False)
    monkeypatch.delenv("MINT_TOKENS_PER_DELTA_ONE", raising=False)
    monkeypatch.delenv("MINT_PER_EVAL_BUDGET_CEILING", raising=False)
    monkeypatch.delenv("MINT_PAUSED", raising=False)

    config = BudgetConfig.from_yaml_or_env(bad_config)

    assert config.mint_paused is True


def test_budget_config_from_yaml_or_env_falls_back_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    # Missing YAML file is the intended "fall back to env" path.
    missing_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("MINT_MAX_REWARD", "11")
    monkeypatch.setenv("MINT_TOKENS_PER_DELTA_ONE", "2")
    monkeypatch.delenv("MINT_PER_EVAL_BUDGET_CEILING", raising=False)
    monkeypatch.delenv("MINT_PAUSED", raising=False)

    config = BudgetConfig.from_yaml_or_env(missing_path)

    assert config.max_reward_per_eval == 11.0
    assert config.tokens_per_delta_one == 2.0
    assert config.mint_paused is False


def test_compute_reward_no_cap() -> None:
    result = compute_reward(2.0, tokens_per_delta_one=50.0)
    assert result.reward_tokens == 100.0
    assert result.capped is False


def test_compute_reward_max_reward_cap() -> None:
    result = compute_reward(10.0, tokens_per_delta_one=50.0, max_reward_per_eval=250.0)
    assert result.reward_tokens == 250.0
    assert result.capped is True


def test_compute_reward_boundary() -> None:
    result = compute_reward(5.0, tokens_per_delta_one=50.0, max_reward_per_eval=250.0)
    assert result.reward_tokens == 250.0
    assert result.capped is False


def test_per_eval_budget_ceiling_field_round_trips(tmp_path: Path) -> None:
    config_path = tmp_path / "budget.yaml"
    config_path.write_text(
        "\n".join(
            [
                "tokensPerDeltaOne: 10",
                "maxRewardPerEval: 20",
                "perEvalBudgetCeilingUsd: 30",
                "mint_paused: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = BudgetConfig.from_yaml_or_env(config_path)

    assert config.tokens_per_delta_one == 10.0
    assert config.max_reward_per_eval == 20.0
    assert config.per_eval_budget_ceiling_usd == 30.0
    assert config.mint_paused is False
