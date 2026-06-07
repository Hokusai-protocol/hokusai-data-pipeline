"""Unit tests for signer custody validation."""

from __future__ import annotations

import pytest

from src.api.services.signer_custody import (
    SignerCustodyError,
    SignerCustodyMode,
    resolve_custody_mode,
    validate_custody_for_env,
)


def test_env_custody_rejected_on_production() -> None:
    with pytest.raises(SignerCustodyError):
        validate_custody_for_env(SignerCustodyMode.ENV, "production")


def test_env_custody_allowed_on_development() -> None:
    validate_custody_for_env(SignerCustodyMode.ENV, "development")


def test_kms_custody_allowed_everywhere() -> None:
    validate_custody_for_env(SignerCustodyMode.KMS, "development")
    validate_custody_for_env(SignerCustodyMode.KMS, "staging")
    validate_custody_for_env(SignerCustodyMode.KMS, "production")


def test_resolve_custody_mode_defaults_to_kms_on_production(monkeypatch) -> None:
    monkeypatch.delenv("SIGNER_CUSTODY_MODE", raising=False)

    assert resolve_custody_mode("production") is SignerCustodyMode.KMS
