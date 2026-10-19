# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.dataset_hash`: a file's SHA-256, a
directory's path-aware Merkle root, the ceiling and every failure.

See also: tests/core/test_file_hash.py (the reader),
tests/core/test_loom_dataset.py (the elements loom builds from these).
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pytest

from pitloom.core import dataset_hash, walk_rules
from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.core.file_hash import sha256_digest_and_size
from pitloom.core.models import merkle_root
from tests._symlink import CAN_SYMLINK
from tests._unreadable import POSIX_NON_ROOT, deny, unlistable

_BIG = 1 << 40
_NEEDS_SYMLINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlinks")
_NEEDS_POSIX_PERMISSIONS = pytest.mark.skipif(
    not POSIX_NON_ROOT, reason="needs POSIX permissions, non-root"
)


def _leaf(relpath: bytes, content: bytes) -> bytes:
    return hashlib.sha256(relpath + b"\x00" + hashlib.sha256(content).digest()).digest()


def _tree(root: Path, files: dict[str, bytes]) -> Path:
    for relpath, content in files.items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_bytes(content)
    return root


def _root_of(files: dict[str, bytes]) -> str:
    """The expected root: leaves sorted by path bytes, then the shared tree."""
    return merkle_root([_leaf(p.encode(), c) for p, c in sorted(files.items())])


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize("sha512", [False, True], ids=["sha256", "both"])
def test_regular_file_is_its_own_sha256(tmp_path: Path, sha512: bool) -> None:
    """Asked for it (the SBOM describes the file), the SHA-512 of the same
    read too; the lookup key, the SHA-256, is the same either way."""
    path = _tree(tmp_path, {"t.txt": b"hello\n"}) / "t.txt"
    assert hash_dataset(path, max_bytes=_BIG, sha512=sha512) == DatasetDigest(
        "file",
        hashlib.sha256(b"hello\n").hexdigest(),
        1,
        hex_sha512=hashlib.sha512(b"hello\n").hexdigest() if sha512 else None,
    )


@pytest.mark.parametrize(
    ("files", "max_bytes"),
    [({"t.txt": b"hello\n"}, _BIG), ({}, 1)],
    ids=["directory", "over-ceiling"],
)
def test_no_sha512_without_a_file_digest(
    tmp_path: Path, files: dict[str, bytes], max_bytes: int
) -> None:
    """A Merkle root is SHA-256 only, and a file over the ceiling has no
    digest at all: asking for a SHA-512 invents none."""
    target = _tree(tmp_path, files) if files else tmp_path / "big.bin"
    if not files:
        target.write_bytes(b"too big")
    found = hash_dataset(target, max_bytes=max_bytes, sha512=True)
    assert found.kind == ("dir" if files else "file")
    assert (found.hex_digest is None) is (not files)
    assert found.hex_sha512 is None


@pytest.mark.parametrize(
    "name", ["missing.txt", "imdb", "a\x00b"], ids=["missing", "remote", "nul"]
)
def test_absent_or_not_a_path_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    """A remote name, a missing path or a NUL: nothing, and no warning."""
    with caplog.at_level(logging.DEBUG):
        assert hash_dataset(tmp_path / name, max_bytes=_BIG) == DatasetDigest(None)
    assert not caplog.records


def test_empty_directory_has_no_root_silently(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "sub").mkdir()  # directories alone are no data
    with caplog.at_level(logging.DEBUG):
        assert hash_dataset(tmp_path, max_bytes=_BIG) == DatasetDigest("dir")
    assert not caplog.records


def test_one_file_directory_root_is_not_the_file_hash(tmp_path: Path) -> None:
    """The leaf holds the path, so a directory never hash-merges with a
    single-file dataset of the same bytes."""
    found = hash_dataset(_tree(tmp_path, {"t.txt": b"hello\n"}), max_bytes=_BIG)
    assert found == DatasetDigest("dir", _leaf(b"t.txt", b"hello\n").hex(), 1)
    assert found.hex_digest != hashlib.sha256(b"hello\n").hexdigest()


