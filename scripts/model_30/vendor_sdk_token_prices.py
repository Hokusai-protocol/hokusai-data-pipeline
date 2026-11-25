#!/usr/bin/env python3
"""Vendor or check the SDK-generated price table and computation vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = {
    "configs/hokusai_token_prices.v1.json": "packages/core/prices/hokusai_token_prices.v1.json",
    "tests/fixtures/token-prices/parity.v1.json": "fixtures/token-prices/parity.v1.json",
}
MANIFEST = ROOT / "tests/fixtures/token-prices/provenance.json"


def main() -> None:
    """Copy both generated files atomically at the version-control boundary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdk", type=Path, help="SDK checkout with generated artifacts")
    parser.add_argument("--check", action="store_true", help="Fail on byte or hash drift")
    args = parser.parse_args()
    revision = subprocess.check_output(  # noqa: S603 -- read-only git on explicit local checkout
        ["git", "-C", str(args.sdk), "rev-parse", "HEAD"],  # noqa: S603, S607
        text=True,
    ).strip()
    artifacts = {}
    for destination, source in ARTIFACTS.items():
        content = (args.sdk / source).read_bytes()
        artifacts[destination] = {"sdk_path": source, "sha256": hashlib.sha256(content).hexdigest()}
        target = ROOT / destination
        if args.check:
            if target.read_bytes() != content:
                raise SystemExit(f"{destination} differs from the SDK; re-vendor both artifacts")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    manifest = {
        "sdk_repository": "https://github.com/Hokusai-protocol/hokusai-sdk",
        "sdk_commit": revision,
        "artifacts": artifacts,
    }
    if args.check:
        if json.loads(MANIFEST.read_text()) != manifest:
            raise SystemExit("SDK price provenance differs; re-vendor from the pinned SDK commit")
    else:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
