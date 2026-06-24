from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.model_30 import build_synthetic_reward_e2e as synthetic
from src.events.schemas import MintRequest

ESCROW = "0x9999999999999999999999999999999999999999"


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
