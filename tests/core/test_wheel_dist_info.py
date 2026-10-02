# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which ``.dist-info`` is a wheel's own, the bounded member read and the
Zstandard error probe.

See also: tests/core/test_wheel_dist_info_names.py (the file name and the
directory name), tests/extract/test_wheel_identity.py (``read_wheel``),
tests/test_wheel_identity_surfaces.py (every surface) and
tests/assemble/test_embed_internals.py (``_find_dist_info_prefix``).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core import wheel_dist_info
from pitloom.core.archive_member_names import normalize_member_name, zip_file_members
from pitloom.core.wheel_dist_info import (
    PROBLEM_NONE,
    PROBLEM_NOT_A_WHEEL_NAME,
    PROBLEM_SEVERAL_MATCH,
    PROBLEM_SEVERAL_NONE_MATCH,
    WheelRefused,
    open_wheel_zip,
    read_metadata_headers,
    refusal,
    resolve_own_dist_info,
    wheel_members,
)
from tests._wheel_damage import (
    WHEEL,
    central_name_damaged_wheel,
    damaged_wheel,
    raw_wheel,
    zip_version_wheel,
)


def _members(*dist_infos: str) -> list[str]:
    return [f"{d}/METADATA" for d in dist_infos] + ["demo/__init__.py"]


@pytest.mark.parametrize(
    ("wheel", "dirs", "prefix", "problem"),
    [
        (WHEEL, ["demo-1.0.dist-info"], "demo-1.0.dist-info/", None),
        # PEP 503 name and PEP 440 version equivalence: not a disagreement.
        (
            "My.Pkg-1.0-py3-none-any.whl",
            ["my_pkg-1.0.0.dist-info"],
            "my_pkg-1.0.0.dist-info/",
            None,
        ),
        # The file name picks among several; the foreign one is ignored.
        (
            WHEEL,
            ["demo-1.0.dist-info", "evil-9.9.dist-info"],
            "demo-1.0.dist-info/",
            None,
        ),
        (
            WHEEL,
            ["evil-9.9.dist-info", "demo-1.0.dist-info"],
            "demo-1.0.dist-info/",
            None,
        ),
        # Not a wheel file name: the only one, silently.
        ("pkg.whl", ["demo-1.0.dist-info"], "demo-1.0.dist-info/", None),
        # A wheel file name that names another directory: the only one, said.
        (WHEEL, ["evil-9.9.dist-info"], "evil-9.9.dist-info/", "names no"),
        # Zero, or several none of which the file name names.
        (WHEEL, [], None, PROBLEM_NONE),
        (WHEEL, ["a-1.dist-info", "b-1.dist-info"], None, PROBLEM_SEVERAL_NONE_MATCH),
        ("pkg.whl", ["a-1.dist-info", "b-1.dist-info"], None, PROBLEM_NOT_A_WHEEL_NAME),
        # Two directories spelling the one name: ambiguous, not "first".
        (
            WHEEL,
            ["demo-1.0.dist-info", "Demo-1.0.dist-info"],
            None,
            PROBLEM_SEVERAL_MATCH,
        ),
        # A name may hold the dash that splits name from version (pip takes it).
        (
            "foo_bar-2.0-py3-none-any.whl",
            ["foo-bar-2.0.dist-info", "x-1.dist-info"],
            "foo-bar-2.0.dist-info/",
            None,
        ),
        # Tags are not read, so what a ``packaging`` release makes of them
        # cannot change the choice.
        *(
            (name, ["demo-1.0.dist-info", "x-1.dist-info"], "demo-1.0.dist-info/", None)
            for name in (
                "demo-1.0-py3-none-.whl",
                "demo-1.0-3x-none-any.whl",
                "demo-1.0-py3..py2-none-any.whl",
            )
        ),
    ],
    ids=[
        "plain",
        "pep503-pep440",
        "foreign-after",
        "foreign-before",
        "renamed-file",
        "disagreement",
        "none",
        "several",
        "renamed-several",
        "same-name-twice",
        "dash-in-name",
        "empty-tag",
        "bad-interpreter",
        "empty-tag-component",
    ],
)
def test_the_own_dist_info_and_what_is_said(
    wheel: str, dirs: list[str], prefix: str | None, problem: str | None
) -> None:
    choice = resolve_own_dist_info(wheel, _members(*dirs))

    assert choice.prefix == prefix
    if problem is None:
        assert choice.problem is None
    else:
        assert choice.problem is not None and problem in choice.problem


