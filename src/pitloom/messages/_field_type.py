# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One value a catalogued line names: :class:`Field`.

See also: :mod:`pitloom.messages._fields` (every field) and
:mod:`pitloom.messages._fields_registry` (the ID registry's).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Field:
    """One value a template names."""

    #: The text the written value always matches (a regular expression).
    pattern: str
    #: Turns the caller's value into the text printed.
    write: Callable[[object], str]
    #: How the reference shows the value in a line.
    shown: str
    #: What the value is, for the reference.
    meaning: str
    #: Whether the value can be any text (a file name), so a template may not
    #: start with it or put it beside another field: it would take in what
    #: lies next to it.
    free: bool = False


#: A path or a text in quotes, as
#: :func:`~pitloom.core.quote_source.quote_source` writes it.
QUOTED: Final = r"'[^']*'|\"[^\"]*\"|'(?:[^'\\]|\\.)*'"
