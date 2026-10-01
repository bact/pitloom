# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a hostile model file may declare before its parser runs: a pickle's
opcodes (before fickling), fickling's stderr, a GGUF header's counts and an
``.npy`` header's length (before numpy).

See also: :mod:`tests.extract.ai_model.test_archive_member` (inner archive
members) and :mod:`tests.extract.scanner.test_scanner_model_limits` (what
the scanner makes of each).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import ast
import io
import logging
import pickle
import pickletools
import struct
import sys
import tracemalloc
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.extract.ai_model import (
    _gguf_bounds,
    _pickle_bounds,
    archive_member,
    pytorch,
)
from pitloom.extract.ai_model import numpy as numpy_reader
from pitloom.extract.ai_model._gguf_bounds import check_gguf_header
from pitloom.extract.ai_model._pickle_bounds import first_pickle
from pitloom.extract.ai_model.archive_member import ArchiveMemberTooLarge
from pitloom.extract.ai_model.gguf import read_gguf
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.extract.ai_model.pytorch import (
    _fickling_get_top_class,
    read_pytorch,
)

_GGUF_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "gguf"


# -- pickle -----------------------------------------------------------------


def test_first_pickle_ends_at_stop() -> None:
    data = pickle.dumps({"a": [1, 2]}, protocol=2)
    assert first_pickle(data + b"\x00junk after the pickle") == data


@pytest.mark.parametrize("data", [b"", b"\x80\x02N", b"\x80\x99", b"garbage"])
def test_first_pickle_rejects_malformed(data: bytes) -> None:
    with pytest.raises(ValueError, match="pickle"):
        first_pickle(data)


@pytest.mark.parametrize(
    "opcodes",
    [[], [(SimpleNamespace(name="STOP"), None, None)]],
    ids=["no-opcodes", "stop-without-position"],
)
def test_first_pickle_never_slices_without_a_stop_position(
    opcodes: list[tuple[SimpleNamespace, None, None]],
) -> None:
    """``genops`` gives no position for a non-seekable stream; ``data[:None+1]``
    must not be returned as the pickle."""
    with mock.patch.object(pickletools, "genops", return_value=opcodes):
        with pytest.raises(ValueError, match="no STOP"):
            first_pickle(b"\x80\x02N.")


