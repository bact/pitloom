# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model ZIP is refused, before ``zipfile`` builds a ``ZipInfo`` per entry,
when its end-of-central-directory record (or the ZIP64 one) declares more
entries than the cap, or a central directory too large for that many.

See also: :mod:`tests.extract.ai_model.test_archive_member` (the member
bound) and :mod:`pitloom.extract.ai_model.archive_member`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import io
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import archive_member, read_ai_model
from pitloom.extract.ai_model.archive_member import (
    MAX_MODEL_ZIP_ENTRIES,
    check_zip_bounds,
    open_model_zip,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.extract.scanner_project import scan_project_for_ai_models
from tests.warning_helpers import logged_warnings

# The plain record's counts are 16 bits, so a cap above 65535 is out of its
# reach: the crafted cases lower the cap (and write 0, not the 0xFFFF a real
# ZIP64 archive puts in the plain record); the real one is used further below.
_CAP = 1000
_DIRECTORY_CAP = archive_member._MAX_ZIP_DIRECTORY_BYTES
_MAX_COMMENT = 0xFFFF


def _eocd(on_disk: int, total: int, size: int = 0, comment: bytes = b"") -> bytes:
    return (
        struct.pack(
            "<4s4H2LH", b"PK\x05\x06", 0, 0, on_disk, total, size, 0, len(comment)
        )
        + comment
    )


def _zip64(on_disk: int, total: int, size: int = 0) -> bytes:
    """A ZIP64 end record and its locator, as they precede the end record."""
    record = struct.pack(
        "<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, on_disk, total, size, 0
    )
    return record + struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1)


_FFFF = 0xFFFF
_FFFFFFFF = 0xFFFFFFFF
# id -> (file bytes, refused with this reason, or None when read on)
_CRAFTED: dict[str, tuple[bytes, str | None]] = {
    "at-the-cap": (_eocd(_CAP, _CAP), None),
    "over-the-cap": (_eocd(_CAP + 1, _CAP + 1), "entries"),
    "disk-count-larger": (_eocd(_CAP + 1, 1), "entries"),
    "total-larger": (_eocd(1, _CAP + 1), "entries"),
    "zip64-total": (_zip64(1, _CAP + 1) + _eocd(0, 0), "entries"),
    "zip64-disk": (_zip64(_CAP + 1, 1) + _eocd(0, 0), "entries"),
    "zip64-at-the-cap": (_zip64(_CAP, _CAP) + _eocd(0, 0), None),
    # What a real ZIP64 archive carries: the plain fields at their maximum.
    "zip64-overflowed-plain-fields": (
        _zip64(_CAP, _CAP, 5000) + _eocd(_FFFF, _FFFF, _FFFFFFFF),
        None,
    ),
    "zip64-overflowed-plain-fields-over": (
        _zip64(_CAP + 1, _CAP + 1, 5000) + _eocd(_FFFF, _FFFF, _FFFFFFFF),
        "entries",
    ),
    "plain-larger-than-zip64": (_zip64(1, 1) + _eocd(1, _CAP + 1), "entries"),
    "plain-size-larger-than-zip64": (
        _zip64(1, 1, 1) + _eocd(_FFFF, _FFFF, _DIRECTORY_CAP + 1),
        "central directory",
    ),
    "zip64-size": (
        _zip64(1, 1, _DIRECTORY_CAP + 1) + _eocd(0, 0, 1),
        "central directory",
    ),
    "size": (_eocd(1, 1, _DIRECTORY_CAP + 1), "central directory"),
    "size-at-the-cap": (_eocd(1, 1, _DIRECTORY_CAP), None),
    "comment-at-its-longest": (
        b"x" * 10 + _eocd(_CAP + 1, _CAP + 1, comment=b"c" * _MAX_COMMENT),
        "entries",
    ),
    # Not a record: left to zipfile's own error.
    "no-record": (b"not a zip file at all" * 10, None),
    "empty": (b"", None),
    "record-cut-short": (_eocd(_CAP + 1, _CAP + 1)[:-1], None),
    "locator-without-record": (
        b"\0" * 3 + struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1) + _eocd(0, 0),
        None,
    ),
    # A record or locator that is not one: its counts are not read.
    "wrong-record-signature": (
        b"PK\x06\x00" + _zip64(1, _CAP + 1)[4:] + _eocd(0, 0),
        None,
    ),
    "wrong-locator-signature": (
        _zip64(1, _CAP + 1)[:56] + b"PK\x06\x00" + _zip64(1, 1)[60:] + _eocd(0, 0),
        None,
    ),
    # The last record is the one zipfile uses (a comment may hold a fake one).
    "last-record-wins": (_eocd(1, 1) + _eocd(_CAP + 1, _CAP + 1), "entries"),
}


@pytest.mark.parametrize("case", _CRAFTED)
def test_the_declared_directory_is_checked_before_zipfile_reads_it(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, refused = _CRAFTED[case]
    path = tmp_path / "m.zip"
    path.write_bytes(data)
    opened: list[Any] = []
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", _CAP)

    def spy(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise zipfile.BadZipFile("spy")

    monkeypatch.setattr(archive_member, "zipfile", SimpleNamespace(ZipFile=spy))
    if refused is None:
        check_zip_bounds(path)
        with pytest.raises(zipfile.BadZipFile, match="spy"):
            open_model_zip(path)  # past the check, on to zipfile
        assert len(opened) == 1
    else:
        with pytest.raises(ModelLimitExceeded, match=refused):
            open_model_zip(path)
        assert not opened  # never reached zipfile


@pytest.mark.parametrize(
    ("entries", "refused"),
    [(MAX_MODEL_ZIP_ENTRIES, False), (MAX_MODEL_ZIP_ENTRIES + 1, True)],
)
def test_the_real_cap_is_inclusive_and_reached_through_zip64(
    entries: int, refused: bool, tmp_path: Path
) -> None:
    """Over 65535 entries only a ZIP64 record can say so (a few million
    empty entries fit a 16 MiB archive)."""
    path = tmp_path / "m.zip"
    path.write_bytes(_zip64(entries, entries) + _eocd(_FFFF, _FFFF))
    if refused:
        with pytest.raises(ModelLimitExceeded, match="ZIP archive of 100001 entries"):
            check_zip_bounds(path)
    else:
        check_zip_bounds(path)


def test_only_the_tail_of_a_large_file_is_read(tmp_path: Path) -> None:
    """The record is looked for in the last 64 KiB + 22 bytes, not the whole
    file: a signature earlier than that is not found (zipfile ignores it too)."""
    early = _eocd(1, 1, _DIRECTORY_CAP + 1)  # would be refused if it were found
    path = tmp_path / "m.zip"
    path.write_bytes(early + b"\0" * (_MAX_COMMENT + 22))
    check_zip_bounds(path)  # no record in the tail: nothing refused


def _entries(count: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.comment = b"c" * _MAX_COMMENT
        for i in range(count):
            zf.writestr(f"{i}", b"")
    return buf.getvalue()


def test_a_real_archive_is_refused_just_over_the_cap_and_read_at_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", 3)
    for count, refused in ((3, False), (4, True)):
        path = tmp_path / f"{count}.zip"
        path.write_bytes(_entries(count))
        if refused:
            with pytest.raises(ModelLimitExceeded, match="ZIP archive of 4 entries"):
                open_model_zip(path)
        else:
            with open_model_zip(path) as zf:
                assert len(zf.namelist()) == count


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
    with pytest.raises(ModelLimitExceeded, match="ZIP archive of 5 entries"):
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
        f"FORMAT={fmt} FILE={name}: ZIP archive of 5 entries; metadata not read"
    )
