# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The GGUF header reader: what it refuses as malformed, what it reads, and
where each bound stops it (a partial read, never a refusal).

See also: :mod:`pitloom.extract.ai_model.formats.gguf_header` and
:mod:`tests.extract.ai_model.test_gguf_bounds` (Pitloom's adapter).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import struct
import time
from typing import Any

import pytest

from pitloom.extract.ai_model.formats import Limits, Malformed
from pitloom.extract.ai_model.formats.gguf_header import (
    DeclaredBeyondFile,
    GgufArray,
    GgufHeader,
    UnknownVersion,
    read_gguf_header,
)
from tests.extract.ai_model.gguf_builders import (
    ARRAY,
    FLOAT32,
    STRING,
    UINT8,
    UINT32,
    array,
    gguf_file,
    gguf_with_tensors,
    kv,
    string,
    tensor_info,
)

_EMPTY = struct.pack("<Q", 0)
_NESTED_4 = struct.pack("<IQ", ARRAY, 1) * 3 + struct.pack("<IQ", UINT8, 1) + b"\0"


def _read(data: bytes, keep: dict[str, int] | None = None, **bounds: int) -> GgufHeader:
    return read_gguf_header(data, Limits(**bounds), keep)


def _strings(*texts: str) -> bytes:
    return b"".join(string(text) for text in texts)


def _array_field(header: GgufHeader, key: str) -> GgufArray:
    (value,) = [f.value for f in header.fields if f.key == key]
    assert isinstance(value, GgufArray)
    return value


# -- refused ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "what", "count"),
    [
        (gguf_file(10**6, 0), "tensors", 10**6),
        (gguf_file(2**40, 0), "tensors", 2**40),
        (gguf_file(0, 10**6), "pairs", 10**6),
        (gguf_file(0, 2**40), "pairs", 2**40),
        (gguf_file(0, 1, array(STRING, 10**9), tail=64), "array", 10**9),
        (gguf_file(0, 1, array(UINT32, 10**9), tail=64), "array", 10**9),
        (gguf_file(0, 1, array(STRING, 1000), tail=64), "array", 1000),
        (gguf_file(0, 1, array(UINT32, 1000), tail=64), "array", 1000),
        (gguf_file(0, 1, array(ARRAY, 10**9), tail=64), "array", 10**9),
        (
            gguf_file(
                0,
                1,
                kv(b"k", ARRAY, struct.pack("<IQ", ARRAY, 1))
                + struct.pack("<IQ", STRING, 10**9),
            ),
            "array",
            10**9,
        ),
        (
            gguf_file(0, 1, array(STRING, 10**9, endian=">"), endian=">", tail=64),
            "array",
            10**9,
        ),
    ],
    ids=[
        "tensors",
        "tensors-2**40",
        "pairs",
        "pairs-2**40",
        "strings",
        "scalars",
        "strings-1000",
        "scalars-1000",
        "arrays",
        "nested",
        "big-endian",
    ],
)
def test_a_count_beyond_the_file_is_refused(data: bytes, what: str, count: int) -> None:
    with pytest.raises(DeclaredBeyondFile) as excinfo:
        _read(data)
    assert (excinfo.value.what, excinfo.value.count) == (what, count)


_ALIGNMENT = b"general.alignment"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"GGUF", "shorter than a GGUF header"),
        (b"not a gguf file at all, but longer than a header", "magic"),
        (gguf_file(0, 1, kv(b"k", STRING, struct.pack("<Q", 100))), "past the end"),
        (gguf_file(0, 1, kv(b"k", 99, b"\0" * 8)), "unknown value type 99"),
        (gguf_file(0, 1, array(99, 1, b"\0" * 8)), "unknown array element type"),
        (gguf_file(0, 1, b"\0\0\0"), "truncated"),
        (gguf_file(0, 1, kv(b"k", UINT32, b"\0")), "truncated"),
        (
            gguf_file(0, 2, kv(b"k", UINT8, b"\0") * 2),
            "duplicate key 'k'",
        ),
        (gguf_file(0, 1, kv(b"\xff", UINT8, b"\0")), "not UTF-8"),
        (
            gguf_with_tensors([tensor_info("t", (1,)), tensor_info("t", (2,))]),
            "duplicate tensor 't'",
        ),
        (
            gguf_file(1, 0, string("t") + struct.pack("<I", 2**20), tail=40),
            "runs past the end",
        ),
        (
            gguf_with_tensors([], 1, kv(_ALIGNMENT, UINT8, b"\x40")),
            "no uint32",
        ),
        (
            gguf_with_tensors([], 1, kv(_ALIGNMENT, UINT32, struct.pack("<I", 3))),
            "no power of two",
        ),
        (
            gguf_with_tensors([], 1, kv(_ALIGNMENT, UINT32, struct.pack("<I", 0))),
            "no power of two",
        ),
        (
            gguf_file(0, 1, array(STRING, 2, _EMPTY + struct.pack("<Q", 9) + b"a")),
            "past the end",
        ),
    ],
    ids=[
        "short",
        "other",
        "string-cut",
        "unknown-type",
        "unknown-element",
        "key-cut",
        "value-cut",
        "duplicate-key",
        "key-not-utf8",
        "duplicate-tensor",
        "tensor-cut",
        "alignment-type",
        "alignment-3",
        "alignment-0",
        "hopped-string-cut",
    ],
)
def test_a_malformed_header_is_refused(data: bytes, reason: str) -> None:
    with pytest.raises(Malformed, match=reason):
        _read(data)


