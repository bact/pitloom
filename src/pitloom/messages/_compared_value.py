# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Showing two values a line compares (a wheel's ``METADATA`` and its
embedded SBOM) so that two different values never look alike.

A value is shown exactly: a ``str`` as stated, any other value as JSON
(keys sorted, ASCII), never collapsed. The whole value is masked first
(:func:`~pitloom.log_masking.masked_text`: a URL's credentials, a
secret-named parameter with or without a URL), then cut to
:data:`~pitloom.logging_config.EXCERPT_CHARS` characters with ``...``,
then its backslashes doubled, then quoted and escaped
(:func:`~pitloom.core.quote_source.quote_source`), so the escape syntax is
one-to-one: ``'demo\\\\t'`` (a backslash and a ``t``) is not ``'demo\\t'``
(a tab).

Two different values can still look alike: equal up to the cut, or
different only in characters that look the same (an NFC ``e`` with acute
against ``e`` and a combining acute). So :func:`compared_pair` adds `` (from
character N: <rest>)`` to both sides when the masked values differ and
either their shown forms are equal or either holds a non-ASCII character:
*N* counts characters of the masked value (a masked credential shifts it),
*rest* is the masked value from there, cut alike and written as an ASCII
literal (``'\\u0301'``). Values equal once masked (two credentials) look
alike by design; the comparison is of the raw text, not a normalised name
or version.

See also: :mod:`pitloom.messages._fields_wheels` (the fields that use it).
"""

from __future__ import annotations

import json
from typing import NamedTuple

from pitloom.core.quote_source import quote_source
from pitloom.log_masking import masked_text
from pitloom.logging_config import EXCERPT_CHARS
from pitloom.messages._field_writers import NAME_CUT_MARK, cut_masked


class ComparedValue(NamedTuple):
    """A value a line compares with another, as :func:`compared_pair`
    makes it: shown from character *differs_at* on as well."""

    #: The value as stated.
    value: object
    #: Where (0-based, in the masked value) it first differs from the other
    #: side; ``None`` when its shown form already tells them apart.
    differs_at: int | None = None


def _source(value: object) -> str:
    """*value* as text, masked whole: a ``str`` as it is, any other value as
    JSON (keys sorted, ASCII), else its ``repr``."""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, ensure_ascii=True)
        except (TypeError, ValueError):
            text = repr(value)
    return masked_text(text)


def _shown(text: str) -> str:
    """*text*, already masked, cut, its backslashes doubled, quoted and
    escaped: a one-to-one form of the cut text."""
    return quote_source(cut_masked(text, EXCERPT_CHARS).replace("\\", "\\\\"))


def _rest(text: str) -> str:
    """*text*, already masked, cut alike, as an ASCII literal."""
    cut = text[:EXCERPT_CHARS]
    return ascii(cut) + (NAME_CUT_MARK if len(text) > EXCERPT_CHARS else "")


def compared_text(value: object) -> str:
    """*value* (or a :class:`ComparedValue`) shown exactly (:func:`_shown`),
    then, with *differs_at*, `` (from character N: <rest>)``."""
    differs_at = None
    if isinstance(value, ComparedValue):
        value, differs_at = value
    text = _source(value)
    shown = _shown(text)
    if differs_at is None:
        return shown
    return f"{shown} (from character {differs_at + 1}: {_rest(text[differs_at:])})"


def compared_pair(wheel: object, sbom: object) -> tuple[object, object]:
    """*wheel* and *sbom* for one line: as they are when their shown forms
    tell them apart (both ASCII and different), else, when the masked
    values differ, each as a :class:`ComparedValue` shown from the first
    character that differs."""
    left, right = _source(wheel), _source(sbom)
    if left == right:
        return wheel, sbom
    shown_left, shown_right = _shown(left), _shown(right)
    if shown_left != shown_right and (shown_left + shown_right).isascii():
        return wheel, sbom
    pairs = zip(left, right, strict=False)
    shorter = min(len(left), len(right))
    at = next((i for i, (a, b) in enumerate(pairs) if a != b), shorter)
    return ComparedValue(wheel, at), ComparedValue(sbom, at)
