"""Build guarded synthetic reward artifacts for Model 30 end-to-end testing.

This tool is intentionally test-only. It creates a schema-valid nonzero
attribution report and matching MintRequest from real training/evaluation
artifacts when the real candidate did not improve the baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.events.publishers.mint_request_publisher import MintRequestPublisher  # noqa: E402
from src.events.schemas import MintRequest  # noqa: E402

ALLOW_ENV = "ALLOW_SYNTHETIC_REWARD_E2E"
PRODUCTION_ENVIRONMENTS = {"prod", "production", "mainnet"}
SYNTHETIC_BASELINE_COMMITMENT = "0x" + ("11" * 32)
SYNTHETIC_CANDIDATE_COMMITMENT = "0x" + ("22" * 32)
DEFAULT_SYNTHETIC_DELTA = 0.001
_ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--comparison-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--source-attribution")
    parser.add_argument("--model-id", default="30")
    parser.add_argument("--model-id-uint", default="30")
    parser.add_argument("--baseline-run-id")
    parser.add_argument("--candidate-run-id")
    parser.add_argument("--eval-id")
    parser.add_argument("--benchmark-spec-id", default="technical_task_router_spec.v2")
    parser.add_argument("--metric-family", default="proportion")
    parser.add_argument("--synthetic-delta", type=float, default=DEFAULT_SYNTHETIC_DELTA)
    parser.add_argument("--wallet")
    parser.add_argument("--escrow-wallet", default=os.getenv("PENDING_CLAIMS_ESCROW_ADDRESS"))
    parser.add_argument(
        "--extra-test-wallet",
        action="append",
        default=[],
        metavar="WALLET:BPS",
        help=(
            "Reserve reward basis points for an extra synthetic test wallet. "
            "May be passed more than once. Example: --extra-test-wallet 0xabc...:100"
        ),
    )
    parser.add_argument("--baseline-commitment")
    parser.add_argument("--candidate-commitment")
    parser.add_argument("--allow-synthetic-commitments", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--schema",
        default=str(REPO_ROOT / "schema" / "attribution_report.v1.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Create synthetic artifacts and optionally publish the MintRequest."""
    args = parse_args(argv)
    _assert_synthetic_enabled(args.environment)

    manifest_path = Path(args.manifest).expanduser().resolve()
    comparison_path = Path(args.comparison_report).expanduser().resolve()
    source_attribution_path = (
        Path(args.source_attribution).expanduser().resolve() if args.source_attribution else None
    )
    output_dir = Path(args.output_dir).expanduser().resolve()

    manifest = _load_json(manifest_path)
    comparison_report = _load_json(comparison_path)
    source_attribution = _load_json(source_attribution_path) if source_attribution_path else {}
    extra_test_wallets = _parse_extra_test_wallets(args.extra_test_wallet)
    attribution_report = build_synthetic_attribution_report(
        manifest=manifest,
        comparison_report=comparison_report,
        source_attribution=source_attribution,
        model_id=args.model_id,
        baseline_run_id=args.baseline_run_id,
        candidate_run_id=args.candidate_run_id,
        synthetic_delta=args.synthetic_delta,
        created_at=_utc_now_iso(),
        source_paths={
            "manifest": str(manifest_path),
            "comparison_report": str(comparison_path),
            "source_attribution": str(source_attribution_path) if source_attribution_path else None,
        },
        extra_test_wallets=extra_test_wallets,
    )
    _validate_attribution_report(attribution_report, Path(args.schema).expanduser().resolve())

    baseline_commitment, candidate_commitment = _resolve_commitments(args)
    mint_request = build_synthetic_mint_request(
        attribution_report=attribution_report,
        comparison_report=comparison_report,
        manifest=manifest,
        model_id_uint=args.model_id_uint,
        eval_id=args.eval_id,
        benchmark_spec_id=args.benchmark_spec_id,
        metric_family=args.metric_family,
        wallet_override=args.wallet,
        escrow_wallet=args.escrow_wallet,
        extra_test_wallets=extra_test_wallets,
        baseline_commitment=baseline_commitment,
        candidate_commitment=candidate_commitment,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    attribution_path = output_dir / "synthetic_attribution_report.json"
    mint_request_path = output_dir / "synthetic_mint_request.json"
    attribution_path.write_text(
        json.dumps(attribution_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mint_request_path.write_text(
        mint_request.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.publish:
        _assert_publish_safe(args, baseline_commitment, candidate_commitment)
        if _auth_reward_recording_required():
            _assert_auth_recordable_contributors(mint_request)
        MintRequestPublisher().publish(mint_request)

    sys.stdout.write(f"wrote attribution_report={attribution_path}\n")
    sys.stdout.write(f"wrote mint_request={mint_request_path}\n")
    if args.publish:
        sys.stdout.write("published synthetic MintRequest to hokusai:mint_requests\n")
    return 0


def build_synthetic_attribution_report(
    *,
    manifest: dict[str, Any],
    comparison_report: dict[str, Any],
    source_attribution: dict[str, Any],
    model_id: str,
    baseline_run_id: str | None,
    candidate_run_id: str | None,
    synthetic_delta: float,
    created_at: str,
    source_paths: dict[str, str | None],
    extra_test_wallets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a nonzero synthetic attribution report from manifest contributor blocks."""
    contributors = _contributors_from_manifest(manifest)
    if not contributors:
        raise SystemExit("manifest has no attributable contributors with account_id or wallet")

    baseline_run = baseline_run_id or source_attribution.get("baseline_run_id")
    candidate_run = candidate_run_id or source_attribution.get("candidate_run_id")
    if not baseline_run or not candidate_run:
        raise SystemExit(
            "baseline/candidate run ids are required; pass --source-attribution or explicit ids"
        )

    rows_improved = sum(int(item["rows_credited"]) for item in contributors)
    comparison = _comparison_section(comparison_report)
    source_delta = float(comparison.get("primary_delta", 0.0) or 0.0)
    primary_metric = str(
        comparison.get("primary_metric")
        or source_attribution.get("method_details", {}).get("primary_metric")
        or "technical_task_router.benchmark_score_v2"
    )
    weight_bps = _largest_remainder_bps(
        {item["identity"]: float(item["rows_credited"]) for item in contributors}
    )

    report_contributors: list[dict[str, Any]] = []
    for contributor in contributors:
        item: dict[str, Any] = {
            "submission_ids": contributor["submission_ids"],
            "rows_credited": contributor["rows_credited"],
            "raw_score": float(contributor["rows_credited"]),
            "weight_bps": weight_bps[contributor["identity"]],
        }
        if contributor.get("wallet"):
            item["wallet"] = contributor["wallet"]
        if contributor.get("account_id"):
            item["account_id"] = contributor["account_id"]
        report_contributors.append(item)

    return {
        "schema_version": "attribution_report/v1",
        "model_id": model_id,
        "method": "loco_shapley",
        "baseline_run_id": str(baseline_run),
        "candidate_run_id": str(candidate_run),
        "created_at": created_at,
        "total_rows_evaluated": _total_rows_evaluated(comparison_report, source_attribution),
        "rows_improved": rows_improved,
        "contributors": sorted(
            report_contributors,
            key=lambda item: item.get("account_id") or item.get("wallet") or "",
        ),
        "weight_bps_total": sum(weight_bps.values()),
        "method_details": {
            "synthetic_e2e": True,
            "synthetic_delta": synthetic_delta,
            "source_primary_delta": source_delta,
            "source_primary_metric": primary_metric,
            "dataset_hash": manifest.get("dataset_hash"),
            "manifest_digest": manifest.get("manifest_digest"),
            "source_paths": source_paths,
            "extra_test_wallets": extra_test_wallets or [],
            "reason": "synthetic_reward_token_pipeline_test_only",
        },
    }


def build_synthetic_mint_request(
    *,
    attribution_report: dict[str, Any],
    comparison_report: dict[str, Any],
    manifest: dict[str, Any],
    model_id_uint: str,
    eval_id: str | None,
    benchmark_spec_id: str,
    metric_family: str,
    wallet_override: str | None,
    escrow_wallet: str | None,
    extra_test_wallets: list[dict[str, Any]],
    baseline_commitment: str,
    candidate_commitment: str,
) -> MintRequest:
    """Create a validated MintRequest from the synthetic attribution report."""
    primary_metric = str(attribution_report["method_details"]["source_primary_metric"])
    baseline_score = _metric_value(comparison_report, "baseline_metrics", primary_metric)
    candidate_score = max(
        baseline_score + float(attribution_report["method_details"]["synthetic_delta"]),
        _metric_value(comparison_report, "candidate_metrics", primary_metric),
    )
    baseline_bps, candidate_bps = _improving_bps_pair(baseline_score, candidate_score)
    contributors = _mint_contributors(
        attribution_report["contributors"],
        wallet_override=wallet_override,
        escrow_wallet=escrow_wallet,
        extra_test_wallets=extra_test_wallets,
    )
    timestamp = _utc_now_iso()
    attestation_hash = _sha256_hex(
        {
            "attribution_report": attribution_report,
            "baseline_score_bps": baseline_bps,
            "candidate_score_bps": candidate_bps,
            "synthetic_e2e": True,
        }
    )
    idempotency_key = _sha256_text(f"{model_id_uint}:{attestation_hash}")
    sample_size = max(1, int(attribution_report["total_rows_evaluated"]))

    return MintRequest(
        message_id=str(uuid.uuid4()),
        timestamp=timestamp,
        model_id=str(attribution_report["model_id"]),
        model_id_uint=str(model_id_uint),
        eval_id=eval_id or f"synthetic-e2e-{attribution_report['candidate_run_id']}",
        benchmark_spec_id=benchmark_spec_id,
        dataset_hash=_dataset_hash_for_mint(manifest),
        attestation_hash=attestation_hash,
        idempotency_key=idempotency_key,
        baseline_commitment=baseline_commitment,
        candidate_commitment=candidate_commitment,
        attester_signatures=[],
        totalSamples=sample_size,
        deadline=int((datetime.now(UTC) + timedelta(days=5)).timestamp()),
        evaluation={
            "metric_name": primary_metric,
            "metric_family": metric_family,
            "baseline_score_bps": baseline_bps,
            "new_score_bps": candidate_bps,
            "max_cost_usd_micro": 0,
            "actual_cost_usd_micro": 0,
            "sample_size_baseline": sample_size,
            "sample_size_candidate": sample_size,
            "ci_low_bps": 1,
            "ci_high_bps": max(1, candidate_bps - baseline_bps),
            "effect_size_bps": max(1, candidate_bps - baseline_bps),
            "statistical_method": "synthetic_e2e",
            "statistical_reason": "synthetic_reward_token_pipeline_test_only",
        },
        contributors=contributors,
    )


def _assert_synthetic_enabled(environment: str) -> None:
    normalized = environment.strip().lower()
    if normalized in PRODUCTION_ENVIRONMENTS:
        raise SystemExit("synthetic reward E2E tooling is forbidden in production/mainnet")
    if os.getenv(ALLOW_ENV, "").strip().lower() != "true":
        raise SystemExit(f"set {ALLOW_ENV}=true to build synthetic reward E2E artifacts")


def _assert_publish_safe(
    args: argparse.Namespace,
    baseline_commitment: str,
    candidate_commitment: str,
) -> None:
    if (
        baseline_commitment == SYNTHETIC_BASELINE_COMMITMENT
        and not args.allow_synthetic_commitments
    ):
        raise SystemExit(
            "publishing requires --baseline-commitment or --allow-synthetic-commitments"
        )
    if (
        candidate_commitment == SYNTHETIC_CANDIDATE_COMMITMENT
        and not args.allow_synthetic_commitments
    ):
        raise SystemExit(
            "publishing requires --candidate-commitment or --allow-synthetic-commitments"
        )


def _auth_reward_recording_required() -> bool:
    raw = os.getenv("MINT_REQUIRE_AUTH_REWARD_RECORDING")
    if raw is not None:
        return raw.strip().lower() == "true"
    return os.getenv("CONTRIBUTION_AUTH_CALLBACK_ENABLED", "false").strip().lower() == "true"


def _assert_auth_recordable_contributors(mint_request: MintRequest) -> None:
    invalid: list[dict[str, str | None]] = []
    for contributor in mint_request.contributors:
        if (
            not contributor.submission_id
            or not contributor.contributor_id
            or not _looks_like_account_id(contributor.contributor_id)
        ):
            invalid.append(
                {
                    "wallet_address": contributor.wallet_address,
                    "submission_id": contributor.submission_id,
                    "contributor_id": contributor.contributor_id,
                }
            )
    if invalid:
        raise SystemExit(
            "synthetic MintRequest contains contributors that cannot be recorded by "
            f"auth reward ingest: {invalid}"
        )


def _looks_like_account_id(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _resolve_commitments(args: argparse.Namespace) -> tuple[str, str]:
    baseline = (args.baseline_commitment or SYNTHETIC_BASELINE_COMMITMENT).lower()
    candidate = (args.candidate_commitment or SYNTHETIC_CANDIDATE_COMMITMENT).lower()
    return baseline, candidate


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise SystemExit(f"json file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"json parse error in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"expected object json in {path}")
    return payload


def _parse_extra_test_wallets(raw_values: list[str]) -> list[dict[str, Any]]:
    """Parse WALLET:BPS CLI values into deterministic test-recipient records."""
    parsed: list[dict[str, Any]] = []
    for index, raw_value in enumerate(raw_values, start=1):
        wallet, separator, bps_raw = raw_value.partition(":")
        if not separator:
            raise SystemExit(f"invalid --extra-test-wallet {raw_value!r}; expected WALLET:BPS")
        wallet = wallet.strip().lower()
        if not _ETH_ADDRESS_RE.match(wallet):
            raise SystemExit(f"invalid --extra-test-wallet address: {wallet!r}")
        try:
            weight_bps = int(bps_raw)
        except ValueError as exc:
            raise SystemExit(f"invalid --extra-test-wallet bps for {wallet}: {bps_raw!r}") from exc
        if weight_bps <= 0:
            raise SystemExit("--extra-test-wallet bps must be positive")
        parsed.append(
            {
                "wallet_address": wallet,
                "weight_bps": weight_bps,
                "contributor_id": f"synthetic-test-wallet-{index}",
            }
        )
    total = sum(item["weight_bps"] for item in parsed)
    if total >= 10000:
        raise SystemExit("extra test wallets must reserve less than 10000 bps")
    return parsed


def _validate_attribution_report(report: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=report, schema=schema)


def _contributors_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for block in manifest.get("blocks", []):
        account_id = block.get("account_id")
        wallet = block.get("wallet")
        wallet = str(wallet).lower() if wallet else None
        account_id = str(account_id) if account_id else None
        identity = account_id or wallet
        if identity is None:
            continue
        bucket = grouped.setdefault(
            identity,
            {
                "identity": identity,
                "account_id": account_id,
                "wallet": wallet,
                "submission_ids": set(),
                "rows_credited": 0,
            },
        )
        if bucket["account_id"] is None and account_id is not None:
            bucket["account_id"] = account_id
        if bucket["wallet"] is None and wallet is not None:
            bucket["wallet"] = wallet
        bucket["submission_ids"].add(str(block["submission_id"]))
        bucket["rows_credited"] += int(block.get("row_count", 0) or 0)

    contributors: list[dict[str, Any]] = []
    for identity, bucket in sorted(grouped.items()):
        if int(bucket["rows_credited"]) <= 0:
            continue
        contributors.append(
            {
                "identity": identity,
                "account_id": bucket["account_id"],
                "wallet": bucket["wallet"],
                "submission_ids": sorted(bucket["submission_ids"]),
                "rows_credited": int(bucket["rows_credited"]),
            }
        )
    return contributors


def _largest_remainder_bps(raw_scores: dict[str, float]) -> dict[str, int]:
    total = sum(raw_scores.values())
    if total <= 0:
        raise SystemExit("cannot allocate synthetic rewards with zero contributed rows")
    exact = {key: raw_scores[key] * 10000.0 / total for key in sorted(raw_scores)}
    floors = {key: int(value) for key, value in exact.items()}
    remaining = 10000 - sum(floors.values())
    remainders = sorted(exact, key=lambda key: (-(exact[key] - floors[key]), key))
    for key in remainders[:remaining]:
        floors[key] += 1
    return floors


def _total_rows_evaluated(
    comparison_report: dict[str, Any],
    source_attribution: dict[str, Any],
) -> int:
    if source_attribution.get("total_rows_evaluated") is not None:
        return int(source_attribution["total_rows_evaluated"])
    candidate = comparison_report.get("candidate")
    if isinstance(candidate, dict):
        row_counts = candidate.get("row_counts")
        if isinstance(row_counts, dict) and row_counts.get("evaluated_rows") is not None:
            return max(1, int(row_counts["evaluated_rows"]))
    if comparison_report.get("benchmark_rows") is not None:
        return max(1, int(comparison_report["benchmark_rows"]))
    return 1


def _metric_value(report: dict[str, Any], key: str, metric: str) -> float:
    metrics = _comparison_section(report).get(key)
    if not isinstance(metrics, dict):
        return 0.0
    value = metrics.get(metric)
    return float(value) if value is not None else 0.0


def _comparison_section(report: dict[str, Any]) -> dict[str, Any]:
    comparison = report.get("comparison")
    return comparison if isinstance(comparison, dict) else report


def _improving_bps_pair(baseline_score: float, candidate_score: float) -> tuple[int, int]:
    baseline_bps = _to_bps(baseline_score)
    candidate_bps = _to_bps(candidate_score)
    if candidate_bps <= baseline_bps:
        if baseline_bps >= 10000:
            baseline_bps = 9999
        candidate_bps = baseline_bps + 1
    return baseline_bps, min(candidate_bps, 10000)


def _to_bps(value: float) -> int:
    return min(max(int(round(value * 10000)), 0), 10000)


def _mint_contributors(
    attribution_contributors: list[dict[str, Any]],
    *,
    wallet_override: str | None,
    escrow_wallet: str | None,
    extra_test_wallets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contributors: list[dict[str, Any]] = []
    extra_weight_bps = sum(int(item["weight_bps"]) for item in extra_test_wallets)
    remaining_weight_bps = 10000 - extra_weight_bps
    if remaining_weight_bps <= 0:
        raise SystemExit("extra test wallets leave no reward allocation for contributors")
    base_weights = _scale_base_contributor_weights(
        attribution_contributors,
        total_bps=remaining_weight_bps,
    )
    for item in attribution_contributors:
        account_id = item.get("account_id")
        wallet = (wallet_override or item.get("wallet") or escrow_wallet or "").lower()
        if not wallet:
            raise SystemExit(
                "attribution contributor has no wallet; pass --escrow-wallet or "
                "set PENDING_CLAIMS_ESCROW_ADDRESS"
            )
        contributor: dict[str, Any] = {
            "wallet_address": wallet,
            "weight_bps": base_weights[_contributor_key(item)],
        }
        submission_ids = item.get("submission_ids") or []
        if submission_ids:
            contributor["submissionId"] = str(submission_ids[0])
        if account_id:
            contributor["contributorId"] = str(account_id)
        contributors.append(contributor)
    for item in extra_test_wallets:
        contributors.append(
            {
                "wallet_address": item["wallet_address"],
                "weight_bps": int(item["weight_bps"]),
                "contributorId": item["contributor_id"],
            }
        )
    return contributors


def _scale_base_contributor_weights(
    contributors: list[dict[str, Any]],
    *,
    total_bps: int,
) -> dict[str, int]:
    raw_weights = {_contributor_key(item): float(item["weight_bps"]) for item in contributors}
    scaled = _largest_remainder_bps(raw_weights)
    if total_bps == 10000:
        return scaled
    exact = {key: scaled[key] * total_bps / 10000.0 for key in sorted(scaled)}
    floors = {key: int(value) for key, value in exact.items()}
    remaining = total_bps - sum(floors.values())
    remainders = sorted(exact, key=lambda key: (-(exact[key] - floors[key]), key))
    for key in remainders[:remaining]:
        floors[key] += 1
    return floors


def _contributor_key(item: dict[str, Any]) -> str:
    return str(item.get("account_id") or item.get("wallet") or item.get("submission_ids"))


def _dataset_hash_for_mint(manifest: dict[str, Any]) -> str:
    value = str(manifest.get("dataset_hash") or "")
    if value.startswith("sha256:"):
        return "0x" + value.removeprefix("sha256:")
    if value.startswith("0x"):
        return value.lower()
    raise SystemExit("manifest dataset_hash must be sha256:<64 hex> or 0x<64 hex>")


def _sha256_hex(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256_text(canonical)


def _sha256_text(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
