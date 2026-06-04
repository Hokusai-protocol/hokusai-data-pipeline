"""Inspect MLflow registry state for the Sales Lead Scoring model.

Authentication follows the normal MLflow SDK environment, including
`MLFLOW_TRACKING_TOKEN` when bearer auth is required.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import mlflow
from mlflow import MlflowClient

from src.utils.mlflow_config import configure_internal_mtls

DEFAULT_REPORT_PATH = Path(__file__).with_name("inspect_report.json")


def inspect_registry(args: argparse.Namespace) -> dict[str, Any]:
    """Inspect candidate registered models and emit a JSON report."""
    configure_internal_mtls()
    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    tracking_uri = args.tracking_uri or mlflow.get_tracking_uri()
    tracking_token = os.getenv("MLFLOW_TRACKING_TOKEN")
    if tracking_token:
        os.environ["MLFLOW_TRACKING_TOKEN"] = tracking_token

    client = MlflowClient(tracking_uri=tracking_uri)
    candidates = _candidate_models(client, query=args.query)
    report = {
        "tracking_uri": tracking_uri,
        "query": args.query,
        "candidates": [_serialize_registered_model(client, candidate) for candidate in candidates],
    }
    for candidate in report["candidates"]:
        candidate["recommended_version"] = _recommend_version(candidate["versions"])
    return report


def _candidate_models(client: MlflowClient, *, query: str) -> list[Any]:
    models = list(client.search_registered_models())
    lowered_query = query.lower()
    matches = [model for model in models if lowered_query in str(model.name).lower()]
    if matches:
        return matches

    fallback_terms = ("sales", "lead", "scoring")
    return [
        model for model in models if any(term in str(model.name).lower() for term in fallback_terms)
    ]


def _serialize_registered_model(client: MlflowClient, registered_model: Any) -> dict[str, Any]:
    alias_map = getattr(registered_model, "aliases", {}) or {}
    versions = []
    for version in getattr(registered_model, "latest_versions", []) or []:
        versions.append(_serialize_model_version(client, registered_model.name, version, alias_map))
    if not versions:
        for version in client.search_model_versions(f"name = '{registered_model.name}'"):
            versions.append(
                _serialize_model_version(client, registered_model.name, version, alias_map)
            )
    versions.sort(key=lambda item: int(item["version"]))
    return {
        "registered_model_name": registered_model.name,
        "aliases": alias_map,
        "versions": versions,
    }


def _serialize_model_version(
    client: MlflowClient,
    registered_model_name: str,
    version: Any,
    alias_map: dict[str, str],
) -> dict[str, Any]:
    version_number = str(version.version)
    aliases = sorted(alias for alias, target in alias_map.items() if str(target) == version_number)
    model_uri = f"models:/{registered_model_name}/{version_number}"
    signature_inputs = None
    signature_outputs = None
    load_error = None
    try:
        loaded_model = mlflow.pyfunc.load_model(model_uri)
        signature = getattr(getattr(loaded_model, "metadata", None), "signature", None)
        signature_inputs = _signature_columns(getattr(signature, "inputs", None))
        signature_outputs = _signature_columns(getattr(signature, "outputs", None))
    except Exception as exc:  # noqa: BLE001 - inspection should capture errors in report
        load_error = str(exc)

    return {
        "version": version_number,
        "status": getattr(version, "status", None),
        "current_stage": getattr(version, "current_stage", None),
        "aliases": aliases,
        "source": getattr(version, "source", None),
        "run_id": getattr(version, "run_id", None),
        "signature_inputs": signature_inputs,
        "signature_outputs": signature_outputs,
        "load_error": load_error,
    }


def _signature_columns(signature: Any) -> list[dict[str, Any]] | None:
    if signature is None:
        return None
    if hasattr(signature, "inputs"):
        signature = signature.inputs
    fields = []
    for item in signature or []:
        fields.append(
            {
                "name": getattr(item, "name", None),
                "type": str(getattr(item, "type", None)),
                "required": getattr(item, "required", None),
            }
        )
    return fields or None


def _recommend_version(versions: list[dict[str, Any]]) -> str | None:
    viable_versions = [
        version
        for version in versions
        if version.get("signature_inputs") and version.get("status") != "FAILED_REGISTRATION"
    ]
    if not viable_versions:
        return None
    viable_versions.sort(key=lambda item: int(item["version"]))
    return viable_versions[-1]["version"]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for registry inspection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--query", default="sales lead")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def main() -> None:
    """Run the inspection and write the JSON report."""
    args = parse_args()
    report = inspect_registry(args)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
