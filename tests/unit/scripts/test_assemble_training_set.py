from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import jsonschema
import pytest

from scripts.model_30 import assemble_training_set as assembler
from src.api.services.auth_service_notifier import WalletResolution

# MLflow auth in production uses shared env such as `MLFLOW_TRACKING_TOKEN`.


class FakePaginator:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:  # noqa: N803
        del Bucket
        return [{"Contents": [{"Key": key} for key in self._keys if key.startswith(Prefix)]}]


class FakeS3Client:
    def __init__(self, objects: dict[str, str], listing_order: list[str] | None = None) -> None:
        self._objects = objects
        self._listing_order = listing_order or sorted(objects)

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator(self._listing_order)

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        del Bucket
        return {"Body": io.BytesIO(self._objects[Key].encode("utf-8"))}


class FakeNotifier:
    def __init__(
        self, wallets: dict[tuple[str | None, str | None, str | None], str | None]
    ) -> None:
        self.wallets = wallets
        self.calls: list[tuple[str | None, str | None, str | None]] = []

    def resolve_wallet(
        self,
        *,
        user_id: str | None,
        api_key_id: str | None = None,
        service_id: str | None = None,
    ) -> WalletResolution:
        key = (user_id, api_key_id, service_id)
        self.calls.append(key)
        wallet = self.wallets.get(key)
        return WalletResolution(
            resolved=wallet is not None,
            has_verified_wallet=wallet is not None,
            wallet_address=wallet,
        )


def _valid_row(row_id: str) -> dict[str, Any]:
    return {
        "schema_version": "technical_task_router_row/v1",
        "row_id": row_id,
        "benchmark_spec_id": "bench-1",
        "eval_id": "eval-1",
        "model_id": "30",
        "task_descriptor": {"task_type": "bugfix"},
        "allowed_models": ["gpt-5.4"],
        "selected_models": ["gpt-5.4"],
        "max_cost_usd": 1.0,
        "actual_cost_usd": 0.5,
        "completed_successfully": True,
        "scorer_ref": "technical_task_router.success_under_budget/v1",
        "observed_at": "2026-06-01T00:00:00Z",
    }


def _record_payload(
    submission_id: str,
    rows: list[dict[str, Any]],
    *,
    created_at: str = "2026-06-01T00:00:00Z",
    user_id: str = "user-1",
    api_key_id: str = "api-1",
    service_id: str = "svc-1",
) -> dict[str, Any]:
    return {
        "submission_id": submission_id,
        "model_id": "30",
        "idempotency_key": f"idem-{submission_id}",
        "body_hash": f"hash-{submission_id}",
        "rows": rows,
        "metadata": {
            "auth": {
                "user_id": user_id,
                "api_key_id": api_key_id,
                "service_id": service_id,
            }
        },
        "response_payload": {"accepted": True},
        "created_at": created_at,
    }


def _object_key(name: str) -> str:
    return f"prefix/contributions/model_id=30/{name}.json"


def _run_assemble(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    objects: dict[str, dict[str, Any] | str],
    listing_order: list[str] | None = None,
    wallets: dict[tuple[str | None, str | None, str | None], str | None] | None = None,
    on_missing_wallet: str = "quarantine",
    mlflow_run_id: str | None = None,
) -> tuple[dict[str, Any], Path, FakeNotifier]:
    serialized = {
        key: value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        for key, value in objects.items()
    }
    fake_s3 = FakeS3Client(serialized, listing_order=listing_order)
    fake_notifier = FakeNotifier(wallets or {})
    monkeypatch.setattr(assembler.boto3, "client", lambda name: fake_s3)
    monkeypatch.setattr(
        assembler,
        "AuthServiceNotifier",
        lambda **kwargs: fake_notifier,
    )

    args = SimpleNamespace(
        as_of="2026-06-02T00:00:00Z",
        model_id="30",
        s3_bucket="bucket",
        s3_prefix="prefix",
        output_dir=str(tmp_path),
        on_missing_wallet=on_missing_wallet,
        mlflow_run_id=mlflow_run_id,
        mlflow_tracking_uri=None,
        row_schema=str(Path("schema/technical_task_router_row.v1.json").resolve()),
    )
    report = assembler.assemble(args)
    return report, tmp_path, fake_notifier


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines()]


