"""Deterministic MLflow weight artifact commitment helpers.

Algorithm ID: ``sha256-merkle-v1``. This must stay byte-for-byte identical to
``hokusai-token/scripts/lib/weight-commitment.js``. That implementation set the
on-chain ``ModelRegistry.weightGenesis`` values, and ``DeltaVerifier`` compares
every MintRequest's ``baselineCommitment`` against them.

- Each leaf is ``SHA-256(utf8(path) || 0x00 || SHA-256(file_bytes))``, with
  ``path`` as the POSIX path relative to the artifact root. Binding the path
  means renaming a file changes the root.
- Leaves are ordered by the UTF-8 bytes of their path.
- Merkle parents are ``SHA-256(left || right)`` over the raw 32-byte digests.
- An odd node at any level is paired with itself.
- A single included file's root is its leaf. The file digest is never used as
  the root directly.
- Paths excluded as MLflow-volatile metadata are:
  - ``MLmodel``
  - any path under ``metadata/``
  - any path containing ``registered_model_meta``
- Symlinks are skipped and recorded as excluded.

Before HOK-3394 this module hashed leaves as ``SHA-256(file_bytes)`` without
the path, so its roots disagreed with the on-chain genesis. Commitments tagged
on MLflow runs before that fix (e.g. Model 30 v5 ``0xc504…`` and v8
``0x7b71…``) are not comparable with on-chain heads.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ALGORITHM = "sha256-merkle-v1"
MLFLOW_VOLATILE_PATHS = frozenset({"MLmodel"})
_LEAF_SEPARATOR = b"\x00"


@dataclass(frozen=True)
class WeightCommitment:
    """Deterministic digest over an MLflow artifact directory.

    ``files`` holds ``(path, sha256(file_bytes), size)`` per included file. The
    per-file digest is the plain content hash (what deployment manifests
    record); the path-bound leaf is derived from it by :func:`leaf_digest`.
    """

    root: str
    algorithm: str
    files: tuple[tuple[str, str, int], ...]
    excluded: tuple[str, ...]


def _is_excluded(rel_posix: str) -> bool:
    """Return whether *rel_posix* is excluded from the commitment."""
    return (
        rel_posix in MLFLOW_VOLATILE_PATHS
        or rel_posix.startswith("metadata/")
        or "registered_model_meta" in rel_posix
    )


def _hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest for *path*."""
    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def leaf_digest(rel_posix: str, file_sha256_hex: str) -> bytes:
    """Return the path-bound leaf ``SHA-256(utf8(path) || 0x00 || file_digest)``."""
    return sha256(
        rel_posix.encode("utf-8") + _LEAF_SEPARATOR + bytes.fromhex(file_sha256_hex)
    ).digest()


def merkle_root(leaves: list[bytes]) -> str:
    """Return the hex Merkle root for ordered 32-byte *leaves*."""
    if not leaves:
        raise ValueError("no files to commit")
    level = list(leaves)
    while len(level) > 1:
        next_level: list[bytes] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(sha256(left + right).digest())
        level = next_level
    return level[0].hex()


def commitment_from_file_digests(files: list[tuple[str, str]]) -> str:
    """Return the root for ``(path, sha256(file_bytes))`` records.

    This lets a commitment be checked from a manifest alone (for example the
    ``includedFiles`` of a genesis config) without the artifact bytes.
    """
    ordered = sorted(files, key=lambda item: item[0].encode("utf-8"))
    paths = [path for path, _ in ordered]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate paths in commitment records")
    return merkle_root([leaf_digest(path, digest) for path, digest in ordered])


def compute_weight_commitment(
    artifact_dir: str | Path,
    *,
    chunk_size: int = 1 << 20,
) -> WeightCommitment:
    """Return the deterministic commitment for an MLflow artifact directory."""
    artifact_path = Path(artifact_dir)
    if not artifact_path.exists():
        raise FileNotFoundError(f"artifact directory does not exist: {artifact_path}")
    if not artifact_path.is_dir():
        raise NotADirectoryError(f"artifact path is not a directory: {artifact_path}")

    included_paths: list[str] = []
    excluded_paths: list[str] = []

    for path in artifact_path.rglob("*"):
        rel_posix = path.relative_to(artifact_path).as_posix()
        if path.is_symlink():
            excluded_paths.append(rel_posix)
            continue
        if path.is_dir():
            continue
        if _is_excluded(rel_posix):
            excluded_paths.append(rel_posix)
            continue
        included_paths.append(rel_posix)

    if not included_paths:
        raise ValueError("no files to commit")

    files: list[tuple[str, str, int]] = []
    for rel_posix in sorted(included_paths, key=lambda item: item.encode("utf-8")):
        path = artifact_path / rel_posix
        files.append((rel_posix, _hash_file(path, chunk_size=chunk_size), path.stat().st_size))

    return WeightCommitment(
        root=commitment_from_file_digests([(path, digest) for path, digest, _ in files]),
        algorithm=ALGORITHM,
        files=tuple(files),
        excluded=tuple(sorted(excluded_paths, key=lambda item: item.encode("utf-8"))),
    )
