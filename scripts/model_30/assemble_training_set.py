# ruff: noqa: D101, D103
"""Assemble a deterministic Model 30 training set from accepted contributions.

MLflow auth is inherited from the runtime environment, typically via
``MLFLOW_TRACKING_TOKEN`` when the tracking server requires bearer auth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import jsonschema
import mlflow
from botocore.exceptions import BotoCoreError, ClientError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.services.auth_service_notifier import (  # noqa: E402
    AuthServiceNotifier,
    WalletResolution,
)
from src.api.services.contribution_service import (  # noqa: E402
    S3ContributionStore,
    StoredContributionRecord,
)

LOGGER = logging.getLogger(__name__)
WALLET_POLICIES = ("quarantine", "exclude", "hold")


@dataclass(frozen=True)
class ProcessedSubmission:
    submission_id: str
    s3_key: str
    rows: list[dict[str, Any]]
    wallet: str | None
    account_id: str | None
    reward_hold: bool


def canonical_row_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_dataset_hash(rows: Iterable[dict[str, Any]]) -> tuple[str, int]:
    digest = hashlib.sha256()
    row_count = 0
    for row in rows:
        digest.update(canonical_row_bytes(row))
        digest.update(b"\n")
        row_count += 1
    return f"sha256:{digest.hexdigest()}", row_count


def validate_row(row: dict[str, Any], validator: jsonschema.protocols.Validator) -> str | None:
    errors = sorted(validator.iter_errors(row), key=lambda err: list(err.absolute_path))
    if not errors:
        return None
    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{path}: {error.message}"


def is_valid_wallet(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith("0x") or len(value) != 42:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value[2:])


def quarantine_record(
    submission_id: str,
    s3_key: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "submission_id": submission_id,
        "s3_key": s3_key,
        "reason": reason,
    }
    if extra:
        payload.update(extra)
    return payload


def list_contribution_keys(s3_client: Any, bucket: str, prefix: str, model_id: str) -> list[str]:
    store = S3ContributionStore(bucket=bucket, prefix=prefix)
    store._client = s3_client
    return store.list_keys(model_id=model_id)


def read_record(
    s3_client: Any, bucket: str, key: str
) -> tuple[StoredContributionRecord | None, str | None]:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"failed to read contribution object {key}") from exc

    try:
        payload = json.loads(response["Body"].read().decode("utf-8"))
        return (
            StoredContributionRecord(
                submission_id=payload["submission_id"],
                model_id=payload["model_id"],
                idempotency_key=payload["idempotency_key"],
                body_hash=payload["body_hash"],
                rows=payload["rows"],
                metadata=payload["metadata"],
                response_payload=payload["response_payload"],
                created_at=payload["created_at"],
            ),
            None,
        )
    except Exception:  # noqa: BLE001
        return None, "unparseable_record"


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def as_of_filter(
    records: Iterable[tuple[str, StoredContributionRecord]], as_of: datetime
) -> tuple[list[tuple[str, StoredContributionRecord]], list[dict[str, Any]]]:
    included: list[tuple[str, StoredContributionRecord]] = []
    quarantined: list[dict[str, Any]] = []
    for s3_key, record in records:
        try:
            created_at = parse_iso_datetime(record.created_at)
        except ValueError:
            quarantined.append(
                quarantine_record(
                    record.submission_id,
                    s3_key,
                    "unparseable_timestamp",
                    {"created_at": record.created_at},
                )
            )
            continue
        if created_at <= as_of:
            included.append((s3_key, record))
    return included, quarantined


def dedup_by_submission_id(
    records: Iterable[tuple[str, StoredContributionRecord]],
) -> tuple[list[tuple[str, StoredContributionRecord]], list[str]]:
    kept: dict[str, tuple[str, StoredContributionRecord]] = {}
    duplicates: list[str] = []
    for s3_key, record in sorted(records, key=lambda item: (item[1].submission_id, item[0])):
        existing = kept.get(record.submission_id)
        if existing is None:
            kept[record.submission_id] = (s3_key, record)
            continue
        duplicates.append(s3_key)
    return sorted(kept.values(), key=lambda item: item[1].submission_id), sorted(duplicates)


def tag_mlflow_run(run_id: str, report: dict[str, Any]) -> None:
    client = mlflow.tracking.MlflowClient(
        tracking_uri=report.get("mlflow_tracking_uri") or mlflow.get_tracking_uri()
    )
    client.set_tag(run_id, "training_dataset_hash", report["dataset_hash"])
    client.set_tag(run_id, "training_manifest_digest", report["manifest_digest"])
    client.set_tag(run_id, "training_as_of", report["as_of"])


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_validator(schema_path: Path) -> jsonschema.protocols.Validator:
    schema = load_json(schema_path)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def resolve_wallet_for_record(
    record: StoredContributionRecord,
    notifier: AuthServiceNotifier,
    cache: dict[tuple[str | None, str | None, str | None], WalletResolution],
    report: dict[str, Any],
) -> str | None:
    auth = record.metadata.get("auth_context") if isinstance(record.metadata, dict) else None
    if not isinstance(auth, dict):
        report["wallet_resolution"]["unresolved"] += 1
        return None
    key = (
        str(auth.get("user_id")) if auth.get("user_id") is not None else None,
        str(auth.get("api_key_id")) if auth.get("api_key_id") is not None else None,
        str(auth.get("service_id")) if auth.get("service_id") is not None else None,
    )
    if key not in cache:
        cache[key] = notifier.resolve_wallet(
            user_id=key[0],
            api_key_id=key[1],
            service_id=key[2],
        )
        report["wallet_resolution"]["requests"] += 1
    wallet = cache[key].wallet_address
    if wallet is None:
        report["wallet_resolution"]["unresolved"] += 1
        return None
    if not is_valid_wallet(wallet):
        report["wallet_resolution"]["invalid_format"] += 1
        return None
    return wallet.lower()


def account_id_for_record(record: StoredContributionRecord) -> str | None:
    """Return the contributing account (auth_context.user_id) for a submission, if present.

    This is the account identity threaded into the training manifest so attribution can be
    account-centric (HOK-2245): the wallet is resolved from the account at mint, but a
    wallet-less contributor is still identified and creditable by account_id.
    """
    auth = record.metadata.get("auth_context") if isinstance(record.metadata, dict) else None
    if not isinstance(auth, dict):
        return None
    user_id = auth.get("user_id")
    return str(user_id) if user_id is not None else None


def assemble(args: argparse.Namespace) -> dict[str, Any]:  # noqa: C901
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = parse_iso_datetime(args.as_of)
    validator = build_validator(Path(args.row_schema).expanduser().resolve())
    s3_client = boto3.client("s3")
    notifier = AuthServiceNotifier(
        auth_service_url=os.getenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.hokus.ai"),
        internal_token=os.getenv("HOKUSAI_AUTH_INTERNAL_TOKEN", ""),
        dry_run=False,
    )
    report: dict[str, Any] = {
        "as_of": args.as_of,
        "model_id": args.model_id,
        "wallet_policy": args.on_missing_wallet,
        "listed_keys": 0,
        "read_records": 0,
        "filtered_after_as_of": 0,
        "duplicates_dropped": [],
        "quarantine_count": 0,
        "quarantined_submissions": 0,
        "quarantined_rows": 0,
        "excluded_no_wallet": [],
        "wallet_resolution": {
            "requests": 0,
            "unresolved": 0,
            "invalid_format": 0,
        },
        "dataset_hash": "",
        "manifest_digest": "",
        "row_count": 0,
        "block_count": 0,
        "mlflow_run_id": args.mlflow_run_id,
        "mlflow_tracking_uri": args.mlflow_tracking_uri,
    }
    quarantines: list[dict[str, Any]] = []

    try:
        keys = list_contribution_keys(s3_client, args.s3_bucket, args.s3_prefix, args.model_id)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("failed to list contribution records") from exc
    report["listed_keys"] = len(keys)

    parsed_records: list[tuple[str, StoredContributionRecord]] = []
    for key in keys:
        record, reason = read_record(s3_client, args.s3_bucket, key)
        if record is None:
            quarantines.append(quarantine_record("<unknown>", key, reason or "read_failed"))
            continue
        parsed_records.append((key, record))
    report["read_records"] = len(parsed_records)

    filtered_records, timestamp_quarantines = as_of_filter(parsed_records, as_of)
    report["filtered_after_as_of"] = (
        len(parsed_records) - len(filtered_records) - len(timestamp_quarantines)
    )
    quarantines.extend(timestamp_quarantines)

    deduped_records, duplicates = dedup_by_submission_id(filtered_records)
    report["duplicates_dropped"] = duplicates

    wallet_cache: dict[tuple[str | None, str | None, str | None], WalletResolution] = {}
    processed_submissions: list[ProcessedSubmission] = []

    for s3_key, record in deduped_records:
        valid_rows: list[dict[str, Any]] = []
        invalid_row_count = 0
        for row_index, row in enumerate(record.rows):
            reason = validate_row(row, validator)
            if reason is None:
                valid_rows.append(row)
                continue
            invalid_row_count += 1
            quarantines.append(
                quarantine_record(
                    record.submission_id,
                    s3_key,
                    "invalid_row",
                    {"row_index": row_index, "detail": reason},
                )
            )
        if not valid_rows:
            report["quarantined_submissions"] += 1
            if invalid_row_count == 0:
                quarantines.append(
                    quarantine_record(record.submission_id, s3_key, "empty_submission")
                )
            continue

        wallet = resolve_wallet_for_record(record, notifier, wallet_cache, report)
        if wallet is None and args.on_missing_wallet == "quarantine":
            quarantines.append(quarantine_record(record.submission_id, s3_key, "wallet_unresolved"))
            report["quarantined_submissions"] += 1
            continue
        if wallet is None and args.on_missing_wallet == "exclude":
            report["excluded_no_wallet"].append(record.submission_id)
            continue

        processed_submissions.append(
            ProcessedSubmission(
                submission_id=record.submission_id,
                s3_key=s3_key,
                rows=valid_rows,
                wallet=wallet,
                account_id=account_id_for_record(record),
                reward_hold=wallet is None and args.on_missing_wallet == "hold",
            )
        )

    processed_submissions.sort(key=lambda item: item.submission_id)
    report["excluded_no_wallet"] = sorted(report["excluded_no_wallet"])

    dataset_path = output_dir / "dataset.jsonl"
    manifest_path = output_dir / "manifest.json"
    quarantine_path = output_dir / "quarantine.jsonl"
    report_path = output_dir / "report.json"

    blocks: list[dict[str, Any]] = []
    row_count = 0
    dataset_digest = hashlib.sha256()
    with dataset_path.open("w", encoding="utf-8", newline="\n") as dataset_file:
        for submission in processed_submissions:
            row_start = row_count
            for row in submission.rows:
                encoded = canonical_row_bytes(row)
                dataset_file.write(encoded.decode("utf-8"))
                dataset_file.write("\n")
                dataset_digest.update(encoded)
                dataset_digest.update(b"\n")
                row_count += 1
            blocks.append(
                {
                    "submission_id": submission.submission_id,
                    "wallet": submission.wallet,
                    "account_id": submission.account_id,
                    "s3_key": submission.s3_key,
                    "row_start": row_start,
                    "row_end": row_count - 1 if submission.rows else row_start - 1,
                    "row_count": len(submission.rows),
                    "reward_hold": submission.reward_hold,
                }
            )

    with quarantine_path.open("w", encoding="utf-8", newline="\n") as quarantine_file:
        for quarantine in quarantines:
            quarantine_file.write(json.dumps(quarantine, sort_keys=True, separators=(",", ":")))
            quarantine_file.write("\n")

    dataset_hash = f"sha256:{dataset_digest.hexdigest()}"
    manifest = {
        "schema_version": "model_30_training_manifest/v1",
        "as_of": args.as_of,
        "dataset_hash": dataset_hash,
        "manifest_digest": "",
        "row_count": row_count,
        "model_id": args.model_id,
        "blocks": blocks,
        "quarantine_count": len(quarantines),
        "duplicates_dropped": duplicates,
        "wallet_policy": args.on_missing_wallet,
    }
    manifest_digest = f"sha256:{hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()}"
    manifest["manifest_digest"] = manifest_digest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    report["dataset_hash"] = dataset_hash
    report["manifest_digest"] = manifest_digest
    report["row_count"] = row_count
    report["block_count"] = len(blocks)
    report["quarantine_count"] = len(quarantines)
    report["quarantined_rows"] = len(
        [entry for entry in quarantines if entry["reason"] == "invalid_row"]
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.mlflow_run_id:
        if args.mlflow_tracking_uri:
            mlflow.set_tracking_uri(args.mlflow_tracking_uri)
        tag_mlflow_run(args.mlflow_run_id, report)

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, help="Inclusive ISO 8601 cutoff timestamp.")
    parser.add_argument("--model-id", default="30")
    parser.add_argument(
        "--s3-bucket",
        default=os.getenv("HOKUSAI_CONTRIBUTIONS_BUCKET"),
        required=os.getenv("HOKUSAI_CONTRIBUTIONS_BUCKET") is None,
    )
    parser.add_argument(
        "--s3-prefix",
        default=os.getenv("HOKUSAI_CONTRIBUTIONS_PREFIX", ""),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--on-missing-wallet",
        choices=WALLET_POLICIES,
        default="quarantine",
    )
    parser.add_argument("--mlflow-run-id")
    parser.add_argument("--mlflow-tracking-uri")
    parser.add_argument(
        "--row-schema",
        default=str(REPO_ROOT / "schema" / "technical_task_router_row.v1.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        assemble(parse_args(argv))
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    except RuntimeError:
        LOGGER.exception("assembler_s3_failure")
        return 3
    except mlflow.exceptions.MlflowException:
        LOGGER.exception("assembler_mlflow_failure")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
