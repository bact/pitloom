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
        max_gguf_parsed: Budget for what a GGUF header walk parses: a
            key/value pair or a tensor info costs 4, a tensor dimension or
            an array element asked for 1. Real models declare thousands of
            tensors and tens of pairs.
        max_gguf_skipped_elements: Most strings and nested arrays a GGUF
            walk hops over unparsed, one length prefix each (about 0.1 us
            a hop: a Gemma-4 tokeniser's 777,050 strings take 0.09 s).
            Elements of a fixed size are passed in one step and not counted.
        max_gguf_string_bytes: Longest GGUF key, tensor name or string
            value decoded.
        max_gguf_total_string_bytes: Most bytes of GGUF keys, tensor names
            and string values decoded in one header, all together.
        max_gguf_nesting: Deepest GGUF array of arrays followed.
    """

    max_pickle_opcodes: int = 250_000
    max_pickle_decimal_digits: int = 4300
    max_crfsuite_labels: int = 1000
    max_crfsuite_labels_chunk_bytes: int = 1 << 20
    max_label_bytes: int = 4096
    max_gguf_parsed: int = 1_000_000
    max_gguf_skipped_elements: int = 4_194_304
    max_gguf_string_bytes: int = 8 * 1024 * 1024
    max_gguf_total_string_bytes: int = 64 * 1024 * 1024
    max_gguf_nesting: int = 4

    def __post_init__(self) -> None:
        for name in (
            "max_pickle_opcodes",
            "max_pickle_decimal_digits",
            "max_crfsuite_labels",
            "max_crfsuite_labels_chunk_bytes",
            "max_label_bytes",
            "max_gguf_parsed",
            "max_gguf_skipped_elements",
            "max_gguf_string_bytes",
            "max_gguf_total_string_bytes",
            "max_gguf_nesting",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"Limits.{name} must be an int of at least 1")

    @property
    def max_pickle_decimal_bytes(self) -> int:
        """Longest decimal argument text: the digits, a sign and
        ``LONG``'s trailing ``L``."""
        return self.max_pickle_decimal_digits + 2