def test_root_sorts_leaves_by_path_bytes_and_prunes_ignored_names(
    tmp_path: Path,
) -> None:
    """``os.walk`` gives top-level files before subdirectories, so ``z.txt``
    comes before ``a/b.txt`` unsorted; a ``build/`` below is pruned, the
    dataset's own ancestors are never matched."""
    files = {"z.txt": b"z", "a/b.txt": b"b", "a/c d.txt": b"c"}
    top = _tree(tmp_path / "build" / "data", files)
    _tree(top, {"build/skip.txt": b"x", "a/.git/HEAD": b"x"})
    found = hash_dataset(top, max_bytes=_BIG)
    assert found == DatasetDigest("dir", _root_of(files), 3)


def test_renamed_file_changes_the_root(tmp_path: Path) -> None:
    top = _tree(tmp_path, {"a.txt": b"same", "b.txt": b"other"})
    before = hash_dataset(top, max_bytes=_BIG).hex_digest
    (top / "a.txt").rename(top / "c.txt")
    assert sorted(p.name for p in top.iterdir()) == ["b.txt", "c.txt"]
    after = hash_dataset(top, max_bytes=_BIG).hex_digest
    assert before is not None and after is not None
    assert after != before


def test_excluded_registry_is_left_out(tmp_path: Path) -> None:
    files = {"t.txt": b"t"}
    top = _tree(tmp_path, {**files, "sub/ids.json": b"{}"})
    found = hash_dataset(top, max_bytes=_BIG, exclude=top / "sub" / "ids.json")
    assert found == DatasetDigest("dir", _root_of(files), 1, excluded=True)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_fifo_is_skipped_without_blocking(tmp_path: Path) -> None:
    files = {"t.txt": b"t"}
    top = _tree(tmp_path, files)
    os.mkfifo(top / "pipe")  # pylint: disable=no-member
    assert hash_dataset(top, max_bytes=_BIG).hex_digest == _root_of(files)


@_NEEDS_SYMLINK
def test_symlinks_dangling_looping_or_to_directories_end(tmp_path: Path) -> None:
    """A dangling link, a self-loop and a link back up the tree end the
    walk; a link to a file is hashed under the link's own path."""
    files = {"t.txt": b"t"}
    top = _tree(tmp_path / "data", files)
    (top / "dangling").symlink_to(tmp_path / "nowhere")
    (top / "self").symlink_to(top / "self")
    (top / "up").symlink_to(top, target_is_directory=True)
    (top / "alias.txt").symlink_to(top / "t.txt")
    expected = _root_of({**files, "alias.txt": b"t"})
    assert hash_dataset(top, max_bytes=_BIG).hex_digest == expected


def _no_read(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("nothing over the ceiling is opened")


@pytest.mark.parametrize("kind", ["file", "dir"])
@pytest.mark.parametrize("over", [0, 1], ids=["exact", "one-over"])
def test_ceiling_counts_total_bytes_from_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: str,
    over: int,
) -> None:
    """``max_bytes == total`` hashes; one byte more is one ``WARNING:`` and
    no hash, with nothing opened."""
    top = _tree(tmp_path / "d", {"a.txt": b"12345", "b/c.txt": b"678"})
    path, total = (top, 8) if kind == "dir" else (top / "a.txt", 5)
    if over:
        monkeypatch.setattr(dataset_hash, "sha256_digest_and_size", _no_read)
    with caplog.at_level(logging.WARNING):
        found = hash_dataset(path, max_bytes=total - over)
    assert (found.hex_digest is None) is bool(over)
    expected = [
        f"{kind.upper()}={path}: larger than the {total - 1}-byte "
        "max-dataset-hash-bytes cap; dataset hash omitted"
    ]
    assert _warnings(caplog) == (expected if over else [])


