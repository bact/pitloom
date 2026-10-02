# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Archive member name normalisation
(:mod:`pitloom.core.archive_member_names`).

See also: tests/extract/test_wheel_member_names.py (``read_wheel`` and the
SBOM), tests/extract/project/test_sdist_member_names.py (sdist archives),
tests/test_archive_member_name_surfaces.py (every wheel and sdist surface).
"""

from __future__ import annotations

import logging
import warnings
import zipfile
from pathlib import Path

import pytest

from pitloom.core.archive_member_names import (
    MemberName,
    archive_members,
    is_directory_name,
    normalize_member_name,
    zip_file_members,
)
from tests._raw_archive import write_raw_member

_LOG = logging.getLogger("test.archive_member_names")
_P = "P: ARCHIVE='a.zip' ENTRY="


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pkg/mod.py", MemberName("pkg/mod.py", "ok")),
        ("mod.py", MemberName("mod.py", "ok")),
        ("pkg\\mod.py", MemberName("pkg/mod.py", "normalized")),
        ("./pkg/mod.py", MemberName("pkg/mod.py", "normalized")),
        ("././pkg/mod.py", MemberName("pkg/mod.py", "normalized")),
        (".\\pkg\\mod.py", MemberName("pkg/mod.py", "normalized")),
        ("pkg//mod.py", MemberName("pkg/mod.py", "normalized")),
        ("pkg/./mod.py", MemberName("pkg/mod.py", "normalized")),
        ("pkg/...py", MemberName("pkg/...py", "ok")),
        ("pkg/..a/b", MemberName("pkg/..a/b", "ok")),
        ("../evil.py", MemberName("../evil.py", "unsafe")),
        ("pkg/../evil.py", MemberName("pkg/../evil.py", "unsafe")),
        ("pkg/..", MemberName("pkg/..", "unsafe")),
        ("..\\evil.py", MemberName("../evil.py", "unsafe")),
        ("/etc/evil", MemberName("/etc/evil", "unsafe")),
        ("C:/evil.py", MemberName("C:/evil.py", "unsafe")),
        ("C:\\evil.py", MemberName("C:/evil.py", "unsafe")),
        ("./C:/evil.py", MemberName("./C:/evil.py", "unsafe")),
        (".\\C:\\evil.py", MemberName("./C:/evil.py", "unsafe")),
        ("pkg/c:x.py", MemberName("pkg/c:x.py", "ok")),
        ("c:evil.py", MemberName("c:evil.py", "unsafe")),
        ("a:b.py", MemberName("a:b.py", "unsafe")),
        ("\\\\host\\share\\x", MemberName("//host/share/x", "unsafe")),
        ("pkg/mod.py\0.txt", MemberName("pkg/mod.py\0.txt", "unsafe")),
        (".", MemberName(".", "unsafe")),
        ("", MemberName("", "unsafe")),
    ],
)
def test_normalize_member_name(raw: str, expected: MemberName) -> None:
    """One case per boundary: conforming, each non-conforming shape, each
    shape with no install location (never rewritten into a legal path)."""
    assert normalize_member_name(raw) == expected


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
def test_is_directory_name(raw: str, is_dir: bool) -> None:
    """``pkg\\`` is a directory on every OS and in every archive kind."""
    assert is_directory_name(raw) is is_dir


@pytest.mark.parametrize(
    ("raws", "names", "messages"),
    [
        (["pkg/mod.py"], ["pkg/mod.py"], []),
        (
            ["pkg\\mod.py"],
            ["pkg/mod.py"],
            [_P + "'pkg\\\\mod.py': non-conforming name -- recorded as 'pkg/mod.py'"],
        ),
        (
            ["../evil.py", "pkg/a"],
            ["pkg/a"],
            [_P + "'../evil.py': no safe install location -- skipped"],
        ),
        (
            ["pkg/a", "./pkg/a", "pkg\\a"],
            ["pkg/a"],
            [
                _P + "'pkg/a': overwritten by later entry 'pkg\\\\a' -- skipped",
                _P + "'./pkg/a': overwritten by later entry 'pkg\\\\a' -- skipped",
                _P + "'pkg\\\\a': non-conforming name -- recorded as 'pkg/a'",
            ],
        ),
        (
            ["pkg/a", "pkg/a"],
            ["pkg/a"],
            [_P + "'pkg/a': overwritten by later entry 'pkg/a' -- skipped"],
        ),
        (
            ["pkg", "pkg/sub/mod.py", "pkg/sub"],
            ["pkg/sub/mod.py"],
            [
                _P + "'pkg': also a directory of other entries -- skipped",
                _P + "'pkg/sub': also a directory of other entries -- skipped",
            ],
        ),
        (["pkg", "pkgx/mod.py"], ["pkg", "pkgx/mod.py"], []),
    ],
)
def test_archive_members_warns_once_per_member(
    caplog: pytest.LogCaptureFixture,
    raws: list[str],
    names: list[str],
    messages: list[str],
) -> None:
    """Exactly one ``WARNING:`` per non-conforming, unsafe, overwritten or
    directory-shadowed member, quoting the raw name; none for a conforming
    one. Of members sharing one install location, the last one in the
    archive (the one an installer leaves behind) is kept."""
    with caplog.at_level(logging.WARNING):
        members = archive_members(
            [(raw, index) for index, raw in enumerate(raws)], "a.zip", _LOG, "P: "
        )
    assert [name for name, _ in members] == names
    for name, index in members:
        assert index == max(
            i for i, raw in enumerate(raws) if normalize_member_name(raw).name == name
        )
    assert [r.getMessage() for r in caplog.records] == messages


@pytest.mark.parametrize(
    ("raw", "warned"),
    [
        ("./pkg/a", False),
        ("././pkg/a", True),
        (".//pkg/a", True),
        (".\\pkg/a", True),
        ("pkg\\a", True),
    ],
)
def test_archive_members_dot_prefix_ok(
    caplog: pytest.LogCaptureFixture, raw: str, warned: bool
) -> None:
    """With *dot_prefix_ok* (tar), exactly one leading ``./`` is conforming;
    anything else non-conforming still warns."""
    with caplog.at_level(logging.WARNING):
        members = archive_members([(raw, 0)], "a.tar", _LOG, dot_prefix_ok=True)
    assert members == [("pkg/a", 0)]
    assert len(caplog.records) == int(warned)


def test_archive_members_without_logger_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``logger=None`` normalises the same way and logs nothing."""
    with caplog.at_level(logging.WARNING):
        members = archive_members([("./a", 0), ("../b", 1)], "a.zip", None)
    assert members == [("a", 0)]
    assert not caplog.records


