# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The CRFsuite reader: the fixtures' numbers, what it reads, and one case
per check it makes.

See also: :mod:`pitloom.extract.ai_model.formats.crfsuite`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest

from pitloom.extract.ai_model.formats import (
    FormatError,
    LimitExceeded,
    Limits,
    Malformed,
    UnsupportedVersion,
)
from pitloom.extract.ai_model.formats.crfsuite import CrfsuiteModel, read_crfsuite

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "aimodels" / "crfsuite"
_COMPLETE = (_FIXTURES / "complete.crfsuite").read_bytes()
_MINIMAL = (_FIXTURES / "minimal.model").read_bytes()

# The complete fixture's layout, read here so the cases below name chunks,
# not numbers.
_SIZE = len(_COMPLETE)
_OFF_FEAT, _OFF_LAB, _OFF_ATTR, _OFF_LREF, _OFF_AREF = struct.unpack_from(
    "<5I", _COMPLETE, 28
)
_LAB_SIZE, _, _, _, _BWD_OFF = struct.unpack_from("<5I", _COMPLETE, _OFF_LAB + 4)
_NUM_LABELS = 5


def _record(label_id: int) -> int:
    """File offset of label *label_id*'s record."""
    (rec_off,) = struct.unpack_from("<I", _COMPLETE, _OFF_LAB + _BWD_OFF + 4 * label_id)
    return int(_OFF_LAB + rec_off)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _mutate(data: bytes, *patches: tuple[int, bytes]) -> bytes:
    out = bytearray(data)
    for offset, raw in patches:
        out[offset : offset + len(raw)] = raw
    return bytes(out)


def _read(data: bytes, limits: Limits | None = None) -> CrfsuiteModel:
    return read_crfsuite(io.BytesIO(data), limits or Limits())


