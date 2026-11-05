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

from pitloom.core.quote_source import quote_source
from pitloom.logging_config import loggable, one_line


def size_text(size: int) -> str:
    """*size* as every message and comment states it: ``1 byte``, ``N bytes``."""
    return f"{size} byte" if size == 1 else f"{size} bytes"


def _path_text(value: object) -> str:
    """*value*, a ``str`` or :class:`os.PathLike` path, as text.

    Raises:
        ValueError: It is neither, or names a path in bytes.
    """
    text = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(text, str):
        raise ValueError(f"not a path: {value!r}")
    return text


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


def free_text(value: object) -> str:
    """A free text value: as it is when printable, else escaped."""
    return loggable(plain_text(value))


def failure_text(value: object) -> str:
    """What stopped a read, from the exception *value*, on one line: an
    :class:`OSError`'s own description (``strerror``, ``Permission
    denied``), never its text, which quotes the path; any other
    exception's text, its class name when it has none.

    Raises:
        ValueError: *value* is not an exception (a text included).
    """
    if not isinstance(value, BaseException):
        raise ValueError(f"not an exception: {value!r}")
    if isinstance(value, OSError) and value.strerror:
        return one_line(value.strerror)
    return one_line(value)


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
