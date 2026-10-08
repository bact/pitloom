# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one spelling of a scalar as text.

A model file's scalar (a boolean, an integer, a float) becomes text in a
reader's ``properties``, in an ``ai_hyperparameter`` value and in the
artifact-metadata annotation; :func:`scalar_text` is the only way it does,
so one value has one spelling in all three. :func:`text_type` names the
type the text was, for the annotation's ``valueTypes``.

NumPy is optional: its scalars are recognised through the :mod:`numbers`
ABCs it registers them with, and ``numpy.bool_`` (registered with none)
through the already imported module, so this module never imports it.

See also: :mod:`pitloom.core.ai_metadata` (``source_metadata``, its main
user).
"""

from __future__ import annotations

import math
import numbers
import sys
from typing import Any

import rfc8785

#: :func:`scalar_type` names, the values of the annotation's ``valueTypes``.
BOOLEAN = "boolean"
FLOAT = "float"
INTEGER = "integer"

#: Most decimal digits of an integer :func:`integer_text` writes out: 640,
#: the lowest limit :func:`sys.set_int_max_str_digits` accepts, so ``str()``
#: takes it under any interpreter setting and the text never depends on one.
MAX_INTEGER_DIGITS = 640

_INTEGER_TEXT_BOUND = 10**MAX_INTEGER_DIGITS


def _is_bool(value: Any) -> bool:
    """Whether *value* is a ``bool`` or a ``numpy.bool_``."""
    if isinstance(value, bool):
        return True
    # A numpy.bool_ exists only once numpy is imported; a stand-in module
    # (a test's) may have no such type.
    bool_type = getattr(sys.modules.get("numpy"), "bool_", None)
    return isinstance(bool_type, type) and isinstance(value, bool_type)


def scalar_type(value: Any) -> str | None:
    """:data:`BOOLEAN`, :data:`INTEGER` or :data:`FLOAT` for a boolean, an
    integer or a real number (NumPy's too), else ``None`` (a string, a
    collection, ``None``). A boolean is tested first: ``bool`` is an
    ``int``."""
    if _is_bool(value):
        return BOOLEAN
    if isinstance(value, numbers.Integral):
        return INTEGER
    if isinstance(value, numbers.Real):
        return FLOAT
    return None


def integer_text(value: int) -> str:
    """*value* in decimal; over :data:`MAX_INTEGER_DIGITS` digits, as
    ``<integer of N bits>`` (``<negative integer of N bits>``), N its
    :meth:`int.bit_length`: a longer decimal is no use to a reader, and
    Python's ``str()`` refuses one over its limit (4300 digits by default).
    """
    if abs(value) < _INTEGER_TEXT_BOUND:
        return str(value)
    sign = "negative " if value < 0 else ""
    return f"<{sign}integer of {value.bit_length()} bits>"


def text_type(value: Any) -> str | None:
    """The ``valueTypes`` name of :func:`scalar_text` of *value*: its
    :func:`scalar_type`, but ``None`` for an integer :func:`integer_text`
    spells as ``<integer of N bits>``, which no reader can type back."""
    kind = scalar_type(value)
    if kind == INTEGER and abs(int(value)) >= _INTEGER_TEXT_BOUND:
        return None
    return kind


def _float_text(value: float) -> str:
    """*value* in the RFC 8785 (ECMAScript) spelling; NaN and the infinities,
    which RFC 8785 has none for, in the XSD ``double`` spelling."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "INF" if value > 0 else "-INF"
    return rfc8785.dumps(value).decode("ascii")


def scalar_text(value: Any) -> str:
    """*value*, a string or a scalar, as text.

    - a string as is;
    - a boolean (also ``numpy.bool_``) ``true`` or ``false``;
    - an integer (also ``numpy.integer``) as :func:`integer_text` spells
      it: in decimal up to :data:`MAX_INTEGER_DIGITS` digits, else
      ``<integer of N bits>``;
    - a float (also ``numpy.floating``, as the double it converts to) in
      the RFC 8785 spelling (``0.000001``, ``1e-7``, ``100``, ``1e+21``);
      NaN, infinity and negative infinity as ``NaN``, ``INF`` and ``-INF``.

    ``-0.0`` is ``0``, as in RFC 8785: the value is equal, only the sign of
    the zero is lost. A float32 is spelt as the double it widens to; a
    reader that knows a value is a float32 narrows it first (the GGUF
    reader does).

    A ``decimal.Decimal`` is no scalar here (not a :class:`numbers.Real`)
    and raises; :func:`pitloom.core.ai_metadata.value_text` spells it with
    ``str()``. No reader yields one, nor a ``numpy.timedelta64`` or a
    ``numpy.longdouble``.

    Raises:
        TypeError: *value* is ``None`` or not a string or a scalar; a
            caller leaves an absent value out instead.
    """
    if isinstance(value, str):
        return str(value)
    kind = scalar_type(value)
    if kind == BOOLEAN:
        return "true" if value else "false"
    if kind == INTEGER:
        return integer_text(int(value))
    if kind == FLOAT:
        return _float_text(float(value))
    raise TypeError(f"not a scalar: {type(value).__name__}")


def key_text(key: Any) -> str:
    """A mapping key as text: a string or a scalar its :func:`scalar_text`
    (``true``, ``1e-7``), ``None`` ``null``, anything else ``str()``, so a
    key reads as the same value would. Two keys that spell the same
    (``1`` and ``"1"``) are one key; the caller keeps the later one, as a
    JSON parser does with a repeated key."""
    if key is None:
        return "null"
    if isinstance(key, str) or scalar_type(key) is not None:
        return scalar_text(key)
    return str(key)