def test_deterministic_hash_same_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {
        _object_key("sub-2"): _record_payload("sub-2", [_valid_row("r-2"), _valid_row("r-3")]),
        _object_key("sub-1"): _record_payload("sub-1", [_valid_row("r-1")]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    report_one, out_one, _ = _run_assemble(
        tmp_path / "run-one",
        monkeypatch,
        objects=objects,
        wallets=wallets,
    )
    report_two, out_two, _ = _run_assemble(
        tmp_path / "run-two",
        monkeypatch,
        objects=objects,
        wallets=wallets,
    )

    assert report_one["dataset_hash"] == report_two["dataset_hash"]
    assert (out_one / "dataset.jsonl").read_bytes() == (out_two / "dataset.jsonl").read_bytes()


def test_listing_order_does_not_affect_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    objects = {
        _object_key("sub-b"): _record_payload("sub-b", [_valid_row("r-2")]),
        _object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    report_one, _, _ = _run_assemble(
        tmp_path / "one",
        monkeypatch,
        objects=objects,
        listing_order=[_object_key("sub-b"), _object_key("sub-a")],
        wallets=wallets,
    )
    report_two, _, _ = _run_assemble(
        tmp_path / "two",
        monkeypatch,
        objects=objects,
        listing_order=[_object_key("sub-a"), _object_key("sub-b")],
        wallets=wallets,
    )

    assert report_one["dataset_hash"] == report_two["dataset_hash"]


def test_as_of_filter_excludes_later_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    objects = {
        _object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")]),
        _object_key("sub-b"): _record_payload(
            "sub-b",
            [_valid_row("r-2")],
            created_at="2026-06-03T00:00:00Z",
        ),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)

    assert report["filtered_after_as_of"] == 1
    assert _read_jsonl(output_dir / "dataset.jsonl") == [_valid_row("r-1")]


def test_manifest_block_contiguity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {
        _object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1"), _valid_row("r-2")]),
        _object_key("sub-b"): _record_payload("sub-b", [_valid_row("r-3")]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    _, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["row_count"] == 3
    assert manifest["blocks"][0]["row_start"] == 0
    assert manifest["blocks"][0]["row_end"] == 1
    assert manifest["blocks"][1]["row_start"] == 2
    assert manifest["blocks"][1]["row_end"] == 2


def test_dedup_keeps_lowest_s3_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {
        _object_key("aaa-sub"): _record_payload("dup", [_valid_row("r-1")]),
        _object_key("zzz-sub"): _record_payload("dup", [_valid_row("r-2")]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)

    assert report["duplicates_dropped"] == [_object_key("zzz-sub")]
    assert _read_jsonl(output_dir / "dataset.jsonl") == [_valid_row("r-1")]


def test_invalid_row_quarantined_with_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = _valid_row("bad")
    del invalid["observed_at"]
    objects = {
        _object_key("sub-a"): _record_payload("sub-a", [_valid_row("ok"), invalid]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)
    quarantine_rows = _read_jsonl(output_dir / "quarantine.jsonl")

    assert report["quarantined_rows"] == 1
    assert any(entry["reason"] == "invalid_row" for entry in quarantine_rows)
    assert _read_jsonl(output_dir / "dataset.jsonl") == [_valid_row("ok")]


def test_unparseable_record_quarantined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects: dict[str, dict[str, Any] | str] = {
        _object_key("sub-a"): "{not-json",
    }

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects)

    assert report["quarantine_count"] == 1
    assert _read_jsonl(output_dir / "quarantine.jsonl")[0]["reason"] == "unparseable_record"


def test_wallet_resolution_called_once_per_auth_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    objects = {
        _object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")]),
        _object_key("sub-b"): _record_payload("sub-b", [_valid_row("r-2")]),
    }
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}

    _, _, notifier = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)

    assert notifier.calls == [("user-1", "api-1", "svc-1")]


def test_on_missing_wallet_quarantine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {_object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")])}

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects)

    assert report["row_count"] == 0
    assert _read_jsonl(output_dir / "quarantine.jsonl")[0]["reason"] == "wallet_unresolved"


def test_on_missing_wallet_exclude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {_object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")])}

    report, output_dir, _ = _run_assemble(
        tmp_path,
        monkeypatch,
        objects=objects,
        on_missing_wallet="exclude",
    )

    assert report["excluded_no_wallet"] == ["sub-a"]
    assert _read_jsonl(output_dir / "quarantine.jsonl") == []


def test_on_missing_wallet_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {_object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")])}

    _, output_dir, _ = _run_assemble(
        tmp_path,
        monkeypatch,
        objects=objects,
        on_missing_wallet="hold",
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["blocks"][0]["wallet"] is None
    assert manifest["blocks"][0]["reward_hold"] is True
    assert _read_jsonl(output_dir / "dataset.jsonl") == [_valid_row("r-1")]


def test_invalid_wallet_format_treated_as_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    objects = {_object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")])}
    wallets = {("user-1", "api-1", "svc-1"): "0x123"}

    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects=objects, wallets=wallets)

    assert report["wallet_resolution"]["invalid_format"] == 1
    assert _read_jsonl(output_dir / "quarantine.jsonl")[0]["reason"] == "wallet_unresolved"


def test_mlflow_tags_written_on_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    objects = {_object_key("sub-a"): _record_payload("sub-a", [_valid_row("r-1")])}
    wallets = {("user-1", "api-1", "svc-1"): "0x742d35cc6634c0532925a3b844bc9e7595f62341"}
    client = Mock()
    monkeypatch.setattr(assembler.mlflow.tracking, "MlflowClient", Mock(return_value=client))

    report, _, _ = _run_assemble(
        tmp_path,
        monkeypatch,
        objects=objects,
        wallets=wallets,
        mlflow_run_id="run-123",
    )

    client.set_tag.assert_any_call("run-123", "training_dataset_hash", report["dataset_hash"])
    client.set_tag.assert_any_call("run-123", "training_manifest_digest", report["manifest_digest"])
    client.set_tag.assert_any_call("run-123", "training_as_of", report["as_of"])


def test_empty_input_produces_well_defined_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, output_dir, _ = _run_assemble(tmp_path, monkeypatch, objects={})
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report["dataset_hash"] == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"
    )
    assert manifest["blocks"] == []
    assert manifest["row_count"] == 0


def test_schema_example_is_valid() -> None:
    schema = json.loads(Path("schema/model_30_training_manifest.v1.json").read_text())
    example = json.loads(Path("schema/examples/model_30_training_manifest.v1.json").read_text())

    jsonschema.validate(example, schema)
