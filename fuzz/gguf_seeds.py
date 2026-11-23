# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Hostile GGUF headers, as seeds for ``fuzz_gguf_header.py``.

Each seed sits at one edge of the header reader: a count beyond the file,
a truncation, a huge string length, nesting past the bound, an out-of-range
type id, a duplicate key, a bad alignment, a big-endian header, a large
fixed-size array (passed in one step) and a tokeniser-shaped string array
(hopped). ``SEEDS`` is also the start of the seeded mutation test
(``tests/extract/ai_model/formats/test_gguf_header_adversarial.py``).

Usage: ``python fuzz/gguf_seeds.py <directory>`` writes one ``.gguf`` file
per seed.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

_STRING = 8
_ARRAY = 9


def _header(n_tensors: int, n_kv: int, body: bytes = b"", endian: str = "<") -> bytes:
    return b"GGUF" + struct.pack(endian + "IQQ", 3, n_tensors, n_kv) + body


def _kv(key: bytes, vtype: int, value: bytes, endian: str = "<") -> bytes:
    return (
        struct.pack(endian + "Q", len(key))
        + key
        + struct.pack(endian + "I", vtype)
        + value
    )


def _string(text: bytes, endian: str = "<") -> bytes:
    return struct.pack(endian + "Q", len(text)) + text


def _array(key: bytes, elem: int, count: int, payload: bytes = b"") -> bytes:
    return _kv(key, _ARRAY, struct.pack("<IQ", elem, count) + payload)


def _tensor(name: bytes, dims: tuple[int, ...], ggml_type: int = 0) -> bytes:
    shape = b"".join(struct.pack("<Q", d) for d in dims)
    return (
        _string(name)
        + struct.pack("<I", len(dims))
        + shape
        + struct.pack("<IQ", ggml_type, 0)
    )


def _nested(depth: int) -> bytes:
    return struct.pack("<IQ", _ARRAY, 1) * depth + struct.pack("<IQ", 0, 1) + b"\0"


SEEDS: dict[str, bytes] = {
    "tensors-beyond-file": _header(10**6, 0),
    "pairs-beyond-file": _header(0, 2**40),
    "strings-beyond-file": _header(0, 1, _array(b"k", _STRING, 10**9)) + b"\0" * 64,
    "scalars-beyond-file": _header(0, 1, _array(b"k", 4, 10**9)) + b"\0" * 64,
    "truncated-key": _header(0, 1, b"\0\0\0"),
    "truncated-value": _header(0, 1, _kv(b"k", 4, b"\0")),
    "huge-string-length": _header(0, 1, _kv(b"k", _STRING, struct.pack("<Q", 2**63))),
    "nesting-past-bound": _header(0, 1, _kv(b"k", _ARRAY, _nested(5))),
    "unknown-value-type": _header(0, 1, _kv(b"k", 0xFFFFFFFF, b"\0" * 8)),
    "unknown-element-type": _header(0, 1, _array(b"k", 13, 1, b"\0" * 8)),
    "unknown-tensor-type": _header(1, 0, _tensor(b"t", (2, 2), 0xFFFF)) + b"\0" * 64,
    "duplicate-key": _header(0, 2, _kv(b"k", 0, b"\0") * 2),
    "bad-alignment": _header(0, 1, _kv(b"general.alignment", 4, struct.pack("<I", 3))),
    "big-endian": _header(
        0, 1, _kv(b"general.name", _STRING, _string(b"x", ">"), ">"), ">"
    ),
    "large-fixed-array": _header(0, 1, _array(b"k", 0, 1 << 16, b"\0" * (1 << 16))),
    "tokeniser-strings": _header(
        0, 1, _array(b"tokenizer.ggml.tokens", _STRING, 512, _string(b"t") * 512)
    ),
    "datasets": _header(
        0,
        1,
        _array(b"general.datasets", _STRING, 2, _string(b"a/b") + _string(b"\xff")),
    ),
}


def main(argv: list[str]) -> int:
    """Write every seed into the directory *argv[1]*."""
    if len(argv) != 2:
        print("ERROR: usage: gguf_seeds.py <directory>", file=sys.stderr)
        return 2
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, data in SEEDS.items():
        (out / f"seed-{name}.gguf").write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
