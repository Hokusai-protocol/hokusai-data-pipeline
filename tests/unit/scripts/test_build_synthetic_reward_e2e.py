from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.model_30 import build_synthetic_reward_e2e as synthetic
from src.events.schemas import MintRequest

ESCROW = "0x9999999999999999999999999999999999999999"
TEST_WALLET_A = "0x2222222222222222222222222222222222222222"
TEST_WALLET_B = "0x3333333333333333333333333333333333333333"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "model_30_training_manifest/v1",
        "as_of": "2026-06-24T00:00:00Z",
        "dataset_hash": "sha256:" + ("a" * 64),
        "manifest_digest": "sha256:" + ("b" * 64),
        "row_count": 3,
        "model_id": "30",
        "blocks": [
            {
                "submission_id": "sub-a",
                "account_id": "acct-a",
                "wallet": None,
                "s3_key": "s3://bucket/a.jsonl",
                "row_start": 0,
                "row_end": 1,
                "row_count": 2,
                "reward_hold": True,
            },
            {
                "submission_id": "sub-b",
                "account_id": "acct-b",
                "wallet": "0x1111111111111111111111111111111111111111",
                "s3_key": "s3://bucket/b.jsonl",
                "row_start": 2,
                "row_end": 2,
                "row_count": 1,
                "reward_hold": False,
            },
        ],
        "quarantine_count": 0,
        "duplicates_dropped": [],
        "wallet_policy": "hold",
    }


def _comparison() -> dict[str, object]:
    return {
        "baseline_model_id": "models:/Technical Task Router@production",
        "candidate_model_id": "models:/Technical Task Router/7",
        "baseline_metrics": {"technical_task_router.benchmark_score_v2": 0.53},
        "candidate_metrics": {"technical_task_router.benchmark_score_v2": 0.53},
        "deltas": {"technical_task_router.benchmark_score_v2": 0.0},
        "primary_metric": "technical_task_router.benchmark_score_v2",
        "primary_delta": 0.0,
        "benchmark_rows": 25,
    }


def _source_attribution() -> dict[str, object]:
    return {
        "schema_version": "attribution_report/v1",
        "model_id": "30",
        "method": "neighbor_provenance",
        "baseline_run_id": "run-base",
        "candidate_run_id": "run-cand",
        "created_at": "2026-06-24T00:00:00Z",
        "total_rows_evaluated": 25,
        "rows_improved": 0,
        "contributors": [],
        "weight_bps_total": 0,
    }


def test_main_writes_schema_valid_attribution_and_mint_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    comparison = _write_json(tmp_path / "comparison.json", _comparison())
    source = _write_json(tmp_path / "source_attribution.json", _source_attribution())
    output_dir = tmp_path / "out"

    result = synthetic.main(
        [
            "--manifest",
            str(manifest),
            "--comparison-report",
            str(comparison),
            "--source-attribution",
            str(source),
            "--output-dir",
            str(output_dir),
            "--environment",
            "development",
            "--escrow-wallet",
            ESCROW,
            "--allow-synthetic-commitments",
        ]
    )

    assert result == 0
    report = json.loads((output_dir / "synthetic_attribution_report.json").read_text())
    assert report["method_details"]["synthetic_e2e"] is True
    assert report["weight_bps_total"] == 10000
    assert [item["weight_bps"] for item in report["contributors"]] == [6667, 3333]
    assert report["contributors"][0]["account_id"] == "acct-a"

    request = MintRequest.model_validate_json(
        (output_dir / "synthetic_mint_request.json").read_text()
    )
    assert request.model_id == "30"
    assert request.evaluation.new_score_bps > request.evaluation.baseline_score_bps
    assert request.contributors[0].wallet_address == ESCROW
    assert request.contributors[0].contributor_id == "acct-a"
    # v2 conformance: the dry-run MintRequest must advertise the canonical composite metric
    # name and the continuous family signed by the on-chain DeltaVerifier (HOK-2216/2217).
    assert request.evaluation.metric_name == "technical_task_router.benchmark_score/v2"
    assert request.evaluation.metric_family == "continuous"
    assert request.benchmark_spec_id == "technical_task_router.benchmark_score/v2"


