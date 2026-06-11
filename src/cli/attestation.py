"""Attestation helpers for reproducible evaluation runs."""

from __future__ import annotations

# Auth-hook note: MLflow authentication is provided by the caller's configured
# tracking client/session; this module does not add custom headers directly.
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.eip712 import (
    MintRequestSigningConfig,
    build_typed_data,
    compute_digest,
    read_attester_threshold,
    read_is_attester,
    recover_signer,
    validate_signatures_against_registry,
)

ATTESTATION_ARTIFACT_PATH = "attestation/attestation.json"
ATTEST_BUILD_TAG = "hokusai.mint.attest.build_v1"
ATTEST_SIGNATURES_TAG = "hokusai.mint.attest.signatures_v1"
ATTEST_ARTIFACT_DIR = "attest"
_TAG_VALUE_LIMIT = 4500


@dataclass(frozen=True)
class AttestationState:
    """Persisted build/signature state stored on an MLflow run."""

    digest_hex: str
    baseline_commitment: str
    built_at: str
    signatures: list[str]


@dataclass(frozen=True)
class AttestationBuildResult:
    """Canonical typed-data build result for a run."""

    mint_request: Any
    typed_data: dict[str, Any]
    digest_hex: str
    baseline_commitment: str


def _attester_signature_required() -> bool:
    return (os.getenv("MINT_REQUIRE_ATTESTER_SIGNATURE") or "").strip().lower() != "false"


def load_attestation_state(client: Any, run_id: str) -> AttestationState | None:
    """Load persisted build/signature state from MLflow tags."""
    run = client.get_run(run_id)
    tags = (getattr(getattr(run, "data", None), "tags", None) or {}) if run else {}
    build_raw = tags.get(ATTEST_BUILD_TAG)
    if not build_raw:
        return None
    build_payload = json.loads(build_raw)
    signatures_raw = tags.get(ATTEST_SIGNATURES_TAG) or "[]"
    signatures = json.loads(signatures_raw)
    return AttestationState(
        digest_hex=str(build_payload["digest"]),
        baseline_commitment=str(build_payload["baseline_commitment"]),
        built_at=str(build_payload["built_at"]),
        signatures=[str(signature) for signature in signatures],
    )


def record_attestation_build(
    client: Any,
    *,
    run_id: str,
    digest_hex: str,
    baseline_commitment: str,
    typed_data: dict[str, Any],
    output_path: str | Path,
) -> None:
    """Persist a build witness tag plus the exact typed-data payload."""
    built_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "digest": digest_hex,
        "baseline_commitment": baseline_commitment,
        "built_at": built_at,
    }
    client.set_tag(
        run_id,
        ATTEST_BUILD_TAG,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )
    _write_typed_data_output(typed_data, output_path)
    _log_typed_data_artifact(run_id=run_id, digest_hex=digest_hex, typed_data=typed_data)


def record_attestation_signatures(client: Any, *, run_id: str, signatures: list[str]) -> None:
    """Persist the verified signature set on the run."""
    serialized = json.dumps(signatures, separators=(",", ":"))
    if len(serialized) > _TAG_VALUE_LIMIT:
        raise ValueError("serialized attester signatures exceed MLflow tag size guard")
    client.set_tag(run_id, ATTEST_SIGNATURES_TAG, serialized)


def build_typed_data_for_run(client: Any, run_id: str) -> AttestationBuildResult:
    """Rebuild the canonical MintRequest typed data for a previously accepted run."""
    from src.evaluation.deltaone_mint_orchestrator import build_mint_request_for_run

    mint_request, baseline_commitment = build_mint_request_for_run(client, run_id)
    typed_data = build_typed_data(mint_request, _load_signing_config())
    digest_hex = f"0x{compute_digest(typed_data).hex()}"
    return AttestationBuildResult(
        mint_request=mint_request,
        typed_data=typed_data,
        digest_hex=digest_hex,
        baseline_commitment=baseline_commitment,
    )