def test_archive_members_on_duplicate_refuses_before_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With *on_duplicate*, the first member a later one repeats (by its raw
    name) is handed over and its exception raised; nothing is logged first,
    not even for the non-conforming member that precedes it. Without a
    duplicate, it changes nothing."""
    seen: list[str] = []

    def refuse(raw: str) -> Exception:
        seen.append(raw)
        return LookupError(raw)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(LookupError):
            archive_members(
                [("./x", 0), ("pkg/a", 1), ("pkg\\a", 2)],
                "a.zip",
                _LOG,
                on_duplicate=refuse,
            )
        assert seen == ["pkg/a"] and not caplog.records
        kept = archive_members(
            [("./x", 0), ("pkg/a", 1)], "a.zip", _LOG, on_duplicate=refuse
        )
    assert kept == [("x", 0), ("pkg/a", 1)] and len(caplog.records) == 1


def _zip(tmp_path: Path, raws: list[tuple[str, bytes]]) -> Path:
    path = tmp_path / "a.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # zipfile: duplicate name
        with zipfile.ZipFile(path, "w") as zf:
            for raw, data in raws:
                write_raw_member(zf, raw, data)
    return path


def test_zip_file_members_keeps_last_and_reads_its_bytes(tmp_path: Path) -> None:
    """The kept ``ZipInfo`` is the later member's, so hashing it reads the
    bytes an installer leaves behind."""
    path = _zip(tmp_path, [("pkg/a", b"first"), ("pkg\\a", b"second")])
    with zipfile.ZipFile(path) as zf:
        ((name, info),) = zip_file_members(zf, "a.zip", _LOG)
        assert (name, zf.read(info)) == ("pkg/a", b"second")


@pytest.mark.parametrize(
    ("data", "logger", "warned"),
    [(b"", _LOG, False), (b"x", _LOG, True), (b"x", None, False)],
)
def test_zip_file_members_directory_entries(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    data: bytes,
    logger: logging.Logger | None,
    warned: bool,
) -> None:
    """A directory entry is skipped; one carrying data warns, since its
    bytes are dropped -- unless no logger is given."""
    path = _zip(tmp_path, [("pkg\\", data), ("pkg/a", b"")])
    with zipfile.ZipFile(path) as zf, caplog.at_level(logging.WARNING):
        members = zip_file_members(zf, "a.zip", logger, "P: ")
    assert [name for name, _ in members] == ["pkg/a"]
    expected = [_P + "'pkg\\\\': directory entry carries data -- skipped"]
    assert [r.getMessage() for r in caplog.records] == (expected if warned else [])


def test_zip_file_members_ignores_os_converted_filename(tmp_path: Path) -> None:
    """Names come from ``orig_filename``, never the OS-dependent
    ``filename``."""
    path = _zip(tmp_path, [("pkg/mod.py", b"")])
    with zipfile.ZipFile(path) as zf:
        zf.filelist[0].filename = "decoy/from-filename.py"
        members = zip_file_members(zf, "a.zip", _LOG)
    assert [name for name, _ in members] == ["pkg/mod.py"]
