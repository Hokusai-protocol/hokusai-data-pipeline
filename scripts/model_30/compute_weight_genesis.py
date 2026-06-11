"""Compute the initial on-chain weight genesis commitment for Model 30 artifacts.

MLflow authentication comes from the shared SDK environment, including
``MLFLOW_TRACKING_TOKEN`` when a remote registry requires bearer auth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import mlflow

from src.lineage.weight_commitment import compute_weight_commitment


def _is_mlflow_uri(value: str) -> bool:
    return value.startswith(("models:/", "runs:/", "mlflow-artifacts:/"))


def _resolve_artifact_dir(value: str) -> str:
    if _is_mlflow_uri(value):
        return mlflow.artifacts.download_artifacts(artifact_uri=value)
    artifact_dir = Path(value).expanduser().resolve()
    return str(artifact_dir)


def compute_genesis_payload(artifact: str, *, model_id_uint: int) -> dict[str, Any]:
    """Return a machine-readable genesis payload for a local directory or MLflow URI."""
    artifact_dir = _resolve_artifact_dir(artifact)
    commitment = compute_weight_commitment(artifact_dir)
    commitment_hex = f"0x{commitment.root}"
    return {
        "model_id_uint": model_id_uint,
        "artifact": artifact,
        "resolved_artifact_dir": artifact_dir,
        "algorithm": commitment.algorithm,
        "included_file_count": len(commitment.files),
        "excluded_file_count": len(commitment.excluded),
        "commitment": commitment_hex,
        "set_weight_genesis_call": (
            f"ModelRegistry.setWeightGenesis({model_id_uint}, {commitment_hex})"
        ),
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", help="Artifact directory path or MLflow model URI.")
    parser.add_argument(
        "--model-id-uint",
        type=int,
        default=30,
        help="uint256 model identifier used by ModelRegistry.",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable lines.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the genesis helper CLI."""
    args = parse_args()
    payload = compute_genesis_payload(args.artifact, model_id_uint=args.model_id_uint)
    if args.output_json:
        print(json.dumps(payload, indent=2, sort_keys=True))  # noqa: T201
        return

    for key in (
        "model_id_uint",
        "artifact",
        "resolved_artifact_dir",
        "algorithm",
        "included_file_count",
        "excluded_file_count",
        "commitment",
        "set_weight_genesis_call",
    ):
        print(f"{key}: {payload[key]}")  # noqa: T201


if __name__ == "__main__":
    main()
