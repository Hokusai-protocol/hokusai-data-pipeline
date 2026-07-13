"""Regression checks for runtime assets packaged into the API image."""

from __future__ import annotations

from pathlib import Path


def test_api_dockerfile_packages_contribution_schema_assets() -> None:
    dockerfile = Path("Dockerfile.api").read_text(encoding="utf-8")

    assert "COPY schema/ ./schema/" in dockerfile
