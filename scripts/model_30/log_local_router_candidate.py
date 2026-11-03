"""Log a Model 30 candidate to a local MLflow store without the on-chain step.

``register_technical_task_router.py`` always resolves ``ETH_RPC_URL`` and the
contract addresses, and registers to the shared registry. Experiments only need
a loadable pyfunc. This tool runs the same dataset validation and coverage gates
(warn mode), then calls the same ``mlflow.pyfunc.log_model`` without
``registered_model_name`` and without the weight-commitment read.

Interim tool until HOK-3392 adds ``--skip-onchain`` to the register script.

Auth: only local ``file://`` tracking URIs are accepted, so no
``MLFLOW_TRACKING_TOKEN`` is needed. Remote (http/https) URIs are rejected.

Example::

    python scripts/model_30/log_local_router_candidate.py \
      --tracking-uri file://$PWD/data/model_30/retrain-2026-11/mlruns \
      --run-name B --router-dataset data/model_30/retrain-2026-11/train.csv

Prints one JSON line with ``run_id`` and ``model_uri`` (``runs:/<id>/model``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mlflow  # noqa: E402

from scripts.model_30 import register_technical_task_router as reg  # noqa: E402
from src.models.technical_task_router import TechnicalTaskRouterModel  # noqa: E402


def log_local_candidate(
    *,
    tracking_uri: str,
    run_name: str,
    dataset_path: Path,
    k_neighbors: int = 40,
    experiment_name: str = "model30-local-candidates",
    prices_path: Path | None = None,
) -> dict[str, Any]:
    """Validate a router dataset and log it as a local, unregistered pyfunc."""
    if tracking_uri.startswith(("http://", "https://")):
        raise ValueError(
            "log_local_router_candidate.py is for local stores only; "
            "use register_technical_task_router.py for the shared registry"
        )
    dataset_path = dataset_path.resolve()
    summary = reg.validate_router_dataset_model_ids(
        dataset_path,
        launch_priority_models=reg._load_launch_priority_models(
            reg.DEFAULT_LAUNCH_PRIORITY_MODELS_PATH
        ),
    )
    in_pool = reg._enforce_in_pool_evidence_gate(
        summary,
        mode="warn",
        min_role_coverage=reg.DEFAULT_MIN_IN_POOL_EVIDENCE_COVERAGE,
        min_group_coverage=reg.DEFAULT_MIN_GROUP_IN_POOL_EVIDENCE_COVERAGE,
    )
    launch = reg._enforce_launch_priority_gate(summary, mode="warn")

    artifacts = {reg.ROUTER_DATASET_ARTIFACT: str(dataset_path)}
    if prices_path is not None:
        artifacts[reg.ROUTER_PRICES_ARTIFACT] = str(Path(prices_path).resolve())
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(
            {
                "k_neighbors": k_neighbors,
                "router_dataset": dataset_path.name,
                "router_dataset_rows": summary.row_count,
                "router_dataset_sha256": f"sha256:{summary.sha256}",
            }
        )
        mlflow.set_tag("hokusai.registration_mode", "local")
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=TechnicalTaskRouterModel(k_neighbors=k_neighbors),
            artifacts=artifacts,
        )
    return {
        "name": run_name,
        "run_id": run.info.run_id,
        "model_uri": f"runs:/{run.info.run_id}/model",
        "rows": summary.row_count,
        "dataset_sha256": f"sha256:{summary.sha256}",
        "in_pool_gate_violations": len(in_pool or []),
        "launch_priority_violations": len(launch or []),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tracking-uri", required=True, help="Local store, e.g. file://...")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--router-dataset", required=True)
    parser.add_argument("--k-neighbors", type=int, default=40)
    parser.add_argument("--router-prices", help="Optional *.model-prices.json artifact.")
    parser.add_argument("--experiment-name", default="model30-local-candidates")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    result = log_local_candidate(
        tracking_uri=args.tracking_uri,
        run_name=args.run_name,
        dataset_path=Path(args.router_dataset),
        k_neighbors=args.k_neighbors,
        experiment_name=args.experiment_name,
        prices_path=Path(args.router_prices) if args.router_prices else None,
    )
    print(json.dumps(result, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
