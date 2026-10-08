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
        max_crfsuite_labels: Most labels in one CRFsuite model. Real
            models hold a few to a few dozen.
        max_crfsuite_labels_chunk_bytes: Largest CRFsuite labels chunk,
            which is read whole: its hash tables and every label string.
        max_label_bytes: Longest label of a model (CRFsuite, fastText) a
            caller records, in UTF-8 bytes. Not checked by a format reader,
            which returns every label: what to do with a longer one is the
            caller's policy.
    """

    max_pickle_opcodes: int = 250_000
    max_pickle_decimal_digits: int = 4300
    max_crfsuite_labels: int = 1000
    max_crfsuite_labels_chunk_bytes: int = 1 << 20
    max_label_bytes: int = 4096

    def __post_init__(self) -> None:
        for name in (
            "max_pickle_opcodes",
            "max_pickle_decimal_digits",
            "max_crfsuite_labels",
            "max_crfsuite_labels_chunk_bytes",
            "max_label_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"Limits.{name} must be an int of at least 1")

    @property
    def max_pickle_decimal_bytes(self) -> int:
        """Longest decimal argument text: the digits, a sign and
        ``LONG``'s trailing ``L``."""
        return self.max_pickle_decimal_digits + 2
