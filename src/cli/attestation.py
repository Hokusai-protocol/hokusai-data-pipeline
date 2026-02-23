"""Attestation helpers for reproducible evaluation runs."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import uuid4

ATTESTATION_ARTIFACT_PATH = "attestation/attestation.json"


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
