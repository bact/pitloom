# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounds on a pickle before fickling sees it.

fickling turns every opcode into Python AST nodes, at roughly two hundred
times the pickle's size in memory and time, so a few MiB of opcodes is
enough to exhaust a machine. :func:`first_pickle` walks the opcodes with
:func:`pitloom.extract.ai_model.formats.pickle_walk.first_pickle` (which
keeps no per-opcode state and converts no decimal number), refuses a
pickle past :data:`MAX_PICKLE_OPCODES` or holding a decimal number over
:data:`MAX_PICKLE_DECIMAL_DIGITS` digits, and returns only the bytes of the
first pickle, so fickling's input is bounded by what was verified.

See also: :mod:`pitloom.extract.ai_model.pytorch`.
"""

from __future__ import annotations

from pitloom.extract.ai_model.formats import (
    LimitExceeded,
    Limits,
    Malformed,
    pickle_walk,
)
from pitloom.extract.ai_model.limits import ModelLimitExceeded

#: Most opcodes of the pickle fickling is given. A model's ``data.pkl`` holds
#: thousands to a few hundred thousand.
MAX_PICKLE_OPCODES = Limits().max_pickle_opcodes

#: Most digits of one decimal number (``INT``, ``LONG``, ``GET``, ``PUT``
#: text), CPython's default ``int_max_str_digits``: fickling converts each
#: one, so a number it could not convert under the default limit never
#: reaches it, with the limit at its default or off. (A limit set lower than
#: the default can still make fickling fail on a shorter number.)
MAX_PICKLE_DECIMAL_DIGITS = Limits().max_pickle_decimal_digits


def first_pickle(data: bytes) -> bytes:
    """The bytes of the first pickle in *data*, through its ``STOP`` opcode.

    Raises:
        ModelLimitExceeded: The pickle has more than
            :data:`MAX_PICKLE_OPCODES` opcodes, or a decimal number over
            :data:`MAX_PICKLE_DECIMAL_DIGITS` digits.
        ValueError: *data* is not a complete, well-formed pickle.
    """
    limits = Limits(
        max_pickle_opcodes=MAX_PICKLE_OPCODES,
        max_pickle_decimal_digits=MAX_PICKLE_DECIMAL_DIGITS,
    )
    try:
        walk = pickle_walk.first_pickle(data, limits)
    except LimitExceeded as exc:
        raise ModelLimitExceeded(exc.reason) from None
    except Malformed as exc:
        raise ValueError(f"not a well-formed pickle: {exc.reason}") from exc
    return data[: walk.end]
