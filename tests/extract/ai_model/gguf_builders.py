# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Byte builders for GGUF tests: a header, key/value pairs and arrays, laid
out by hand (``GGUFWriter`` drops empty arrays and cannot write a hostile
count).

See also: :mod:`tests.extract.ai_model.test_model_bounds` and
:mod:`tests.extract.ai_model.test_gguf_arrays`.
"""

from __future__ import annotations

import struct

# GGUF value types (``gguf.GGUFValueType``).
UINT8 = 0
UINT32 = 4
INT32 = 5
FLOAT32 = 6
STRING = 8
ARRAY = 9


def gguf_file(
    n_tensors: int,
    n_kv: int,
    body: bytes = b"",
    *,
    endian: str = "<",
    tail: int = 0,
) -> bytes:
    """A version 3 header declaring *n_tensors* and *n_kv*, then *body* and
    *tail* zero bytes."""
    head = b"GGUF" + struct.pack(endian + "IQQ", 3, n_tensors, n_kv)
    return head + body + b"\0" * tail


def kv(key: bytes, vtype: int, value: bytes, endian: str = "<") -> bytes:
    """One key/value pair; *value* is already encoded."""
    return (
        struct.pack(endian + "Q", len(key))
        + key
        + struct.pack(endian + "I", vtype)
        + value
    )


def string(text: str) -> bytes:
    """A GGUF string value: its length, then its UTF-8 bytes."""
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def array(
    elem: int,
    count: int,
    payload: bytes = b"",
    endian: str = "<",
    key: bytes = b"k",
) -> bytes:
    """An array pair *key* of *count* elements of type *elem*."""
    return kv(key, ARRAY, struct.pack(endian + "IQ", elem, count) + payload, endian)