@pytest.mark.parametrize(
    "members",
    [
        # Nested, vendored: never the wheel's own, wherever it sorts.
        ["demo/_vendor/evil-9.9.dist-info/METADATA"],
        ["demo/_vendor/demo-1.0.dist-info/METADATA"],
        # A file, not a directory.
        ["demo-1.0.dist-info"],
    ],
)
def test_only_a_top_level_directory_is_the_wheels_own(members: list[str]) -> None:
    assert resolve_own_dist_info(WHEEL, members).prefix is None
    assert resolve_own_dist_info(
        WHEEL, [*members, "demo-1.0.dist-info/METADATA"]
    ).prefix == ("demo-1.0.dist-info/")


def test_the_choice_does_not_depend_on_member_order() -> None:
    names = _members("demo-1.0.dist-info", "evil-9.9.dist-info", "x-1.dist-info")
    assert (
        resolve_own_dist_info(WHEEL, names).prefix
        == resolve_own_dist_info(WHEEL, names[::-1]).prefix
    )


def _stream(data: bytes, chunk: int) -> Any:
    """*data* as a member stream that hands out at most *chunk* bytes."""
    buffer = io.BytesIO(data)
    return SimpleNamespace(read=lambda _size=-1: buffer.read(chunk))


@pytest.mark.parametrize("chunk", [1, 2, 3, 8192])
@pytest.mark.parametrize(
    ("data", "block"),
    [
        (b"A: 1\nB: 2\n\nbody\n", b"A: 1\nB: 2\n"),
        (b"A: 1\r\nB: 2\r\n\r\nbody", b"A: 1\r\nB: 2\r\n"),
        (b"A: 1\rB: 2\r\rbody", b"A: 1\rB: 2\r"),
        (b"A: 1\n\r\nbody", b"A: 1\n"),
        (b"A: 1\nB: 2", b"A: 1\nB: 2"),
        # Whitespace alone is a continuation line, not the end of the headers.
        (b"A: 1\n \nB: 2\n\n", b"A: 1\n \nB: 2\n"),
        (b"", b""),
        (b"\nA: 1\n", b""),
    ],
    ids=["lf", "crlf", "cr", "lf-crlf", "no-blank", "whitespace", "empty", "leading"],
)
def test_the_header_block_ends_at_the_first_blank_line(
    monkeypatch: pytest.MonkeyPatch, data: bytes, block: bytes, chunk: int
) -> None:
    """Whatever the line ends, and wherever a chunk splits a CRLF."""
    monkeypatch.setattr(wheel_dist_info, "_CHUNK_BYTES", chunk)
    assert wheel_dist_info._header_block(_stream(data, chunk)) == block


@pytest.mark.parametrize(
    ("data", "limits", "unit"),
    [
        (b"A: 1\nB: 2\nC: 3\n", {"MAX_METADATA_HEADERS": 3}, None),
        (b"A: 1\nB: 2\nC: 3\nD: 4\n", {"MAX_METADATA_HEADERS": 3}, "headers"),
        # A continuation line is not another header.
        (b"A: 1\n" + b" x\n\t\n" * 50, {"MAX_METADATA_HEADERS": 1}, None),
        # The counted ends are CR too: no ``\n`` to hide behind.
        (b"A: 1\rB: 2\rC: 3\rD: 4\r", {"MAX_METADATA_HEADERS": 3}, "headers"),
        (b"A: 12345\n", {"MAX_METADATA_BYTES": 9}, None),
        (b"A: 123456\n", {"MAX_METADATA_BYTES": 9}, "bytes"),
        # One line without an end: caught while it is still being read.
        (b"x" * 10_000, {"MAX_METADATA_BYTES": 9_999}, "bytes"),
        (b"x" * 9_999, {"MAX_METADATA_BYTES": 9_999}, None),
    ],
    ids=[
        "headers-at-cap",
        "headers-over-cap",
        "continuations-free",
        "headers-cr",
        "bytes-at-cap",
        "bytes-over-cap",
        "long-line-over",
        "long-line-at",
    ],
)
def test_the_header_block_is_capped_in_bytes_and_headers(
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
    limits: dict[str, int],
    unit: str | None,
) -> None:
    for name, value in limits.items():
        monkeypatch.setattr(wheel_dist_info, name, value)
    stream = _stream(data, 8192)

    if unit is None:
        assert wheel_dist_info._header_block(stream)
    else:
        with pytest.raises(wheel_dist_info._OverCap) as over:
            wheel_dist_info._header_block(stream)
        assert over.value.unit == unit


class _Endless(io.RawIOBase):
    """A member of headers, a blank line, then a body that never ends;
    counts what it hands out."""

    def __init__(self, head: bytes) -> None:
        self.head = head
        self.served = 0

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        size = 8192 if size < 0 else size
        out = self.head[self.served : self.served + size]
        out = out or b"x" * size
        self.served += size
        if self.served > 64 * 1024 * 1024:
            raise AssertionError("read past the end of the headers")
        return out


