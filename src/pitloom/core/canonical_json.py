# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one serialisation of JSON text embedded in an SBOM string.

Every JSON object or array Pitloom writes into a string value (an
``Annotation.statement``, ``ai_informationAboutApplication``, a reader's
``properties`` entry holding a collection) goes through
:func:`canonical_json`, so it is RFC 8785 (JCS): compact, keys in UTF-16
code-unit order, one spelling per number.

RFC 8785 has no spelling for NaN, the infinities or an integer outside
+-(2**53 - 1), and no hook for other types; :func:`json_safe` turns each
into a string first (the first three as
:func:`~pitloom.core.scalar_text.scalar_text` spells them, the integer in
full decimal), so serialisation never raises on a value read from a file.

See also: :mod:`pitloom.core.scalar_text` (a scalar's text outside JSON).
"""

from __future__ import annotations

import base64
import math
from collections.abc import Mapping
from typing import Any, cast

import rfc8785

from pitloom.core.scalar_text import BOOLEAN, FLOAT, INTEGER, scalar_text, scalar_type

#: Largest magnitude of an integer RFC 8785 serialises as a number.
MAX_SAFE_INTEGER = 2**53 - 1


def _json_safe_scalar(value: Any) -> object:
    """A boolean, an integer or a float (NumPy's too) as a JSON-safe value."""
    kind = scalar_type(value)
    if kind == BOOLEAN:
        return bool(value)
    if kind == INTEGER:
        number = int(value)
        return number if abs(number) <= MAX_SAFE_INTEGER else str(number)
    if kind == FLOAT:
        number_f = float(value)
        return number_f if math.isfinite(number_f) else scalar_text(number_f)
    return str(value)


def json_safe(value: object) -> object:
    """*value* with everything RFC 8785 cannot serialise made a string.

    - a mapping's keys as ``str()``;
    - a list or a tuple as a list; a set or a frozenset as a list sorted by
      each element's canonical form (a set has no stable order);
    - ``bytes`` as Base64;
    - NaN, infinity and negative infinity as ``NaN``, ``INF``, ``-INF``;
    - an integer beyond +-(2**53 - 1) as its decimal text;
    - a string, ``None`` and other scalars as JSON values;
    - anything else as ``str()``.
    """
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    # Loops, not comprehensions: one stack frame per nesting level, as in
    # the parser and the serialiser, so any depth they take passes here.
    if isinstance(value, Mapping):
        mapping: dict[str, object] = {}
        for key, item in value.items():
            mapping[str(key)] = json_safe(item)
        return mapping
    if isinstance(value, (list, tuple)):
        items: list[object] = []
        for item in value:
            items.append(json_safe(item))
        return items
    if isinstance(value, (set, frozenset)):
        return sorted((json_safe(v) for v in value), key=canonical_json_bytes)
    return _json_safe_scalar(value)


def canonical_json_bytes(value: object) -> bytes:
    """*value*, made :func:`json_safe`, as RFC 8785 UTF-8 bytes."""
    return rfc8785.dumps(cast(Any, json_safe(value)))


def canonical_json(value: object) -> str:
    """*value*, made :func:`json_safe`, as RFC 8785 text."""
    return canonical_json_bytes(value).decode("utf-8")