@pytest.mark.parametrize(
    ("kind", "files", "max_bytes"),
    [
        ("file", {"a.txt": b"1234"}, 4),
        ("dir", {"a.txt": b"1234"}, 4),
        ("dir", {"a.txt": b"1234", "b.txt": b"1234"}, 8),
    ],
    ids=["file", "dir", "dir-later-file"],
)
def test_file_growing_during_the_read_is_over_the_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: str,
    files: dict[str, bytes],
    max_bytes: int,
) -> None:
    """A file growing after its ``stat()``: the read's own budget catches
    it, the budget left for a later file shrinking by what earlier ones
    read (``a.txt`` grew; ``b.txt`` alone is within the size checked)."""
    top = _tree(tmp_path / "d", files)
    path = top if kind == "dir" else top / "a.txt"
    real = sha256_digest_and_size

    def _grow_then_read(member: str, **kwargs: Any) -> tuple[bytes, int]:
        if os.path.basename(member) == "a.txt":
            with open(member, "ab") as grown:
                grown.write(b"5")
        return real(member, **kwargs)

    monkeypatch.setattr(dataset_hash, "sha256_digest_and_size", _grow_then_read)
    with caplog.at_level(logging.WARNING):
        assert hash_dataset(path, max_bytes=max_bytes).hex_digest is None
    (warning,) = _warnings(caplog)
    assert f"{max_bytes}-byte max-dataset-hash-bytes cap" in warning


def test_excluded_file_is_resolved_once_not_per_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The *exclude* file is resolved once per walk, never once per
    member: a large dataset pays one ``stat()`` per file, not four."""
    files = {f"f{n}.bin": b"x" for n in range(5)}
    top = _tree(tmp_path, {**files, "ids.json": b"{}"})
    calls: list[object] = []

    def counting_realpath(path: str | os.PathLike[str]) -> str:
        calls.append(path)
        return os.path.realpath(path)

    fake_path = SimpleNamespace(realpath=counting_realpath, basename=os.path.basename)
    fake_os = SimpleNamespace(path=fake_path, stat=os.stat)
    monkeypatch.setattr(walk_rules, "os", fake_os)
    found = hash_dataset(
        top, max_bytes=_BIG, exclude=top / ".." / top.name / "ids.json"
    )
    assert found == DatasetDigest("dir", _root_of(files), 5, excluded=True)
    assert len(calls) <= 2


def test_member_removed_after_listing_warns_and_gives_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A member gone between the walk and its read: the ``FILE=`` warning
    and no root (one gone before its ``stat()`` is skipped silently, as a
    dangling symlink is)."""
    top = _tree(tmp_path / "d", {"a.txt": b"a", "b.txt": b"b"})
    real_listed = dataset_hash._listed  # pylint: disable=protected-access

    def _list_then_remove(*args: Any) -> Any:
        listed = real_listed(*args)
        (top / "b.txt").unlink()
        return listed

    monkeypatch.setattr(dataset_hash, "_listed", _list_then_remove)
    with caplog.at_level(logging.WARNING):
        assert hash_dataset(top, max_bytes=_BIG) == DatasetDigest("dir")
    (warning,) = _warnings(caplog)
    assert warning.startswith(f"FILE={top / 'b.txt'}: could not read for dataset")


def test_file_gone_after_it_was_found_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = _tree(tmp_path, {"t.txt": b"t"}) / "t.txt"

    def _gone(_path: object) -> int:
        raise FileNotFoundError(errno.ENOENT, "gone", str(path))

    monkeypatch.setattr(dataset_hash, "_file_size", _gone)
    with caplog.at_level(logging.WARNING):
        assert hash_dataset(path, max_bytes=_BIG) == DatasetDigest(None)
    assert not caplog.records