def test_reading_stops_at_the_end_of_the_headers() -> None:
    head = b"Name: demo\nVersion: 1.0\n\n"
    stream: Any = _Endless(head)

    assert wheel_dist_info._header_block(stream) == head[:-1]
    assert stream.served <= 8192  # the one chunk holding the blank line


def test_one_endless_line_is_stopped_at_the_cap_not_buffered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No line end to split on: the unfinished line itself is what is capped."""
    monkeypatch.setattr(wheel_dist_info, "MAX_METADATA_BYTES", 50_000)
    stream: Any = _Endless(b"")

    with pytest.raises(wheel_dist_info._OverCap):
        wheel_dist_info._header_block(stream)

    assert stream.served <= 50_000 + 8192


def _zip_with(
    tmp_path: Path, metadata: bytes | None, prefix: str = "demo-1.0.dist-info/"
) -> tuple[zipfile.ZipFile, list[tuple[str, zipfile.ZipInfo]]]:
    path = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("demo/__init__.py", "")
        if metadata is not None:
            zf.writestr(f"{prefix}METADATA", metadata)
    zf = zipfile.ZipFile(path)
    return zf, wheel_members(zf, path.name)


@pytest.mark.parametrize(
    ("metadata", "limits", "warning"),
    [
        (b"Name: demo\nVersion: 1.0\n\nbody " * 1000, {}, None),
        (None, {}, "no demo-1.0.dist-info/METADATA"),
        (b"A: 1\nB: 2\nC: 3\n", {"MAX_METADATA_HEADERS": 2}, "over 2 headers"),
        (b"A: 12345678\n", {"MAX_METADATA_BYTES": 9}, "over 9 bytes"),
    ],
    ids=["read", "absent", "too-many-headers", "too-large"],
)
def test_the_metadata_headers_or_one_warning_saying_why_not(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    metadata: bytes | None,
    limits: dict[str, int],
    warning: str | None,
) -> None:
    for name, value in limits.items():
        monkeypatch.setattr(wheel_dist_info, name, value)
    zf, members = _zip_with(tmp_path, metadata)

    with zf:
        msg = read_metadata_headers(zf, members, "demo-1.0.dist-info/", "a.whl")

    messages = [r.getMessage() for r in caplog.records if r.levelno >= 30]
    if warning is None:
        assert msg is not None and msg["Name"] == "demo" and not messages
        assert msg.get_payload() == ""  # headers only: the body is not parsed
    else:
        assert msg is None
        (message,) = messages
        assert warning in message and message.endswith("identity unknown")


def test_the_metadata_headers_refuse_a_member_that_cannot_be_read(
    tmp_path: Path,
) -> None:
    wheel = damaged_wheel(tmp_path, "deflate", in_metadata=True)
    with zipfile.ZipFile(wheel) as zf:
        with pytest.raises(WheelRefused, match="could not read"):
            read_metadata_headers(
                zf, wheel_members(zf, WHEEL), "demo-1.0.dist-info/", WHEEL
            )


@pytest.mark.parametrize(
    ("exc", "label"),
    [
        (EOFError(), "EOFError"),
        (zlib.error(), "zlib.error"),
        (zipfile.BadZipFile(), "zipfile.BadZipFile"),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "x"), "UnicodeDecodeError"),
    ],
)
def test_the_exception_is_named_bare_for_a_builtin_and_qualified_otherwise(
    exc: Exception, label: str
) -> None:
    assert wheel_dist_info.exception_label(exc) == label
    assert f"could not read ({label}) -- wheel refused" in str(
        wheel_dist_info.unreadable_member_error("a.whl", "m", exc)
    )


@pytest.mark.parametrize(
    ("entry", "shape"),
    [
        ("m\nFORGED", "ARCHIVE='a\\n.whl' ENTRY='m\\nFORGED': why -- wheel refused"),
        (None, "ARCHIVE='a\\n.whl': why -- wheel refused"),
    ],
)
def test_a_refusal_is_one_line_in_one_shape(entry: str | None, shape: str) -> None:
    error = refusal("a\n.whl", entry, "why")
    assert str(error) == shape and isinstance(error, ValueError)


@pytest.mark.parametrize(
    "entries",
    [
        [("a/M", "1"), ("a/M", "2")],
        [("a/M", "1"), ("a\\M", "2")],
        [("a\\M", "1"), ("a/M", "2")],
        [("./a/M", "1"), ("a/M", "2")],
        [("a/M", "1"), ("b/x", ""), ("a//M", "2")],
    ],
    ids=["exact", "backslash", "backslash-first", "dot-prefix", "empty-segment"],
)
def test_a_wheel_holding_one_name_twice_is_refused(
    tmp_path: Path, entries: list[tuple[str, str]]
) -> None:
    wheel = raw_wheel(tmp_path / WHEEL, entries)

    with zipfile.ZipFile(wheel) as zf:
        with pytest.raises(WheelRefused) as refused:
            wheel_members(zf, WHEEL)
        # Any other reader of the same archive still warns and keeps the last.
        assert len(zip_file_members(zf, WHEEL, None)) == len(
            {m.name for m in map(normalize_member_name, (r for r, _ in entries))}
        )
    message = str(refused.value)
    assert f"ARCHIVE={WHEEL!r}" in message
    assert f"ENTRY={entries[0][0]!r}: duplicate member name -- wheel refused" in (
        message
    )


@pytest.mark.parametrize(
    ("entries", "names"),
    [
        # A directory entry is no member; two are no duplicate.
        ([("a/", ""), ("a\\", ""), ("a/M", "1")], ["a/M"]),
        # Unsafe names are skipped, not refused.
        ([("../x", ""), ("../x", ""), ("a/M", "1")], ["a/M"]),
        (
            [("a/M", "1"), ("a/N", "2"), ("A/M", "3")],
            ["a/M", "a/N", "A/M"],
        ),
    ],
    ids=["directories", "unsafe", "case-differs"],
)
def test_names_that_are_not_duplicates_are_not_refused(
    tmp_path: Path, entries: list[tuple[str, str]], names: list[str]
) -> None:
    wheel = raw_wheel(tmp_path / WHEEL, entries)
    with zipfile.ZipFile(wheel) as zf:
        assert [name for name, _ in wheel_members(zf, WHEEL)] == names


def test_a_central_directory_name_that_is_not_utf8_refuses_at_open(
    tmp_path: Path,
) -> None:
    wheel = central_name_damaged_wheel(tmp_path)

    with pytest.raises(WheelRefused) as refused:
        open_wheel_zip(wheel)

    assert str(refused.value) == (
        f"ARCHIVE={WHEEL!r}: could not open (UnicodeDecodeError) -- wheel refused"
    )


class _ZstdError(Exception):
    pass


def _importer(result: object) -> Any:
    def import_module(_name: str) -> object:
        if isinstance(result, Exception):
            raise result
        return result

    return import_module


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (SimpleNamespace(ZstdError=_ZstdError), (_ZstdError,)),
        (SimpleNamespace(ZstdError="not a class"), ()),
        (SimpleNamespace(), ()),
        (ImportError("no compression.zstd"), ()),
    ],
    ids=["present", "not-a-class", "absent-name", "no-module"],
)
def test_the_zstd_error_is_used_only_when_the_module_defines_one(
    monkeypatch: pytest.MonkeyPatch, module: object, expected: tuple[type, ...]
) -> None:
    monkeypatch.setattr(
        wheel_dist_info, "importlib", SimpleNamespace(import_module=_importer(module))
    )
    assert wheel_dist_info._zstd_errors() == expected


@pytest.mark.parametrize(
    "duplicate", [True, False], ids=["truncates-to-a-twin", "alone"]
)
def test_a_nul_in_a_member_name_refuses_the_wheel(
    tmp_path: Path, duplicate: bool
) -> None:
    """``zipfile`` cuts ``filename`` at the NUL (``orig_filename`` keeps it):
    an installer extracts ``m.py\\0.evil`` as ``m.py``."""
    names = ["m.py", "m.py\0.evil"] if duplicate else ["m.py\0.evil"]
    wheel = raw_wheel(tmp_path / WHEEL, [(name, "x") for name in names])

    with zipfile.ZipFile(wheel) as zf:
        assert zf.infolist()[-1].filename == "m.py"  # the truncation is real
        with pytest.raises(WheelRefused) as refused:
            wheel_members(zf, WHEEL)

    assert str(refused.value) == (
        f"ARCHIVE={WHEEL!r} ENTRY={'m.py' + chr(0) + '.evil'!r}: "
        "NUL in member name -- wheel refused"
    )


@pytest.mark.parametrize(
    ("kind", "error"),
    [("zip", "zipfile.BadZipFile"), ("version", "NotImplementedError")],
)
def test_a_file_zipfile_cannot_open_refuses_at_open_and_a_missing_one_does_not(
    tmp_path: Path, kind: str, error: str
) -> None:
    if kind == "zip":
        wheel = tmp_path / WHEEL
        wheel.write_bytes(b"not a zip file at all")
    else:
        wheel = zip_version_wheel(tmp_path)

    with pytest.raises(WheelRefused) as refused:
        open_wheel_zip(wheel)
    assert str(refused.value) == (
        f"ARCHIVE={WHEEL!r}: could not open ({error}) -- wheel refused"
    )
    with pytest.raises(OSError):
        open_wheel_zip(tmp_path / "missing.whl")
