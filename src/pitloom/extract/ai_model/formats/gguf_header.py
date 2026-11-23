# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The key/value pairs and tensor infos of a GGUF file, nothing else.

A GGUF file is a 24-byte header (magic, version, tensor and pair counts),
the key/value pairs, the tensor infos (name, dimensions, type, offset) and,
aligned, the tensor data. :func:`read_gguf_header` walks the pairs and the
infos with :mod:`struct` over a buffer (a memory map) and never touches the
data.

An array's elements are parsed only for a key the caller asks for, and only
as many as it asks; every other array is passed over. Elements of a fixed
size cost nothing to pass (one offset step); a string or a nested array is
hopped over one length prefix at a time, each hop counted against
:attr:`Limits.max_gguf_skipped_elements`. What is parsed (pairs, tensor
infos and their dimensions, array elements asked for) counts against
:attr:`Limits.max_gguf_parsed`, keys and strings decoded against the string
caps. A bound reached stops the walk where it is: the pairs read so far are
returned, with the bound in :attr:`GgufHeader.stop`, and no tensor infos. An
array whose end the walk did not reach keeps its declared length and type
(:attr:`GgufArray.complete` false).

A declaration that cannot fit in the file, an unknown type code, a
duplicate key or tensor name, a tensor of more than :data:`MAX_DIMS`
dimensions, a key that is no UTF-8, a bad
``general.alignment`` or a structure cut short raise :class:`Malformed`.

