"""Tests for central MLflow mTLS SDK configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.utils.mlflow_config import configure_internal_mtls


@pytest.fixture(autouse=True)
def clear_mlflow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MLFLOW_MTLS_ENABLED",
        "MLFLOW_CA_BUNDLE_PATH",
        "MLFLOW_CLIENT_CERT_PATH",
        "MLFLOW_CLIENT_KEY_PATH",
        "MLFLOW_TRACKING_CLIENT_CERT_PATH",
        "MLFLOW_TRACKING_CLIENT_KEY_PATH",
        "MLFLOW_TRACKING_SERVER_CERT_PATH",
        "MLFLOW_TRACKING_INSECURE_TLS",
        "MLFLOW_HTTP_REQUEST_TIMEOUT",
        "MLFLOW_HTTP_REQUEST_MAX_RETRIES",
        "MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR",
    ):
        monkeypatch.delenv(key, raising=False)

    combined_path = Path("/tmp/mlflow_client_combined.pem")
    if combined_path.exists():
        combined_path.unlink()


def _write_cert_materials(tmp_path: Path) -> tuple[Path, Path, Path]:
    ca_path = tmp_path / "ca.crt"
    cert_path = tmp_path / "client.crt"
    key_path = tmp_path / "client.key"
    ca_path.write_text("CA CERT\n", encoding="utf-8")
    cert_path.write_text("CLIENT CERT\n", encoding="utf-8")
    key_path.write_text("CLIENT KEY\n", encoding="utf-8")
    return ca_path, cert_path, key_path


def test_configure_internal_mtls_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_INSECURE_TLS", "true")

    configure_internal_mtls()

    assert os.environ["MLFLOW_TRACKING_INSECURE_TLS"] == "true"
    assert "MLFLOW_TRACKING_CLIENT_CERT_PATH" not in os.environ
    assert not Path("/tmp/mlflow_client_combined.pem").exists()


def test_configure_internal_mtls_sets_sdk_env_and_combined_pem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ca_path, cert_path, key_path = _write_cert_materials(tmp_path)
    monkeypatch.setenv("MLFLOW_MTLS_ENABLED", "true")
    monkeypatch.setenv("MLFLOW_CA_BUNDLE_PATH", str(ca_path))
    monkeypatch.setenv("MLFLOW_CLIENT_CERT_PATH", str(cert_path))
    monkeypatch.setenv("MLFLOW_CLIENT_KEY_PATH", str(key_path))
    monkeypatch.setenv("MLFLOW_TRACKING_INSECURE_TLS", "true")

    configure_internal_mtls()

    combined_path = Path("/tmp/mlflow_client_combined.pem")
    assert os.environ["MLFLOW_TRACKING_CLIENT_CERT_PATH"] == str(combined_path)
    assert os.environ["MLFLOW_TRACKING_CLIENT_KEY_PATH"] == str(key_path)
    assert os.environ["MLFLOW_TRACKING_SERVER_CERT_PATH"] == str(ca_path)
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "5"
    assert os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "2"
    assert os.environ["MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR"] == "1"
    assert "MLFLOW_TRACKING_INSECURE_TLS" not in os.environ
    assert combined_path.read_text(encoding="utf-8") == "CLIENT CERT\nCLIENT KEY\n"
    assert oct(combined_path.stat().st_mode & 0o777) == "0o600"


def test_configure_internal_mtls_requires_all_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ca_path, cert_path, _key_path = _write_cert_materials(tmp_path)
    monkeypatch.setenv("MLFLOW_MTLS_ENABLED", "true")
    monkeypatch.setenv("MLFLOW_CA_BUNDLE_PATH", str(ca_path))
    monkeypatch.setenv("MLFLOW_CLIENT_CERT_PATH", str(cert_path))

    with pytest.raises(RuntimeError, match="MLFLOW_CLIENT_KEY_PATH"):
        configure_internal_mtls()


def test_configure_internal_mtls_rejects_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ca_path, cert_path, _key_path = _write_cert_materials(tmp_path)
    missing_key_path = tmp_path / "missing.key"
    monkeypatch.setenv("MLFLOW_MTLS_ENABLED", "true")
    monkeypatch.setenv("MLFLOW_CA_BUNDLE_PATH", str(ca_path))
    monkeypatch.setenv("MLFLOW_CLIENT_CERT_PATH", str(cert_path))
    monkeypatch.setenv("MLFLOW_CLIENT_KEY_PATH", str(missing_key_path))

    with pytest.raises(RuntimeError, match=f"MLFLOW_CLIENT_KEY_PATH.*{missing_key_path}"):
        configure_internal_mtls()


def test_configure_internal_mtls_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ca_path, cert_path, key_path = _write_cert_materials(tmp_path)
    monkeypatch.setenv("MLFLOW_MTLS_ENABLED", "TrUe")
    monkeypatch.setenv("MLFLOW_CA_BUNDLE_PATH", str(ca_path))
    monkeypatch.setenv("MLFLOW_CLIENT_CERT_PATH", str(cert_path))
    monkeypatch.setenv("MLFLOW_CLIENT_KEY_PATH", str(key_path))

    configure_internal_mtls()
    first_bytes = Path("/tmp/mlflow_client_combined.pem").read_bytes()
    first_env = {
        key: os.environ[key]
        for key in (
            "MLFLOW_TRACKING_CLIENT_CERT_PATH",
            "MLFLOW_TRACKING_CLIENT_KEY_PATH",
            "MLFLOW_TRACKING_SERVER_CERT_PATH",
            "MLFLOW_HTTP_REQUEST_TIMEOUT",
            "MLFLOW_HTTP_REQUEST_MAX_RETRIES",
            "MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR",
        )
    }

    configure_internal_mtls()

    assert Path("/tmp/mlflow_client_combined.pem").read_bytes() == first_bytes
    assert {key: os.environ[key] for key in first_env} == first_env
