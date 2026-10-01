# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model ZIP is refused, before ``zipfile`` builds a ``ZipInfo`` per entry,
when it holds more entries than the cap, or a central directory over the byte
cap. The entries are counted the way ``zipfile`` reads them, so every case
here is also opened by a real ``zipfile.ZipFile``: the check refuses exactly
the archives ``zipfile`` would open with more entries than the cap.

See also: :mod:`tests.extract.ai_model.test_archive_member` (the member
bound) and :mod:`pitloom.extract.ai_model.archive_member`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import contextlib
import inspect
import io
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import archive_member, read_ai_model
from pitloom.extract.ai_model.archive_member import (
    MAX_MODEL_ZIP_ENTRIES,
    open_model_binary,
    open_model_zip,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.extract.scanner_project import scan_project_for_ai_models
from tests.warning_helpers import logged_warnings

_CAP = 3
_MAX_COMMENT = 0xFFFF
_HEADER = 46
_FFFF = 0xFFFF
_FFFFFFFF = 0xFFFFFFFF


def _header(name: int = 0, extra: int = 0, comment: int = 0) -> bytes:
    """One central-directory header (what ``zipfile`` reads, nothing more)."""
    fixed = struct.pack(
        "<4s4B4HL2L5H2L",
        b"PK\x01\x02",
        20, 0, 20, 0,
        0, 0, 0, 0,
        0, 0, 0,
        name, extra, comment, 0, 0,
        0, 0,
    )  # fmt: skip
    return fixed + b"n" * name + b"e" * extra + b"c" * comment


def _directory(entries: int) -> bytes:
    return _header() * entries


def _directory_of(header: bytes, entries: int) -> bytes:
    d = header * entries
    return d + _eocd(entries, len(d))


def _eocd(
    count: int,
    size: int,
    offset: int = 0,
    comment: bytes = b"",
    *,
    disk: int = 0,
    disk_cd: int = 0,
) -> bytes:
    return struct.pack(
        "<4s4H2LH",
        b"PK\x05\x06", disk, disk_cd, count, count, size, offset, len(comment),
    ) + comment  # fmt: skip


def _zip64_record(count: int, size: int, offset: int, extensible: bytes = b"") -> bytes:
    return struct.pack(
        "<4sQ2H2L4Q",
        b"PK\x06\x06", 44 + len(extensible), 45, 45, 0, 0, count, count, size, offset,
    ) + extensible  # fmt: skip


def _locator(reloff: int, disks: int = 1) -> bytes:
    return struct.pack("<4sLQL", b"PK\x06\x07", 0, reloff, disks)


def _real_count(data: bytes) -> int | None:
    """What ``zipfile`` makes of *data*: its entry count, ``None`` when it
    raises ``BadZipFile``."""
    try:
        return len(zipfile.ZipFile(io.BytesIO(data)).filelist)
    except zipfile.BadZipFile:
        return None


def _archive(entries: int, comment: bytes = b"", prefix: bytes = b"") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.comment = comment
        for i in range(entries):
            zf.writestr(f"{i}", b"")
    return prefix + buf.getvalue()


def _zip64_reloff(n: int, decoy: bytes = b"\0" * 56) -> bytes:
    """The ZIP64 record is found through the locator's offset, behind 56
    bytes of extensible data; a record at the fixed position is a decoy."""
    d = _directory(n)
    return d + _zip64_record(n, len(d), 0, decoy) + _locator(len(d)) + _eocd(1, _HEADER)


def _signature_in_eocd(n: int) -> bytes:
    """The end record's disk fields spell ``PK\\x05\\x06`` a second time."""
    return _directory(n) + _eocd(1, n * _HEADER, disk=0x4B50, disk_cd=0x0605)


def _window(n: int) -> bytes:
    """An end record 65558 bytes from the end: found by Python 3.10's search
    window, not by 3.14's."""
    d = _directory(n)
    return d + _eocd(1, len(d), comment=b"c" * _MAX_COMMENT) + b"x"


def _walks_past_the_end_record(n: int) -> bytes:
    """One header declaring an extra field longer than the directory it is
    in, so a walk that goes by lengths alone reaches the headers behind the
    end record, which are not part of the directory."""
    return _header(extra=22)[:_HEADER] + _eocd(1, _HEADER) + _directory(n)


# id -> (builder of an archive of n entries, what zipfile makes of it)
_HOSTILE: dict[str, tuple[Callable[[int], bytes], str]] = {
    "zip64-found-by-locator-offset": (_zip64_reloff, "opens"),
    "zip64-decoy-at-the-fixed-position": (
        lambda n: _zip64_reloff(n, decoy=_zip64_record(1, _HEADER, 0)),
        "opens",
    ),
    "signature-inside-the-end-record": (_signature_in_eocd, "opens"),
    "end-record-at-the-window-edge": (_window, "any"),
    "count-lies-low": (
        lambda n: _directory(n) + _eocd(1, n * _HEADER),
        "opens",
    ),
    "count-lies-high": (
        lambda n: _directory(n) + _eocd(_FFFF, n * _HEADER),
        "opens",
    ),
    "walk-ends-at-the-directory-size": (_walks_past_the_end_record, "one"),
    "multi-disk-zip64-locator": (
        lambda n: (
            _directory(n)
            + _zip64_record(n, n * _HEADER, 0)
            + _locator(n * _HEADER, disks=2)
            + _eocd(_FFFF, _FFFFFFFF)
        ),
        "bad",
    ),
    "headers-with-names-extras-and-comments": (
        lambda n: _directory_of(_header(1, 2, 3), n),
        "opens",
    ),
    "no-end-record": (lambda n: _directory(n), "bad"),
    "directory-larger-than-the-file": (
        lambda n: _directory(n) + _eocd(n, 10**6),
        "bad",
    ),
    "bad-header-signature": (
        lambda n: b"PK\x01\x03" + _directory(n)[4:] + _eocd(n, n * _HEADER),
        "bad",
    ),
    "truncated-directory": (
        lambda n: _directory(n) + _eocd(n, n * _HEADER + 10),
        "bad",
    ),
    "prefixed": (lambda n: _archive(n, prefix=b"#!/bin/sh\n" * 50), "opens"),
    "commented": (lambda n: _archive(n, comment=b"PK\x05\x06" + b"c" * 30), "any"),
    "longest-comment": (lambda n: _archive(n, comment=b"c" * _MAX_COMMENT), "opens"),
    "plain": (_archive, "opens"),
}


@pytest.mark.parametrize("case", _HOSTILE)
@pytest.mark.parametrize("extra", [-1, 0, 1, 2])
def test_the_check_refuses_exactly_what_zipfile_opens_over_the_cap(
    case: str, extra: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For each entry count around the cap, and whatever way the archive
    hides it, the real ``ZipFile`` opens N entries iff the check lets it
    through with N at most the cap."""
    build, expected = _HOSTILE[case]
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", _CAP)
    data = build(_CAP + extra)
    real = _real_count(data)
    path = tmp_path / "m.zip"
    path.write_bytes(data)
    # The case really is what it says: a vacuous pass is not possible.
    if expected != "any":
        assert (real is None) == (expected == "bad")
    if expected == "one":
        assert real == 1
    elif expected == "opens":
        assert real == _CAP + extra
    if real is not None and real > _CAP:
        with pytest.raises(ModelLimitExceeded, match="more than 3 entries"):
            with open_model_zip(path):
                pass
    else:
        with open_model_zip(path) if real is not None else open_model_binary(path):
            pass


def test_the_cap_is_inclusive_at_its_real_value(tmp_path: Path) -> None:
    """Over 65535 entries the plain record cannot say how many; only the
    walk can."""
    for entries, refused in (
        (MAX_MODEL_ZIP_ENTRIES, False),
        (MAX_MODEL_ZIP_ENTRIES + 1, True),
    ):
        d = _directory(entries)
        path = tmp_path / f"{entries}.zip"
        path.write_bytes(
            d
            + _zip64_record(entries, len(d), 0)
            + _locator(len(d))
            + _eocd(_FFFF, _FFFFFFFF)
        )
        if refused:
            with pytest.raises(ModelLimitExceeded, match="more than 100000 entries"):
                with open_model_binary(path):
                    pass
        else:
            with open_model_binary(path):
                pass


@pytest.mark.parametrize(("limit_offset", "refused"), [(0, False), (-1, True)])
def test_the_directory_byte_cap_is_inclusive(
    limit_offset: int, refused: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _header(name=40) * 2
    monkeypatch.setattr(
        archive_member, "_MAX_ZIP_DIRECTORY_BYTES", len(d) + limit_offset
    )
    path = tmp_path / "m.zip"
    path.write_bytes(d + _eocd(2, len(d)))
    if refused:
        with pytest.raises(ModelLimitExceeded, match=f"central directory of {len(d)} "):
            open_model_zip(path).__enter__()
    else:
        with open_model_zip(path) as zf:
            assert len(zf.filelist) == 2


def test_a_hostile_count_is_refused_without_building_a_zipinfo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", _CAP)
    path = tmp_path / "m.zip"
    path.write_bytes(_zip64_reloff(_CAP + 2))
    built: list[object] = []

    class _Spy(zipfile.ZipFile):  # pylint: disable=too-few-public-methods
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            built.append(args)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", _Spy)
    with pytest.raises(ModelLimitExceeded):
        open_model_zip(path).__enter__()
    assert not built


# --- zipfile's private end-record function: the shape this relies on --------


def _private(owner: Any, name: str) -> Any:
    """A zipfile name typeshed does not know."""
    return getattr(owner, name)


def _end_record(data: bytes) -> list[Any]:
    result = _private(zipfile, "_EndRecData")(io.BytesIO(data))
    assert isinstance(result, list)
    return result


def test_the_zipfile_end_record_shape_is_the_one_the_check_reads() -> None:
    """Pin of ``zipfile._EndRecData`` on the running interpreter: where the
    directory size and the end record's position are, for a plain and a
    ZIP64 archive, and the arithmetic ``ZipFile`` does with them."""
    size_at = _private(zipfile, "_ECD_SIZE")
    location_at = _private(zipfile, "_ECD_LOCATION")
    plain = _archive(2)
    end = _end_record(plain)
    assert len(end) == 10
    assert end[size_at] == 2 * (46 + len("0")) + 0
    assert end[location_at] == len(plain) - 22  # no comment: the last 22 bytes
    d = _directory(2)
    z64 = (
        d
        + _zip64_record(2, len(d), 0, b"x" * 8)
        + _locator(len(d))
        + _eocd(_FFFF, _FFFFFFFF)
    )
    end64 = _end_record(z64)
    assert end64[size_at] == len(d)
    assert end64[location_at] == len(
        d
    )  # the ZIP64 record's offset, not the end record's
    assert (
        zipfile.ZipFile(io.BytesIO(z64)).start_dir
        == end64[location_at] - end64[size_at]
    )
    # The two lines of arithmetic the check copies, in this interpreter's source.
    source = inspect.getsource(_private(zipfile.ZipFile, "_RealGetContents"))
    handler = getattr(zipfile, "_handle_prepended_data", None)
    source += inspect.getsource(handler) if handler else ""
    for line in (
        "endrec[_ECD_LOCATION] - size_cd - offset_cd",
        "self.start_dir = offset_cd + concat",
        "while total < size_cd",
        "total + sizeCentralDir + centdir[_CD_FILENAME_LENGTH]",
    ):
        assert line in source


@pytest.mark.parametrize(
    "broken",
    ["no-function", "no-size-index", "no-location-index", "raises", "short", "junk"],
)
def test_a_zipfile_that_cannot_be_asked_fails_closed(
    broken: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raises(_fh: Any) -> None:
        raise RuntimeError("changed")

    if broken == "no-function":
        monkeypatch.delattr(zipfile, "_EndRecData")
    elif broken == "no-size-index":
        monkeypatch.delattr(zipfile, "_ECD_SIZE")
    elif broken == "no-location-index":
        monkeypatch.delattr(zipfile, "_ECD_LOCATION")
    else:
        monkeypatch.setattr(
            zipfile,
            "_EndRecData",
            {
                "raises": _raises,
                "short": lambda _fh: [0],
                "junk": lambda _fh: ["a"] * 10,
            }[broken],
        )
    path = tmp_path / "m.zip"
    path.write_bytes(_archive(1))
    with pytest.raises(ModelLimitExceeded, match="not checkable"):
        open_model_zip(path).__enter__()


@pytest.mark.parametrize("error", [OSError("short read"), zipfile.BadZipFile("x")])
def test_an_end_record_zipfile_itself_refuses_is_left_to_it(
    error: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raises(_fh: Any) -> None:
        raise error

    monkeypatch.setattr(zipfile, "_EndRecData", _raises)
    path = tmp_path / "m.zip"
    path.write_bytes(_archive(1))
    with open_model_binary(path):
        pass  # not refused; ZipFile will turn the same error into BadZipFile


def _entries(count: int) -> bytes:
    return _archive(count, comment=b"c" * _MAX_COMMENT)


def _npz(path: Path) -> None:
    np = pytest.importorskip("numpy")
    np.savez(path, **{f"a{i}": np.zeros(1) for i in range(5)})


def _keras(path: Path) -> None:
    path.write_bytes(_entries(5))


_READER_FILES: dict[str, tuple[AiModelFormat, str, Callable[[Path], None]]] = {
    "keras": (AiModelFormat.KERAS, "m.keras", _keras),
    "pt2": (AiModelFormat.PYTORCH_PT2, "m.pt2", _keras),
    "pytorch": (AiModelFormat.PYTORCH, "m.pt", _keras),
    "npz": (AiModelFormat.NUMPY, "m.npz", _npz),
}


@pytest.mark.parametrize("case", _READER_FILES)
def test_a_reader_parses_the_handle_that_was_checked(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One open per read, for every reader: a second open could see another
    file than the one checked."""
    fmt, name, build = _READER_FILES[case]
    path = tmp_path / name
    build(path)
    np = pytest.importorskip("numpy")
    checked: list[Any] = []
    parsed: list[Any] = []
    real_check = archive_member.check_zip_bounds
    real_zip, real_load = zipfile.ZipFile, np.load

    def check(fh: Any) -> None:
        checked.append(fh)
        real_check(fh)

    def zip_file(source: Any, *args: Any, **kwargs: Any) -> zipfile.ZipFile:
        parsed.append(source)
        return real_zip(source, *args, **kwargs)

    def load(source: Any, *args: Any, **kwargs: Any) -> Any:
        parsed.append(source)
        return real_load(source, *args, **kwargs)

    monkeypatch.setattr(archive_member, "check_zip_bounds", check)
    monkeypatch.setattr(zipfile, "ZipFile", zip_file)
    monkeypatch.setattr(np, "load", load)
    with contextlib.suppress(Exception):  # the reader may not like the content
        read_ai_model(path, model_format=fmt)
    (handle,) = checked
    assert parsed
    assert all(source is handle for source in parsed)
    assert handle.closed


@pytest.mark.parametrize("case", _READER_FILES)
def test_every_reader_that_opens_a_model_zip_refuses_one_over_the_cap(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fmt, name, build = _READER_FILES[case]
    path = tmp_path / name
    build(path)
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", 4)
    with pytest.raises(ModelLimitExceeded, match="more than 4 entries"):
        read_ai_model(path, model_format=fmt)
    # In a scan: one warning, a format-only entry.
    (model,) = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path=name, distribution_path=name)],
        scan_usage=False,
        usage_hint=lambda: False,
    )
    assert model.format_info.model_format == fmt
    assert not model.provenance
    (message,) = logged_warnings(caplog)
    assert message == (
        f"FORMAT={fmt} FILE={name}: "
        "ZIP archive of more than 4 entries; metadata not read"
    )
