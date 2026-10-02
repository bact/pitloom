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
import io
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
from tests.extract.ai_model.zip_builders import (
    CAP,
    FFFF,
    FFFFFFFF,
    HEADER,
    MAX_COMMENT,
    archive,
    directory,
    directory_of,
    eocd,
    header,
    locator,
    zip64_fixed,
    zip64_record,
)
from tests.warning_helpers import logged_warnings


def _real_count(data: bytes) -> int | None:
    """What ``zipfile`` makes of *data*: its entry count, ``None`` when it
    raises ``BadZipFile``."""
    try:
        return len(zipfile.ZipFile(io.BytesIO(data)).filelist)
    except zipfile.BadZipFile:
        return None


def _zip64_reloff(n: int, decoy: bytes = b"\0" * 56) -> bytes:
    """The ZIP64 record is found through the locator's offset, behind 56
    bytes of extensible data; a record at the fixed position is a decoy."""
    d = directory(n)
    return d + zip64_record(n, len(d), 0, decoy) + locator(len(d)) + eocd(1, HEADER)


def _signature_in_eocd(n: int) -> bytes:
    """The end record's disk fields spell ``PK\\x05\\x06`` a second time."""
    return directory(n) + eocd(1, n * HEADER, disk=0x4B50, disk_cd=0x0605)


def _window(n: int) -> bytes:
    """An end record 65558 bytes from the end: found by Python 3.10's search
    window, not by 3.14's."""
    d = directory(n)
    return d + eocd(1, len(d), comment=b"c" * MAX_COMMENT) + b"x"


def _walks_past_the_end_record(n: int) -> bytes:
    """One header declaring an extra field longer than the directory it is
    in, so a walk that goes by lengths alone reaches the headers behind the
    end record, which are not part of the directory."""
    return header(extra=22)[:HEADER] + eocd(1, HEADER) + directory(n)


# id -> builder of an archive of n entries. What ``zipfile`` makes of the
# ZIP64 ones with a record found by the locator, or one at the fixed
# position that the locator does not point to, depends on the interpreter's
# release (CVE-2025-8291), so no case states it: the real ``ZipFile`` does.
_HOSTILE: dict[str, Callable[[int], bytes]] = {
    "zip64-found-by-locator-offset": _zip64_reloff,
    "zip64-decoy-at-the-fixed-position": lambda n: _zip64_reloff(
        n, decoy=zip64_record(1, HEADER, 0)
    ),
    "zip64-at-the-fixed-position": zip64_fixed,
    "signature-inside-the-end-record": _signature_in_eocd,
    "end-record-at-the-window-edge": _window,
    "count-lies-low": lambda n: directory(n) + eocd(1, n * HEADER),
    "count-lies-high": lambda n: directory(n) + eocd(FFFF, n * HEADER),
    "walk-ends-at-the-directory-size": _walks_past_the_end_record,
    "multi-disk-zip64-locator": lambda n: (
        directory(n)
        + zip64_record(n, n * HEADER, 0)
        + locator(n * HEADER, disks=2)
        + eocd(FFFF, FFFFFFFF)
    ),
    "headers-with-names-extras-and-comments": lambda n: directory_of(
        header(1, 2, 3), n
    ),
    "no-end-record": directory,
    "directory-larger-than-the-file": lambda n: directory(n) + eocd(n, 10**6),
    "bad-header-signature": lambda n: (
        b"PK\x01\x03" + directory(n)[4:] + eocd(n, n * HEADER)
    ),
    "truncated-directory": lambda n: directory(n) + eocd(n, n * HEADER + 10),
    "short-last-header": lambda n: directory(n) + b"x" * 4 + eocd(n, n * HEADER + 4),
    "prefixed": lambda n: archive(n, prefix=b"#!/bin/sh\n" * 50),
    "commented": lambda n: archive(n, comment=b"PK\x05\x06" + b"c" * 30),
    "longest-comment": lambda n: archive(n, comment=b"c" * MAX_COMMENT),
    "plain": archive,
}
# What ``zipfile`` makes of a case on every release, where the case is
# about something else than the end record: a guard that the cases are not
# vacuous (a wrong builder would otherwise pass as "refused" or "opens").
_OPENS = {
    "signature-inside-the-end-record",
    "count-lies-low",
    "count-lies-high",
    "headers-with-names-extras-and-comments",
    "prefixed",
    "longest-comment",
    "plain",
    "zip64-at-the-fixed-position",
}
_BAD = {
    "multi-disk-zip64-locator",
    "no-end-record",
    "directory-larger-than-the-file",
    "short-last-header",
}


@pytest.mark.parametrize("case", _HOSTILE)
@pytest.mark.parametrize("extra", [-1, 0, 1, 2])
def test_the_check_refuses_exactly_what_zipfile_opens_over_the_cap(
    case: str, extra: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For each entry count around the cap, and whatever way the archive
    hides it, the check never lets through what the running ``zipfile``
    opens with more entries than the cap, and never refuses what it opens
    with at most the cap. An archive ``zipfile`` rejects may be refused or
    passed to it."""
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", CAP)
    data = _HOSTILE[case](CAP + extra)
    real = _real_count(data)
    path = tmp_path / "m.zip"
    path.write_bytes(data)
    if case in _OPENS:
        assert real == CAP + extra
    if case in _BAD:
        assert real is None
    if case == "walk-ends-at-the-directory-size":
        assert real == 1
    if real is None:
        with contextlib.suppress(ModelLimitExceeded):
            with open_model_binary(path):
                pass
    elif real > CAP:
        with pytest.raises(ModelLimitExceeded, match="more than 3 entries"):
            with open_model_zip(path):
                pass
    else:
        with open_model_zip(path):
            pass


def test_the_cap_is_inclusive_at_its_real_value(tmp_path: Path) -> None:
    """Over 65535 entries the plain record cannot say how many; only the
    walk can."""
    for entries, refused in (
        (MAX_MODEL_ZIP_ENTRIES, False),
        (MAX_MODEL_ZIP_ENTRIES + 1, True),
    ):
        path = tmp_path / f"{entries}.zip"
        path.write_bytes(zip64_fixed(entries))
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
    d = header(name=40) * 2
    monkeypatch.setattr(
        archive_member, "_MAX_ZIP_DIRECTORY_BYTES", len(d) + limit_offset
    )
    path = tmp_path / "m.zip"
    path.write_bytes(d + eocd(2, len(d)))
    if refused:
        with pytest.raises(ModelLimitExceeded, match=f"central directory of {len(d)} "):
            open_model_zip(path).__enter__()
    else:
        with open_model_zip(path) as zf:
            assert len(zf.filelist) == 2


def test_a_hostile_count_is_refused_without_building_a_zipinfo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", CAP)
    path = tmp_path / "m.zip"
    path.write_bytes(zip64_fixed(CAP + 2))
    built: list[object] = []

    class _Spy(zipfile.ZipFile):  # pylint: disable=too-few-public-methods
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            built.append(args)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", _Spy)
    with pytest.raises(ModelLimitExceeded):
        open_model_zip(path).__enter__()
    assert not built


def _entries(count: int) -> bytes:
    return archive(count, comment=b"c" * MAX_COMMENT)


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
    # pylint: disable-next=unbalanced-tuple-unpacking
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
    # pylint: disable-next=unbalanced-tuple-unpacking
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
