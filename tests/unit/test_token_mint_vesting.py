"""Unit tests for vesting-aware token mint result parsing."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.api.schemas.token_mint import TokenMintResult


def test_legacy_token_mint_result_still_validates() -> None:
    result = TokenMintResult.model_validate(
        {
            "status": "success",
            "audit_ref": "audit-1",
            "timestamp": datetime.now(timezone.utc),
        }
    )

    assert result.has_vesting_details() is False
    assert result.vesting_payload() is None


def test_nested_vesting_response_round_trips() -> None:
    result = TokenMintResult.model_validate(
        {
            "status": "success",
            "audit_ref": "audit-1",
            "timestamp": datetime.now(timezone.utc),
            "vesting": {
                "liquid_amount": "100",
                "vested_amount": "900",
                "vault_address": "0xvault",
                "schedule_id": "schedule-1",
                "claimable_amount": "25",
                "vesting_config": {
                    "enabled": True,
                    "immediateUnlockBps": 1000,
                    "vestingDurationSeconds": 86400,
                },
            },
        }
    )

    assert result.vesting_payload() == {
        "liquid_amount": "100",
        "vested_amount": "900",
        "vault_address": "0xvault",
        "schedule_id": "schedule-1",
        "claimable_amount": "25",
        "vesting_config": {
            "enabled": True,
            "immediateUnlockBps": 1000,
            "vestingDurationSeconds": 86400,
        },
    }


def test_flat_vesting_fields_normalize_to_nested_payload() -> None:
    result = TokenMintResult.model_validate(
        {
            "status": "success",
            "audit_ref": "audit-1",
            "timestamp": datetime.now(timezone.utc),
            "liquid_amount": "100",
            "vested_amount": "900",
            "schedule_id": "schedule-1",
        }
    )

    assert result.vesting is not None
    assert result.vesting_payload() == {
        "liquid_amount": "100",
        "vested_amount": "900",
        "schedule_id": "schedule-1",
    }


@pytest.mark.parametrize("invalid_amount", [100, 10.5])
def test_amount_fields_reject_non_string_values(invalid_amount: object) -> None:
    with pytest.raises(ValidationError):
        TokenMintResult.model_validate(
            {
                "status": "success",
                "audit_ref": "audit-1",
                "timestamp": datetime.now(timezone.utc),
                "vesting": {
                    "liquid_amount": invalid_amount,
                },
            }
        )


def test_empty_vesting_is_omitted() -> None:
    result = TokenMintResult.model_validate(
        {
            "status": "success",
            "audit_ref": "audit-1",
            "timestamp": datetime.now(timezone.utc),
            "vesting": {
                "liquid_amount": None,
                "vested_amount": None,
            },
        }
    )

    assert result.vesting is None
    assert result.has_vesting_details() is False
    assert result.vesting_payload() is None
