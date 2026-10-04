# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._license_detect`: which root-level
license file is picked when names differ only in case, the size cap on a
detection input, and the directory adapter against the bytes core it feeds.

See also: tests/assemble/test_license_detection.py and
tests/assemble/test_license_edge_cases.py (the detection suite).
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path
from typing import IO, Any
from unittest.mock import patch

import pytest

from pitloom.extract._license_detect import (
    LICENSE_FILE_MAX_BYTES,
    collect_license_candidates,
    find_license_files,
    license_candidates_from_members,
    pick_license_names,
)


def _case_sensitive(directory: Path) -> bool:
    """Whether *directory* can hold two names differing only in case."""
    probe = directory / "case-probe"
    probe.mkdir()
    (probe / "a").write_bytes(b"")
    (probe / "A").write_bytes(b"")
    return len(list(probe.iterdir())) == 2


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["License", "LICENSE"], ["LICENSE"]),  # exact case wins
        (["license", "License"], ["License"]),  # else first in str order
        (["LICENSE.TXT", "LICENSE.txt"], ["LICENSE.txt"]),  # not str order
        (
            ["COPYING", "license.TXT", "License.txt", "LICENSE", "README"],
            ["LICENSE", "License.txt", "COPYING"],
        ),
        (["README", "NOTICE"], []),
    ],
)
def test_pick_license_names_ignores_listing_order(
    names: list[str], expected: list[str]
) -> None:
    for order in itertools.permutations(names):
        assert pick_license_names(order) == expected


@pytest.mark.parametrize("reverse", [False, True])
def test_find_license_files_ignores_iterdir_order(
    tmp_path: Path, reverse: bool
) -> None:
    """``LICENSE`` and ``License`` side by side: the listing order the file
    system gives never decides (faked here, so it runs on any platform)."""
    listing = [tmp_path / "License", tmp_path / "LICENSE"]
    if reverse:
        listing.reverse()
    with (
        patch.object(Path, "iterdir", return_value=iter(listing)),
        patch.object(Path, "is_file", return_value=True),
    ):
        found = find_license_files(tmp_path)
    # Names, not Paths: WindowsPath compares case-insensitively.
    assert [p.name for p in found] == ["LICENSE"]


def test_find_license_files_on_a_case_sensitive_directory(tmp_path: Path) -> None:
    if not _case_sensitive(tmp_path):
        pytest.skip("file system cannot hold LICENSE and License side by side")
    (tmp_path / "License").write_text("other", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "license").write_text("other", encoding="utf-8")
    assert [p.name for p in find_license_files(tmp_path)] == ["LICENSE"]


def test_directory_adapter_matches_the_bytes_core(tmp_path: Path) -> None:
    """Drift guard: a directory and the same files as ``{name: bytes}``
    give identical candidates (CRLF and non-UTF-8 text included)."""
    files = {
        "CITATION.cff": b"cff-version: 1.2.0\r\nlicense: MIT\r\n",
        "codemeta.json": b'\xef\xbb\xbf{"license": "Apache-2.0"}',  # BOM
        "LICENSE": b"MIT License\r\nCopyright \xff 2026\rline\n",
        "LICENCE.txt": b" \n\t",  # whitespace only: no candidate
        "COPYING": b"",  # empty: no candidate
        "COPYRIGHT.md": b"Copyright 2026",
        "README.md": b"# not a license",
    }
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)

    from_dir = collect_license_candidates(tmp_path)

    assert from_dir == license_candidates_from_members(files)
    assert from_dir == [
        ("MIT", "Source: CITATION.cff | Field: license"),
        ("Apache-2.0", "Source: codemeta.json | Field: license"),
        ("MIT License\nCopyright \ufffd 2026\nline\n", "Source: LICENSE"),
        ("Copyright 2026", "Source: COPYRIGHT.md"),
    ]


@pytest.mark.parametrize("codemeta", [b"[]", b'"MIT"', b"3", b"null"])
def test_a_codemeta_json_that_is_not_an_object_states_nothing(
    tmp_path: Path, codemeta: bytes
) -> None:
    """Regression: a JSON array crashed detection (``list.get``)."""
    files = {"codemeta.json": codemeta, "LICENSE": b"MIT\n"}
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    expected = [("MIT\n", "Source: LICENSE")]
    assert collect_license_candidates(tmp_path) == expected
    assert license_candidates_from_members(files) == expected


def test_symlinked_license_is_followed_and_dangling_one_skipped(
    tmp_path: Path,
) -> None:
    """The directory side follows a symlinked license file, as a plain read
    does; a dangling one is no file and no candidate."""
    target = tmp_path / "elsewhere.txt"
    target.write_text("MIT License", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    try:
        (project / "LICENSE").symlink_to(target)
        (project / "COPYING").symlink_to(tmp_path / "missing")
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"cannot create a symlink: {exc}")

    assert collect_license_candidates(project) == [("MIT License", "Source: LICENSE")]


class _ReadSpy:
    """A file handle recording the size of every ``read()``."""

    def __init__(self, fh: IO[bytes], sizes: list[int]) -> None:
        self._fh = fh
        self._sizes = sizes

    def __enter__(self) -> _ReadSpy:
        return self

    def __exit__(self, *exc: object) -> None:
        self._fh.close()

    def read(self, size: int = -1) -> bytes:
        self._sizes.append(size)
        return self._fh.read(size)


@pytest.mark.parametrize(
    ("name", "head", "candidate"),
    [
        ("LICENSE", b"MIT License\n", None),
        (
            "CITATION.cff",
            b"license: MIT\n",
            ("MIT", "Source: CITATION.cff | Field: license"),
        ),
    ],
    ids=["license", "citation-cff"],
)
@pytest.mark.parametrize("over", [0, 1], ids=["at-cap", "cap+1"])
def test_detection_input_over_cap_is_skipped_with_one_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
    head: bytes,
    candidate: tuple[str, str] | None,
    over: int,
) -> None:
    """Over the cap, a detection input is skipped with one ``WARNING:``
    naming it (not one per read), read no further than one byte past the
    cap; the next license file is still used. Exactly at the cap is
    read."""
    assert LICENSE_FILE_MAX_BYTES == 256 * 1024
    raw = head + b"#" * (LICENSE_FILE_MAX_BYTES + over - len(head))
    (tmp_path / name).write_bytes(raw)
    (tmp_path / "COPYING").write_text("GPL", encoding="utf-8")
    sizes: list[int] = []
    real_open = Path.open

    def spy_open(path: Path, *args: Any, **kwargs: Any) -> _ReadSpy:
        return _ReadSpy(real_open(path, *args, **kwargs), sizes)

    with (
        caplog.at_level(logging.WARNING),
        patch.object(Path, "open", autospec=True, side_effect=spy_open),
    ):
        found = collect_license_candidates(tmp_path)
        # One run reads a project more than once: still one WARNING:.
        assert collect_license_candidates(tmp_path) == found

    assert sizes and all(0 <= size <= LICENSE_FILE_MAX_BYTES + 1 for size in sizes)
    kept = candidate or (raw.decode(), f"Source: {name}")
    assert found == ([] if over else [kept]) + [("GPL", "Source: COPYING")]
    warnings = [r.getMessage() for r in caplog.records]
    if not over:
        assert not warnings
        return
    assert len(warnings) == 1
    assert f"FILE={tmp_path / name}:" in warnings[0]
    assert f"larger than the {LICENSE_FILE_MAX_BYTES}-byte" in warnings[0]