def verify_signatures_for_attach(
    typed_data: dict[str, Any],
    signatures: list[str],
    *,
    rpc_url: str,
    contract_address: str,
    dev_fallback_addresses: list[str] | None = None,
) -> tuple[list[str], list[str], int]:
    """Verify attach-time signatures against the on-chain registry and threshold."""
    if dev_fallback_addresses is None:
        dev_fallback_addresses = []

    def _registry_check(address: str) -> bool:
        try:
            return read_is_attester(
                rpc_url,
                contract_address=contract_address,
                address=address,
            )
        except Exception:
            if _attester_signature_required() or not dev_fallback_addresses:
                raise
            return address.lower() in {candidate.lower() for candidate in dev_fallback_addresses}

    try:
        threshold = read_attester_threshold(rpc_url, contract_address=contract_address)
    except Exception:
        if _attester_signature_required() or not dev_fallback_addresses:
            raise
        threshold = 1

    ordered = validate_signatures_against_registry(
        typed_data,
        signatures,
        registry_check=_registry_check,
        threshold=threshold,
    )
    recovered = [recover_signer(typed_data, signature).lower() for signature in ordered]
    return ordered, recovered, threshold


def build_attestation_payload(
    *,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    results: dict[str, Any],
    attestation_nonce: str | None = None,
    benchmark_spec_id: str | None = None,
    dataset_hash: str | None = None,
    attribution_report_hash: str | None = None,
) -> dict[str, Any]:
    """Build canonical attestation payload from run inputs and outputs."""
    payload = {
        "model_id": model_id,
        "eval_spec": eval_spec,
        "provider": provider,
        "seed": seed,
        "temperature": temperature,
        "results": results,
        "attestation_nonce": attestation_nonce or str(uuid4()),
    }
    if benchmark_spec_id:
        payload["benchmark_spec_id"] = benchmark_spec_id
    if dataset_hash:
        payload["dataset_hash"] = dataset_hash
    if attribution_report_hash:
        payload["attribution_report_hash"] = attribution_report_hash
    return payload


def compute_attestation_hash(payload: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash for attestation payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def create_attestation(
    *,
    model_id: str,
    eval_spec: str,
    provider: str | None,
    seed: int | None,
    temperature: float | None,
    results: dict[str, Any],
    attestation_nonce: str | None = None,
    benchmark_spec_id: str | None = None,
    dataset_hash: str | None = None,
    attribution_report_hash: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create attestation hash and payload."""
    payload = build_attestation_payload(
        model_id=model_id,
        eval_spec=eval_spec,
        provider=provider,
        seed=seed,
        temperature=temperature,
        results=results,
        attestation_nonce=attestation_nonce,
        benchmark_spec_id=benchmark_spec_id,
        dataset_hash=dataset_hash,
        attribution_report_hash=attribution_report_hash,
    )
    return compute_attestation_hash(payload), payload


def log_attestation(
    *,
    mlflow_module: Any,
    run_id: str,
    attestation_hash: str,
    payload: dict[str, Any],
) -> None:
    """Log attestation hash and payload to MLflow."""
    with mlflow_module.start_run(run_id=run_id):
        mlflow_module.set_tag("hokusai_eval.attestation_hash", attestation_hash)
        mlflow_module.log_dict(
            {
                "attestation_hash": attestation_hash,
                "payload": payload,
            },
            ATTESTATION_ARTIFACT_PATH,
        )


def _log_typed_data_artifact(*, run_id: str, digest_hex: str, typed_data: dict[str, Any]) -> None:
    import mlflow

    artifact_path = f"{ATTEST_ARTIFACT_DIR}/{digest_hex}.typed-data.json"
    with mlflow.start_run(run_id=run_id):
        mlflow.log_dict(typed_data, artifact_path)


def _write_typed_data_output(typed_data: dict[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(typed_data, indent=2) + "\n", encoding="utf-8")


def _load_signing_config() -> MintRequestSigningConfig:
    return MintRequestSigningConfig.from_env()
