# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""How the catalogue writes a caller's value as a field's text: each
writer takes the value a call site passes and returns the text printed, or
raises :class:`ValueError` for a value of the wrong type.

See also: :mod:`pitloom.messages._fields` (the fields and their shapes).
"""

from __future__ import annotations

import os
import re
from typing import Final

from pitloom.core.given_path import given_spelling
from pitloom.core.quote_source import given_path_text, quote_source
from pitloom.logging_config import failure_reason, loggable, one_line

#: The most characters of an exception's text a ``failure`` field shows.
FAILURE_CHARACTERS: Final = 500

#: A bracket, or `` at 0x...``: the address in an object's default repr
#: (``<A object at 0x7f3a...>``, ``<cell at 0x10: int object>``) differs per run.
_ADDRESS_OR_BRACKET: Final = re.compile(r"[<>]| at 0x[0-9a-fA-F]+\b")


def _without_addresses(text: str) -> str:
    """*text* without each `` at 0x...`` inside ``<...>`` (an object's repr);
    one outside (a path, an offset such as ``header corrupt at 0x1a``) stays."""
    depth = 0
    kept = 0
    out: list[str] = []
    for found in _ADDRESS_OR_BRACKET.finditer(text):
        mark = found.group()
        if mark == "<":
            depth += 1
        elif mark == ">":
            depth = max(depth - 1, 0)
        elif depth:
            out.append(text[kept : found.start()])
            kept = found.end()
    out.append(text[kept:])
    return "".join(out)


class DescribedValue(str):
    """A value a caller has already described as text for a message (an
    SBOM element by type, id and name, a ``Hash`` by its fields, a number):
    the ``kept`` and ``dropped`` fields write it on one line, masked and cut,
    but not in quotes, which they put around a plain ``str`` value."""

    __slots__ = ()


def size_text(size: int) -> str:
    """*size* as every message and comment states it: ``1 byte``, ``N bytes``."""
    return f"{size} byte" if size == 1 else f"{size} bytes"


def _path_text(value: object) -> str:
    """*value*, a ``str`` or :class:`os.PathLike` path, as text: spelt as the
    user gave it (:func:`~pitloom.core.given_path.given_spelling`), a URL in
    it masked (:func:`~pitloom.core.url_masking.masked_given_path`).

    Raises:
        ValueError: It is neither, or names a path in bytes.
    """
    if isinstance(value, (str, os.PathLike)):
        spelt = given_spelling(value)
        if isinstance(os.fspath(spelt), str):
            return given_path_text(spelt)
    raise ValueError(f"not a path: {value!r}")


def file_text(value: object) -> str:
    """A ``FILE=`` value: the path as it is when printable, else escaped."""
    return loggable(_path_text(value))


def path_text(value: object) -> str:
    """A path in quotes, as every message quotes one."""
    return quote_source(_path_text(value))


def whole(value: object) -> int:
    """*value* when it is an ``int`` of zero or more (a ``bool`` is not).

    Raises:
        ValueError: It is not.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"not a whole number: {value!r}")
    return value


def count_text(value: object) -> str:
    """`` (N files)`` for two files or more, else nothing."""
    number = whole(value)
    return f" ({number} files)" if number > 1 else ""


def bytes_text(value: object) -> str:
    """A whole number of bytes (:func:`size_text`)."""
    return size_text(whole(value))


def number_text(value: object) -> str:
    """A whole number, in digits."""
    return str(whole(value))


def plain_text(value: object) -> str:
    """*value* when it is a ``str``.

    Raises:
        ValueError: It is not.
    """
    if not isinstance(value, str):
        raise ValueError(f"not text: {value!r}")
    return value


def quoted_text(value: object) -> str:
    """A text value in quotes, escaped, as :func:`path_text` quotes a path."""
    return quote_source(plain_text(value))


def free_text(value: object) -> str:
    """A free text value: as it is when printable, else escaped."""
    return loggable(plain_text(value))


def failure_text(value: object) -> str:
    """What stopped a read, from the exception *value*, on one line: an
    :class:`OSError`'s own description (``strerror``, ``Permission
    denied``), never its text, which quotes the path; any other
    exception's text, its class name when it has none, the credentials of a
    URL in it masked (:func:`~pitloom.logging_config.failure_reason`) and a
    memory address (`` at 0x...``, as in an object's default repr) dropped,
    so the line is the same on every run; cut to :data:`FAILURE_CHARACTERS`
    characters (then ``...``): a server's error page can be as long as it
    likes. The text also reaches a library
    caller in an exception, past the log sink.

    Raises:
        ValueError: *value* is not an exception (a text included).
    """
    if not isinstance(value, BaseException):
        raise ValueError(f"not an exception: {value!r}")
    if isinstance(value, OSError) and value.strerror:
        return one_line(value.strerror, FAILURE_CHARACTERS, ellipsis=True)
    return _without_addresses(failure_reason(value, FAILURE_CHARACTERS, ellipsis=True))


def joined(value: object) -> str:
    """A list or tuple of texts, comma-separated; an empty one writes
    nothing, which the field's shape refuses.

    Raises:
        ValueError: It is neither (a ``str`` included), or holds anything
            but text.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"not a list: {value!r}")
    return ", ".join(plain_text(item) for item in value)


def entity_text(value: object) -> str:
    """An element's name or registry key as given: the credentials of a URL
    in it masked (a dataset may be named by its URL), escaped when it holds
    a control character.

    Raises:
        ValueError: It is not a ``str``.
    """
    return loggable(given_path_text(plain_text(value)))


def entities_text(value: object) -> str:
    """A list or tuple of names or keys, each as :func:`entity_text` writes
    it, comma-separated in the order given; an empty one writes nothing,
    which the field's shape refuses.

    Raises:
        ValueError: It is neither (a ``str`` included), or holds anything
            but text.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"not a list: {value!r}")
    return ", ".join(entity_text(item) for item in value)
