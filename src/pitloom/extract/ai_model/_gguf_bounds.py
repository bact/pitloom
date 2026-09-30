# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounds on a GGUF header before the ``gguf`` package parses it.

``gguf.GGUFReader`` loops once per declared tensor, key/value pair and
array element (scalar or string, at any nesting depth), in Python, and keeps
a numpy view for each. A header that declares millions of them in a few MiB
therefore costs gigabytes and minutes. :func:`check_gguf_header` walks the
key/value section with :mod:`struct` first (no allocation per element),
counts all of them against one budget, and refuses a declaration that is
over it, nests deeper than the walker follows, or cannot fit in the file. A
file that is merely truncated or malformed is left to the reader to reject:
that costs nothing.

See also: :mod:`pitloom.extract.ai_model.gguf`.
"""

from __future__ import annotations

import mmap
import struct
from pathlib import Path

from pitloom.extract.ai_model.limits import ModelLimitExceeded

#: Most tensors, key/value pairs and array elements (scalar, string and
#: nested-array, at every depth) accepted, all together. Real models declare
#: hundreds of tensors, tens of keys, and a vocabulary plus merges of a few
#: hundred thousand elements. Each element costs the reader about 0.5-1 KiB
#: and several microseconds, so the worst accepted header is about a GiB.
MAX_GGUF_COUNT = 1_000_000

#: Longest key or string accepted.
_MAX_STRING_BYTES = 8 * 1024 * 1024

# Smallest possible records: a tensor info (name length, n_dims, type,
# offset) and a key/value pair (key length, value type, a one-byte value).
_MIN_TENSOR_INFO_BYTES = 24
_MIN_KV_BYTES = 13

_HEADER_BYTES = 24
_SUPPORTED_VERSIONS = (2, 3)
_MAX_NESTING = 4

_STRING = 8
_ARRAY = 9
# Value types with a fixed size: uint8 int8 uint16 int16 uint32 int32 float32
# bool (0-7), uint64 int64 float64 (10-12).
_SCALAR_BYTES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


class _Malformed(Exception):
    """The structure is cut short or unknown; the reader rejects it alone."""


def _over_budget(what: str) -> ModelLimitExceeded:
    return ModelLimitExceeded(f"GGUF {what}, over the {MAX_GGUF_COUNT} budget")


class _Walker:
    """A cursor over the key/value section of a mapped file."""

    def __init__(self, data: mmap.mmap, endian: str) -> None:
        self.data = data
        self.size = len(data)
        self.u32 = struct.Struct(endian + "I")
        self.u64 = struct.Struct(endian + "Q")
        self.elements = 0  # tensors, pairs and array elements, all together

    def charge(self, count: int, what: str) -> None:
        """Spend *count* of the budget."""
        self.elements += count
        if self.elements > MAX_GGUF_COUNT:
            raise _over_budget(what)

    def number(self, reader: struct.Struct, offset: int) -> int:
        """The unsigned integer at *offset*."""
        if offset + reader.size > self.size:
            raise _Malformed
        return int(reader.unpack_from(self.data, offset)[0])

    def string(self, offset: int) -> int:
        """The offset after the length-prefixed string at *offset*."""
        length = self.number(self.u64, offset)
        if length > _MAX_STRING_BYTES:
            raise ModelLimitExceeded(f"GGUF string of {length} bytes")
        end = offset + 8 + length
        if end > self.size:
            raise _Malformed
        return end

    def value(self, vtype: int, offset: int, depth: int) -> int:
        """The offset after the value of type *vtype* at *offset*."""
        if vtype in _SCALAR_BYTES:
            return offset + _SCALAR_BYTES[vtype]
        if vtype == _STRING:
            return self.string(offset)
        if vtype == _ARRAY:
            if depth >= _MAX_NESTING:  # the reader follows any depth
                raise ModelLimitExceeded(f"GGUF arrays nested over {_MAX_NESTING}")
            return self.array(offset, depth + 1)
        raise _Malformed

    def array(self, offset: int, depth: int) -> int:
        """The offset after the array at *offset* (element type, count,
        elements)."""
        elem = self.number(self.u32, offset)
        count = self.number(self.u64, offset + 4)
        offset += 12
        self.charge(count, f"array of {count} elements")
        if elem in _SCALAR_BYTES:
            end = offset + count * _SCALAR_BYTES[elem]
            if end > self.size:
                raise ModelLimitExceeded(
                    f"GGUF array of {count} elements, more than the file holds"
                )
            return end
        if count * 8 > self.size - offset:  # a string or array takes >= 8 bytes
            raise ModelLimitExceeded(
                f"GGUF array of {count} elements, more than the file holds"
            )
        for _ in range(count):
            offset = self.value(elem, offset, depth)
        return offset


def _walk(data: mmap.mmap, endian: str) -> None:
    walker = _Walker(data, endian)
    size = walker.size
    n_tensors = walker.number(walker.u64, 8)
    n_kv = walker.number(walker.u64, 16)
    if n_tensors * _MIN_TENSOR_INFO_BYTES > size:
        raise ModelLimitExceeded(f"GGUF header declares {n_tensors} tensors")
    if n_kv * _MIN_KV_BYTES > size:
        raise ModelLimitExceeded(f"GGUF header declares {n_kv} key/value pairs")
    walker.charge(n_tensors, f"header declares {n_tensors} tensors")
    walker.charge(n_kv, f"header declares {n_kv} key/value pairs")
    offset = _HEADER_BYTES
    for _ in range(n_kv):
        offset = walker.string(offset)
        vtype = walker.number(walker.u32, offset)
        offset = walker.value(vtype, offset + 4, 0)


def check_gguf_header(path: Path) -> None:
    """Refuse a GGUF file whose header declares more than a reader should
    loop over.

    Raises:
        ModelLimitExceeded: The declared tensors, pairs and array elements
            are over the budget, arrays nest too deep, or a string length is
            over its cap or cannot fit in the file.
        OSError: The file cannot be read.
    """
    with path.open("rb") as fh:
        head = fh.read(_HEADER_BYTES)
        if len(head) < _HEADER_BYTES or head[:4] != b"GGUF":
            return
        version = struct.unpack("<I", head[4:8])[0]
        endian = "<"
        if version > 0xFFFF:  # written big-endian
            version, endian = struct.unpack(">I", head[4:8])[0], ">"
        if version not in _SUPPORTED_VERSIONS:
            return
        with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
            try:
                _walk(data, endian)
            except _Malformed:
                return
