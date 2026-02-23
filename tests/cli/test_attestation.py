"""Unit tests for hokusai eval attestation helpers."""

from __future__ import annotations

from contextlib import nullcontext

from src.cli.attestation import create_attestation, log_attestation


class _FakeMlflow:
    def __init__(self) -> None:
        # Authentication (MLFLOW_TRACKING_TOKEN / Authorization) is handled externally.
        self.tags: list[tuple[str, str]] = []
        self.artifacts: list[tuple[dict, str]] = []

    def start_run(self, run_id: str):
        return nullcontext()

    def set_tag(self, key: str, value: str) -> None:
        self.tags.append((key, value))

    def log_dict(self, payload: dict, path: str) -> None:
        self.artifacts.append((payload, path))


def test_attestation_hash_is_deterministic() -> None:
    inputs = {
        "model_id": "model-a",
        "eval_spec": "dataset-v1",
        "provider": "openai",
        "seed": 42,
        "temperature": 0.1,
        "results": {"accuracy": 0.95},
    }
    first_hash, first_payload = create_attestation(**inputs)
    second_hash, second_payload = create_attestation(**inputs)

    assert first_hash == second_hash
    assert first_payload == second_payload


def test_attestation_hash_changes_with_result_change() -> None:
    base = {
        "model_id": "model-a",
        "eval_spec": "dataset-v1",
        "provider": "openai",
        "seed": 42,
        "temperature": 0.1,
    }
    first_hash, _ = create_attestation(results={"accuracy": 0.95}, **base)
    second_hash, _ = create_attestation(results={"accuracy": 0.90}, **base)

    assert first_hash != second_hash


def test_log_attestation_logs_tag_and_artifact() -> None:
    fake_mlflow = _FakeMlflow()
    att_hash, payload = create_attestation(
        model_id="model-a",
        eval_spec="dataset-v1",
        provider="openai",
        seed=42,
        temperature=0.1,
        results={"accuracy": 0.95},
    )

    log_attestation(
        mlflow_module=fake_mlflow,
        run_id="run-123",
        attestation_hash=att_hash,
        payload=payload,
    )

    assert ("hoku_eval.attestation_hash", att_hash) in fake_mlflow.tags
    assert fake_mlflow.artifacts
    artifact_payload, artifact_path = fake_mlflow.artifacts[0]
    assert artifact_payload["attestation_hash"] == att_hash
    assert artifact_path.endswith("attestation.json")