_HUGE = struct.pack("<Q", 1 << 40)


@pytest.mark.parametrize(
    "body",
    [
        _HUGE + b"k" * 8,
        kv(b"k", STRING, _HUGE + b"v" * 8),
        kv(b"d", ARRAY, struct.pack("<IQ", STRING, 1) + _HUGE + b"v" * 8),
    ],
    ids=["key", "value", "kept-element"],
)
def test_a_string_past_the_end_is_malformed_even_over_a_cap(body: bytes) -> None:
    """A declared length never decides a cap: the file cannot hold it."""
    with pytest.raises(Malformed, match="past the end"):
        _read(
            gguf_file(0, 1, body, tail=8),
            {"d": 1},
            max_gguf_string_bytes=4,
            max_gguf_total_string_bytes=4,
        )


@pytest.mark.parametrize("version", [0, 1, 4, 99])
def test_an_unknown_version_is_refused_with_its_number(version: int) -> None:
    with pytest.raises(UnknownVersion) as excinfo:
        _read(b"GGUF" + struct.pack("<IQQ", version, 10**9, 0))
    assert excinfo.value.version == version


# -- read ------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        gguf_file(0, 0),
        gguf_file(0, 1, array(UINT32, 3, b"\0" * 12)),  # exactly fills the file
        gguf_file(0, 1, array(STRING, 2, _EMPTY * 2)),  # two empty strings
        gguf_file(0, 1, kv(b"k", ARRAY, _NESTED_4)),  # nested to the limit
        gguf_file(0, 1, array(99, 0)),  # an empty array of any type
    ],
    ids=["empty", "scalar-exact", "strings-exact", "nested-4", "empty-unknown"],
)
def test_a_well_formed_header_is_read_whole(data: bytes) -> None:
    header = _read(data)
    assert header.stop is None
    assert header.tensors == ()
    assert all(
        f.value.complete for f in header.fields if isinstance(f.value, GgufArray)
    )


@pytest.mark.parametrize("endian", ["<", ">"])
def test_values_are_read_in_the_files_byte_order(endian: str) -> None:
    body = kv(b"n", UINT32, struct.pack(endian + "I", 7), endian) + kv(
        b"f", FLOAT32, struct.pack(endian + "f", 1e-6), endian
    )
    header = _read(gguf_file(0, 2, body, endian=endian))
    assert header.big_endian is (endian == ">")
    assert [(f.key, f.value) for f in header.fields] == [
        ("n", 7),
        ("f", struct.unpack("<f", struct.pack("<f", 1e-6))[0]),
    ]


def test_tensor_infos_and_the_data_offset_are_read() -> None:
    tensors = [tensor_info("a", (2, 3), ggml_type=2, offset=0), tensor_info("b", ())]
    data = gguf_with_tensors(tensors, 1, kv(_ALIGNMENT, UINT32, struct.pack("<I", 64)))
    header = _read(data)
    assert header.tensors is not None
    assert [(t.name, t.shape, t.ggml_type) for t in header.tensors] == [
        ("a", (2, 3), 2),
        ("b", (), 0),
    ]
    assert header.data_offset is not None and header.data_offset % 64 == 0


def test_only_the_strings_asked_for_are_parsed() -> None:
    no_utf8 = struct.pack("<Q", 2) + b"b\xff"
    body = array(STRING, 3, string("a") + no_utf8 + string("c"), key=b"d")
    body += array(STRING, 1, _strings("x"), key=b"other")
    header = _read(gguf_file(0, 2, body), {"d": 2, "other": 0})
    listed = _array_field(header, "d")
    assert listed.values == ("a", "b\udcff")  # surrogateescape
    assert (listed.length, listed.complete) == (3, True)
    assert _array_field(header, "other").values is None


def test_only_string_arrays_are_kept() -> None:
    header = _read(gguf_file(0, 1, array(UINT8, 2, b"\0\0", key=b"d")), {"d": 5})
    assert _array_field(header, "d").values is None


def test_a_fixed_size_array_is_passed_without_cost() -> None:
    """Ten million bytes pass under bounds of one: one offset step."""
    data = gguf_file(0, 1, array(UINT8, 10**7, b"\0" * 10**7))
    start = time.monotonic()
    header = _read(data, max_gguf_skipped_elements=1, max_gguf_parsed=4)
    assert time.monotonic() - start < 1.0
    assert header.stop is None
    assert _array_field(header, "k").length == 10**7


# -- bounds: a partial read ------------------------------------------------


