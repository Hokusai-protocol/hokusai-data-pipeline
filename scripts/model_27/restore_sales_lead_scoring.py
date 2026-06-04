"""Restore the production alias for the Sales Lead Scoring MLflow model.

Authentication follows the normal MLflow SDK environment, including
`MLFLOW_TRACKING_TOKEN` when bearer auth is required.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import mlflow
import pandas as pd
from mlflow import MlflowClient

from src.utils.mlflow_config import configure_internal_mtls

_NUMERIC_NAME_DEFAULTS = {
    "discount": 0.1,
    "profit": 3200.0,
    "quantity": 25.0,
    "sales": 12500.0,
}
_STRING_NAME_DEFAULTS = {
    "id": "CG-12520",
    "industry": "Technology",
    "segment": "Enterprise",
    "subregion": "US East",
    "region": "North America",
    "country": "United States",
    "product": "Analytics Suite",
}


def restore_model(args: argparse.Namespace) -> dict[str, Any]:
    """Point an alias at a concrete model version and verify load + predict."""
    configure_internal_mtls()
    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    tracking_uri = args.tracking_uri or mlflow.get_tracking_uri()
    tracking_token = os.getenv("MLFLOW_TRACKING_TOKEN")
    if tracking_token:
        os.environ["MLFLOW_TRACKING_TOKEN"] = tracking_token

    client = MlflowClient(tracking_uri=tracking_uri)
    model_version = client.get_model_version(args.registered_name, args.version)
    previous_alias = _alias_target(client, args.registered_name, args.alias)
    if previous_alias and previous_alias.get("version") == str(args.version):
        verification = _verify_alias(args.registered_name, args.alias)
        return {
            "registered_model_name": args.registered_name,
            "version": str(args.version),
            "alias": args.alias,
            "updated": False,
            "previous_alias_target": previous_alias,
            "rollback_command": _rollback_command(args, previous_alias),
            "verification": verification,
            "source": getattr(model_version, "source", None),
            "run_id": getattr(model_version, "run_id", None),
        }

    client.set_registered_model_alias(args.registered_name, args.alias, str(args.version))
    verification = _verify_alias(args.registered_name, args.alias)
    return {
        "registered_model_name": args.registered_name,
        "version": str(args.version),
        "alias": args.alias,
        "updated": True,
        "previous_alias_target": previous_alias,
        "rollback_command": _rollback_command(args, previous_alias),
        "verification": verification,
        "source": getattr(model_version, "source", None),
        "run_id": getattr(model_version, "run_id", None),
    }


def _verify_alias(registered_name: str, alias: str) -> dict[str, Any]:
    model_uri = f"models:/{registered_name}@{alias}"
    loaded_model = mlflow.pyfunc.load_model(model_uri)
    sample = _sample_frame_from_signature(
        getattr(getattr(loaded_model, "metadata", None), "signature", None)
    )
    prediction = loaded_model.predict(sample)
    row_count = len(prediction.index) if hasattr(prediction, "index") else len(prediction)
    if row_count < 1:
        raise ValueError("Verification predict() returned no rows")
    return {
        "model_uri": model_uri,
        "sample_columns": list(sample.columns),
        "prediction_type": type(prediction).__name__,
        "row_count": row_count,
    }


def _sample_frame_from_signature(signature: Any) -> pd.DataFrame:
    if signature is None or getattr(signature, "inputs", None) is None:
        return pd.DataFrame(
            [
                {
                    "Customer ID": "CG-12520",
                    "first_industry": "Technology",
                    "first_segment": "Enterprise",
                    "first_region": "North America",
                    "first_subregion": "US East",
                    "first_country": "United States",
                    "first_product": "Analytics Suite",
                    "first_sales": 12500.0,
                    "first_quantity": 25.0,
                    "first_discount": 0.1,
                    "total_profit": 3200.0,
                }
            ]
        )

    row: dict[str, Any] = {}
    for column in signature.inputs:
        name = getattr(column, "name", None) or "feature"
        row[name] = _sample_value(name, str(getattr(column, "type", "")))
    return pd.DataFrame([row])


def _sample_value(name: str, type_name: str) -> Any:
    lowered_name = name.lower()
    lowered_type = type_name.lower()
    if "bool" in lowered_type:
        return False
    if "int" in lowered_type:
        return 1
    if "float" in lowered_type or "double" in lowered_type or "long" in lowered_type:
        for marker, value in _NUMERIC_NAME_DEFAULTS.items():
            if marker in lowered_name:
                return value
        return 1.0
    for marker, value in _STRING_NAME_DEFAULTS.items():
        if marker in lowered_name:
            return value
    return "sample"


def _alias_target(
    client: MlflowClient,
    registered_name: str,
    alias: str,
) -> dict[str, str] | None:
    registered_model = client.get_registered_model(registered_name)
    aliases = getattr(registered_model, "aliases", {}) or {}
    version = aliases.get(alias)
    if version is None:
        return None
    return {"alias": alias, "version": str(version)}


def _rollback_command(args: argparse.Namespace, previous_alias: dict[str, str] | None) -> str:
    base = (
        "python -m scripts.model_27.restore_sales_lead_scoring "
        f"--registered-name {json.dumps(args.registered_name)} "
    )
    if args.tracking_uri:
        base += f"--tracking-uri {json.dumps(args.tracking_uri)} "
    if previous_alias is None:
        return (
            "python - <<'PY'\n"
            "import mlflow\n"
            "from mlflow import MlflowClient\n"
            f"{f'mlflow.set_tracking_uri({args.tracking_uri!r})\\n' if args.tracking_uri else ''}"
            "client = MlflowClient()\n"
            f"client.delete_registered_model_alias({args.registered_name!r}, {args.alias!r})\n"
            "PY"
        )
    return f"{base}--version {previous_alias['version']} --alias {json.dumps(args.alias)}"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for alias restoration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registered-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--alias", default="production")
    parser.add_argument("--tracking-uri", default=None)
    return parser.parse_args()


def main() -> None:
    """Run the alias restoration and print the verification payload."""
    result = restore_model(parse_args())
    print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201


if __name__ == "__main__":
    main()
