# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Bounds a format reader answers to.

See also: :mod:`pitloom.extract.ai_model.formats._errors`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    """Bounds on what one read may walk.

    Attributes:
        max_pickle_opcodes: Most opcodes in one pickle. A model's
            ``data.pkl`` holds thousands to a few hundred thousand.
        max_pickle_decimal_digits: Most digits in one decimal argument
            (``INT``, ``LONG``, ``GET``, ``PUT``). CPython's default
            ``int_max_str_digits``, so every number accepted converts under
            the default interpreter configuration. Real model pickles use
            the binary integer opcodes; a protocol 0 integer of a model
            has at most ~20 digits.
    """

    max_pickle_opcodes: int = 250_000
    max_pickle_decimal_digits: int = 4300

    def __post_init__(self) -> None:
        for name in ("max_pickle_opcodes", "max_pickle_decimal_digits"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"Limits.{name} must be an int of at least 1")

    @property
    def max_pickle_decimal_bytes(self) -> int:
        """Longest decimal argument text: the digits, a sign and
        ``LONG``'s trailing ``L``."""
        return self.max_pickle_decimal_digits + 2
