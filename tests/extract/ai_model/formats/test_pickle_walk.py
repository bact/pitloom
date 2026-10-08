# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The pickle opcode walk: the same opcodes as :func:`pickletools.genops`
(the drift guard), relative positions on a file object, and what it raises.

See also: :mod:`tests.extract.ai_model.test_pickle_bounds` (the bounds, as
Pitloom applies them).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import dataclasses
import io
import pickle
import pickletools
import zipfile
from pathlib import Path

import pytest

from pitloom.extract.ai_model.formats import LimitExceeded, Limits, Malformed
from pitloom.extract.ai_model.formats.pickle_walk import (
    Opcode,
    first_pickle,
    walk_opcodes,
)

_PYTORCH = Path(__file__).parents[3] / "fixtures" / "aimodels" / "pytorch"
_SHARED = [7]
_OBJECTS = [
    0,
    -1,
    255,
    2**31,
    -(2**63),
    10**40,  # LONG text at protocol 0, LONG1 after
    True,  # the "I01" hack at protocol 0
    False,
    1.5,
    -0.0,
    "text\né",
    b"\x00bytes",
    bytearray(b"ba"),
    None,
    (1, (2, [3, {"k": {4}}])),
    frozenset({1}),
    [_SHARED, _SHARED],  # the second is a memo GET
]


def _fixture_pickles() -> list[bytes]:
    found = []
    for path in sorted(_PYTORCH.glob("*.pt*")):
        with zipfile.ZipFile(path) as archive:
            found += [archive.read(n) for n in archive.namelist() if n.endswith(".pkl")]
    return found


_PICKLES = [
    pickle.dumps(_OBJECTS, protocol=p) for p in range(pickle.HIGHEST_PROTOCOL + 1)
] + _fixture_pickles()


@pytest.mark.parametrize("data", _PICKLES, ids=lambda d: f"{len(d)}B")
def test_the_walk_yields_the_opcodes_genops_yields(data: bytes) -> None:
    expected = [(op.name, pos) for op, _arg, pos in pickletools.genops(data)]
    assert [tuple(op) for op in walk_opcodes(data, Limits())] == expected
    walk = first_pickle(data + b"trailing", Limits())
    assert (walk.end, walk.opcodes) == (len(data), len(expected))


def test_the_fixtures_and_every_protocol_are_covered() -> None:
    """Non-vacuous: both fixture pickles, and the decimal opcodes the cap is
    about, are in the drift set."""
    assert len(_PICKLES) == pickle.HIGHEST_PROTOCOL + 1 + 2
    names = {op.name for op, _arg, _pos in pickletools.genops(_PICKLES[0])}
    assert {"INT", "LONG", "GET", "PUT"} <= names


def test_positions_are_relative_to_where_a_file_object_starts() -> None:
    stream = io.BytesIO(b"prefix" + b"\x80\x02N." + b"rest")
    stream.seek(6)
    assert list(walk_opcodes(stream, Limits())) == [
        Opcode("PROTO", 0),
        Opcode("NONE", 2),
        Opcode("STOP", 3),
    ]
    stream.seek(6)
    assert first_pickle(stream, Limits()) == (4, 3)
    assert stream.tell() == 10


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "pickle exhausted before seeing STOP"),
        (b"\x80\x02N\xff", "at position 3, opcode b'\\xff' unknown"),
        (b"\x80\x02I1", "no newline found"),
        (b"I1  ", "no newline found"),  # cut short at exactly the window
        (b"Sx\n.", "no string quotes"),  # the table's reader raises
        (b"V\\u12\n.", "unicode"),  # a UnicodeDecodeError from the reader
    ],
    ids=[
        "empty",
        "unknown",
        "decimal-cut",
        "decimal-cut-at-window",
        "string",
        "unicode",
    ],
)
def test_what_is_malformed(data: bytes, reason: str) -> None:
    with pytest.raises(Malformed) as excinfo:
        first_pickle(data, Limits(max_pickle_decimal_digits=1))
    assert reason in excinfo.value.reason


@pytest.mark.parametrize(
    ("limits", "data", "reason"),
    [
        (Limits(max_pickle_opcodes=2), b"\x80\x02N.", "more than 2 opcodes"),
        (Limits(max_pickle_decimal_digits=3), b"I1234\n.", "over 3 digits"),
        (Limits(max_pickle_decimal_digits=3), b"I1_2_3_\n.", "over 5 bytes"),
    ],
    ids=["opcodes", "digits", "bytes"],
)
def test_what_is_over_a_limit(limits: Limits, data: bytes, reason: str) -> None:
    with pytest.raises(LimitExceeded) as excinfo:
        first_pickle(data, limits)
    assert reason in excinfo.value.reason


def test_the_decimal_window_holds_a_sign_digits_and_l() -> None:
    limits = Limits(max_pickle_decimal_digits=3)
    assert limits.max_pickle_decimal_bytes == 5
    assert first_pickle(b"L-999L\n.", limits).end == 8


@pytest.mark.parametrize("field", [field.name for field in dataclasses.fields(Limits)])
def test_a_limit_below_one_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        Limits(**{field: 0})
    with pytest.raises(ValueError, match=field):
        Limits(**{field: True})


def test_running_out_of_memory_is_not_malformed() -> None:
    """A reader's declared length can ask for more than there is; that is
    the caller's failure to bound the stream, not a malformed pickle."""

    class Exhausted(io.BytesIO):
        """A stream that cannot allocate a declared length."""

        def read(self, size: int | None = -1) -> bytes:
            if size is not None and size > 1:
                raise MemoryError
            return super().read(size)

    with pytest.raises(MemoryError):
        first_pickle(
            Exhausted(b"\x8e" + (8).to_bytes(8, "little") + b"x" * 8), Limits()
        )


class _Counting(io.BytesIO):
    """Counts every byte handed out through ``read`` and ``readline``."""

    handed_out = 0

    def read(self, size: int | None = -1) -> bytes:
        data = super().read(size)
        self.handed_out += len(data)
        return data

    def readline(self, size: int | None = -1) -> bytes:
        data = super().readline(size)
        self.handed_out += len(data)
        return data


@pytest.mark.parametrize("code", [b"I", b"L", b"g", b"p"])
def test_a_decimal_argument_is_read_no_further_than_its_window(code: bytes) -> None:
    """The cost bound, independent of how fast the interpreter converts
    numbers (CPython 3.12 and later convert big ones far faster than 3.10)."""
    stream = _Counting(b"\x80\x02" + code + b"9" * 1_000_000 + b"\n.")
    with pytest.raises(LimitExceeded, match="over 4300 digits"):
        first_pickle(stream, Limits())
    assert stream.handed_out == 2 + 1 + 4303
