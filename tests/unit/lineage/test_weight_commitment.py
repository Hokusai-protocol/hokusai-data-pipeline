from __future__ import annotations

import os
import re
from hashlib import sha256
from pathlib import Path

import pytest

from src.lineage.weight_commitment import compute_weight_commitment


def _write_files(root: Path, files: dict[str, bytes]) -> None:
    for rel_path, content in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_returns_64_char_hex_root(tmp_path: Path) -> None:
    _write_files(tmp_path, {"a.bin": b"alpha", "b.bin": b"beta"})

    commitment = compute_weight_commitment(tmp_path)

    assert re.fullmatch(r"[0-9a-f]{64}", commitment.root)


def test_algorithm_identifier(tmp_path: Path) -> None:
    _write_files(tmp_path, {"weights.bin": b"payload"})

    commitment = compute_weight_commitment(tmp_path)

    assert commitment.algorithm == "sha256-merkle-v1"


def test_determinism_same_call_twice(tmp_path: Path) -> None:
    _write_files(tmp_path, {"weights.bin": b"payload"})

    first = compute_weight_commitment(tmp_path)
    second = compute_weight_commitment(tmp_path)

    assert first == second


def test_determinism_after_mtime_touch(tmp_path: Path) -> None:
    path = tmp_path / "weights.bin"
    path.write_bytes(b"payload")
    first = compute_weight_commitment(tmp_path).root

    os.utime(path, None)
    second = compute_weight_commitment(tmp_path).root

    assert first == second


def test_sensitivity_byte_change(tmp_path: Path) -> None:
    path = tmp_path / "weights.bin"
    path.write_bytes(b"\x00\x01\x02")
    first = compute_weight_commitment(tmp_path).root

    path.write_bytes(b"\x00\x01\x03")
    second = compute_weight_commitment(tmp_path).root

    assert first != second


def test_sensitivity_add_file(tmp_path: Path) -> None:
    _write_files(tmp_path, {"a.bin": b"alpha"})
    first = compute_weight_commitment(tmp_path).root

    _write_files(tmp_path, {"b.bin": b"beta"})
    second = compute_weight_commitment(tmp_path).root

    assert first != second


def test_sensitivity_remove_file(tmp_path: Path) -> None:
    _write_files(tmp_path, {"a.bin": b"alpha", "b.bin": b"beta"})
    first = compute_weight_commitment(tmp_path).root

    (tmp_path / "b.bin").unlink()
    second = compute_weight_commitment(tmp_path).root

    assert first != second


def test_sensitivity_rename_file(tmp_path: Path) -> None:
    _write_files(tmp_path, {"a.bin": b"alpha", "b.bin": b"beta"})
    first = compute_weight_commitment(tmp_path).root

    (tmp_path / "a.bin").rename(tmp_path / "c.bin")
    second = compute_weight_commitment(tmp_path).root

    assert first != second


def test_ordering_canonical_not_filesystem(tmp_path: Path) -> None:
    forward = tmp_path / "forward"
    reverse = tmp_path / "reverse"
    _write_files(forward, {"a.bin": b"alpha", "b.bin": b"beta", "c.bin": b"gamma"})
    _write_files(reverse, {"c.bin": b"gamma", "b.bin": b"beta", "a.bin": b"alpha"})

    assert compute_weight_commitment(forward).root == compute_weight_commitment(reverse).root


def test_single_file_root_equals_leaf(tmp_path: Path) -> None:
    payload = b"payload"
    _write_files(tmp_path, {"weights.bin": payload})

    commitment = compute_weight_commitment(tmp_path)

    assert commitment.root == sha256(payload).hexdigest()


def test_nested_subdirectory_included(tmp_path: Path) -> None:
    _write_files(tmp_path, {"sub/weights.bin": b"payload"})

    commitment = compute_weight_commitment(tmp_path)

    assert commitment.files == [
        ("sub/weights.bin", sha256(b"payload").hexdigest(), len(b"payload")),
    ]


def test_mlmodel_excluded(tmp_path: Path) -> None:
    _write_files(tmp_path, {"weights.bin": b"payload", "MLmodel": b"first"})
    first = compute_weight_commitment(tmp_path)

    (tmp_path / "MLmodel").write_bytes(b"second")
    second = compute_weight_commitment(tmp_path)

    assert first.root == second.root
    assert "MLmodel" in first.excluded


def test_metadata_dir_excluded(tmp_path: Path) -> None:
    _write_files(
        tmp_path,
        {
            "weights.bin": b"payload",
            "metadata/registered_model_meta": b"first",
        },
    )
    first = compute_weight_commitment(tmp_path)

    (tmp_path / "metadata/registered_model_meta").write_bytes(b"second")
    second = compute_weight_commitment(tmp_path)

    assert first.root == second.root
    assert "metadata/registered_model_meta" in first.excluded


def test_directory_only_excluded_files_raises(tmp_path: Path) -> None:
    _write_files(tmp_path, {"MLmodel": b"payload"})

    with pytest.raises(ValueError, match="no files to commit"):
        compute_weight_commitment(tmp_path)


def test_nonexistent_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_weight_commitment(tmp_path / "missing")


def test_file_not_directory_raises(tmp_path: Path) -> None:
    path = tmp_path / "weights.bin"
    path.write_bytes(b"payload")

    with pytest.raises(NotADirectoryError):
        compute_weight_commitment(path)


def test_empty_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files to commit"):
        compute_weight_commitment(tmp_path)


def test_symlink_skipped(tmp_path: Path) -> None:
    target = tmp_path / "weights.bin"
    target.write_bytes(b"payload")
    symlink = tmp_path / "weights-link.bin"
    symlink.symlink_to(target)

    commitment = compute_weight_commitment(tmp_path)

    assert "weights-link.bin" in commitment.excluded
    assert [entry[0] for entry in commitment.files] == ["weights.bin"]


def test_files_field_sorted_posix(tmp_path: Path) -> None:
    _write_files(
        tmp_path,
        {
            "z.bin": b"z",
            "a/a.bin": b"a",
            "m.bin": b"m",
        },
    )

    commitment = compute_weight_commitment(tmp_path)

    assert [entry[0] for entry in commitment.files] == ["a/a.bin", "m.bin", "z.bin"]
