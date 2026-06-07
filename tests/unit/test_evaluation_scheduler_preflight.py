"""Unit tests for scheduler preflight guardrails."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.services.evaluation_scheduler import SchedulerPreflightError, preflight_check


def test_preflight_fails_without_max_reward(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "budget.yaml"
    config_path.write_text("mint_paused: false\n", encoding="utf-8")
    monkeypatch.setenv("SIGNER_CUSTODY_MODE", "kms")

    with pytest.raises(SchedulerPreflightError, match="max_reward_per_eval"):
        preflight_check(
            {
                "ENVIRONMENT": "production",
                "MINT_BUDGET_CONFIG_PATH": str(config_path),
            }
        )


def test_preflight_fails_env_custody_on_prod(tmp_path: Path) -> None:
    config_path = tmp_path / "budget.yaml"
    config_path.write_text(
        "maxRewardPerEval: 10\nmint_paused: false\n",
        encoding="utf-8",
    )

    with pytest.raises(SchedulerPreflightError, match="SIGNER_CUSTODY_MODE=env"):
        preflight_check(
            {
                "ENVIRONMENT": "production",
                "MINT_BUDGET_CONFIG_PATH": str(config_path),
                "SIGNER_CUSTODY_MODE": "env",
            }
        )


def test_preflight_passes_with_valid_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "budget.yaml"
    config_path.write_text(
        "maxRewardPerEval: 10\nperEvalBudgetCeilingUsd: 5\nmint_paused: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SIGNER_CUSTODY_MODE", "kms")

    preflight_check(
        {
            "ENVIRONMENT": "production",
            "MINT_BUDGET_CONFIG_PATH": str(config_path),
        }
    )
