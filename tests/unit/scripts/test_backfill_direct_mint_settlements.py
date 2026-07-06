from __future__ import annotations

import pytest

from scripts.backfill_direct_mint_settlements import (
    build_mint_result_from_receipt,
    recipient_kinds_from_mint_request,
    validate_no_ambiguous_pending_wallet_rows,
)
from src.api.services.auth_service_notifier import AuthServiceNotifier
from src.events.schemas import MintRequest, MintRequestContributor, MintRequestEvaluation


def _mint_request(
    *,
    wallet_kind: str = "wallet",
    escrow_kind: str = "escrow",
) -> MintRequest:
    return MintRequest(
        message_id="mint-msg-1",
        timestamp="2026-07-05T14:44:12+00:00",
        model_id="30",
        model_id_uint="30",
        eval_id="eval-1",
        benchmark_spec_id="technical_task_router.benchmark_score/v2",
        dataset_hash="0x" + "1" * 64,
        attestation_hash="0x" + "2" * 64,
        idempotency_key="0x" + "3" * 64,
        baseline_commitment="0x" + "4" * 64,
        candidate_commitment="0x" + "5" * 64,
        attester_signatures=["0x" + ("0123456789abcdef" * 8) + "1b"],
        total_samples=25,
        deadline=4102444800,
        evaluation=MintRequestEvaluation(
            metric_name="technical_task_router.benchmark_score/v2",
            metric_family="continuous",
            baseline_score_bps=5331,
            new_score_bps=5431,
            max_cost_usd_micro=100,
            actual_cost_usd_micro=50,
            sample_size_candidate=25,
        ),
        contributors=[
            MintRequestContributor(
                wallet_address="0x1111111111111111111111111111111111111111",
                weight_bps=6000,
                submission_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                contributor_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                recipient_kind=wallet_kind,
            ),
            MintRequestContributor(
                wallet_address="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                weight_bps=4000,
                submission_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                contributor_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
                recipient_kind=escrow_kind,
            ),
        ],
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


def test_build_mint_result_from_receipt_uses_historical_deployment_token_address() -> None:
    result = build_mint_result_from_receipt(
        {
            "status": 1,
            "transactionHash": "0x" + "9" * 64,
            "blockTimestamp": "2026-07-03T18:00:00+00:00",
        },
        token_symbol="HROUT",
        token_address=None,
        deployment={"token_address": "0x" + "7" * 40},
    )

    assert result.token_address == "0x" + "7" * 40
    assert result.deployment == {"token_address": "0x" + "7" * 40}


def test_recipient_kinds_from_mint_request_preserves_mixed_routing() -> None:
    assert recipient_kinds_from_mint_request(_mint_request()) == {
        "0x1111111111111111111111111111111111111111": "wallet",
        "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee": "escrow",
    }


def test_mixed_backfill_settlement_rows_skip_escrow_contributors() -> None:
    mint_request = _mint_request()
    mint_result = build_mint_result_from_receipt(
        {
            "status": "0x1",
            "transactionHash": "0x" + "9" * 64,
            "blockTimestamp": "2026-07-03T18:00:00+00:00",
            "vesting": {
                "schedule_id": "10",
                "vault_address": "0x" + "8" * 40,
                "liquid_amount": "25000",
                "vested_amount": "225000",
            },
        },
        token_symbol="HROUT",
        token_address="0x" + "7" * 40,
        deployment={"network": "sepolia", "token_address": "0x" + "7" * 40},
    )
    notifier = AuthServiceNotifier(
        auth_service_url="https://auth.service.local",
        internal_token="secret",
        dry_run=True,
    )

    rows = notifier._build_direct_mint_settlement_rows(
        mint_request=mint_request,
        mint_result=mint_result,
        reward_tokens=250000,
        token_address=mint_result.token_address,
        token_symbol="HROUT",
        deployment=mint_result.deployment,
        recipient_kinds=recipient_kinds_from_mint_request(mint_request),
    )

    assert len(rows) == 1
    assert rows[0].user_id == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert rows[0].recipient_address == "0x1111111111111111111111111111111111111111"
    assert rows[0].amount == 150000
    assert rows[0].immediate_amount == 15000
    assert rows[0].vested_amount == 135000
    assert rows[0].vesting_schedule is not None
    assert rows[0].vesting_schedule["schedule_id"] == "10"


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


def test_validate_no_ambiguous_pending_wallet_rows_allows_escrow_pending() -> None:
    validate_no_ambiguous_pending_wallet_rows(
        [
            {
                "reward_id": "reward-escrow",
                "status": "pending",
                "recipient_kind": "escrow",
                "metadata": {"escrow_address": "0x" + "e" * 40},
            }
        ]
    )


def test_validate_no_ambiguous_pending_wallet_rows_allows_settlement_metadata() -> None:
    validate_no_ambiguous_pending_wallet_rows(
        [
            {
                "reward_id": "reward-settled",
                "status": "pending",
                "recipient_kind": "wallet",
                "metadata": {"settlement": {"type": "direct_mint"}},
            }
        ]
    )