class _Recording(io.BytesIO):
    """Records the ``(offset, length)`` of every read."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.reads: list[tuple[int, int]] = []

    def read(self, size: int | None = -1, /) -> bytes:
        start = self.tell()
        data = super().read(size)
        self.reads.append((start, len(data)))
        return data

    def bytes_in(self, start: int, end: int) -> int:
        """How many bytes read fall in ``[start, end)``."""
        return sum(max(0, min(off + n, end) - max(off, start)) for off, n in self.reads)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            _COMPLETE,
            CrfsuiteModel(
                "FOMC", 100, 24, 14, ("บุคคล", "O", "B-LOC", "I PER/x", "E-X:1")
            ),
        ),
        (_MINIMAL, CrfsuiteModel("FOMC", 100, 4, 2, ("I", "E"))),
    ],
    ids=["complete", "minimal"],
)
def test_the_fixtures_read_as_documented(data: bytes, expected: CrfsuiteModel) -> None:
    assert struct.unpack_from("<I", data, 16) == (0,)  # header num_features
    assert _read(data) == expected


def test_limits_equal_to_the_fixture_are_enough() -> None:
    limits = Limits(max_crfsuite_labels=_NUM_LABELS, max_crfsuite_label_bytes=_LAB_SIZE)
    assert len(_read(_COMPLETE, limits).labels) == _NUM_LABELS


def test_reads_the_headers_and_the_labels_chunk_only() -> None:
    source = _Recording(_COMPLETE)
    read_crfsuite(source, Limits())
    total = sum(n for _, n in source.reads)
    assert total == 48 + 12 + _LAB_SIZE + 24 + 12 + 12
    assert total <= Limits().max_crfsuite_label_bytes + 108
    assert source.bytes_in(_OFF_FEAT + 12, _OFF_LAB) == 0  # feature weights
    assert source.bytes_in(_OFF_ATTR + 24, _OFF_LREF) == 0  # attribute strings
    assert source.bytes_in(_OFF_LREF + 12, _OFF_AREF) == 0
    assert source.bytes_in(_OFF_AREF + 12, _SIZE) == 0


def test_too_many_labels_is_refused_before_the_labels_chunk_is_read() -> None:
    source = _Recording(_COMPLETE)
    with pytest.raises(LimitExceeded, match="labels"):
        read_crfsuite(source, Limits(max_crfsuite_labels=_NUM_LABELS - 1))
    assert source.bytes_in(_OFF_LAB, _SIZE) == 0


def test_an_oversized_labels_chunk_is_refused_unread() -> None:
    source = _Recording(_COMPLETE)
    with pytest.raises(LimitExceeded, match="CQDB"):
        read_crfsuite(source, Limits(max_crfsuite_label_bytes=_LAB_SIZE - 1))
    assert source.bytes_in(_OFF_LAB, _SIZE) == 24  # its header only


@pytest.mark.parametrize("length", [*range(61), _SIZE - 1])
def test_a_truncated_file_is_malformed(length: int) -> None:
    with pytest.raises(Malformed) as caught:
        _read(_COMPLETE[:length])
    reason = "header truncated" if length < 48 else "declared size"
    assert reason in caught.value.reason


def test_a_short_read_is_truncation() -> None:
    class Short(io.BytesIO):
        """Every read one byte short."""

        def read(self, size: int | None = -1, /) -> bytes:
            return super().read(size)[:-1]

    with pytest.raises(Malformed, match="truncated"):
        read_crfsuite(Short(_COMPLETE), Limits())


def test_bytes_past_size_are_ignored() -> None:
    data = _COMPLETE + b"garbage"
    assert data != _COMPLETE
    assert _read(data) == _read(_COMPLETE)


def test_zero_labels_are_valid() -> None:
    data = _mutate(
        _COMPLETE,
        (20, _u32(0)),  # header num_labels
        (_OFF_LAB + 16, _u32(0) + _u32(0)),  # bwd_size, bwd_offset
        (_OFF_LAB + 24, bytes(2048)),  # hash-table refs: all empty
    )
    assert _read(data).labels == ()


@pytest.mark.parametrize(
    ("raw", "label"),
    [(b"\xff\xfe", "\\xff\\xfeLOC"), (b"B\0", "B")],
    ids=["invalid-utf8", "inner-nul"],
)
def test_label_bytes_decode_without_failing(raw: bytes, label: str) -> None:
    data = _mutate(_COMPLETE, (_record(2) + 8, raw))  # "B-LOC"
    assert _read(data).labels[2] == label


_BAD = [
    # 2-3: magic, type, version
    ("magic", [(0, b"lCRX")], Malformed, "magic"),
    ("type", [(8, b"ABCD")], UnsupportedVersion, "FOMC"),
    ("version-99", [(12, _u32(99))], UnsupportedVersion, "version"),
    ("version-101", [(12, _u32(101))], UnsupportedVersion, "version"),
    # 4: size
    ("size-47", [(4, _u32(47))], Malformed, "declared size"),
    ("size-past-end", [(4, _u32(_SIZE + 1))], Malformed, "declared size"),
    # 5: offsets
    ("off-in-header", [(28, _u32(47))], Malformed, "chunk offsets"),
    ("off-equal", [(32, _u32(_OFF_ATTR))], Malformed, "chunk offsets"),
    ("off-no-room", [(44, _u32(_SIZE - 11))], Malformed, "chunk offsets"),
    # 6: FEAT
    ("feat-tag", [(_OFF_FEAT, b"FEAX")], Malformed, "FEAT chunk tag"),
    ("feat-size", [(_OFF_FEAT + 4, _u32(493))], Malformed, "FEAT chunk size"),
    (
        "feat-overlap",
        [(_OFF_FEAT + 4, _u32(_OFF_LAB - _OFF_FEAT + 20) + _u32(25))],
        Malformed,
        "overlaps",
    ),
    # 8: labels CQDB header
    ("lab-tag", [(_OFF_LAB, b"CQDX")], Malformed, "labels CQDB tag"),
    ("lab-order", [(_OFF_LAB + 12, _u32(0x71534462))], UnsupportedVersion, "order"),
    ("lab-flag", [(_OFF_LAB + 8, _u32(1))], UnsupportedVersion, "flag"),
    # 9: labels CQDB size
    ("lab-size-23", [(_OFF_LAB + 4, _u32(23))], Malformed, "labels CQDB size"),
    (
        "lab-size-over",
        [(_OFF_LAB + 4, _u32(_OFF_ATTR - _OFF_LAB + 1))],
        Malformed,
        "labels CQDB size",
    ),
    # 10: backward array
    ("bwd-count", [(_OFF_LAB + 16, _u32(4))], Malformed, "count differs"),
    ("bwd-num-100", [(20, _u32(100))], Malformed, "count differs"),
    ("bwd-low", [(_OFF_LAB + 20, _u32(2071))], Malformed, "backward array"),
    (
        "bwd-past",
        [(_OFF_LAB + 20, _u32(_LAB_SIZE - 4 * _NUM_LABELS + 1))],
        Malformed,
        "backward array",
    ),
    # 11: records
    ("rec-low", [(_OFF_LAB + _BWD_OFF, _u32(2071))], Malformed, "record outside"),
    (
        "rec-high",
        [(_OFF_LAB + _BWD_OFF, _u32(_LAB_SIZE - 7))],
        Malformed,
        "record outside",
    ),
    ("rec-id", [(_record(1), _u32(0))], Malformed, "inconsistent"),
    ("ksize-0", [(_record(1) + 4, _u32(0))], Malformed, "inconsistent"),
    (
        "ksize-past",
        [(_record(4) + 4, _u32(_OFF_LAB + _LAB_SIZE - _record(4) - 8 + 1))],
        Malformed,
        "inconsistent",
    ),
    ("no-nul", [(_record(1) + 9, b"x")], Malformed, "NUL"),  # "O\0"
    # 12: attributes CQDB header
    ("attr-tag", [(_OFF_ATTR, b"CQDX")], Malformed, "attributes CQDB tag"),
    ("attr-order", [(_OFF_ATTR + 12, _u32(0x71534462))], Malformed, "order"),
    ("attr-count", [(_OFF_ATTR + 16, _u32(13))], Malformed, "attributes CQDB count"),
    ("attr-size-23", [(_OFF_ATTR + 4, _u32(23))], Malformed, "attributes CQDB size"),
    (
        "attr-size-over",
        [(_OFF_ATTR + 4, _u32(_OFF_LREF - _OFF_ATTR + 1))],
        Malformed,
        "attributes CQDB size",
    ),
    # 13: LFRF, AFRF
    ("lfrf-tag", [(_OFF_LREF, b"LFRX")], Malformed, "LFRF"),
    ("afrf-tag", [(_OFF_AREF, b"AFRX")], Malformed, "AFRF chunk tag"),
    ("afrf-num", [(_OFF_AREF + 8, _u32(13))], Malformed, "AFRF count"),
    ("lfrf-num-huge", [(_OFF_LREF + 8, _u32(2**30))], Malformed, "LFRF count"),
    # a forged attribute count is pinned by the file: all three fields agree
    # (header, attributes CQDB, AFRF) and it still cannot exceed the chunks
    (
        "attr-count-forged",
        [
            (24, _u32(2**32 - 1)),
            (_OFF_ATTR + 16, _u32(2**32 - 1)),
            (_OFF_AREF + 8, _u32(2**32 - 1)),
        ],
        Malformed,
        "attribute",
    ),
    # AFRF's offset array must fit in ``size``: shrink size to end right at AFRF
    ("afrf-past-size", [(4, _u32(_OFF_AREF + 12))], Malformed, "does not fit"),
    ("attr-bwd-past", [(_OFF_ATTR + 20, _u32(2**31))], Malformed, "attributes back"),
    ("labels-size-2071", [(_OFF_LAB + 4, _u32(2071))], Malformed, "labels CQDB size"),
    ("attr-size-2071", [(_OFF_ATTR + 4, _u32(2071))], Malformed, "attributes CQDB"),
]


@pytest.mark.parametrize(
    ("patches", "error", "reason"),
    [case[1:] for case in _BAD],
    ids=[case[0] for case in _BAD],
)
def test_each_check_refuses_its_case(
    patches: list[tuple[int, bytes]], error: type[FormatError], reason: str
) -> None:
    data = _mutate(_COMPLETE, *patches)
    assert data != _COMPLETE
    with pytest.raises(error) as caught:
        _read(data)
    assert reason in caught.value.reason
