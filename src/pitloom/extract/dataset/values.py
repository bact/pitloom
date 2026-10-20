# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one set of checks a dataset source's field values go through before
they reach :class:`~pitloom.core.dataset_metadata.DatasetMetadata`, for
every dataset reader (Croissant: every field it returns, its data types
included; a local or Hub dataset card: licence, ``pretty_name``,
``version`` and tags), so a wrong type is refused the same way everywhere.

Each helper returns ``None`` (or ``[]``) silently when the field is absent
or blank (nothing was stated), and also when the value has a shape the
field cannot hold, then with one ``WARNING:`` (the source stated something
not recordable). A list is never walked past its own items: a YAML alias
can make a tree of exponential size, or a cycle.

See also: :mod:`pitloom.extract.dataset.licence` (the licence rules, on
top of :func:`stated_text`).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from pitloom.core.canonical_json import MAX_SAFE_INTEGER
from pitloom.core.dataset_metadata import is_placeholder
from pitloom.logging_config import Cap, loggable, warn_over_cap

log = logging.getLogger(__name__)

__all__ = [
    "MAX_VERSION_DIGITS",
    "NOT_A_COUNT_WARNING",
    "NOT_A_URL_WARNING",
    "NOT_TEXT_WARNING",
    "UNQUOTED_VERSION_WARNING",
    "is_placeholder",
    "stated_count",
    "stated_name",
    "stated_text",
    "stated_texts",
    "stated_total",
    "stated_url",
    "stated_version",
    "text_of",
    "warn_not_text",
]

#: ``log.warning()`` format for a dataset field holding no text.
#: Arguments: the source, the field, the value's type name.
NOT_TEXT_WARNING = "dataset metadata: %s field %s is of type %s, not text; skipped"

#: ``log.warning()`` format for a card ``version`` YAML did not read as text
#: (``1.10`` reads as ``1.1``, ``1:1:1`` as ``3661``, ``010`` as ``8``).
#: Arguments: the source, the value's type name.
UNQUOTED_VERSION_WARNING = (
    "dataset metadata: %s field version is of type %s, not text; "
    "quote it to keep it as written; skipped"
)

#: ``log.warning()`` format for a size or count that is not a whole number
#: of zero or more. Arguments: the source, the field.
NOT_A_COUNT_WARNING = (
    "dataset metadata: %s field %s is not a whole number of zero or more; skipped"
)

#: ``log.warning()`` format for a URL field holding text that is not a URL.
#: Arguments: the source, the field.
NOT_A_URL_WARNING = "dataset metadata: %s field %s is not a URL; skipped"


#: A URL a download can name: a scheme, then a host (``https://``, ``s3://``,
#: ``hf://``), and no whitespace or control character.
_URL_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")

#: A size or count over the largest integer canonical JSON (RFC 8785) can
#: write: the SBOM could not be serialised with it.
_COUNT_CAP = Cap(MAX_SAFE_INTEGER, "item", "canonical-JSON-integer", "FIELD")

#: The most digits a version written as a number (Croissant JSON) may have:
#: far more than any version, well under Python's int-to-text limit.
MAX_VERSION_DIGITS = 64
_VERSION_CAP = Cap(MAX_VERSION_DIGITS, "digit", "dataset-version", "FIELD")


def warn_not_text(source: str, field: str, value: object) -> None:
    """The one ``WARNING:`` for a *field* of *source* holding *value*, of a
    type that is not text."""
    log.warning(NOT_TEXT_WARNING, loggable(source), field, type(value).__name__)


def _is_blank(item: object) -> bool:
    """Whether *item* states nothing: ``None`` or blank text."""
    return item is None or (isinstance(item, str) and not item.strip())


def text_of(value: object) -> tuple[str | None, bool]:
    """The stripped text *value* states (``None``: none), and whether its
    shape can hold text: a string, a one-item list of one, or a JSON-LD
    node's ``@value`` (a literal) or ``@id`` (a reference) string."""
    if isinstance(value, list):
        if len(value) > 1:
            return None, False
        value = value[0] if value else None
    if isinstance(value, dict):
        for key in ("@value", "@id"):
            if isinstance(value.get(key), str):
                value = value[key]
                break
    if _is_blank(value):
        return None, True
    if isinstance(value, str):
        return value.strip(), True
    return None, False


def stated_text(value: object, source: str, field: str) -> str | None:
    """*value*, a source's *field*, as stripped text (:func:`text_of`).
    ``None`` when absent or blank (``[None]`` and ``[""]`` too), silently;
    for any other shape (a number, another mapping, several items) also
    ``None``, with one ``WARNING:``."""
    text, holds_text = text_of(value)
    if not holds_text:
        warn_not_text(source, field, value)
    return text


def stated_texts(
    value: object, source: str, field: str, *, split: bool = True
) -> list[str]:
    """*value* as a list of stripped texts: each item of a list that reads
    as text (a string or a JSON-LD node's string), the others left out with
    one ``WARNING:`` for the field; a single text is one item, or, with
    *split*, several when it reads as a comma-separated list (a comma, no
    semicolon, under 200 characters)."""
    if not isinstance(value, list):
        text = stated_text(value, source, field)
        if text is None:
            return []
        if split and "," in text and ";" not in text and len(text) < 200:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    found: list[str] = []
    refused: list[object] = []
    for item in value:
        text, holds_text = (None, False) if isinstance(item, list) else text_of(item)
        if text is not None:
            found.append(text)
        elif not holds_text:
            refused.append(item)
    if refused:
        warn_not_text(source, field, refused[0])
    return found


