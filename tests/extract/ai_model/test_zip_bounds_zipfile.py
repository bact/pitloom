# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``zipfile``'s private end-record function, which the model-ZIP bound check
asks where a directory starts: the shape it relies on, both conventions
among its releases (CVE-2025-8291) on any interpreter, and the check failing
closed when the function, its answer or the directory is not as expected.

See also: :mod:`tests.extract.ai_model.test_zip_bounds` and
:mod:`pitloom.extract.ai_model.archive_member`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import inspect
import io
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.ai_model import archive_member
from pitloom.extract.ai_model.archive_member import open_model_binary, open_model_zip
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from tests.extract.ai_model.zip_builders import (
    CAP,
    HEADER,
    archive,
    directory,
    eocd,
    zip64_fixed,
)

# --- zipfile's private end-record function: the shape this relies on --------


def _private(owner: Any, name: str) -> Any:
    """A zipfile name typeshed does not know."""
    return getattr(owner, name)


def _end_record(data: bytes) -> list[Any]:
    result = _private(zipfile, "_EndRecData")(io.BytesIO(data))
    assert isinstance(result, list)
    return result


@pytest.mark.parametrize(
    "build",
    [archive, zip64_fixed, lambda n: archive(n, prefix=b"#!/bin/sh\n" * 50)],
    ids=["plain", "zip64", "prefixed"],
)
def test_the_directory_start_is_where_zipfile_seeks(
    build: Callable[[int], bytes],
) -> None:
    """Pin of ``zipfile._EndRecData`` on the running interpreter, whichever
    convention it follows: the start this computes is the one ``ZipFile``
    seeks to."""
    data = build(2)
    found = archive_member._directory_start_and_size(io.BytesIO(data))
    assert found is not None
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert found[0] == zf.start_dir
    assert found[1] > 0
    # The lines of arithmetic the check copies, in this interpreter's source.
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


_real_end_record: Any = _private(zipfile, "_EndRecData")


def _end_record_as(fixed: bool) -> Callable[[Any], Any]:
    """``zipfile._EndRecData`` as of a release with (*fixed*) or without the
    CVE-2025-8291 fix, whichever the running interpreter is. Without
    (CPython v3.11.9, ``_EndRecData64``) the end record's position stays the
    plain one and the ZIP64 record is read from the fixed position behind
    the locator; with, the position is the ZIP64 record's."""
    zf: Any = zipfile

    def end_record(fh: Any) -> Any:
        current = zf._EndRecData64
        zf._EndRecData64 = lambda _fh, _offset, endrec: endrec  # plain only
        try:
            endrec = _real_end_record(fh)
        finally:
            zf._EndRecData64 = current
        if not endrec:
            return endrec
        where = endrec[zf._ECD_LOCATION]
        fh.seek(where - zf.sizeEndCentDir64Locator - zf.sizeEndCentDir64)
        record = fh.read(zf.sizeEndCentDir64)
        fh.seek(where - zf.sizeEndCentDir64Locator)
        locator = fh.read(zf.sizeEndCentDir64Locator)
        if not (
            record.startswith(zf.stringEndArchive64)
            and locator.startswith(zf.stringEndArchive64Locator)
            and len(record) == zf.sizeEndCentDir64
        ):
            return endrec
        fields = struct.unpack(zf.structEndArchive64, record)
        endrec[zf._ECD_SIGNATURE] = fields[0]
        endrec[zf._ECD_DISK_NUMBER], endrec[zf._ECD_DISK_START] = fields[4:6]
        endrec[zf._ECD_ENTRIES_THIS_DISK], endrec[zf._ECD_ENTRIES_TOTAL] = fields[6:8]
        endrec[zf._ECD_SIZE], endrec[zf._ECD_OFFSET] = fields[8:10]
        if fixed:
            endrec[zf._ECD_LOCATION] = (
                where - zf.sizeEndCentDir64Locator - zf.sizeEndCentDir64
            )
        return endrec

    return end_record


