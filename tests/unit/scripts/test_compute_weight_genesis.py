from __future__ import annotations

from pathlib import Path

from scripts.model_30.compute_weight_genesis import compute_genesis_payload
from src.lineage.weight_commitment import compute_weight_commitment


def test_compute_genesis_payload_for_local_artifact(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    (artifact_dir / "weights.bin").write_text("abc", encoding="utf-8")
    (artifact_dir / "MLmodel").write_text("ignored", encoding="utf-8")

    payload = compute_genesis_payload(str(artifact_dir), model_id_uint=30)

    assert payload["algorithm"] == "sha256-merkle-v1"
    assert payload["commitment"] == f"0x{compute_weight_commitment(artifact_dir).root}"
    assert payload["included_file_count"] == 1
    assert payload["excluded_file_count"] == 1
    assert payload["set_weight_genesis_call"] == (
        f"ModelRegistry.setWeightGenesis(30, {payload['commitment']})"
    )
