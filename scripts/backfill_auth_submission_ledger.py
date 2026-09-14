#!/usr/bin/env python3
"""Backfill auth data-submission ledger rows from persisted S3 contributions."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.services.auth_service_notifier import AuthServiceNotifier  # noqa: E402
from src.api.services.contribution_service import StoredContributionRecord  # noqa: E402

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bucket", required=True, help="S3 bucket containing contribution records."
    )
    parser.add_argument("--model-id", required=True, help="Model id to backfill, for example 30.")
    parser.add_argument(
        "--prefix", default="", help="Optional bucket prefix before contributions/."
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument(
        "--auth-service-url",
        default=os.getenv("HOKUSAI_AUTH_SERVICE_URL", "https://auth.hokus.ai"),
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum records to process.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Post to auth. Without this flag the script logs the records it would send.",
    )
    return parser.parse_args()


def contribution_prefix(*, base_prefix: str, model_id: str) -> str:
    """Return the S3 key prefix for model contribution records."""
    prefix = base_prefix.strip("/")
    key_prefix = f"contributions/model_id={model_id}/"
    if prefix:
        return f"{prefix}/{key_prefix}"
    return key_prefix


def iter_records(
    *,
    bucket: str,
    prefix: str,
    region: str,
    limit: int | None,
) -> list[tuple[StoredContributionRecord, dict[str, Any], str]]:
    """Load contribution records and stored auth contexts from S3."""
    s3_client = boto3.client("s3", region_name=region)
    paginator = s3_client.get_paginator("list_objects_v2")
    records: list[tuple[StoredContributionRecord, dict[str, Any], str]] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item.get("Key")
            if not isinstance(key, str) or not key.endswith(".json"):
                continue

            response = s3_client.get_object(Bucket=bucket, Key=key)
            payload = json.loads(response["Body"].read().decode("utf-8"))
            record = StoredContributionRecord(
                submission_id=payload["submission_id"],
                model_id=payload["model_id"],
                idempotency_key=payload["idempotency_key"],
                body_hash=payload["body_hash"],
                rows=payload["rows"],
                metadata=payload["metadata"],
                response_payload=payload["response_payload"],
                created_at=payload["created_at"],
            )
            auth_context = record.metadata.get("auth_context")
            if not isinstance(auth_context, dict) or not auth_context:
                LOGGER.warning("Skipping %s: missing auth_context", key)
                continue

            records.append((record, auth_context, f"s3://{bucket}/{key}"))
            if limit is not None and len(records) >= limit:
                return records

    return records


def main() -> int:
    """Run the backfill command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    args = parse_args()
    prefix = contribution_prefix(base_prefix=args.prefix, model_id=args.model_id)
    records = iter_records(
        bucket=args.bucket,
        prefix=prefix,
        region=args.region,
        limit=args.limit,
    )
    notifier = AuthServiceNotifier(
        auth_service_url=args.auth_service_url,
        internal_token=os.getenv("HOKUSAI_AUTH_INTERNAL_TOKEN", ""),
        dry_run=not args.execute,
    )

    row_count = 0
    for record, auth_context, storage_ref in records:
        row_count += len(record.rows)
        notifier.notify_accepted(record=record, auth=auth_context, storage_ref=storage_ref)

    LOGGER.info(
        "Backfill %s: records=%s rows=%s model_id=%s prefix=%s",
        "executed" if args.execute else "dry-run",
        len(records),
        row_count,
        args.model_id,
        prefix,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
