"""Cross-repo conformance for weight commitments (HOK-3394).

The expected roots come from hokusai-token ``scripts/lib/weight-commitment.js``,
which produced the on-chain ``ModelRegistry.weightGenesis`` values. If these
tests fail, MintRequests built by this repo will revert on chain with
``LineageParentMismatch``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.lineage.weight_commitment import (
    commitment_from_file_digests,
    compute_weight_commitment,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures/weight_commitment/conformance_vectors.json"
)
VECTORS = json.loads(FIXTURE.read_text())["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_manifest_root_matches_onchain_scheme(vector: dict) -> None:
    if "hex" in vector["files"][0]:
        from hashlib import sha256

        records = [
            (f["path"], sha256(bytes.fromhex(f["hex"].removeprefix("0x"))).hexdigest())
            for f in vector["files"]
        ]
    else:
        records = [(f["path"], f["sha256"]) for f in vector["files"]]

    assert f"0x{commitment_from_file_digests(records)}" == vector["expectedRoot"]


def test_directory_root_matches_onchain_scheme_with_real_bytes(tmp_path: Path) -> None:
    vector = next(v for v in VECTORS if v["name"] == "sepolia-rehearsal-model-30")
    for entry in vector["files"]:
        path = tmp_path / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes.fromhex(entry["hex"].removeprefix("0x")))
    # MLflow-volatile metadata must not affect the root.
    (tmp_path / "MLmodel").write_text("flavors: {}\n")

    commitment = compute_weight_commitment(tmp_path)

    assert f"0x{commitment.root}" == vector["expectedRoot"]
    assert commitment.excluded == ("MLmodel",)


def test_duplicate_paths_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        commitment_from_file_digests([("a", "00" * 32), ("a", "11" * 32)])
