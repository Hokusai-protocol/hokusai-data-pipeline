"""Deterministic MLflow weight artifact commitment helpers.

Algorithm ID: ``sha256-merkle-v1``.

- Leaves are SHA-256 digests over raw file bytes only.
- Included files are ordered by POSIX relative path in lexicographic byte order.
- Merkle parents are ``SHA-256(left_digest_bytes || right_digest_bytes)``.
- Odd node counts duplicate the last node before pairing.
- A single included file uses its leaf digest as the root.
- Paths excluded as MLflow-volatile metadata are:
  - ``MLmodel``
  - any path under ``metadata/``
  - any path containing ``registered_model_meta``
- Symlinks are skipped and recorded as excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

ALGORITHM = "sha256-merkle-v1"
MLFLOW_VOLATILE_PATHS = frozenset({"MLmodel"})


@dataclass(frozen=True)
class WeightCommitment:
    """Deterministic digest over an MLflow artifact directory."""

    root: str
    algorithm: str
    files: list[tuple[str, str, int]]
    excluded: list[str]


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


def _merkle_root(leaf_digests: list[str]) -> str:
    """Return the Merkle root for the ordered *leaf_digests*."""
    if not leaf_digests:
        raise ValueError("no files to commit")
    if len(leaf_digests) == 1:
        return leaf_digests[0]

    level = leaf_digests[:]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])

        next_level: list[str] = []
        for index in range(0, len(level), 2):
            next_level.append(
                sha256(bytes.fromhex(level[index]) + bytes.fromhex(level[index + 1])).hexdigest()
            )
        level = next_level
    return level[0]


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

    for path in sorted(artifact_path.rglob("*"), key=lambda candidate: candidate.as_posix()):
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
    leaf_digests: list[str] = []
    for rel_posix in sorted(included_paths):
        path = artifact_path / rel_posix
        digest = _hash_file(path, chunk_size=chunk_size)
        files.append((rel_posix, digest, path.stat().st_size))
        leaf_digests.append(digest)

    return WeightCommitment(
        root=_merkle_root(leaf_digests),
        algorithm=ALGORITHM,
        files=files,
        excluded=sorted(excluded_paths),
    )