def _pairs(n: int) -> bytes:
    return gguf_file(0, n, b"".join(kv(b"k%d" % i, UINT8, b"\0") for i in range(n)))


@pytest.mark.parametrize(("n", "stopped"), [(2, False), (3, True)])
def test_pairs_count_against_the_parsed_budget(n: int, stopped: bool) -> None:
    header = _read(_pairs(n), max_gguf_parsed=8)
    assert (header.stop is not None) is stopped
    if header.stop is not None:
        assert header.stop[:4] == ("max_gguf_parsed", 8, "k2", 2)
        assert [f.key for f in header.fields] == ["k0", "k1"]
        assert header.tensors is None


@pytest.mark.parametrize(
    ("tensors", "stopped"),
    [
        ((tensor_info("a", ()), tensor_info("b", ())), False),
        ((tensor_info("a", (1,)), tensor_info("b", ())), True),
    ],
    ids=["two-tensors", "plus-a-dimension"],
)
def test_tensor_infos_and_dimensions_count_against_it(
    tensors: tuple[bytes, ...], stopped: bool
) -> None:
    header = _read(gguf_with_tensors(list(tensors)), max_gguf_parsed=8)
    assert (header.tensors is None) is stopped
    if stopped:
        assert header.stop is not None
        assert header.stop[2:] == (None, None, False)  # in the tensor infos


def _cut(header: GgufHeader, key: str, bound: str) -> None:
    """The walk stopped inside the array *key*, kept as declared."""
    assert header.stop is not None
    assert (header.stop.bound, header.stop.key, header.stop.in_array) == (
        bound,
        key,
        True,
    )
    cut = _array_field(header, key)
    assert (cut.complete, cut.values) == (False, None)


@pytest.mark.parametrize(("n", "stopped"), [(3, False), (4, True)])
def test_hopped_strings_count_against_the_skip_bound_only(
    n: int, stopped: bool
) -> None:
    body = kv(b"a", UINT8, b"\0") + array(STRING, n, _EMPTY * n, key=b"s")
    header = _read(gguf_file(0, 2, body), max_gguf_skipped_elements=3)
    assert _array_field(header, "s").length == n
    if stopped:
        _cut(header, "s", "max_gguf_skipped_elements")
        assert [f.key for f in header.fields] == ["a", "s"]
    else:
        assert header.stop is None


def test_strings_asked_for_count_against_the_parsed_budget_only() -> None:
    body = array(STRING, 5, _EMPTY * 5, key=b"d")
    whole = _read(gguf_file(0, 1, body), {"d": 4}, max_gguf_parsed=8)
    assert whole.stop is None  # 4 + 4, the fifth hopped
    cut = _read(gguf_file(0, 1, body), {"d": 5}, max_gguf_parsed=8)
    _cut(cut, "d", "max_gguf_parsed")


def test_nesting_past_the_bound_stops_the_walk() -> None:
    deeper = struct.pack("<IQ", ARRAY, 1) + _NESTED_4
    header = _read(gguf_file(0, 1, kv(b"k", ARRAY, deeper)))
    _cut(header, "k", "max_gguf_nesting")


@pytest.mark.parametrize(
    ("key", "value", "stop"),
    [
        (b"abcd", "abcd", None),
        (b"abcd", "abcde", ("abcd", 0, False)),
        (b"abcde", "a", (None, 0, False)),
    ],
    ids=["at-cap", "value-over", "key-over"],
)
def test_a_string_over_its_bound_stops_the_walk(
    key: bytes, value: str, stop: tuple[Any, ...] | None
) -> None:
    header = _read(
        gguf_file(0, 1, kv(key, STRING, string(value))), max_gguf_string_bytes=4
    )
    if stop is None:
        assert header.stop is None
    else:
        assert header.stop is not None
        assert header.stop.bound == "max_gguf_string_bytes"
        assert header.stop[2:] == stop
        assert header.fields == ()


def test_a_stop_after_an_array_is_not_inside_it() -> None:
    """The array before is read whole; the stop names the scalar pair."""
    body = kv(b"a", ARRAY, struct.pack("<IQ", UINT8, 2) + b"\0\0")
    body += kv(b"k", STRING, string("abcde"))
    header = _read(gguf_file(0, 2, body), max_gguf_string_bytes=4)
    assert header.stop is not None
    assert header.stop[2:] == ("k", 1, False)
    assert [f.key for f in header.fields] == ["a"]
    assert _array_field(header, "a").complete


@pytest.mark.parametrize(("value", "stopped"), [("abcd", False), ("abcde", True)])
def test_all_strings_together_count_against_their_bound(
    value: str, stopped: bool
) -> None:
    body = kv(b"ab", STRING, string("cd")) + kv(b"k", STRING, string(value))
    header = _read(gguf_file(0, 2, body), max_gguf_total_string_bytes=9)
    assert (header.stop is not None) is stopped
    if header.stop is not None:
        assert header.stop[:4] == ("max_gguf_total_string_bytes", 9, "k", 1)
        assert [f.key for f in header.fields] == ["ab"]