def stated_name(value: object, source: str, field: str) -> str | None:
    """The name a *field* such as a creator states: text, or the ``name``
    of a node (a ``Person`` or ``Organization``); of a list, its first item
    that states something. A blank name or a placeholder
    (:func:`is_placeholder`) is none, silently."""
    if isinstance(value, list):
        value = next(
            (
                item
                for item in value
                if not _is_blank(item)
                and not (isinstance(item, str) and is_placeholder(item))
            ),
            None,
        )
    if isinstance(value, dict):
        for key in ("name", "sc:name", "schema:name"):
            if key in value:
                value, field = value[key], f"{field} name"
                break
        else:
            return None
    return _not_placeholder(stated_text(value, source, field))


def _not_placeholder(text: str | None) -> str | None:
    """*text*, or ``None`` when it is a placeholder."""
    return None if text is not None and is_placeholder(text) else text


def stated_url(value: object, source: str, field: str) -> str | None:
    """A URL a *field* such as a download location states: text with a
    scheme and a host, no whitespace. ``None`` when absent, blank or a
    placeholder (:func:`is_placeholder`), silently; for any other text, or
    another shape, with one ``WARNING:``."""
    text = _not_placeholder(stated_text(value, source, field))
    if text is None:
        return None
    try:
        parts = urlsplit(text)
        valid = bool(parts.netloc) and _URL_SCHEME.fullmatch(parts.scheme) is not None
    except ValueError:
        valid = False
    if not valid or any(c.isspace() or not c.isprintable() for c in text):
        log.warning(NOT_A_URL_WARNING, loggable(source), field)
        return None
    return text


def stated_version(
    value: object, source: str, *, numbers: bool, field: str = "version"
) -> str | None:
    """A ``version``: text. With *numbers* (JSON, whose integers are
    unambiguous decimals), also a whole number as written, up to
    :data:`MAX_VERSION_DIGITS` digits. A placeholder
    (:func:`is_placeholder`) is none, silently. Anything else (a float:
    ``1.10`` reads as ``1.1``; a YAML 1.1 integer: ``1:1:1`` reads as
    ``3661``) is no version, with one ``WARNING:``."""
    if value is None or isinstance(value, (str, list, dict)):
        return _not_placeholder(stated_text(value, source, field))
    if numbers and isinstance(value, int) and not isinstance(value, bool):
        if abs(value) >= 10**MAX_VERSION_DIGITS:
            warn_over_cap(log, _VERSION_CAP, f"{source} {field}")
            return None
        return str(value)
    if numbers:
        warn_not_text(source, field, value)
    else:
        log.warning(UNQUOTED_VERSION_WARNING, loggable(source), type(value).__name__)
    return None


def _count_of(value: object) -> tuple[int | None, str | None]:
    """The count *value* states, or why it states none: ``"count"`` (not a
    whole number of zero or more) or ``"cap"`` (over :data:`_COUNT_CAP`);
    ``(None, None)`` when absent."""
    if value is None:
        return None, None
    count: int | None = None
    if isinstance(value, bool):
        return None, "count"
    if isinstance(value, int):
        count = value
    elif isinstance(value, float) and value.is_integer():  # not inf or nan
        count = int(value)
    elif isinstance(value, str) and value.strip().isascii():
        digits = value.strip()
        if digits.isdigit():
            if len(digits) > len(str(_COUNT_CAP.limit)):
                return None, "cap"
            count = int(digits)
    if count is None or count < 0:
        return None, "count"
    if count > _COUNT_CAP.limit:
        return None, "cap"
    return count, None


def _warn_count(reason: str, source: str, field: str) -> None:
    """The one ``WARNING:`` for a *field* of *source* that states no count,
    for *reason* (:func:`_count_of`)."""
    if reason == "cap":
        warn_over_cap(log, _COUNT_CAP, f"{source} {field}")
    else:
        log.warning(NOT_A_COUNT_WARNING, loggable(source), field)


def stated_count(value: object, source: str, field: str) -> int | None:
    """A size or count: a whole number of zero or more, as a number, an
    integral float (``3.0``) or ASCII digits as text, up to the largest
    integer canonical JSON can write. Anything else (a negative, ``true``,
    ``1.9``, an infinity, other text, a larger number) is none, with one
    ``WARNING:``."""
    count, reason = _count_of(value)
    if reason is not None:
        _warn_count(reason, source, field)
    return count


def stated_total(values: list[object], source: str, field: str) -> int | None:
    """The sum of the counts *values* state (each read as
    :func:`stated_count` reads one); ``None`` when none states one. Items
    stating none, and a sum over the largest integer canonical JSON can
    write, are one ``WARNING:`` each for the field, not one per item."""
    read = [_count_of(value) for value in values]
    reasons = [reason for _, reason in read if reason is not None]
    if reasons:
        _warn_count(reasons[0], source, field)
    counts = [count for count, _ in read if count is not None]
    if not counts:
        return None
    if sum(counts) > _COUNT_CAP.limit:
        _warn_count("cap", source, field)
        return None
    return sum(counts)
