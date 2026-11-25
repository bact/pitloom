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

import math
import os
import re
from typing import Final

from pitloom.core.given_path import given_spelling
from pitloom.core.quote_source import given_path_text, quote_source
from pitloom.core.url_masking import mask_checkout, sanitize_url
from pitloom.log_masking import masked_text
from pitloom.logging_config import failure_reason, loggable, one_line

#: The most characters of an exception's text a ``failure`` field shows.
FAILURE_CHARACTERS: Final = 500

#: The most characters of a name a message shows (an archive member, an
#: archive, a file an archive or a configuration names), ``...`` after a
#: cut. A display cap: it bounds the report only, so that a line naming
#: the longest names stays under
#: :data:`~pitloom.messages._lines.LONGEST_LINE` and keeps its code; the
#: name itself is read and compared in full.
NAME_CHARACTERS: Final = 500

#: What follows a name cut to :data:`NAME_CHARACTERS`.
NAME_CUT_MARK: Final = "..."

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


#: ``(Request ID: ...)``, as ``huggingface_hub`` writes the id of an HTTP
#: request that failed into its exception's text (the response's
#: ``X-Request-Id``, else ``X-Amzn-Trace-Id``, else ``X-Amz-Cf-Id`` header,
#: each under its own label): a new id on every request.
_REQUEST_ID: Final = re.compile(r"\((?:Request ID|Amzn Trace ID|Amz CF ID): [^()]+\)")


def _steady(text: str) -> str:
    """*text* without what differs per run: a Hub request's id
    (:data:`_REQUEST_ID`) and a memory address (:func:`_without_addresses`)."""
    return _without_addresses(_REQUEST_ID.sub("", text))


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


def duration_text(value: object) -> str:
    """A whole number of seconds: ``1 second``, ``N seconds``."""
    seconds = whole(value)
    return f"{seconds} second" if seconds == 1 else f"{seconds} seconds"


def whole_seconds(seconds: float) -> int:
    """A time limit of *seconds* as the whole number a ``duration`` field
    prints: rounded up, and at least 1, so a sub-second limit does not read
    as none."""
    return max(math.ceil(seconds), 1)


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


def masked(text: str) -> str:
    """*text* with a temporary directory, a URL's credentials and a
    secret-named parameter's value masked
    (:func:`~pitloom.log_masking.masked_text`, which never raises); nothing
    else changed (white space kept)."""
    return masked_text(mask_checkout(text))


def cut_masked(text: str, limit: int) -> str:
    """*text*, already :func:`masked`, cut to *limit* characters with
    :data:`NAME_CUT_MARK` after a cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + NAME_CUT_MARK


def cut_name(text: str) -> str:
    """*text*, a name, for a message: masked (:func:`masked`), then cut to
    :data:`NAME_CHARACTERS` characters with :data:`NAME_CUT_MARK` after it;
    neither quoted nor escaped, so a field's writer quotes and escapes it as
    any other name. Masked before it is cut, so a cut never takes away the
    end of a URL's user information."""
    return cut_masked(masked(text), NAME_CHARACTERS)


def escaped_name(text: str) -> str:
    """*text*, a name a caller writes into a free field (a file or folder
    name), masked and cut (:func:`cut_name`), then escaped
    (:func:`~pitloom.logging_config.loggable`): masked before it is escaped,
    so an escape (``\\t``, ``\\x1b``) cannot stand between a credential and
    what the masker reads before it."""
    return loggable(cut_name(text))


def url_text(url: str) -> str:
    """*url*, a URL a caller writes into a ``url`` or ``target`` field: its
    credentials masked as one URL's
    (:func:`~pitloom.core.url_masking.sanitize_url`: the user information
    whole) and as a line's (:func:`masked`: an access token, an scp-style
    password, a ``Bearer`` credential), then escaped
    (:func:`~pitloom.logging_config.loggable`), as :func:`escaped_name`
    orders them; not cut."""
    return loggable(masked(sanitize_url(url)))


def cut_and_escaped(masked_name: str) -> str:
    """*masked_name*, already :func:`masked`, cut to :data:`NAME_CHARACTERS`
    characters (:func:`cut_masked`), then escaped when it holds a control
    character: the last two steps every cut name writer shares."""
    return loggable(cut_masked(masked_name, NAME_CHARACTERS))


def quoted_name_text(value: object) -> str:
    """A name in quotes (:func:`quoted_text`), masked and cut first
    (:func:`cut_name`), the mark inside the quotes."""
    return quote_source(cut_name(plain_text(value)))


def free_text(value: object) -> str:
    """A free text value: as it is when printable, else escaped."""
    return loggable(plain_text(value))


def free_name_text(value: object) -> str:
    """A name as free text (:func:`free_text`), masked and cut first
    (:func:`cut_name`): a package name read from a file can be as long as
    the file."""
    return cut_and_escaped(masked(plain_text(value)))


def failure_text(value: object) -> str:
    """What stopped a read, from the exception *value*, on one line: an
    :class:`OSError`'s own description (``strerror``, ``Permission
    denied``), never its text, which quotes the path; any other
    exception's text (:func:`~pitloom.logging_config.failure_reason`) with
    a memory address (`` at 0x...``, as in an object's default repr) and a
    Hub request id (``(Request ID: ...)``) dropped (the ``steady`` step of
    :func:`~pitloom.logging_config.one_line`, which collapses the white
    space the drop leaves), so these two do not make the line differ per
    run (a server's own text still can). That step runs for every failure
    without a ``strerror`` (a Hub error, an ``OSError`` with no
    ``strerror``, any other exception) and for the head of an
    :class:`http.client.InvalidURL`; an ``OSError`` with a ``strerror`` is
    shown as the OS wrote it (masked and cut, nothing dropped). Its class
    name when nothing is left; the credentials of a URL in what is left
    masked; then cut to :data:`FAILURE_CHARACTERS` characters (then ``...``): a
    server's error page can be as long as it likes. Dropped before the cut,
    so the cut is decided on the text shown. The text also reaches a
    library caller in an exception, past the log sink.

    Raises:
        ValueError: *value* is not an exception (a text included).
    """
    if not isinstance(value, BaseException):
        raise ValueError(f"not an exception: {value!r}")
    if isinstance(value, OSError) and value.strerror:
        return one_line(value.strerror, FAILURE_CHARACTERS, ellipsis=True)
    return failure_reason(value, FAILURE_CHARACTERS, ellipsis=True, steady=_steady)


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


def cut_entity_text(value: object) -> str:
    """An element's name or registry key as :func:`entity_text` writes it,
    cut to :data:`NAME_CHARACTERS` characters (then :data:`NAME_CUT_MARK`)
    after masking and before escaping: a caller's model or dataset name can
    be as long as it likes. :func:`entity_text` stays uncut, as a
    comparison of two written values needs.

    Raises:
        ValueError: It is not a ``str``.
    """
    return cut_and_escaped(given_path_text(plain_text(value)))


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