def test_extra_test_wallets_reserve_bps_from_contributor_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    manifest = _write_json(tmp_path / "manifest.json", _manifest())
    comparison = _write_json(tmp_path / "comparison.json", _comparison())
    output_dir = tmp_path / "out"

    synthetic.main(
        [
            "--manifest",
            str(manifest),
            "--comparison-report",
            str(comparison),
            "--baseline-run-id",
            "run-base",
            "--candidate-run-id",
            "run-cand",
            "--output-dir",
            str(output_dir),
            "--environment",
            "development",
            "--escrow-wallet",
            ESCROW,
            "--extra-test-wallet",
            f"{TEST_WALLET_A}:100",
            "--extra-test-wallet",
            f"{TEST_WALLET_B}:100",
            "--allow-synthetic-commitments",
        ]
    )

    report = json.loads((output_dir / "synthetic_attribution_report.json").read_text())
    assert report["method_details"]["extra_test_wallets"] == [
        {
            "wallet_address": TEST_WALLET_A,
            "weight_bps": 100,
            "contributor_id": "synthetic-test-wallet-1",
            "submission_id": None,
        },
        {
            "wallet_address": TEST_WALLET_B,
            "weight_bps": 100,
            "contributor_id": "synthetic-test-wallet-2",
            "submission_id": None,
        },
    ]

    request = MintRequest.model_validate_json(
        (output_dir / "synthetic_mint_request.json").read_text()
    )
    contributors = {item.contributor_id: item for item in request.contributors}
    assert sum(item.weight_bps for item in request.contributors) == 10000
    assert contributors["acct-a"].weight_bps == 6534
    assert contributors["acct-b"].weight_bps == 3266
    assert contributors["synthetic-test-wallet-1"].wallet_address == TEST_WALLET_A
    assert contributors["synthetic-test-wallet-1"].weight_bps == 100
    assert contributors["synthetic-test-wallet-2"].wallet_address == TEST_WALLET_B
    assert contributors["synthetic-test-wallet-2"].weight_bps == 100


def test_requires_explicit_synthetic_guard(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=synthetic.ALLOW_ENV):
        synthetic.main(
            [
                "--manifest",
                str(_write_json(tmp_path / "manifest.json", _manifest())),
                "--comparison-report",
                str(_write_json(tmp_path / "comparison.json", _comparison())),
                "--baseline-run-id",
                "run-base",
                "--candidate-run-id",
                "run-cand",
                "--output-dir",
                str(tmp_path / "out"),
                "--environment",
                "development",
                "--escrow-wallet",
                ESCROW,
            ]
        )


def test_refuses_production_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")

    with pytest.raises(SystemExit, match="forbidden"):
        synthetic.main(
            [
                "--manifest",
                str(_write_json(tmp_path / "manifest.json", _manifest())),
                "--comparison-report",
                str(_write_json(tmp_path / "comparison.json", _comparison())),
                "--baseline-run-id",
                "run-base",
                "--candidate-run-id",
                "run-cand",
                "--output-dir",
                str(tmp_path / "out"),
                "--environment",
                "production",
                "--escrow-wallet",
                ESCROW,
            ]
        )


def test_publish_requires_real_commitments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")

    with pytest.raises(SystemExit, match="baseline-commitment"):
        synthetic.main(
            [
                "--manifest",
                str(_write_json(tmp_path / "manifest.json", _manifest())),
                "--comparison-report",
                str(_write_json(tmp_path / "comparison.json", _comparison())),
                "--baseline-run-id",
                "run-base",
                "--candidate-run-id",
                "run-cand",
                "--output-dir",
                str(tmp_path / "out"),
                "--environment",
                "development",
                "--escrow-wallet",
                ESCROW,
                "--publish",
            ]
        )


