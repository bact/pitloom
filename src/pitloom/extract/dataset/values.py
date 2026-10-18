# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one set of checks a dataset source's field values go through before
they reach :class:`~pitloom.core.dataset_metadata.DatasetMetadata`, for
every dataset reader (Croissant, a local or Hub dataset card), so a wrong
type is refused the same way everywhere.

Each helper returns ``None`` (or ``[]``) silently when the field is absent
or blank (nothing was stated), and also when the value has a shape the
field cannot hold, then with one ``WARNING:`` (the source stated something
not recordable).

See also: :mod:`pitloom.extract.dataset.licence` (the licence rules, on
top of :func:`stated_text`).
"""

from __future__ import annotations

import logging

from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

__all__ = [
    "MAX_NUMBER_DIGITS",
    "NOT_A_COUNT_WARNING",
    "NOT_TEXT_WARNING",
    "TOO_MANY_DIGITS_WARNING",
    "stated_count",
    "stated_name",
    "stated_text",
    "stated_texts",
    "stated_version",
]

#: ``log.warning()`` format for a dataset field holding no text.
#: Arguments: the source, the field, the value's type name.
NOT_TEXT_WARNING = "dataset metadata: %s field %s is of type %s, not text; skipped"

#: ``log.warning()`` format for a size or count that is not a whole number
#: of zero or more. Arguments: the source, the field.
NOT_A_COUNT_WARNING = (
    "dataset metadata: %s field %s is not a whole number of zero or more; skipped"
)

#: The most digits a whole number read as text may have: far more than any
#: version or count, and well under Python's int-to-text limit.
MAX_NUMBER_DIGITS = 64

#: ``log.warning()`` format for a whole number over :data:`MAX_NUMBER_DIGITS`.
#: Arguments: the source, the field.
TOO_MANY_DIGITS_WARNING = (
    f"dataset metadata: %s field %s is a number of over {MAX_NUMBER_DIGITS} "
    "digits; skipped"
)

_LIMIT = 10**MAX_NUMBER_DIGITS


def _not_text(source: str, field: str, value: object) -> None:
    log.warning(NOT_TEXT_WARNING, loggable(source), field, type(value).__name__)


def stated_text(value: object, source: str, field: str) -> str | None:
    """*value*, a source's *field*, as stripped text: a string, the one
    item of a one-item list, or a JSON-LD node's ``@value`` (a literal) or
    ``@id`` (a reference) string. ``None`` when absent or blank, silently;
    for any other shape (a number, another mapping, several items) also
    ``None``, with one ``WARNING:``."""
    if value is None or value == []:
        return None
    found = value
    if isinstance(found, list) and len(found) == 1:
        found = found[0]
    if isinstance(found, dict):
        for key in ("@value", "@id"):
            if isinstance(found.get(key), str):
                found = found[key]
                break
    if not isinstance(found, str):
        _not_text(source, field, value)
        return None
    return found.strip() or None


def stated_texts(value: object, source: str, field: str) -> list[str]:
    """*value* as a list of stripped texts: each item of a list read as
    :func:`stated_text` reads one (an item of no text is left out, with one
    ``WARNING:`` for the field); a single text is one item, or several when
    it reads as a comma-separated list (a comma, no semicolon, under 200
    characters)."""
    if value is None:
        return []
    if not isinstance(value, list):
        text = stated_text(value, source, field)
        if text is None:
            return []
        if "," in text and ";" not in text and len(text) < 200:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    found: list[str] = []
    refused: object = None
    for item in value:
        if _is_blank(item):
            continue
        text = item.strip() if isinstance(item, str) else None
        if isinstance(item, dict):
            text = _node_text(item)
        if text:
            found.append(text)
        elif refused is None:
            refused = item
    if refused is not None:
        _not_text(source, field, refused)
    return found


def _node_text(node: dict[object, object]) -> str | None:
    """The stripped ``@value`` or ``@id`` string of a JSON-LD *node*."""
    for key in ("@value", "@id"):
        found = node.get(key)
        if isinstance(found, str):
            return found.strip() or None
    return None


def _is_digits(text: str) -> bool:
    """Whether *text* is ASCII digits only (``str.isdigit`` takes ``²``)."""
    return text.isascii() and text.isdigit()


def _is_blank(item: object) -> bool:
    """Whether *item* states nothing: ``None`` or blank text."""
    return item is None or (isinstance(item, str) and not item.strip())


def stated_name(value: object, source: str, field: str) -> str | None:
    """The name a *field* such as a creator states: text, or the ``name``
    of a node (a ``Person`` or ``Organization``); of a list, its first
    item. A blank name is none, silently."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        for key in ("name", "sc:name", "schema:name"):
            if key in value:
                return stated_text(value[key], source, f"{field} name")
        return None
    return stated_text(value, source, field)


def _whole_number_text(value: int, source: str, field: str) -> str | None:
    """*value* as text, unless it has over :data:`MAX_NUMBER_DIGITS` digits
    (one ``WARNING:``)."""
    if abs(value) >= _LIMIT:
        log.warning(TOO_MANY_DIGITS_WARNING, loggable(source), field)
        return None
    return str(value)


def stated_version(value: object, source: str, field: str = "version") -> str | None:
    """A ``version``: text, or a whole number as written; a float (YAML and
    JSON read ``1.10`` as ``1.1``), a ``true`` or anything else is no
    version, with one ``WARNING:``."""
    if isinstance(value, int) and not isinstance(value, bool):
        return _whole_number_text(value, source, field)
    if value is None or isinstance(value, (str, list, dict)):
        return stated_text(value, source, field)
    _not_text(source, field, value)
    return None


def stated_count(value: object, source: str, field: str) -> int | None:
    """A size or count: a whole number of zero or more, as a number, an
    integral float (``3.0``) or digits as text. Anything else (a negative,
    ``true``, ``1.9``, an infinity, other text) is none, with one
    ``WARNING:``."""
    if value is None:
        return None
    count: int | None = None
    if isinstance(value, bool):
        count = None
    elif isinstance(value, int):
        count = value
    elif isinstance(value, float) and value.is_integer():  # not inf or nan
        count = int(value)
    elif isinstance(value, str) and _is_digits(value.strip()):
        digits = value.strip()
        if len(digits) > MAX_NUMBER_DIGITS:
            log.warning(TOO_MANY_DIGITS_WARNING, loggable(source), field)
            return None
        count = int(digits)
    if count is None or count < 0:
        log.warning(NOT_A_COUNT_WARNING, loggable(source), field)
        return None
    if count >= _LIMIT:
        log.warning(TOO_MANY_DIGITS_WARNING, loggable(source), field)
        return None
    return count