@pytest.mark.parametrize("limit", [5, 6])
def test_first_pickle_opcode_bound_is_inclusive(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    """``PROTO NONE STOP`` is 3 opcodes; ``[1, 2, 3]`` is more."""
    monkeypatch.setattr(_pickle_bounds, "MAX_PICKLE_OPCODES", limit)
    assert first_pickle(b"\x80\x02N.")
    many = pickle.dumps(list(range(3)), protocol=2)  # 9 opcodes
    with pytest.raises(ModelLimitExceeded, match="opcodes"):
        first_pickle(many)


@pytest.mark.parametrize(("opcodes", "refused"), [(250_000, False), (250_001, True)])
def test_the_pickle_opcode_cap_is_250k(opcodes: int, refused: bool) -> None:
    """``PROTO``, ``NONE`` repeated, ``STOP``: *opcodes* in all."""
    data = b"\x80\x02" + b"N" * (opcodes - 2) + b"."
    if refused:
        with pytest.raises(ModelLimitExceeded, match="250000 opcodes"):
            first_pickle(data)
    else:
        assert first_pickle(data) == data


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
    """A legacy ``.pt`` is one small pickle followed by the tensors' bytes:
    the cap applies to the pickle, not the file."""
    monkeypatch.setattr(archive_member, "MAX_ARCHIVE_MEMBER_BYTES", 1000)
    legacy = tmp_path / "legacy.pt"
    legacy.write_bytes(pickle.dumps({"k": 1}, protocol=2) + b"\x00" * 50_000)
    assert read_pytorch(legacy).properties["format_detail"] == "raw pickle"

    big = tmp_path / "big.pt"
    big.write_bytes(pickle.dumps("x" * 5000, protocol=2))
    with pytest.raises(ArchiveMemberTooLarge) as excinfo:
        read_pytorch(big)
    assert excinfo.value.limit == 1000


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
    """Regression: the escaped literal was cut after escaping, losing its
    closing quote."""
    from fickling.fickle import Pickled  # pylint: disable=import-outside-toplevel

    def noisy(_stream: io.BytesIO) -> object:
        for _ in range(200):
            sys.stderr.write(noise + "y" * 500 + "\n")
        return SimpleNamespace(ast=ast.parse("Foo()"))

    caplog.set_level(logging.WARNING)
    with mock.patch.object(Pickled, "load", side_effect=noisy):
        result = _fickling_get_top_class(io.BytesIO(b"\x80\x02N."))
    assert result == "Foo"
    assert capsys.readouterr().err == ""
    (record,) = caplog.records
    message = record.getMessage()
    assert message.startswith("fickling reported")
    assert len(message) < 300
    assert "\n" not in message
    text = message.partition("stderr: ")[2]
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


# -- GGUF -------------------------------------------------------------------


def _gguf(
    n_tensors: int,
    n_kv: int,
    body: bytes = b"",
    *,
    endian: str = "<",
    tail: int = 0,
) -> bytes:
    head = b"GGUF" + struct.pack(endian + "IQQ", 3, n_tensors, n_kv)
    return head + body + b"\0" * tail


def _kv(key: bytes, vtype: int, value: bytes, endian: str = "<") -> bytes:
    return (
        struct.pack(endian + "Q", len(key))
        + key
        + struct.pack(endian + "I", vtype)
        + value
    )


def _array(elem: int, count: int, payload: bytes = b"", endian: str = "<") -> bytes:
    return _kv(b"k", 9, struct.pack(endian + "IQ", elem, count) + payload, endian)


_HOSTILE_GGUF = {
    "tensors-beyond-file": _gguf(10**6, 0),
    "tensors-over-cap": _gguf(2**40, 0),
    "kv-beyond-file": _gguf(0, 10**6),
    "kv-over-cap": _gguf(0, 2**40),
    "string-array-beyond-file": _gguf(0, 1, _array(8, 10**9), tail=64),
    "scalar-array-beyond-file": _gguf(0, 1, _array(4, 10**9), tail=64),
    "string-array-under-cap-beyond-file": _gguf(0, 1, _array(8, 1000), tail=64),
    "scalar-array-under-cap-beyond-file": _gguf(0, 1, _array(4, 1000), tail=64),
    "array-over-cap": _gguf(0, 1, _array(7, 2**40)),
    "string-over-cap": _gguf(0, 1, _kv(b"k", 8, struct.pack("<Q", 2**40))),
    "big-endian": _gguf(0, 1, _array(8, 10**9, endian=">"), endian=">", tail=64),
    "nested": _gguf(
        0, 1, _kv(b"k", 9, struct.pack("<IQ", 9, 1) + struct.pack("<IQ", 8, 10**9))
    ),
    # The reader follows any depth, so the walker refuses what it cannot follow.
    "nested-too-deep": _gguf(
        0,
        1,
        _kv(b"k", 9, struct.pack("<IQ", 9, 1) * 5 + struct.pack("<IQ", 8, 10**9)),
    ),
    # One numpy view per element, scalar or not.
    "scalar-array-over-budget": _gguf(0, 1, _array(0, 10**6, b"\0" * 10**6)),
    "scalar-arrays-sum-over-budget": _gguf(
        0, 2, _array(0, 600_000, b"\0" * 600_000) * 2
    ),
    "tensors-over-budget": _gguf(300_000, 0, tail=24 * 300_000),
}


@pytest.mark.parametrize("case", _HOSTILE_GGUF)
def test_a_hostile_gguf_header_is_refused_before_the_reader(
    case: str, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_HOSTILE_GGUF[case])
    with pytest.raises(ModelLimitExceeded):
        check_gguf_header(path)
    gguf = pytest.importorskip("gguf")
    with mock.patch.object(gguf, "GGUFReader", side_effect=AssertionError):
        with pytest.raises(ModelLimitExceeded):
            read_gguf(path)


@pytest.mark.parametrize(
    "data",
    [
        _gguf(0, 0),
        _gguf(0, 1, _array(4, 3, b"\0" * 12)),  # exactly fills the file
        _gguf(0, 1, _array(8, 2, b"\0" * 16)),  # two empty strings, exactly
        _gguf(0, 1, _kv(b"k", 8, struct.pack("<Q", 100))),  # string cut short
        _gguf(0, 1, _kv(b"k", 99, b"\0" * 8)),  # unknown value type
        _gguf(0, 1, _array(99, 1, b"\0" * 8)),  # unknown element type
        _gguf(1, 1, _kv(b"k", 4, struct.pack("<I", 7)), tail=40),
        _gguf(0, 1, _array(8, 2, struct.pack("<Q", 1) + b"a" + struct.pack("<Q", 0))),
        _gguf(0, 1, _kv(b"k", 8, struct.pack("<Q", 2**40))[:-8]),  # cut short
        b"GGUF",  # shorter than a header
        b"not a gguf file at all, but longer than a header....",
    ],
    ids=[
        "empty",
        "scalar-exact",
        "strings-exact",
        "string-cut",
        "unknown-type",
        "unknown-element",
        "scalar",
        "strings",
        "truncated",
        "short",
        "other",
    ],
)
def test_a_plausible_or_unrecognisable_gguf_is_left_to_the_reader(
    data: bytes, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(data)
    check_gguf_header(path)


def test_an_unreadable_gguf_is_a_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(0, 0))

    def denied(_path: Path) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("pitloom.extract.ai_model.gguf.check_gguf_header", denied)
    with pytest.raises(ValueError, match="Failed to read GGUF file"):
        read_gguf(path)


_EMPTY = struct.pack("<Q", 0)
_NESTED_4 = struct.pack("<IQ", 9, 1) * 3 + struct.pack("<IQ", 0, 1) + b"\0"


@pytest.mark.parametrize(
    ("n_tensors", "arrays", "within"),
    [
        (0, [_array(0, 5, b"\0" * 5)], False),  # a pair (4) + 5 elements
        (0, [_array(0, 4, b"\0" * 4)], True),  # exactly 8
        (0, [_array(8, 4, _EMPTY * 4)], True),  # strings count like scalars
        (0, [_array(8, 5, _EMPTY * 5)], False),
        (0, [_array(0, 1, b"\0")] * 2, False),  # two pairs (8) + 2
        (2, [], True),  # two tensors (8)
        (3, [], False),
        (1, [_array(0, 0)], True),  # a tensor + a pair: 8
        (1, [_array(0, 1, b"\0")], False),  # 4 + 4 + 1
    ],
    ids=[
        "scalar",
        "at-cap",
        "string",
        "strings",
        "pairs",
        "tensors",
        "tensors+1",
        "tensor+pair",
        "tensor+pair+1",
    ],
)
def test_tensors_pairs_and_every_element_share_one_budget(
    n_tensors: int,
    arrays: list[bytes],
    within: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_gguf_bounds, "MAX_GGUF_COUNT", 8)
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(n_tensors, len(arrays), b"".join(arrays), tail=24 * 8))
    if within:
        check_gguf_header(path)
    else:
        with pytest.raises(ModelLimitExceeded):
            check_gguf_header(path)