def test_publish_with_auth_reward_recording_rejects_placeholder_contributors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    monkeypatch.setenv("MINT_REQUIRE_AUTH_REWARD_RECORDING", "true")
    monkeypatch.setattr(synthetic.MintRequestPublisher, "publish", lambda *_args: None)

    with pytest.raises(SystemExit, match="cannot be recorded by auth reward ingest"):
        synthetic.main(
            [
                "--manifest",
                str(_write_json(tmp_path / "manifest.json", _manifest())),
                "--comparison-report",
                str(_write_json(tmp_path / "comparison.json", _comparison())),
                "--baseline-run-id",
                "run-base",
                "--candidate-run-id",
                "run-cand",
                "--output-dir",
                str(tmp_path / "out"),
                "--environment",
                "development",
                "--escrow-wallet",
                ESCROW,
                "--baseline-commitment",
                "0x" + "44" * 32,
                "--candidate-commitment",
                "0x" + "55" * 32,
                "--publish",
            ]
        )


def test_extra_test_wallet_can_be_auth_recordable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    user_id = "44444444-4444-4444-4444-444444444444"
    submission_id = "33333333-3333-3333-3333-333333333333"

    output_dir = tmp_path / "out"
    synthetic.main(
        [
            "--manifest",
            str(_write_json(tmp_path / "manifest.json", _manifest())),
            "--comparison-report",
            str(_write_json(tmp_path / "comparison.json", _comparison())),
            "--baseline-run-id",
            "run-base",
            "--candidate-run-id",
            "run-cand",
            "--output-dir",
            str(output_dir),
            "--environment",
            "development",
            "--escrow-wallet",
            ESCROW,
            "--extra-test-wallet",
            f"{TEST_WALLET_A}:100:{user_id}:{submission_id}",
            "--allow-synthetic-commitments",
        ]
    )

    request = MintRequest.model_validate_json(
        (output_dir / "synthetic_mint_request.json").read_text()
    )
    extra = next(item for item in request.contributors if item.wallet_address == TEST_WALLET_A)
    assert extra.contributor_id == user_id
    assert extra.submission_id == submission_id


def test_settlement_template_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    output_dir = tmp_path / "out"

    synthetic.main(
        [
            "--manifest",
            str(_write_json(tmp_path / "manifest.json", _manifest())),
            "--comparison-report",
            str(_write_json(tmp_path / "comparison.json", _comparison())),
            "--baseline-run-id",
            "run-base",
            "--candidate-run-id",
            "run-cand",
            "--output-dir",
            str(output_dir),
            "--environment",
            "development",
            "--escrow-wallet",
            ESCROW,
            "--settlement-reward-tokens",
            "245000",
            "--settlement-token-address",
            "0x" + "7" * 40,
            "--allow-synthetic-commitments",
        ]
    )

    template = (output_dir / "settlement_backfill_command.sh").read_text()
    assert "scripts/backfill_direct_mint_settlements.py" in template
    assert "--mint-request" in template
    assert "synthetic_mint_request.json" in template
    assert "--receipt" in template
    assert "sepolia_tx_receipt.json" in template
    assert "--reward-tokens 245000" in template
    assert "--token-symbol HROUT" in template


def test_attester_signature_deadline_and_typed_data_are_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(synthetic.ALLOW_ENV, "true")
    output_dir = tmp_path / "out"
    signature = "0x" + "1" * 130

    synthetic.main(
        [
            "--manifest",
            str(_write_json(tmp_path / "manifest.json", _manifest())),
            "--comparison-report",
            str(_write_json(tmp_path / "comparison.json", _comparison())),
            "--baseline-run-id",
            "run-base",
            "--candidate-run-id",
            "run-cand",
            "--output-dir",
            str(output_dir),
            "--environment",
            "development",
            "--escrow-wallet",
            ESCROW,
            "--deadline",
            "4102444800",
            "--attester-signature",
            signature,
            "--mint-chain-id",
            "11155111",
            "--mint-verifying-contract",
            "0x" + "8" * 40,
            "--allow-synthetic-commitments",
        ]
    )

    request = MintRequest.model_validate_json(
        (output_dir / "synthetic_mint_request.json").read_text()
    )
    assert request.deadline == 4102444800
    assert request.attester_signatures == [signature.lower()]

    typed_data = json.loads((output_dir / "synthetic_mint_typed_data.json").read_text())
    assert typed_data["domain"]["chainId"] == 11155111
    assert typed_data["domain"]["verifyingContract"] == "0x" + "8" * 40
    assert typed_data["message"]["payload"]["deadline"] == 4102444800
