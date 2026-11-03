"""The API image must ship every config file the serving adapter reads (HOK-3132 outage)."""

from __future__ import annotations

import re
from pathlib import Path

from src.api.endpoints import model_30_adapter

ROOT = Path(__file__).resolve().parents[2]


def _copied_paths() -> set[str]:
    text = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    return {m.group(1) for m in re.finditer(r"^COPY\s+(\S+)\s+\S+\s*$", text, re.MULTILINE)}


def test_dockerfile_copies_model_30_adapter_configs() -> None:
    copied = _copied_paths()
    for path in (
        model_30_adapter.MODEL_30_SUPPORTED_MODELS_PATH,
        model_30_adapter.MODEL_30_LINEAGE_PATH,
    ):
        rel = path.resolve().relative_to(ROOT).as_posix()
        assert rel in copied or "configs/" in copied, f"Dockerfile.api does not COPY {rel}"
