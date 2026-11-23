# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a hostile model file may declare before its parser runs: a pickle
before fickling, fickling's stderr and an ``.npy`` header's length (before
numpy). GGUF: :mod:`tests.extract.ai_model.test_gguf_bounds`.

See also: :mod:`tests.extract.ai_model.test_pickle_bounds` (the pickle
bounds as Pitloom applies them),
:mod:`tests.extract.ai_model.test_archive_member` (inner archive members)
and :mod:`tests.extract.scanner.test_scanner_model_limits` (what the
scanner makes of each).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import ast
import io
import logging
import pickle
import struct
import sys
import tracemalloc
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import (
    _pickle_bounds,
    archive_member,
    pytorch,
)
from pitloom.extract.ai_model import numpy as numpy_reader
from pitloom.extract.ai_model.limits import ModelLimitExceeded, ModelOverCap
from pitloom.extract.ai_model.pytorch import (
    FICKLING_PREFIX,
    _fickling_get_top_class,
    read_pytorch,
)
from pitloom.extract.scanner import discover_ai_models
from pitloom.extract.scanner_project import project_candidates
from tests.warning_helpers import logged_warnings

# -- pickle -----------------------------------------------------------------


def test_fickling_only_sees_the_first_pickle() -> None:
    from fickling.fickle import Pickled  # pylint: disable=import-outside-toplevel

    first = pickle.dumps({"a": 1}, protocol=2)
    seen: list[bytes] = []

    def load(stream: io.BytesIO) -> object:
        seen.append(stream.getvalue())
        return SimpleNamespace(ast=ast.parse("x"))

    with mock.patch.object(Pickled, "load", side_effect=load):
        _fickling_get_top_class(io.BytesIO(first + b"\x00" * 5000))
    assert seen == [first]


def test_too_many_opcodes_never_reach_fickling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fickling.fickle import Pickled  # pylint: disable=import-outside-toplevel

    monkeypatch.setattr(_pickle_bounds, "MAX_PICKLE_OPCODES", 5)
    with mock.patch.object(Pickled, "load", side_effect=AssertionError):
        with pytest.raises(ModelLimitExceeded):
            _fickling_get_top_class(io.BytesIO(pickle.dumps(list(range(50)))))


