"""CLI commands for per-publish MintRequest attester workflows."""

from __future__ import annotations

# Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled by the
# configured MLflow client environment; this CLI does not construct headers.
import os
from pathlib import Path

import click
from mlflow.tracking import MlflowClient

from src.cli.attestation import (
    build_typed_data_for_run,
    load_attestation_state,
    record_attestation_build,
    record_attestation_signatures,
    verify_signatures_for_attach,
)
from src.eip712 import render_for_human


@click.group()
def attest() -> None:
    """Build and attach MintRequest attester signatures."""


@attest.command("build")
@click.argument("run_id")
@click.option("--output", type=click.Path(path_type=Path), default=None)
def attest_build(run_id: str, output: Path | None) -> None:
    """Build and persist the canonical typed data for a run."""
    client = MlflowClient()
    build = build_typed_data_for_run(client, run_id)
    state = load_attestation_state(client, run_id)
    if state is not None:
        if state.digest_hex == build.digest_hex:
            click.echo(render_for_human(build.typed_data))
            return
        raise click.ClickException("inputs changed since previous build; refusing to overwrite")

    output_path = output or Path("attest") / f"{run_id}.typed-data.json"
    record_attestation_build(
        client,
        run_id=run_id,
        digest_hex=build.digest_hex,
        baseline_commitment=build.baseline_commitment,
        typed_data=build.typed_data,
        output_path=output_path,
    )
    click.echo(render_for_human(build.typed_data))


@attest.command("attach")
@click.argument("run_id")
@click.argument("signatures", nargs=-1)
def attest_attach(run_id: str, signatures: tuple[str, ...]) -> None:
    """Verify, sort, and attach attester signatures for a run."""
    if not signatures:
        raise click.ClickException("at least one signature is required")
    client = MlflowClient()
    state = load_attestation_state(client, run_id)
    if state is None:
        raise click.ClickException("attestation build state is missing; run `attest build` first")

    build = build_typed_data_for_run(client, run_id)
    if build.baseline_commitment != state.baseline_commitment:
        raise click.ClickException(
            "event=attest_attach_baseline_stale on-chain head moved since "
            "`attest build`; re-run `attest build` and re-sign"
        )
    if build.digest_hex != state.digest_hex:
        raise click.ClickException(
            "event=attest_attach_digest_mismatch run inputs (tags/metrics) "
            "changed since `attest build`; investigate run mutations before re-running"
        )

    fallback_addresses = []
    fallback = (os.getenv("MINT_ATTESTER_ADDRESS") or "").strip()
    if fallback:
        fallback_addresses.append(fallback)
    ordered, recovered, threshold = verify_signatures_for_attach(
        build.typed_data,
        list(signatures),
        rpc_url=(os.getenv("ETH_RPC_URL") or "").strip(),
        contract_address=(os.getenv("MINT_VERIFYING_CONTRACT") or "").strip(),
        dev_fallback_addresses=fallback_addresses,
    )
    record_attestation_signatures(client, run_id=run_id, signatures=ordered)
    click.echo(f"ready to publish: threshold={threshold} signers={','.join(recovered)}")
