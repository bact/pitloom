# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The fields of a GGUF header as :func:`~pitloom.extract.ai_model.gguf.read_gguf`
records them.

See also: :mod:`pitloom.extract.ai_model.gguf` and
:mod:`pitloom.extract.ai_model.formats.gguf_header`.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from pitloom.extract.ai_model.formats.gguf_header import (
    VALUE_TYPE_NAMES,
    GgufArray,
    GgufField,
    GgufHeader,
)
from pitloom.messages import emit
from pitloom.messages.model_fields import GGUF_LENGTH_LINE, MODEL_FIELD_CONFLICT

log = logging.getLogger(__name__)

#: An array is recorded as its length, under its key plus this suffix, in
#: ``properties``; its element values are never used.
ARRAY_LENGTH_SUFFIX = ".length"

# The header's own counts, recorded first as fields of these names, in the
# file's byte order (the names the ``gguf`` package gives them).
FORMAT_VERSION_KEY = "GGUF.version"
_TENSOR_COUNT_KEY = "GGUF.tensor_count"
_KV_COUNT_KEY = "GGUF.kv_count"
_FLOAT32 = 6


class GgufFields(NamedTuple):
    """A header's fields, as :func:`read_fields` returns them.

    Attributes:
        fields: Every field in file order: a scalar under its key, an array
            ``k`` as ``k.length``, its declared element count, at ``k``'s
            position.
        raw_metadata: The file's keys: a scalar's value, an array's
            :func:`_array_summary`.
        derived: Each length key mapped back to its array's key.
        declared: The length keys of arrays whose end the read did not
            reach: their length is declared, not measured.
    """

    fields: dict[str, Any]
    raw_metadata: dict[str, Any]
    derived: dict[str, str]
    declared: frozenset[str]


def _float32_double(value: float) -> float:
    """The double whose shortest decimal is the shortest decimal of the
    float32 *value* (a double that is exactly a float32).

    ``numpy.format_float_scientific(unique=True)`` gives that decimal
    whatever the print options, so the stored ``1e-6`` is spelt
    ``0.000001``, not ``9.999999974752427e-7``; it converts back to the
    same float32.
    """
    # pylint: disable-next=import-outside-toplevel
    import numpy  # a dependency of gguf, imported once a file is read

    return float(numpy.format_float_scientific(numpy.float32(value), unique=True))


def _scalar_value(field: GgufField) -> Any:
    """A scalar field's value: a ``FLOAT32`` through
    :func:`_float32_double`, a ``FLOAT64`` as stored."""
    if field.value_type == _FLOAT32 and isinstance(field.value, float):
        return _float32_double(field.value)
    return field.value


def _array_summary(array: GgufArray) -> dict[str, Any]:
    """An array as its length and declared element type name; the type is
    absent for a code that names no type (possible only when empty)."""
    summary: dict[str, Any] = {"length": array.length}
    name = VALUE_TYPE_NAMES.get(array.element_type)
    if name is not None:
        summary["type"] = name
    return summary


def _all_fields(header: GgufHeader) -> list[GgufField]:
    """The header's counts, then its pairs.

    Raises:
        ValueError: A pair repeats the name of a count.
    """
    counts = [
        GgufField(FORMAT_VERSION_KEY, 4, header.version),
        GgufField(_TENSOR_COUNT_KEY, 10, header.tensor_count),
        GgufField(_KV_COUNT_KEY, 10, header.kv_count),
    ]
    names = {field.key for field in counts}
    for field in header.fields:
        if field.key in names:
            raise ValueError(f"duplicate key {field.key!r}")
    return counts + list(header.fields)


def read_fields(header: GgufHeader) -> GgufFields:
    """Every field of a GGUF *header*, in file order (see
    :class:`GgufFields`). A real key ``k.length`` wins over an array
    ``k``'s length, whatever their order in the file, with a ``WARNING:``.

    Raises:
        ValueError: A pair repeats the name of one of the header's counts.
    """
    every = _all_fields(header)
    scalar_keys = {f.key for f in every if not isinstance(f.value, GgufArray)}
    fields: dict[str, Any] = {}
    raw_metadata: dict[str, Any] = {}
    derived: dict[str, str] = {}
    declared: set[str] = set()
    for field in every:
        key = field.key
        if not isinstance(field.value, GgufArray):
            fields[key] = raw_metadata[key] = _scalar_value(field)
            continue
        raw_metadata[key] = _array_summary(field.value)
        length_key = key + ARRAY_LENGTH_SUFFIX
        if length_key in scalar_keys:
            emit(
                log,
                MODEL_FIELD_CONFLICT,
                logging.WARNING,
                line=GGUF_LENGTH_LINE,
                entry=length_key,
                name=key,
            )
            continue
        fields[length_key] = field.value.length
        derived[length_key] = key
        if not field.value.complete:
            declared.add(length_key)
    return GgufFields(fields, raw_metadata, derived, frozenset(declared))


def listed_strings(header: GgufHeader, key: str) -> tuple[str, ...] | None:
    """The string elements read of the array *key*, ``None`` when the
    header has no such array of strings."""
    for field in header.fields:
        if field.key == key and isinstance(field.value, GgufArray):
            values = field.value.values
            if values is None:
                return None
            return tuple(v for v in values if isinstance(v, str))
    return None