See also: :mod:`pitloom.extract.ai_model._gguf_bounds` (Pitloom's adapter).
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, NamedTuple

from ._errors import Malformed, UnsupportedVersion
from ._limits import Limits

if TYPE_CHECKING:
    import mmap

    Buffer = bytes | bytearray | memoryview | mmap.mmap
    Scalar = bool | int | float | str

MAGIC = b"GGUF"
SUPPORTED_VERSIONS = (2, 3)
#: The data section starts at a multiple of this, or of
#: ``general.alignment``.
DEFAULT_ALIGNMENT = 32
ALIGNMENT_KEY = "general.alignment"

UINT32 = 4
STRING = 8
ARRAY = 9
#: The value type names, as the ``gguf`` package spells them.
VALUE_TYPE_NAMES = {
    0: "UINT8",
    1: "INT8",
    2: "UINT16",
    3: "INT16",
    4: "UINT32",
    5: "INT32",
    6: "FLOAT32",
    7: "BOOL",
    8: "STRING",
    9: "ARRAY",
    10: "UINT64",
    11: "INT64",
    12: "FLOAT64",
}
_SCALAR_FORMATS = {
    0: "B",
    1: "b",
    2: "H",
    3: "h",
    4: "I",
    5: "i",
    6: "f",
    7: "?",
    10: "Q",
    11: "q",
    12: "d",
}

_HEADER_BYTES = 24
# Smallest possible records: a tensor info (name length, n_dims, type,
# offset), a key/value pair (key length, value type, a one-byte value), a
# string (its length) and an array (element type, count).
_MIN_TENSOR_INFO_BYTES = 24
_MIN_KV_BYTES = 13
_MIN_STRING_BYTES = 8
_MIN_ARRAY_BYTES = 12
# Budget units a pair or a tensor info costs; an element, a dimension one.
_RECORD_WEIGHT = 4
#: Most dimensions a tensor has: ggml's ``GGML_MAX_DIMS``, past which
#: llama.cpp refuses the file (``ggml/include/ggml.h`` l. 49 and
#: ``ggml/src/gguf.cpp`` l. 661, llama.cpp a8f8294c, 2026-11-23).
MAX_DIMS = 4


class GgufArray(NamedTuple):
    """An array value.

    Attributes:
        element_type: The declared element type code (any code when
            *length* is 0, as the file says it).
        length: The declared element count.
        values: The first elements, for a key the caller asked for (strings
            decoded with ``surrogateescape``); ``None`` otherwise.
        complete: Whether the walk reached the array's end, so its length
            is measured; false when a bound stopped the walk inside it.
    """

    element_type: int
    length: int
    values: tuple[Scalar, ...] | None
    complete: bool


class GgufField(NamedTuple):
    """One key/value pair: a scalar, a string or a :class:`GgufArray`."""

    key: str
    value_type: int
    value: Scalar | GgufArray


class GgufTensor(NamedTuple):
    """One tensor info, as stored (dimensions innermost first)."""

    name: str
    shape: tuple[int, ...]
    ggml_type: int
    offset: int


class GgufStop(NamedTuple):
    """Where a bound stopped the walk.

    Attributes:
        bound: The :class:`Limits` field reached.
        limit: Its value.
        key: The key of the pair the walk stopped in, ``None`` when it
            stopped in the tensor infos or before its key was read.
        pair: The 0-based index of that pair, ``None`` in the tensor infos.
        in_array: Whether the walk stopped inside that pair's array (whose
            declared length and type :attr:`GgufHeader.fields` keeps).
    """

    bound: str
    limit: int
    key: str | None
    pair: int | None
    in_array: bool = False


class GgufHeader(NamedTuple):
    """What a GGUF header says.

    Attributes:
        version: The format version.
        big_endian: Whether the file is big-endian.
        tensor_count: The declared tensor count.
        kv_count: The declared pair count.
        fields: The pairs read, in file order.
        tensors: The tensor infos, ``None`` when a bound stopped the walk
            before their end.
        data_offset: Where the tensor data starts, ``None`` with *tensors*.
        stop: The bound that stopped the walk, ``None`` for a full read.
    """

    version: int
    big_endian: bool
    tensor_count: int
    kv_count: int
    fields: tuple[GgufField, ...]
    tensors: tuple[GgufTensor, ...] | None
    data_offset: int | None
    stop: GgufStop | None


class DeclaredBeyondFile(Malformed):
    """A count declares more records than the file can hold.

    Attributes:
        what: ``"tensors"``, ``"pairs"`` or ``"array"``.
        count: The declared count.
    """

    def __init__(self, what: str, count: int) -> None:
        super().__init__(f"declares {count} {what}, more than the file holds")
        self.what = what
        self.count = count


class UnknownVersion(UnsupportedVersion):
    """A version other than :data:`SUPPORTED_VERSIONS`.

    Attributes:
        version: The version the header states.
    """

    def __init__(self, version: int) -> None:
        super().__init__(f"GGUF version {version} is not supported")
        self.version = version


class _Stop(Exception):
    """A bound was reached; the walk ends where it is."""

    def __init__(self, bound: str, limit: int) -> None:
        super().__init__(bound)
        self.bound = bound
        self.limit = limit


class _Walker:
    """A cursor over a GGUF buffer, with the bounds' running totals."""

    def __init__(self, data: Buffer, endian: str, limits: Limits) -> None:
        self.data = data
        self.size = len(data)
        self.endian = endian
        self.u32 = struct.Struct(endian + "I")
        self.u64 = struct.Struct(endian + "Q")
        self.scalars = {
            code: struct.Struct(endian + fmt) for code, fmt in _SCALAR_FORMATS.items()
        }
        self.limits = limits
        self.parsed = 0
        self.skipped = 0
        self.string_bytes = 0
        # The pair's array being walked: (element type, count).
        self.current_array: tuple[int, int] | None = None

    def charge_parsed(self, count: int) -> None:
        self.parsed += count
        if self.parsed > self.limits.max_gguf_parsed:
            raise _Stop("max_gguf_parsed", self.limits.max_gguf_parsed)

    def charge_skipped(self, count: int) -> None:
        self.skipped += count
        if self.skipped > self.limits.max_gguf_skipped_elements:
            raise _Stop(
                "max_gguf_skipped_elements", self.limits.max_gguf_skipped_elements
            )

    def number(self, reader: struct.Struct, offset: int) -> int:
        """The unsigned integer at *offset*."""
        if offset + reader.size > self.size:
            raise Malformed(f"truncated at offset {offset}")
        return int(reader.unpack_from(self.data, offset)[0])

    def read_string(self, offset: int, *, key: bool) -> tuple[str, int]:
        """The string at *offset* and the offset after it: a key or a tensor
        name decoded strictly, a value with ``surrogateescape``."""
        length = self.number(self.u64, offset)
        start = offset + 8
        end = start + length
        # A length past the end is a malformed file, whatever the caps say.
        if end > self.size:
            raise Malformed(f"string at offset {offset} runs past the end")
        limits = self.limits
        if length > limits.max_gguf_string_bytes:
            raise _Stop("max_gguf_string_bytes", limits.max_gguf_string_bytes)
        self.string_bytes += length
        if self.string_bytes > limits.max_gguf_total_string_bytes:
            raise _Stop(
                "max_gguf_total_string_bytes", limits.max_gguf_total_string_bytes
            )
        raw = bytes(self.data[start:end])
        if not key:
            return raw.decode("utf-8", errors="surrogateescape"), end
        try:
            return raw.decode("utf-8"), end
        except UnicodeDecodeError:
            raise Malformed(f"key or name at offset {offset} is not UTF-8") from None

    def scalar(self, vtype: int, offset: int) -> tuple[Scalar, int]:
        """The fixed-size value of type *vtype* at *offset*."""
        reader = self.scalars[vtype]
        if offset + reader.size > self.size:
            raise Malformed(f"truncated at offset {offset}")
        value: Scalar = reader.unpack_from(self.data, offset)[0]
        return value, offset + reader.size

    def value(
        self, vtype: int, offset: int, keep: int
    ) -> tuple[Scalar | GgufArray, int]:
        """A pair's value; an array's first *keep* string elements parsed."""
        if vtype in _SCALAR_FORMATS:
            return self.scalar(vtype, offset)
        if vtype == STRING:
            return self.read_string(offset, key=False)
        if vtype == ARRAY:
            return self.top_array(offset, keep)
        raise Malformed(f"unknown value type {vtype}")

    def array_head(self, offset: int) -> tuple[int, int, int]:
        """The element type, count and first element offset of the array at
        *offset*, its count checked against the file."""
        elem = self.number(self.u32, offset)
        count = self.number(self.u64, offset + 4)
        offset += _MIN_ARRAY_BYTES
        if count:
            if elem in _SCALAR_FORMATS:
                need = self.scalars[elem].size
            elif elem == STRING:
                need = _MIN_STRING_BYTES
            elif elem == ARRAY:
                need = _MIN_ARRAY_BYTES
            else:
                raise Malformed(f"unknown array element type {elem}")
            if count * need > self.size - offset:
                raise DeclaredBeyondFile("array", count)
        return elem, count, offset

    def top_array(self, offset: int, keep: int) -> tuple[GgufArray, int]:
        """A pair's array value: its first *keep* strings parsed, the rest
        passed over."""
        elem, count, offset = self.array_head(offset)
        self.current_array = (elem, count)
        values: tuple[Scalar, ...] | None = None
        rest = count
        if keep and elem == STRING:
            taken = min(count, keep)
            self.charge_parsed(taken)
            read: list[Scalar] = []
            for _ in range(taken):
                text, offset = self.read_string(offset, key=False)
                read.append(text)
            values = tuple(read)
            rest = count - taken
        offset = self.pass_over(elem, rest, offset, 1)
        self.current_array = None
        return GgufArray(elem, count, values, True), offset

    def pass_over(self, elem: int, count: int, offset: int, depth: int) -> int:
        """The offset after *count* elements of type *elem* at *offset*,
        none of them parsed."""
        if not count:
            return offset
        if elem in _SCALAR_FORMATS:
            # Inside the file: array_head checked the count.
            return offset + count * self.scalars[elem].size
        self.charge_skipped(count)
        if elem == STRING:
            return self.hop_strings(count, offset)
        if depth >= self.limits.max_gguf_nesting:
            raise _Stop("max_gguf_nesting", self.limits.max_gguf_nesting)
        for _ in range(count):
            inner, inner_count, offset = self.array_head(offset)
            offset = self.pass_over(inner, inner_count, offset, depth + 1)
        return offset

    def hop_strings(self, count: int, offset: int) -> int:
        """The offset after *count* strings at *offset*, none decoded."""
        data, size, unpack = self.data, self.size, self.u64.unpack_from
        for _ in range(count):
            if offset + 8 > size:
                raise Malformed(f"truncated at offset {offset}")
            offset += 8 + unpack(data, offset)[0]
        if offset > size:
            raise Malformed("a string runs past the end")
        return offset


def _byte_order(data: Buffer) -> tuple[int, str]:
    """The version and the :mod:`struct` byte order of the header."""
    if len(data) < _HEADER_BYTES:
        raise Malformed("shorter than a GGUF header")
    if bytes(data[:4]) != MAGIC:
        raise Malformed("GGUF magic invalid")
    version = int(struct.unpack_from("<I", data, 4)[0])
    endian = "<"
    if version & 0xFFFF == 0:  # written in the other byte order
        version, endian = int(struct.unpack_from(">I", data, 4)[0]), ">"
    if version not in SUPPORTED_VERSIONS:
        raise UnknownVersion(version)
    return version, endian


def _read_pairs(
    walker: _Walker, kv_count: int, keep: dict[str, int]
) -> tuple[list[GgufField], int, GgufStop | None]:
    fields: list[GgufField] = []
    seen: set[str] = set()
    offset = _HEADER_BYTES
    for index in range(kv_count):
        known: str | None = None
        try:
            key, offset = walker.read_string(offset, key=True)
            known = key
            walker.charge_parsed(_RECORD_WEIGHT)
            if key in seen:
                raise Malformed(f"duplicate key {key!r}")
            seen.add(key)
            vtype = walker.number(walker.u32, offset)
            value, offset = walker.value(vtype, offset + 4, keep.get(key, 0))
        except _Stop as stop:
            current = walker.current_array if known is not None else None
            if known is not None and current is not None:
                cut = GgufArray(current[0], current[1], None, False)
                fields.append(GgufField(known, ARRAY, cut))
            found = GgufStop(stop.bound, stop.limit, known, index, current is not None)
            return fields, offset, found
        fields.append(GgufField(key, vtype, value))
    return fields, offset, None


def _read_tensors(
    walker: _Walker, tensor_count: int, offset: int
) -> tuple[list[GgufTensor], int]:
    tensors: list[GgufTensor] = []
    names: set[str] = set()
    for _ in range(tensor_count):
        walker.charge_parsed(_RECORD_WEIGHT)
        name, offset = walker.read_string(offset, key=True)
        if name in names:
            raise Malformed(f"duplicate tensor {name!r}")
        names.add(name)
        n_dims = walker.number(walker.u32, offset)
        offset += 4
        if n_dims * 8 + 12 > walker.size - offset:
            raise Malformed(f"tensor {name!r} runs past the end")
        if n_dims > MAX_DIMS:
            raise Malformed(
                f"tensor {name!r} has {n_dims} dimensions, more than {MAX_DIMS}"
            )
        walker.charge_parsed(n_dims)
        shape = struct.unpack_from(f"{walker.endian}{n_dims}Q", walker.data, offset)
        offset += n_dims * 8
        ggml_type = walker.number(walker.u32, offset)
        data_offset = walker.number(walker.u64, offset + 4)
        offset += 12
        tensors.append(GgufTensor(name, tuple(shape), ggml_type, data_offset))
    return tensors, offset


def _alignment(fields: list[GgufField]) -> int:
    for field in fields:
        if field.key != ALIGNMENT_KEY:
            continue
        if field.value_type != UINT32 or not isinstance(field.value, int):
            raise Malformed(f"{ALIGNMENT_KEY} is no uint32")
        if field.value == 0 or field.value & (field.value - 1):
            raise Malformed(f"{ALIGNMENT_KEY} {field.value} is no power of two")
        return field.value
    return DEFAULT_ALIGNMENT


def read_gguf_header(
    data: Buffer, limits: Limits, keep: dict[str, int] | None = None
) -> GgufHeader:
    """Read the pairs and tensor infos of the GGUF file in *data*.

    Args:
        data: The file's bytes (a memory map, so nothing past the header is
            read).
        limits: The bounds of the walk.
        keep: For each key whose array elements the caller needs, how many
            of its first string elements to parse.

    Raises:
        Malformed: Not a GGUF header, or cut short or inconsistent
            (:class:`DeclaredBeyondFile` for a count beyond the file).
        UnknownVersion: A version this reader does not know.
    """
    version, endian = _byte_order(data)
    walker = _Walker(data, endian, limits)
    tensor_count = walker.number(walker.u64, 8)
    kv_count = walker.number(walker.u64, 16)
    if tensor_count * _MIN_TENSOR_INFO_BYTES > walker.size:
        raise DeclaredBeyondFile("tensors", tensor_count)
    if kv_count * _MIN_KV_BYTES > walker.size:
        raise DeclaredBeyondFile("pairs", kv_count)
    fields, offset, stop = _read_pairs(walker, kv_count, keep or {})
    tensors: tuple[GgufTensor, ...] | None = None
    data_offset: int | None = None
    if stop is None:
        try:
            read, offset = _read_tensors(walker, tensor_count, offset)
        except _Stop as hit:
            stop = GgufStop(hit.bound, hit.limit, None, None)
        else:
            alignment = _alignment(fields)
            tensors = tuple(read)
            data_offset = offset + (-offset % alignment)
    return GgufHeader(
        version,
        endian == ">",
        tensor_count,
        kv_count,
        tuple(fields),
        tensors,
        data_offset,
        stop,
    )
