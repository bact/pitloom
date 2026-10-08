# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The CRFsuite reader on hostile input: misplaced chunks, every field at
its boundary values, every byte flipped, and a seeded mutation loop.

Every outcome is a :class:`CrfsuiteModel` or a :class:`FormatError`, never
another exception, and no input makes the reader read more than
``max_crfsuite_labels_chunk_bytes + 108`` bytes.

See also: :mod:`pitloom.extract.ai_model.formats.crfsuite` and
``test_crfsuite.py`` (one case per check, on the fixtures).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import io
import random
import struct
from pathlib import Path

import pytest

from pitloom.extract.ai_model.formats import (
    FormatError,
    Limits,
    Malformed,
)
from pitloom.extract.ai_model.formats.crfsuite import CrfsuiteModel, read_crfsuite

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "aimodels" / "crfsuite"
_COMPLETE = (_FIXTURES / "complete.crfsuite").read_bytes()
_MINIMAL = (_FIXTURES / "minimal.model").read_bytes()
_LIMITS = Limits()
# Bounds every fixture exceeds: the labels stay unread
_TIGHT = Limits(max_crfsuite_labels=1, max_crfsuite_labels_chunk_bytes=2072)
_BUDGET = _LIMITS.max_crfsuite_labels_chunk_bytes + 108
_CHUNKS = ("feat", "lab", "attr", "lref", "aref")

_Outcome = CrfsuiteModel | type[FormatError]


