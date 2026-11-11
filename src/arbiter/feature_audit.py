# ruff: noqa: ANN101, S603 - self needs no annotation; the validator command is operator configuration
"""The merge-time leakage validator, called from Python (HOK-2818).

The rules live in one place: ``validateFeatureColumns`` in hokusai-sdk's
``@hokusai/core`` (HOK-3023). This module runs ``hokusai-scan
corpus-feature-audit`` and holds no rules of its own, so dataset assembly and
TypeScript callers always get the same answer.

The command comes from ``HOKUSAI_SCAN_CMD`` (for example
``node /path/to/corpus-cli.mjs``), else ``hokusai-scan`` on ``PATH``. A missing
validator is an error, never a pass.

CLI exit codes: 0 the columns pass, 1 leakage found, 2 usage or input error.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

VALIDATOR_ENV = "HOKUSAI_SCAN_CMD"
VALIDATOR_TIMEOUT_SECONDS = 60


class LeakageError(Exception):
    """A dataset or split would let post-merge or label-side information into training."""


class ColumnLeakageError(LeakageError):
    """The validator rejected columns. ``codes`` holds its error codes."""

    def __init__(self, message: str, codes: list[str]) -> None:
        super().__init__(message)
        self.codes = codes


class ValidatorUnavailableError(LeakageError):
    """The validator could not be run, so nothing can be shown to be leak-free."""


@dataclass(frozen=True)
class AuditResult:
    """The validator's answer for one column list."""

    manifest_version: str
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    command: tuple[str, ...] = ()

    @property
    def codes(self) -> list[str]:
        return sorted({e["code"] for e in self.errors})


def validator_command() -> list[str]:
    """Return the validator command, or raise if there is none."""
    configured = os.environ.get(VALIDATOR_ENV)
    if configured:
        return shlex.split(configured)
    found = shutil.which("hokusai-scan")
    if found:
        return [found]
    raise ValidatorUnavailableError(
        f"No leakage validator: set {VALIDATOR_ENV} or put hokusai-scan on PATH"
    )


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = validator_command() + args
    try:
        return subprocess.run(  # noqa: S603 - the command is operator configuration
            command,
            capture_output=True,
            text=True,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidatorUnavailableError(f"Leakage validator failed to run: {error}") from error


def audit_columns(columns: Sequence[str], *, allow_segments: bool = False) -> AuditResult:
    """Run the validator on a column list. Raises on exit 2 or unreadable output."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "columns.json")
        with open(path, "w") as f:
            json.dump(list(columns), f)
        args = ["corpus-feature-audit", "--columns", path]
        if allow_segments:
            args.append("--allow-segments")
        proc = _run(args)
    if proc.returncode not in (0, 1):
        raise ValidatorUnavailableError(
            f"Leakage validator rejected its input (exit {proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
        result = AuditResult(
            manifest_version=payload["manifest_version"],
            ok=bool(payload["ok"]),
            errors=list(payload["errors"]),
            command=tuple(validator_command()),
        )
    except (ValueError, KeyError, TypeError) as error:
        raise ValidatorUnavailableError(f"Unreadable validator output: {error}") from error
    if result.ok != (proc.returncode == 0):
        raise ValidatorUnavailableError("Validator exit code and result disagree")
    return result


def require_columns_pass(
    columns: Sequence[str], *, manifest_version: str, allow_segments: bool = False
) -> AuditResult:
    """Fail unless the validator passes the columns under the expected manifest."""
    result = audit_columns(columns, allow_segments=allow_segments)
    if result.manifest_version != manifest_version:
        raise LeakageError(
            f"Validator checks {result.manifest_version}, but the rows are {manifest_version}"
        )
    if not result.ok:
        detail = "; ".join(e["message"] for e in result.errors)
        raise ColumnLeakageError(f"Leakage validator rejected the columns: {detail}", result.codes)
    return result


def print_manifest() -> dict[str, Any]:
    """Return the frozen manifest as the validator holds it."""
    proc = _run(["corpus-feature-audit", "--print-manifest"])
    if proc.returncode != 0:
        raise ValidatorUnavailableError(f"--print-manifest failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)
