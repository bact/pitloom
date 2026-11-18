# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a configuration line says was found where a value is refused, the
``got`` of ``must be X, got Y``: the value's TOML type, and the value itself
when it is short and harmless to show (:func:`found_text`).

The user reads TOML, so a type is named as TOML names it (``a table``, not
``dict``). A table or an array is never shown, so a line stays short and
holds no nested secret; a string is shown masked, escaped and cut. A value
that may be a secret (a URL credential fingerprint pasted as the credential
itself) is shown by its type only (:func:`kind_text`).

See also: :mod:`pitloom.messages._config_place` (where it was found).
"""

from __future__ import annotations

import datetime
import enum
import numbers
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from pitloom.core.quote_source import given_path_text, quote_source
from pitloom.messages._field_type import QUOTED


class _Missing(enum.Enum):
    """The type of :data:`MISSING`."""

    MISSING = "MISSING"


#: No value at all: a key the configuration does not hold (``nothing``).
MISSING: Final = _Missing.MISSING

#: The most characters of a string a line shows, ``...`` after it when cut.
SHOWN_CHARS: Final = 40
#: The digits of the largest integer a line shows.
_SHOWN_DIGITS: Final = 39

_TYPE_NAME: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")


@dataclass(frozen=True)
class Found:
    """A ``got`` already written (:func:`found_text` or :func:`kind_text`):
    what a coded configuration error keeps, never the value itself."""

    text: str


def _integer(value: object) -> int | None:
    """*value* as an ``int`` when it is an integer (a
    :class:`numbers.Integral`: a ``numpy.int64`` too), else ``None``; a
    ``bool`` is not one."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        return None
    return int(value)


#: Each TOML type (and Python's ``None``) by a test of the value, in the
#: order tried: a ``bool`` before an integer, a date-time before a date.
_KINDS: Final[tuple[tuple[Callable[[object], bool], str], ...]] = (
    (lambda v: v is MISSING, "nothing"),
    (lambda v: v is None, "None"),
    (lambda v: isinstance(v, bool), "a boolean"),
    (lambda v: _integer(v) is not None, "an integer"),
    (lambda v: isinstance(v, float), "a float"),
    (lambda v: isinstance(v, str), "a string"),
    (lambda v: isinstance(v, datetime.datetime), "a date-time"),
    (lambda v: isinstance(v, datetime.date), "a date"),
    (lambda v: isinstance(v, datetime.time), "a time"),
    (lambda v: isinstance(v, (list, tuple)), "an array"),
    (lambda v: isinstance(v, Mapping), "a table"),
)


def _kind(value: object) -> str:
    """The TOML type of *value*, with its article (``a table``); for
    another Python type, its name."""
    found = next((name for test, name in _KINDS if test(value)), None)
    if found is not None:
        return found
    name = type(value).__name__
    if _TYPE_NAME.fullmatch(name) is None:
        return "a value of another type"
    return f"a value of type {name}"


def _shown(value: object) -> str | None:
    """*value* as a line shows it after its type, or ``None`` when the line
    shows the type only (a table, an array, a date-time)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    number = _integer(value)
    if number is not None:
        if abs(number) >= 10**_SHOWN_DIGITS:
            return f"of {_SHOWN_DIGITS + 1} digits or more"
        return str(number)
    if isinstance(value, float):
        return float.__repr__(value)
    if isinstance(value, str):
        # Masked before it is cut, so a cut never shows the start of a
        # URL's user information; quote_source escapes what is left.
        masked = given_path_text(value)
        cut = masked[:SHOWN_CHARS]
        return quote_source(cut) + ("..." if len(masked) > SHOWN_CHARS else "")
    return None


def found_text(value: object) -> str:
    """What was found, as a line says it after ``got``: ``nothing``
    (:data:`MISSING`), ``a boolean true``, ``an integer 0``, ``a float
    1.5``, ``a string 'maybe'`` (a URL's credentials masked, at most
    :data:`SHOWN_CHARS` characters and ``...`` after it when cut, in quotes,
    escaped), ``a date-time``, ``a date``, ``a time``, ``an array``, ``a
    table``; from a library caller ``None`` or ``a value of type X``. A
    ``bool`` is a boolean, never an integer. A :class:`Found` is written as
    it was written then."""
    if isinstance(value, Found):
        return value.text
    kind = _kind(value)
    shown = _shown(value)
    return kind if shown is None else f"{kind} {shown}"


def kind_text(value: object) -> str:
    """What was found by its type only (``a string``): for a value that may
    be a secret."""
    return _kind(value)


#: Every ``got`` text.
FOUND_PATTERN: Final = "|".join(
    (
        "nothing",
        "None",
        "a boolean(?: true| false)?",
        rf"an integer(?: -?[0-9]{{1,{_SHOWN_DIGITS}}}| of {_SHOWN_DIGITS + 1} "
        "digits or more)?",
        r"a float(?: \S+)?",
        rf"a string(?: (?:{QUOTED})(?:\.\.\.)?)?",
        "a date-time",
        "a date",
        "a time",
        "an array",
        "a table",
        r"a value of (?:type [A-Za-z_][A-Za-z0-9_]*|another type)",
    )
)