class _Counting(io.BytesIO):
    """Counts every byte read."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.total = 0

    def read(self, size: int | None = -1, /) -> bytes:
        data = super().read(size)
        self.total += len(data)
        return data


def _outcome(data: bytes, limits: Limits = _LIMITS) -> _Outcome:
    """The model, or the class of the :class:`FormatError` raised; any other
    exception propagates. Checks the read budget either way."""
    source = _Counting(data)
    try:
        result: _Outcome = read_crfsuite(source, limits)
    except FormatError as exc:
        result = type(exc)
    assert source.total <= _BUDGET
    return result


def _patched(data: bytes, offset: int, fmt: str, *values: int) -> bytes:
    out = bytearray(data)
    struct.pack_into(fmt, out, offset, *values)
    return bytes(out)


def _offsets(data: bytes) -> tuple[int, ...]:
    return struct.unpack_from("<5I", data, 28)


def _fields(data: bytes) -> list[int]:
    """Offset of every u32 the reader interprets: header, chunk headers,
    the labels' backward array and each label record's id and key size."""
    feat, lab, attr, lref, aref = _offsets(data)
    fields = [4 * i for i in (1, 3, 4, 5, 6, 7, 8, 9, 10, 11)]
    fields += [off + 4 * j for off in (feat, lref, aref) for j in (1, 2)]
    fields += [off + 4 * j for off in (lab, attr) for j in range(1, 6)]
    num, bwd = struct.unpack_from("<2I", data, lab + 16)
    for i in range(num):
        (rec,) = struct.unpack_from("<I", data, lab + bwd + 4 * i)
        fields += [lab + bwd + 4 * i, lab + rec, lab + rec + 4]
    return fields


def _read_region(data: bytes) -> set[int]:
    """Every byte position a well-formed file has read."""
    feat, lab, attr, lref, aref = _offsets(data)
    (lab_size,) = struct.unpack_from("<I", data, lab + 4)
    spans = [(0, 48), (feat, 12), (lab, lab_size), (attr, 24), (lref, 12), (aref, 12)]
    return {pos for start, size in spans for pos in range(start, start + size)}


def _misplaced(index: int, kind: str) -> bytes:
    """``complete`` with chunk offset *index* moved by *kind*."""
    offsets = list(_offsets(_COMPLETE))
    if kind == "swap":
        other = index + 1 if index < 4 else index - 1
        offsets[index], offsets[other] = offsets[other], offsets[index]
    else:
        offsets[index] = {"zero": 0, "header": 40, "past": len(_COMPLETE)}[kind]
    return _patched(_COMPLETE, 28, "<5I", *offsets)


@pytest.mark.parametrize("kind", ["zero", "header", "past", "swap"])
@pytest.mark.parametrize("index", range(5), ids=_CHUNKS)
def test_a_misplaced_chunk_offset_is_malformed(index: int, kind: str) -> None:
    data = _misplaced(index, kind)
    assert data != _COMPLETE
    with pytest.raises(Malformed, match="chunk offsets"):
        read_crfsuite(io.BytesIO(data), _LIMITS)


@pytest.mark.parametrize(
    ("data", "error", "reason"),
    [
        (_patched(_COMPLETE, 4, "<I", 0), Malformed, "declared size"),
        (_COMPLETE[: len(_COMPLETE) // 2], Malformed, "declared size"),
        (_MINIMAL[: len(_MINIMAL) // 2], Malformed, "declared size"),
        # over the label cap but not the labels chunk's count: inconsistent
        (
            _patched(_COMPLETE, 20, "<I", _LIMITS.max_crfsuite_labels + 1),
            Malformed,
            "count differs",
        ),
    ],
    ids=["size-0", "half", "half-minimal", "labels-over-limit"],
)
def test_header_level_damage_is_refused(
    data: bytes, error: type[FormatError], reason: str
) -> None:
    with pytest.raises(error) as caught:
        read_crfsuite(io.BytesIO(data), _LIMITS)
    assert reason in caught.value.reason


def _hash_table_ref(field: int, value: int) -> bytes:
    """``complete`` with its last non-empty labels hash-table ref's
    *field* (0 offset, 1 count) set to *value*."""
    lab = _offsets(_COMPLETE)[1]
    refs = struct.unpack_from("<512I", _COMPLETE, lab + 24)
    table = max(t for t in range(256) if refs[2 * t + 1])
    return _patched(_COMPLETE, lab + 24 + 8 * table + 4 * field, "<I", value)


# Reader bug found in step 3: the reader ignores the labels CQDB's 256
# hash-table refs, but CRFsuite sizes its backward array from them (the sum
# of each table's count / 2, cqdb.c cqdb_reader()) and reads each table's
# buckets at its offset. python-crfsuite 0.9.12 crashes on all three cases
# while the reader returns five labels.
@pytest.mark.parametrize(
    ("field", "value"),
    [(1, 0), (1, 1 << 28), (0, 0xFFFFFF00), (0, 8), (0, 2071)],
    ids=["count-short", "count-huge", "offset-past", "offset-low", "offset-2071"],
)
def test_labels_hash_tables_inconsistent_with_the_records(
    field: int, value: int
) -> None:
    data = _hash_table_ref(field, value)
    assert data != _COMPLETE
    with pytest.raises(Malformed, match="hash table"):
        read_crfsuite(io.BytesIO(data), _LIMITS)


def test_a_labels_cqdb_without_room_for_hash_tables_is_refused() -> None:
    # CRFsuite's writer always pads a CQDB to its first record (2,072 bytes),
    # even with no labels, and its reader refuses a smaller one.
    lab = _offsets(_COMPLETE)[1]
    data = _patched(_COMPLETE, 20, "<I", 0)  # header num_labels
    data = _patched(data, lab + 4, "<I", 2071)  # labels CQDB size
    data = _patched(data, lab + 16, "<2I", 0, 0)  # backward array
    with pytest.raises(Malformed, match="CQDB size"):
        read_crfsuite(io.BytesIO(data), _LIMITS)


@pytest.mark.parametrize("limits", [_LIMITS, _TIGHT], ids=["default", "tight"])
@pytest.mark.parametrize("data", [_COMPLETE, _MINIMAL], ids=["complete", "minimal"])
def test_every_field_at_every_boundary_value(data: bytes, limits: Limits) -> None:
    size = len(data)
    refused = 0
    for offset in _fields(data):
        (original,) = struct.unpack_from("<I", data, offset)
        values = {0, 1, size - 1, size, size + 1, 2**31, 2**32 - 1}
        values |= {(original - 1) & 0xFFFFFFFF, (original + 1) & 0xFFFFFFFF}
        for value in sorted(values - {original}):
            outcome = _outcome(_patched(data, offset, "<I", value), limits)
            refused += not isinstance(outcome, CrfsuiteModel)
            if isinstance(outcome, CrfsuiteModel) and limits is _TIGHT:
                assert outcome.labels is None
    assert refused > 0


def test_every_byte_of_minimal_truncated_and_flipped() -> None:
    original = _outcome(_MINIMAL)
    assert isinstance(original, CrfsuiteModel)
    read = _read_region(_MINIMAL)
    for pos, byte in enumerate(_MINIMAL):
        assert _outcome(_MINIMAL[:pos]) is Malformed
        flipped = _outcome(_patched(_MINIMAL, pos, "B", byte ^ 0xFF))
        if pos not in read:
            assert flipped == original, pos


def _mutant(rng: random.Random, data: bytes) -> bytes:
    """One seeded mutation: byte flips (mostly where the reader reads), a
    u32 field set to an edge or random value, or a cut/extended file."""
    choice = rng.randrange(4)
    if choice == 0:
        read = sorted(_read_region(data))
        out = bytearray(data)
        for _ in range(rng.choice((1, 1, 2, 4))):
            out[rng.choice(read)] = rng.randrange(256)
        return bytes(out)
    if choice == 1:
        value = rng.choice((0, 1, len(data), 2**31, 2**32 - 1, rng.getrandbits(32)))
        return _patched(data, rng.choice(_fields(data)), "<I", value)
    if choice == 2:
        out = bytearray(data)
        out[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
        return bytes(out)
    return data[: rng.randrange(len(data))] + bytes(rng.randrange(2) * 64)


@pytest.mark.parametrize("data", [_COMPLETE, _MINIMAL], ids=["complete", "minimal"])
def test_seeded_mutations_raise_only_format_errors(data: bytes) -> None:
    rng = random.Random(20261008)  # nosec B311: seeded test input
    accepted = 0
    for _ in range(2000):
        mutant = _mutant(rng, data)
        outcome = _outcome(mutant)
        if isinstance(outcome, CrfsuiteModel):  # bytes past ``size`` are ignored
            accepted += 1
            assert _outcome(mutant + b"\xff" * 9) == outcome
    assert 0 < accepted < 2000
