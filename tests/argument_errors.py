# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The exception class a library refusal of an integer argument raises: a
value that is no integer (a ``bool``, a ``float``, a string, ``None``) is a
:class:`TypeError`, an integer the parameter does not take a
:class:`ValueError` (both ``option-invalid``).

See also: tests/core/test_library_argument_types.py (the rule).

:func:`enter_loom_run` enters a ``loom.run`` block, whose checks run then.
"""

from __future__ import annotations

import operator
from typing import Any

from pitloom import loom


def integer_refusal(bad: object) -> type[Exception]:
    """:class:`ValueError` for an integer (an ``int`` or any
    :func:`operator.index`-able value, a ``numpy.int64``; not a ``bool``),
    else :class:`TypeError`."""
    if isinstance(bad, bool):
        return TypeError
    try:
        operator.index(bad)  # type: ignore[arg-type]
    except TypeError:
        return TypeError
    return ValueError


def enter_loom_run(**kwargs: Any) -> None:
    """Open (and close) a ``loom.run("o.json", **kwargs)`` block: its
    argument checks run on entry."""
    with loom.run("o.json", **kwargs):
        pass