def test_a_raw_pickle_is_bounded_but_trailing_data_is_not_its_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.pt`` in the legacy format is one small pickle followed by the tensors'
    bytes: the cap applies to the pickle, not the file."""
    monkeypatch.setattr(archive_member, "MAX_ARCHIVE_MEMBER_BYTES", 1000)
    legacy = tmp_path / "legacy.pt"
    legacy.write_bytes(pickle.dumps({"k": 1}, protocol=2) + b"\x00" * 50_000)
    assert read_pytorch(legacy).properties["format_detail"] == "raw pickle"

    big = tmp_path / "big.pt"
    big.write_bytes(pickle.dumps("x" * 5000, protocol=2))
    with pytest.raises(ModelOverCap) as excinfo:
        read_pytorch(big)
    # Not an archive member: the reason says what the file is.
    assert excinfo.value.member is None
    assert excinfo.value.reason == "larger than the 1000-byte first-pickle cap"


def test_a_raw_pickle_over_the_cap_is_reported_as_a_file_not_a_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(archive_member, "MAX_ARCHIVE_MEMBER_BYTES", 1000)
    (tmp_path / "big.pt").write_bytes(pickle.dumps("x" * 5000, protocol=2))
    files = [ProjectFile(physical_path="big.pt", distribution_path="big.pt")]
    # pylint: disable-next=unbalanced-tuple-unpacking
    (model,) = discover_ai_models(project_candidates(tmp_path, files))
    assert not model.provenance  # format-only
    (message,) = logged_warnings(caplog)
    assert message == (
        "FORMAT=pytorch FILE=big.pt: larger than the 1000-byte first-pickle cap;"
        " metadata not read"
    )


# -- fickling's stderr ------------------------------------------------------


@pytest.mark.parametrize(
    ("noise", "quoted"),
    [("line\n::error::forged ", False), ("\x1b[31m", True)],
    ids=["printable", "escaped"],
)
def test_fickling_stderr_becomes_one_bounded_escaped_warning(
    noise: str,
    quoted: bool,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An escaped literal is cut before escaping, keeping its closing quote."""
    from fickling.fickle import Pickled  # pylint: disable=import-outside-toplevel

    def noisy(_stream: io.BytesIO) -> object:
        for _ in range(200):
            sys.stderr.write(noise + "y" * 500 + "\n")
        return SimpleNamespace(ast=ast.parse("result = Foo()"))

    caplog.set_level(logging.WARNING)
    with mock.patch.object(Pickled, "load", side_effect=noisy):
        result = _fickling_get_top_class(io.BytesIO(b"\x80\x02N."))
    assert result == "Foo"
    assert capsys.readouterr().err == ""
    (record,) = caplog.records
    message = record.getMessage()
    assert message.startswith(FICKLING_PREFIX)
    assert len(message) < 300
    assert "\n" not in message
    text = message.removeprefix(FICKLING_PREFIX)
    assert text.startswith("'") == quoted
    assert text.endswith("'" if quoted else "y")


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("load", "fickling failed to parse pickle bytes: "),
        ("walk", "fickling parsed pickle but AST walk failed: "),
    ],
)
def test_a_fickling_failure_is_one_warning_and_no_type(
    stage: str, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    from fickling.fickle import Pickled  # pylint: disable=import-outside-toplevel

    error = KeyError("a\nb")
    load = mock.patch.object(
        Pickled,
        "load",
        side_effect=error if stage == "load" else None,
        return_value=SimpleNamespace(),
    )
    walk = mock.patch.object(pytorch, "_top_class", side_effect=error)
    caplog.set_level(logging.WARNING)
    with load, walk:
        assert _fickling_get_top_class(io.BytesIO(b"\x80\x02N.")) is None
    (record,) = caplog.records
    message = record.getMessage()
    assert message.startswith(expected)
    assert "type_of_model" in message
    assert "\n" not in message


# -- NumPy ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("major", "length", "fits"),
    [
        (1, 10_000, True),
        (1, 10_001, False),
        (2, 10_000, True),
        (2, 0xFFFFFFFF, False),
        (3, 10_001, False),
    ],
)
def test_the_npy_header_length_is_checked_before_it_is_read(
    major: int, length: int, fits: bool
) -> None:
    width = "<H" if major == 1 else "<I"
    stream = io.BytesIO(struct.pack(width, length) + b" " * 20_000)
    if fits:
        assert len(numpy_reader._bounded_header(stream, major).read()) > length
    else:
        with pytest.raises(ModelLimitExceeded):
            numpy_reader._bounded_header(stream, major)
        assert stream.tell() == struct.calcsize(width)  # none of it was read


def test_a_truncated_length_field_is_not_a_limit() -> None:
    with pytest.raises(ValueError, match="truncated"):
        numpy_reader._bounded_header(io.BytesIO(b"\x01"), 2)


@pytest.mark.parametrize("version", [1, 2])
def test_an_npy_file_declaring_a_huge_header_is_refused_before_numpy(
    version: int, tmp_path: Path
) -> None:
    np = pytest.importorskip("numpy")
    path = tmp_path / "m.npy"
    length = struct.pack("<H", 65535) if version == 1 else struct.pack("<I", 2**32 - 1)
    path.write_bytes(b"\x93NUMPY" + bytes([version, 0]) + length + b"{")
    with mock.patch.object(np, "load", side_effect=AssertionError):
        with pytest.raises(ModelLimitExceeded):
            numpy_reader.read_numpy(path)


def test_an_npz_member_declaring_a_4_gib_v2_header_holds_no_big_read(
    tmp_path: Path,
) -> None:
    """The declaration is four bytes; the member inflates to 48 MiB of zeros
    from ~50 KiB. numpy would read up to the declared length first."""
    pytest.importorskip("numpy")
    path = tmp_path / "bomb.npz"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        with zf.open("a.npy", "w", force_zip64=True) as member:
            member.write(b"\x93NUMPY\x02\x00" + struct.pack("<I", 0xFFFFFFF0))
            for _ in range(48):
                member.write(bytes(1 << 20))
    assert path.stat().st_size < 200_000
    tracemalloc.start()
    try:
        with pytest.raises(ModelLimitExceeded, match="header"):
            numpy_reader.read_numpy(path)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024


def test_an_npz_of_thousands_of_members_stops_reading_early(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    path = tmp_path / "many.npz"
    np.savez(path, **{f"a{i:04d}": np.zeros(1) for i in range(1100)})
    with mock.patch.object(
        numpy_reader, "_bounded_header", wraps=numpy_reader._bounded_header
    ) as spy:
        meta = numpy_reader.read_numpy(path)
    assert meta.properties["array_count"] == "1100"  # every member is counted
    assert spy.call_count == 1001  # headers are read for one over the cap only
