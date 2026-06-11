from __future__ import annotations

# Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is patched out in
# this suite; the tests use fake MLflow clients and no live tracking requests.
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

from click.testing import CliRunner

from src.cli.attest_cli import attest
from src.cli.attestation import AttestationBuildResult, AttestationState


@dataclass
class _FakeClient:
    tags: dict[str, str]


def _build_result() -> AttestationBuildResult:
    return AttestationBuildResult(
        mint_request=object(),
        typed_data={"message": {"payload": {"baselineCommitment": "0x" + "11" * 32}}},
        digest_hex="0x" + "aa" * 32,
        baseline_commitment="0x" + "11" * 32,
    )


def test_attest_build_records_first_build(monkeypatch, tmp_path: Path) -> None:
    client = _FakeClient(tags={})
    runner = CliRunner()
    recorder = Mock()

    monkeypatch.setattr("src.cli.attest_cli.MlflowClient", Mock(return_value=client))
    monkeypatch.setattr(
        "src.cli.attest_cli.build_typed_data_for_run",
        Mock(return_value=_build_result()),
    )
    monkeypatch.setattr("src.cli.attest_cli.load_attestation_state", Mock(return_value=None))
    monkeypatch.setattr("src.cli.attest_cli.record_attestation_build", recorder)
    monkeypatch.setattr("src.cli.attest_cli.render_for_human", Mock(return_value="rendered"))

    result = runner.invoke(attest, ["build", "run-123", "--output", str(tmp_path / "out.json")])

    assert result.exit_code == 0
    recorder.assert_called_once()
    assert "rendered" in result.output


def test_attest_build_is_idempotent_when_digest_matches(monkeypatch) -> None:
    client = _FakeClient(tags={})
    runner = CliRunner()

    monkeypatch.setattr("src.cli.attest_cli.MlflowClient", Mock(return_value=client))
    monkeypatch.setattr(
        "src.cli.attest_cli.build_typed_data_for_run",
        Mock(return_value=_build_result()),
    )
    monkeypatch.setattr(
        "src.cli.attest_cli.load_attestation_state",
        Mock(
            return_value=AttestationState(
                digest_hex="0x" + "aa" * 32,
                baseline_commitment="0x" + "11" * 32,
                built_at="2026-06-11T00:00:00+00:00",
                signatures=[],
            )
        ),
    )
    monkeypatch.setattr("src.cli.attest_cli.render_for_human", Mock(return_value="rendered"))

    result = runner.invoke(attest, ["build", "run-123"])

    assert result.exit_code == 0
    assert "rendered" in result.output


def test_attest_attach_rejects_stale_baseline(monkeypatch) -> None:
    client = _FakeClient(tags={})
    runner = CliRunner()

    monkeypatch.setattr("src.cli.attest_cli.MlflowClient", Mock(return_value=client))
    monkeypatch.setattr(
        "src.cli.attest_cli.load_attestation_state",
        Mock(
            return_value=AttestationState(
                digest_hex="0x" + "aa" * 32,
                baseline_commitment="0x" + "22" * 32,
                built_at="2026-06-11T00:00:00+00:00",
                signatures=[],
            )
        ),
    )
    monkeypatch.setattr(
        "src.cli.attest_cli.build_typed_data_for_run",
        Mock(return_value=_build_result()),
    )

    result = runner.invoke(attest, ["attach", "run-123", "0x" + "11" * 65])

    assert result.exit_code != 0
    assert "event=attest_attach_baseline_stale" in result.output


def test_attest_attach_records_sorted_signatures(monkeypatch) -> None:
    client = _FakeClient(tags={})
    runner = CliRunner()
    recorder = Mock()

    monkeypatch.setattr("src.cli.attest_cli.MlflowClient", Mock(return_value=client))
    monkeypatch.setattr(
        "src.cli.attest_cli.load_attestation_state",
        Mock(
            return_value=AttestationState(
                digest_hex="0x" + "aa" * 32,
                baseline_commitment="0x" + "11" * 32,
                built_at="2026-06-11T00:00:00+00:00",
                signatures=[],
            )
        ),
    )
    monkeypatch.setattr(
        "src.cli.attest_cli.build_typed_data_for_run",
        Mock(return_value=_build_result()),
    )
    monkeypatch.setattr(
        "src.cli.attest_cli.verify_signatures_for_attach",
        Mock(return_value=(["sig-a", "sig-b"], ["0x1", "0x2"], 2)),
    )
    monkeypatch.setattr("src.cli.attest_cli.record_attestation_signatures", recorder)

    result = runner.invoke(attest, ["attach", "run-123", "sig-b", "sig-a"])

    assert result.exit_code == 0
    recorder.assert_called_once_with(client, run_id="run-123", signatures=["sig-a", "sig-b"])
    assert "ready to publish: threshold=2 signers=0x1,0x2" in result.output
