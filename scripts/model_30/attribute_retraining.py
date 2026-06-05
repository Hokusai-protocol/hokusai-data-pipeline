"""Attribute Model 30 benchmark lift via deterministic retraining marginals."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.model_30.assemble_training_set import (  # noqa: E402
    build_validator,
    compute_dataset_hash,
)
from src.evaluation.attribution.retraining_attributor import (  # noqa: E402
    Cohort,
    RetrainingConfig,
    attribute,
)

PRIMARY_METRIC = "technical_task_router.benchmark_score_v1"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for retraining-based attribution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--model-id", default="30")
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--created-at")
    parser.add_argument("--tau", type=float, default=0.10)
    parser.add_argument("--budget", type=int, default=64)
    parser.add_argument("--max-groups", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-seeds", default="0,1,2")
    parser.add_argument("--min-examples", type=int, default=0)
    parser.add_argument("--enable-add-one-in", action="store_true")
    parser.add_argument("--k-neighbors", type=int, default=40)
    parser.add_argument(
        "--schema",
        default=str(REPO_ROOT / "schema" / "attribution_report.v1.json"),
    )
    parser.add_argument(
        "--real-training",
        action="store_true",
        help="Train/evaluate real filtered Model 30 subsets instead of raising a gate error.",
    )
    return parser.parse_args()


def main() -> None:
    """Run retraining attribution and write a validated JSON report."""
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    dataset_path = Path(args.dataset).expanduser().resolve()
    holdout_path = Path(args.holdout).expanduser().resolve()

    manifest = _load_manifest(manifest_path)
    cohorts = _build_cohorts(manifest)
    if not cohorts:
        raise SystemExit("no cohorts in manifest")

    dataset_rows, dataset_hash = _load_dataset_rows(dataset_path)
    manifest_hash = str(manifest["manifest_digest"])
    config = RetrainingConfig(
        tau=args.tau,
        budget=args.budget,
        max_groups=args.max_groups,
        rng_seed=args.seed,
        eval_seeds=_parse_eval_seeds(args.eval_seeds),
        enable_add_one_in=args.enable_add_one_in,
        min_examples=args.min_examples,
    )
    created_at = args.created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )

    with _Model30SubsetTrainer(
        dataset_rows=dataset_rows,
        blocks=list(manifest["blocks"]),
        holdout_path=holdout_path,
        model_id=args.model_id,
        k_neighbors=args.k_neighbors,
        real_training=args.real_training,
    ) as trainer:
        try:
            report = attribute(
                cohorts=cohorts,
                train_fn=trainer.train,
                eval_fn=trainer.evaluate,
                model_id=args.model_id,
                baseline_run_id=args.baseline_run_id,
                candidate_run_id=args.candidate_run_id,
                created_at=created_at,
                dataset_hash=dataset_hash,
                manifest_hash=manifest_hash,
                total_rows_evaluated=trainer.total_rows_evaluated,
                config=config,
            )
        except ValueError as exc:
            if str(exc) == "retrain budget too small for LOCO":
                raise SystemExit("retrain budget too small for LOCO") from exc
            raise

    schema = json.loads(Path(args.schema).expanduser().resolve().read_text(encoding="utf-8"))
    jsonschema.validate(instance=report, schema=schema)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"manifest parse error: {exc}") from exc

    validator = build_validator(REPO_ROOT / "schema" / "model_30_training_manifest.v1.json")
    errors = sorted(validator.iter_errors(manifest), key=lambda err: list(err.absolute_path))
    if errors:
        path_parts = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        raise SystemExit(f"manifest parse error: {path_parts}: {errors[0].message}")
    return dict(manifest)


def _build_cohorts(manifest: dict[str, Any]) -> list[Cohort]:
    grouped: dict[str, dict[str, Any]] = {}
    for block in manifest.get("blocks", []):
        wallet = block.get("wallet")
        if wallet is None:
            continue
        bucket = grouped.setdefault(
            str(wallet),
            {
                "submission_ids": set(),
                "row_count": 0,
            },
        )
        bucket["submission_ids"].add(str(block["submission_id"]))
        bucket["row_count"] += int(block["row_count"])

    return [
        Cohort(
            cohort_id=wallet,
            wallet=wallet,
            submission_ids=tuple(sorted(bucket["submission_ids"])),
            row_count=int(bucket["row_count"]),
        )
        for wallet, bucket in sorted(grouped.items())
    ]


def _load_dataset_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        raise SystemExit(f"dataset not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"dataset parse error on line {line_number}: {exc}") from exc
            rows.append(dict(row))
    dataset_hash, _ = compute_dataset_hash(rows)
    return rows, dataset_hash


def _parse_eval_seeds(raw_value: str) -> tuple[int, ...]:
    values = [item.strip() for item in raw_value.split(",") if item.strip()]
    return tuple(int(value) for value in values) or (0,)


class _Model30SubsetTrainer:
    """Filter the assembled training set into temporary Model 30 artifacts."""

    def __init__(
        self: _Model30SubsetTrainer,
        *,
        dataset_rows: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
        holdout_path: Path,
        model_id: str,
        k_neighbors: int,
        real_training: bool,
    ) -> None:
        self._dataset_rows = dataset_rows
        self._holdout_path = holdout_path
        self._model_id = model_id
        self._k_neighbors = k_neighbors
        self._real_training = real_training
        self._tempdirs: list[tempfile.TemporaryDirectory[str]] = []
        self._wallet_by_row = _wallet_by_row_index(blocks=blocks, row_count=len(dataset_rows))
        self.total_rows_evaluated = int(pd.read_csv(holdout_path).shape[0])

    def __enter__(self: _Model30SubsetTrainer) -> _Model30SubsetTrainer:
        return self

    def __exit__(
        self: _Model30SubsetTrainer,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        del exc_type, exc, traceback
        for tempdir in reversed(self._tempdirs):
            tempdir.cleanup()

    def train(self: _Model30SubsetTrainer, included_ids: frozenset[str], seed: int) -> Any:
        del seed
        if not self._real_training:
            raise NotImplementedError("real training is gated; use a stub or --real-training")

        from src.models.technical_task_router import (  # noqa: PLC0415
            ROUTER_DATASET_ARTIFACT,
            TechnicalTaskRouterModel,
        )

        filtered_rows = [
            row
            for index, row in enumerate(self._dataset_rows)
            if self._wallet_by_row[index] is None or self._wallet_by_row[index] in included_ids
        ]
        tempdir = tempfile.TemporaryDirectory(prefix="attribute-retraining-")
        self._tempdirs.append(tempdir)
        dataset_path = Path(tempdir.name) / "router_dataset.csv"
        pd.DataFrame(filtered_rows).to_csv(dataset_path, index=False)

        model = TechnicalTaskRouterModel(k_neighbors=self._k_neighbors)
        model.load_context(
            type(
                "Context",
                (),
                {"artifacts": {ROUTER_DATASET_ARTIFACT: str(dataset_path)}},
            )()
        )
        return model

    def evaluate(self: _Model30SubsetTrainer, handle: Any, eval_seed: int) -> float:
        del eval_seed
        from scripts.model_30.evaluate_technical_task_router import (  # noqa: PLC0415
            evaluate_model,
            parse_objectives,
        )

        report = evaluate_model(
            handle,
            model_id=self._model_id,
            holdout_path=self._holdout_path,
            objectives=parse_objectives("all"),
            eval_id=f"attribute-retraining-{self._model_id}",
        )
        return float(report["metrics"][PRIMARY_METRIC])


def _wallet_by_row_index(*, blocks: list[dict[str, Any]], row_count: int) -> list[str | None]:
    wallets: list[str | None] = [None] * row_count
    for block in blocks:
        start = int(block["row_start"])
        end = int(block["row_end"])
        if start < 0 or end >= row_count or start > end:
            raise SystemExit(
                f"manifest block row range [{start}, {end}] is outside dataset (rows={row_count})",
            )
        wallet = block.get("wallet")
        for index in range(start, end + 1):
            wallets[index] = None if wallet is None else str(wallet)
    return wallets


if __name__ == "__main__":
    main()
