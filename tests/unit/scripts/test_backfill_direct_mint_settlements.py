from __future__ import annotations

import pytest

from scripts.backfill_direct_mint_settlements import (
    build_mint_result_from_receipt,
    validate_no_ambiguous_pending_wallet_rows,
)


def test_build_mint_result_from_receipt_extracts_vesting_log() -> None:
    result = build_mint_result_from_receipt(
        {
            "status": "0x1",
            "transactionHash": "0x" + "9" * 64,
            "blockTimestamp": "2026-07-03T18:00:00+00:00",
            "logs": [
                {
                    "event": "VestingScheduleCreated",
                    "args": {
                        "scheduleId": "7",
                        "vaultAddress": "0x" + "8" * 40,
                        "vestedAmount": "196000",
                        "liquidAmount": "49000",
                    },
                }
            ],
        },
        token_symbol="HROUT",
        token_address="0x" + "7" * 40,
        deployment={"delta_verifier": "0x" + "1" * 40},
    )

    assert result.status == "success"
    assert result.tx_hash == "0x" + "9" * 64
    assert result.token_symbol == "HROUT"
    assert result.token_address == "0x" + "7" * 40
    assert result.vesting_payload() == {
        "liquid_amount": "49000",
        "vested_amount": "196000",
        "vault_address": "0x" + "8" * 40,
        "schedule_id": "7",
        "token_address": "0x" + "7" * 40,
    }


def test_validate_no_ambiguous_pending_wallet_rows_rejects_spinner_rows() -> None:
    with pytest.raises(ValueError, match="ambiguous pending wallet rewards"):
        validate_no_ambiguous_pending_wallet_rows(
            [
                {
                    "reward_id": "reward-1",
                    "status": "pending",
                    "recipient_kind": "wallet",
                    "metadata": {"source": "old-backfill"},
                }
            ]
        )


def test_validate_no_ambiguous_pending_wallet_rows_allows_mint_pending() -> None:
    validate_no_ambiguous_pending_wallet_rows(
        [
            {
                "reward_id": "reward-1",
                "status": "pending",
                "recipient_kind": "wallet",
                "metadata": {"settlement_status": "mint_pending"},
            }
        ]
    )