def test_nesting_is_followed_to_the_limit_and_refused_beyond(tmp_path: Path) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf(0, 1, _kv(b"k", 9, _NESTED_4)))
    check_gguf_header(path)
    path.write_bytes(_gguf(0, 1, _kv(b"k", 9, struct.pack("<IQ", 9, 1) + _NESTED_4)))
    with pytest.raises(ModelLimitExceeded, match="nested"):
        check_gguf_header(path)


def _gguf_version(version: int) -> bytes:
    return b"GGUF" + struct.pack("<IQQ", version, 10**9, 0)  # hostile counts


@pytest.mark.parametrize("version", [1, 4, 99])
def test_a_version_the_reader_rejects_is_left_to_it(
    version: int, tmp_path: Path
) -> None:
    pytest.importorskip("gguf")
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf_version(version))
    check_gguf_header(path)


@pytest.mark.parametrize("reader", ["accepts-4", "unknown"])
def test_a_version_the_walker_does_not_know_but_the_reader_reads_is_refused(
    reader: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: it would be read unbounded."""
    gguf_reader = pytest.importorskip("gguf.gguf_reader")
    if reader == "accepts-4":
        monkeypatch.setattr(gguf_reader, "READER_SUPPORTED_VERSIONS", [2, 3, 4])
    else:  # the reader's own list cannot be found
        monkeypatch.delattr(gguf_reader, "READER_SUPPORTED_VERSIONS")
    path = tmp_path / "m.gguf"
    path.write_bytes(_gguf_version(4))
    with pytest.raises(ModelLimitExceeded, match="version 4"):
        check_gguf_header(path)
    gguf = pytest.importorskip("gguf")
    with mock.patch.object(gguf, "GGUFReader", side_effect=AssertionError):
        with pytest.raises(ModelLimitExceeded):
            read_gguf(path)


@pytest.mark.parametrize("fixture", sorted(_GGUF_FIXTURES.glob("*.gguf")), ids=str)
def test_every_real_gguf_passes(fixture: Path) -> None:
    check_gguf_header(fixture)


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
    assert len(meta.inputs) == 1001  # one over the cap, for the scanner to cut
    assert spy.call_count == 1001