def _denied_read(target: Path) -> Callable[..., tuple[bytes, int]]:
    real = sha256_digest_and_size

    def _read(path: str, **kwargs: Any) -> tuple[bytes, int]:
        if os.path.abspath(path) == os.path.abspath(target):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real(path, **kwargs)

    return _read


@pytest.mark.parametrize("case", ["only-registry", "over-cap", "unreadable", "stat"])
def test_excluded_registry_is_reported_without_a_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """The *exclude* file met by the walk is reported whether or not a root
    comes of it: no other file, the cap, a file that cannot be read or
    ``stat()``-ed after it (below it: ``os.walk`` lists the top first)."""
    files = {} if case == "only-registry" else {"sub/t.txt": b"12345"}
    top = _tree(tmp_path, {**files, "ids.json": b"{}"})
    other = top / "sub" / "t.txt"
    if case == "unreadable":
        monkeypatch.setattr(dataset_hash, "sha256_digest_and_size", _denied_read(other))
    with deny(other, "stat", monkeypatch) if case == "stat" else nullcontext():
        found = hash_dataset(
            top, max_bytes=1 if case == "over-cap" else _BIG, exclude=top / "ids.json"
        )
    assert found == DatasetDigest("dir", excluded=True)


@pytest.mark.parametrize(
    ("dataset", "kind"),
    [("d/sub/x.txt", "file"), ("d", "dir")],
    ids=["file", "dir-member"],
)
@pytest.mark.parametrize("mode", ["open", "stat"])
def test_unreadable_file_warns_and_gives_no_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    dataset: str,
    kind: Literal["file", "dir"],
    mode: str,
) -> None:
    """One unreadable file: the shared ``FILE=`` warning and no hash at
    all -- a root over the other files would be wrong."""
    member = _tree(tmp_path / "d", {"a.txt": b"a", "sub/x.txt": b"x"}) / "sub" / "x.txt"
    if mode == "open":
        monkeypatch.setattr(
            dataset_hash, "sha256_digest_and_size", _denied_read(member)
        )
    with caplog.at_level(logging.WARNING), deny(member, mode, monkeypatch):
        found = hash_dataset(tmp_path / dataset, max_bytes=_BIG)
    stat_failed_on_the_dataset = mode == "stat" and kind == "file"
    assert found == DatasetDigest(None if stat_failed_on_the_dataset else kind)
    (warning,) = _warnings(caplog)
    assert warning.startswith(f"FILE={member}: could not read for dataset hashing;")


@_NEEDS_POSIX_PERMISSIONS
def test_real_unreadable_member_and_unlistable_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The real POSIX permission bits: a ``chmod 000`` member, then a
    ``chmod 000`` subdirectory -- each one warning and no root."""
    top = _tree(tmp_path / "d", {"a.txt": b"a", "sub/x.txt": b"x"})
    with (
        caplog.at_level(logging.WARNING),
        deny(top / "a.txt", "chmod-file", monkeypatch),
    ):
        assert hash_dataset(top, max_bytes=_BIG) == DatasetDigest("dir")
    with caplog.at_level(logging.WARNING), unlistable(top / "sub"):
        assert hash_dataset(top, max_bytes=_BIG) == DatasetDigest("dir")
    first, second = _warnings(caplog)
    assert first.startswith(f"FILE={top / 'a.txt'}: could not read for dataset")
    assert second.startswith(f"DIR={top / 'sub'}: could not list for dataset")


@pytest.mark.parametrize(
    ("relpath", "expected"),
    [
        ("a/é.txt", "a/é.txt".encode()),
        ("\udcff.txt", b"\xff.txt"),  # an undecodable POSIX name's own byte
        ("\ud800.txt", b"\xed\xa0\x80.txt"),  # a Windows lone surrogate
    ],
    ids=["utf-8", "posix-undecodable", "windows-lone-surrogate"],
)
def test_leaf_name_bytes(relpath: str, expected: bytes) -> None:
    # pylint: disable-next=protected-access
    assert dataset_hash._leaf_name(relpath) == expected