@pytest.fixture(name="shift", params=[0, 76], ids=["fixed", "unfixed"])
def _convention(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> int:
    """Each convention of ``zipfile``'s end record on any interpreter: the
    bytes ``ZipFile`` takes off the directory start for a ZIP64 archive
    (see :func:`pitloom.extract.ai_model.archive_member._zip64_start_shift`)."""
    monkeypatch.setattr(archive_member, "MAX_MODEL_ZIP_ENTRIES", CAP)
    monkeypatch.setattr(zipfile, "_EndRecData", _end_record_as(not request.param))
    return int(request.param)


def _probe() -> int:
    return archive_member._zip64_start_shift(
        archive_member._ZipfileApi(
            *(getattr(zipfile, n) for n in archive_member._ZIPFILE_PRIVATES)
        )
    )


def test_a_zip64_archive_over_the_cap_is_refused_under_both_conventions(
    shift: int, tmp_path: Path
) -> None:
    assert _probe() == shift
    path = tmp_path / "m.zip"
    for entries, refused in ((CAP, False), (CAP + 1, True)):
        path.write_bytes(zip64_fixed(entries))
        if refused:
            with pytest.raises(ModelLimitExceeded, match="more than 3 entries"):
                with open_model_binary(path):
                    pass
        else:
            with open_model_binary(path):
                pass


@pytest.mark.parametrize("prefix", [0, 200], ids=["bare", "prefixed"])
def test_a_start_computed_wrongly_is_a_refusal_never_a_bypass(
    shift: int, prefix: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the shift of the other convention the walk reads no directory,
    or the start falls before the file: either way the file is refused, not
    left to ``zipfile``."""
    wrong = 76 - shift
    path = tmp_path / "m.zip"
    path.write_bytes(b"\0" * prefix + zip64_fixed(CAP + 1))
    monkeypatch.setattr(archive_member, "_zip64_start_shift", lambda _api: wrong)
    with pytest.raises(ModelLimitExceeded, match="malformed"):
        with open_model_binary(path):
            pass


@pytest.mark.parametrize(
    ("central_dir", "comment"),
    [
        (b"\0" * HEADER, b""),
        (directory(1) + b"x" * 4, b""),
        # A 46-byte read from the last 4 bytes would run on into the end record.
        (directory(1) + b"PK\x01\x02", b"c" * 40),
    ],
    ids=["no-signature", "short-last-header", "short-last-header-then-end-record"],
)
def test_a_directory_zipfile_could_not_read_is_refused(
    central_dir: bytes, comment: bytes, tmp_path: Path
) -> None:
    """Not a header, or one cut short by the directory's size: ``zipfile``
    raises, and a disagreement about the directory must not read as "within
    the cap"."""
    path = tmp_path / "m.zip"
    path.write_bytes(central_dir + eocd(1, len(central_dir), comment=comment))
    with pytest.raises(ModelLimitExceeded, match="malformed"):
        with open_model_binary(path):
            pass


@pytest.mark.parametrize(
    "broken",
    [
        "no-function",
        "no-size-index",
        "no-location-index",
        "no-zip64-size",
        "raises",
        "short",
        "junk",
        "neither-convention",
        "raises-on-the-probe",
        "raises-on-the-file",
        "short-on-the-file",
        "junk-on-the-file",
    ],
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
    elif broken == "no-zip64-size":
        monkeypatch.delattr(zipfile, "sizeEndCentDir64")
    elif broken == "neither-convention":

        def _elsewhere(fh: Any) -> list[Any]:
            endrec = _real_end_record(fh)
            endrec[_private(zipfile, "_ECD_LOCATION")] += 1
            return endrec  # type: ignore[no-any-return]

        monkeypatch.setattr(zipfile, "_EndRecData", _elsewhere)
    else:
        name, on_file, _ = broken.partition("-on-the-file")
        name, on_probe, _ = name.partition("-on-the-probe")
        wrong: Callable[[Any], Any] = {
            "raises": _raises,
            "short": lambda _fh: [0],
            "junk": lambda _fh: ["a"] * 10,
        }[name]

        def _end_record(fh: Any) -> Any:
            # "on-the-file": the check's own probe is answered truthfully
            if on_file and isinstance(fh, io.BytesIO):
                return _real_end_record(fh)
            if on_probe and not isinstance(fh, io.BytesIO):
                return _real_end_record(fh)
            return wrong(fh)

        monkeypatch.setattr(zipfile, "_EndRecData", _end_record)
    path = tmp_path / "m.zip"
    path.write_bytes(archive(1))
    with pytest.raises(ModelLimitExceeded, match="not checkable"):
        open_model_zip(path).__enter__()


@pytest.mark.parametrize("error", [OSError("short read"), zipfile.BadZipFile("x")])
def test_an_end_record_zipfile_itself_refuses_is_left_to_it(
    error: Exception, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raises(fh: Any) -> list[Any] | None:
        if isinstance(fh, io.BytesIO):  # the check's own probe
            return _real_end_record(fh)  # type: ignore[no-any-return]
        raise error

    monkeypatch.setattr(zipfile, "_EndRecData", _raises)
    path = tmp_path / "m.zip"
    path.write_bytes(archive(1))
    with open_model_binary(path):
        pass  # not refused; ZipFile will turn the same error into BadZipFile
