# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Wheel member name normalisation (:mod:`pitloom.core.wheel_member_names`).

See also: tests/extract/test_wheel_member_names.py (``read_wheel`` and the
SBOM), tests/test_wheel_member_name_surfaces.py (every wheel surface).
"""

from __future__ import annotations

import logging
import warnings
import zipfile
from pathlib import Path

import pytest

from pitloom.core.wheel_member_names import (
    WheelMemberName,
    is_directory_member,
    normalize_wheel_member_name,
    wheel_file_members,
)
from tests._raw_wheel import write_raw_member


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pkg/mod.py", WheelMemberName("pkg/mod.py", "ok")),
        ("mod.py", WheelMemberName("mod.py", "ok")),
        ("pkg\\mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        ("./pkg/mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        ("././pkg/mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        (".\\pkg\\mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        ("pkg//mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        ("pkg/./mod.py", WheelMemberName("pkg/mod.py", "normalized")),
        ("pkg/...py", WheelMemberName("pkg/...py", "ok")),
        ("pkg/..a/b", WheelMemberName("pkg/..a/b", "ok")),
        ("../evil.py", WheelMemberName("../evil.py", "unsafe")),
        ("pkg/../evil.py", WheelMemberName("pkg/../evil.py", "unsafe")),
        ("pkg/..", WheelMemberName("pkg/..", "unsafe")),
        ("..\\evil.py", WheelMemberName("../evil.py", "unsafe")),
        ("/etc/evil", WheelMemberName("/etc/evil", "unsafe")),
        ("C:/evil.py", WheelMemberName("C:/evil.py", "unsafe")),
        ("C:\\evil.py", WheelMemberName("C:/evil.py", "unsafe")),
        ("./C:/evil.py", WheelMemberName("./C:/evil.py", "unsafe")),
        (".\\C:\\evil.py", WheelMemberName("./C:/evil.py", "unsafe")),
        ("pkg/c:x.py", WheelMemberName("pkg/c:x.py", "ok")),
        ("c:evil.py", WheelMemberName("c:evil.py", "unsafe")),
        ("\\\\host\\share\\x", WheelMemberName("//host/share/x", "unsafe")),
        ("pkg/mod.py\0.txt", WheelMemberName("pkg/mod.py\0.txt", "unsafe")),
        (".", WheelMemberName(".", "unsafe")),
        ("", WheelMemberName("", "unsafe")),
    ],
)
def test_normalize_wheel_member_name(raw: str, expected: WheelMemberName) -> None:
    """One case per boundary: conforming, each non-conforming shape, each
    shape with no install location (never rewritten into a legal path)."""
    assert normalize_wheel_member_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "is_dir"),
    [
        ("pkg/", True),
        ("pkg\\", True),
        ("pkg/.", True),
        ("pkg\\.", True),
        (".", True),
        ("pkg", False),
        ("pkg/x", False),
        ("pkg/.x", False),
    ],
)
def test_is_directory_member_reads_raw_name(raw: str, is_dir: bool) -> None:
    """``pkg\\`` is a directory on every OS, not only where ``os.sep`` is
    a backslash."""
    info = zipfile.ZipInfo("placeholder")
    info.orig_filename = raw
    info.filename = "unused"
    assert is_directory_member(info) is is_dir


_P = "P: w.whl: wheel entry "


@pytest.mark.parametrize(
    ("raws", "names", "messages"),
    [
        (["pkg/mod.py"], ["pkg/mod.py"], []),
        (
            ["pkg\\mod.py"],
            ["pkg/mod.py"],
            [_P + "'pkg\\\\mod.py' is non-conforming -- recorded as 'pkg/mod.py'"],
        ),
        (
            ["../evil.py", "pkg/a"],
            ["pkg/a"],
            [_P + "'../evil.py' has no safe install location -- skipped"],
        ),
        (
            ["pkg/", "pkg/."],
            [],
            [],
        ),
        (
            ["pkg/a", "./pkg/a", "pkg\\a"],
            ["pkg/a"],
            [
                _P + "'pkg/a' is overwritten by later entry 'pkg\\\\a' -- skipped",
                _P + "'./pkg/a' is overwritten by later entry 'pkg\\\\a' -- skipped",
                _P + "'pkg\\\\a' is non-conforming -- recorded as 'pkg/a'",
            ],
        ),
        (
            ["pkg/a", "pkg/a"],
            ["pkg/a"],
            [_P + "'pkg/a' is overwritten by later entry 'pkg/a' -- skipped"],
        ),
    ],
)
def test_wheel_file_members_warns_once_per_member(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    raws: list[str],
    names: list[str],
    messages: list[str],
) -> None:
    """Exactly one ``WARNING:`` per non-conforming, unsafe or overwritten
    member, quoting the raw name; none for a conforming one or a
    directory. Of members sharing one install location, the last one in
    the archive (the one an installer leaves behind) is kept."""
    wheel = tmp_path / "w.whl"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # zipfile: duplicate name
        with zipfile.ZipFile(wheel, "w") as zf:
            for index, raw in enumerate(raws):
                write_raw_member(zf, raw, str(index).encode())
    logger = logging.getLogger("test.wheel_member_names")
    with zipfile.ZipFile(wheel) as zf, caplog.at_level(logging.WARNING):
        members = wheel_file_members(zf, "w.whl", logger, "P: ")
        kept = [(m.name, zf.read(m.info)) for m in members]
    assert [name for name, _ in kept] == names
    if names:
        assert kept[-1][1] == str(len(raws) - 1).encode()
    assert [r.getMessage() for r in caplog.records] == messages


def test_wheel_file_members_ignores_os_converted_filename(tmp_path: Path) -> None:
    """Names come from ``orig_filename``, never the OS-dependent
    ``filename``."""
    wheel = tmp_path / "w.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        write_raw_member(zf, "pkg/mod.py", b"")
    with zipfile.ZipFile(wheel) as zf:
        zf.filelist[0].filename = "decoy/from-filename.py"
        members = wheel_file_members(zf, "w.whl", logging.getLogger("t"))
    assert [m.name for m in members] == ["pkg/mod.py"]
