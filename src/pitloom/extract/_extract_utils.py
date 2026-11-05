# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic utility functions for metadata extractors."""

from __future__ import annotations

import email.message
import http.client
import json
import os
import re
import stat
import urllib.request
from collections.abc import Iterable
from importlib.metadata import PackageMetadata
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError
from urllib.parse import urlparse

from pitloom.core.internal_error import InternalError
from pitloom.core.path_confine import NotRegularFileError
from pitloom.core.path_probe import is_missing_errno
from pitloom.core.provenance import provenance_segment
from pitloom.core.quote_source import quote_source
from pitloom.messages import (
    JSON_MALFORMED,
    NOT_JSON_LINE,
    NOT_OBJECT_LINE,
    OVER_CAP,
    SOURCE_LINE,
    Cap,
    CodedValueError,
    file_unreadable_error,
)

if TYPE_CHECKING:
    #: An installed or archived package's Core Metadata: parsed from its raw
    #: text (``email``), or :mod:`importlib.metadata`'s view of it.
    CoreMetadata = email.message.Message[str, str] | PackageMetadata


def record_dict_field_provenance(
    provenance: dict[str, str],
    field_name: str,
    keys: Iterable[str],
    source: str,
    *,
    location_prefix: str = "",
) -> None:
    """Record *exact per-key* provenance for a dict-valued metadata field.

    A dict field like ``properties`` or ``hyperparameters`` is assembled from
    many individual source keys, so each entry needs its own provenance,
    not one shared note for the whole dict. Sets
    ``provenance["<field_name>.<key>"] = "<source> | Field: <location_prefix><key>"``
    for every key, so each property/hyperparameter is individually traceable
    through both the Annotation ``statement`` and the ``comment``. Entries
    are added in sorted key order.

    Use *location_prefix* when the dict key is a short name under a common
    origin path (e.g. ``"config.config."`` for a Keras hyperparameter stored
    under ``config.config.<key>``); by default the key *is* the origin (the
    GGUF kv key, the safetensors ``__metadata__`` key, ...).

    *keys* come from the metadata artifact itself, not from Pitloom: each
    goes through :func:`~pitloom.core.provenance.provenance_segment`, which
    escapes it (see
    :func:`~pitloom.core.provenance.sanitize_provenance_text` for why).

    Args:
        provenance: The metadata object's provenance map, updated in place.
        field_name: The dict field's name (``"properties"``, ``"hyperparameters"``).
        keys: The dict's keys (each becomes its own provenance entry).
        source: The base source string, e.g. ``"Source: model.gguf"``, as
            :func:`~pitloom.core.provenance.provenance_source` built it.
        location_prefix: Prepended to each key to form the ``Field:`` location.
    """
    # Sorted: the source's own key order (a file header, a JSON object)
    # must not change the output bytes.
    for key in sorted(keys, key=str):
        provenance[f"{field_name}.{key}"] = provenance_segment(
            source, "Field", f"{location_prefix}{key}"
        )


def field_declared(container: Any, key: str) -> bool:
    """Return whether *key* is present in *container*, never the resolved
    value's truthiness.

    The one canonical presence check for the provenance-gating pattern
    documented in AGENTS.md's "Recurring bug patterns": a metadata
    producer must record provenance for a container field (``keywords``,
    ``dependencies``, ``authors``, ...) based on whether its raw source
    key was declared at all, not on whether the parsed value is truthy --
    ``dependencies = []`` is a declared, authoritative empty list, not an
    absent field. A bare ``key in container`` is enough for a plain
    ``dict``; some sources (e.g. Hatchling's ``core.config``) can raise
    ``OSError`` from the same underlying access their property accessors
    do, so that failure is treated as "not declared" rather than
    propagating.
    """
    try:
        return key in container
    except OSError:
        return False


def get_first(d: dict[str, Any], *keys: str) -> Any:
    """Return the value for the first matching key in *d*, or ``None``."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def pkg_meta_get(pkg_meta: CoreMetadata, key: str, default: str = "") -> str:
    """Return *pkg_meta*'s value for *key*, or *default* when absent.

    ``PackageMetadata`` has no ``.get()`` in its ``Protocol`` (only
    ``__getitem__``/``__contains__``/``get_all``), so guard with ``in``
    instead -- also avoids ``__getitem__``'s missing-key path, deprecated
    in Python 3.14+.
    """
    return pkg_meta[key] if key in pkg_meta else default


def to_str_list(value: Any) -> list[str]:
    """Normalise *value* to a non-empty list of strings.

    Handles:

    - ``None`` -> ``[]``
    - a single string -> ``[value]`` (splits on commas when the string looks
      like a CSV: contains a comma, no semicolons, and is short enough to be
      a keyword list rather than a sentence)
    - a list -> each element converted to ``str``, ``None`` elements dropped
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    # Single string: split on commas only when it reads like a keyword list.
    s = str(value).strip()
    if "," in s and ";" not in s and len(s) < 200:
        return [part.strip() for part in s.split(",") if part.strip()]
    return [s] if s else []


def close_http_error(exc: BaseException) -> None:
    """Close *exc* if it is an :class:`urllib.error.HTTPError`.

    An ``HTTPError`` is also the open HTTP response. Left unclosed, Python
    3.14 emits ``ResourceWarning: Implicitly cleaning up <HTTPError ...>``
    when it is garbage-collected. Call this in every handler that catches
    an ``urlopen()`` failure (``URLError``, ``OSError``) and does not re-raise
    the exception itself.
    """
    if isinstance(exc, HTTPError):
        exc.close()


# A JSON string (skipped whole, escapes included; one never closed runs to the
# end, so it is scanned once; unrolled, so a long string is not matched one
# character at a time) or a bracket.
_JSON_TOKEN = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"?|[\[\]{}]', re.DOTALL)


def json_nests_over(raw: bytes, limit: int) -> bool:
    """Whether the JSON text *raw* nests arrays and objects deeper than
    *limit*, counted without parsing it (so on every Python version the
    parser's own depth limit is out of the answer). Text that does not
    decode is not over: the parser reports it."""
    try:
        text = raw.decode(json.detect_encoding(raw), "surrogatepass")
    except UnicodeDecodeError:
        return False
    # Every nesting level is an opening bracket: fewer cannot be over.
    if text.count("[") + text.count("{") <= limit:
        return False
    depth = 0
    for token in _JSON_TOKEN.finditer(text):
        char = token.group()
        if char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth = max(depth - 1, 0)
    return False


#: Largest file or response read whole for parsing (JSON sources, lock/pin
#: files); a caller over it fails with its own ``WARNING:``/error.
FETCH_MAX_BYTES = 50 * 1024 * 1024


# pylint: disable-next=too-many-arguments
def fetch_json(
    source: str | Path,
    timeout: float = 30.0,
    max_bytes: int = FETCH_MAX_BYTES,
    max_nesting: Cap | None = None,
    *,
    use: str | None = None,
    subject: str = "source",
) -> dict[str, Any]:
    """Fetch and parse JSON from a local file path or an HTTP/HTTPS URL.

    Args:
        source: A URL string (``http://`` or ``https://``) or a
            :class:`~pathlib.Path` to a local file.
        timeout: Socket timeout in seconds for a URL *source* (ignored for a
            local file); default 30.
        max_bytes: Maximum allowed byte size for the response or file;
            default 50 MiB.
        max_nesting: The most levels of arrays and objects the document may
            nest (:func:`json_nests_over`); none by default.
        use: What a local file is read for, as its ``file-unreadable`` line
            says it (one of :data:`pitloom.messages.READ_USES`); required
            for a local *source*.
        subject: What *source* is, in the error for a URL that cannot be
            fetched or a file that is absent (``Cannot read <subject>
            '<source>': ...``).

    Returns:
        Parsed JSON as a ``dict``.

    Raises:
        ValueError: If the data cannot be fetched, is not valid JSON or is
            over *max_bytes* or *max_nesting*, or if the top-level value is
            not a JSON object. Each carries its ``pitloom_code``
            (``file-unreadable``, ``over-cap``, ``json-malformed``), but a
            URL that cannot be fetched and a file that is absent.
        pitloom.core.internal_error.InternalError: A local *source* without
            *use*.
    """
    url: str | None = None
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        url = source
    if url is None and use is None:
        raise InternalError("fetch_json: a local source needs its use")
    try:
        if url is not None:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
                raw = resp.read(max_bytes + 1)
        else:
            # A FIFO or device would block the open or the read.
            if not stat.S_ISREG(os.stat(source).st_mode):
                raise NotRegularFileError
            with Path(source).open("rb") as fh:
                raw = fh.read(max_bytes + 1)
    except (OSError, http.client.HTTPException) as exc:
        close_http_error(exc)
        # http.client.HTTPException (e.g. IncompleteRead on a connection that
        # closes mid-response) is not an OSError subclass, so it needs its
        # own arm here -- without it, a transient network glitch would raise
        # out of what every caller treats as a "fetch failed" ValueError path.
        # A URL that cannot be fetched and an absent file have no catalogued
        # line yet; an absent file is never unreadable.
        absent = isinstance(exc, OSError) and is_missing_errno(exc)
        if url is not None or use is None or absent or not isinstance(exc, OSError):
            where = quote_source(source)
            raise ValueError(f"Cannot read {subject} {where}: {exc}") from exc
        raise file_unreadable_error(exc, file=source, use=use) from exc

    if len(raw) > max_bytes:
        cap = Cap(max_bytes, "byte", "JSON-document")
        raise CodedValueError(
            OVER_CAP, line=SOURCE_LINE, path=source, **cap.reason_values()
        )
    if max_nesting is not None and json_nests_over(raw, max_nesting.limit):
        raise CodedValueError(
            OVER_CAP, line=SOURCE_LINE, path=source, **max_nesting.reason_values()
        )

    try:
        data = json.loads(raw)
    # Any ValueError: a JSONDecodeError, bytes that are not UTF-8 (or
    # -16/-32), an integer over Python's digit limit; a RecursionError:
    # nesting too deep to parse.
    except (ValueError, RecursionError) as exc:
        raise CodedValueError(
            JSON_MALFORMED, line=NOT_JSON_LINE, path=source, failure=exc
        ) from exc

    if not isinstance(data, dict):
        raise CodedValueError(JSON_MALFORMED, line=NOT_OBJECT_LINE, path=source)
    return data


def filename_from_url(url: str) -> str | None:
    """Extract a clean basename from a URL, stripping any query string
    and fragment (e.g. ``https://host/pkg-1.0.whl?sig=...#sha256=...`` ->
    ``pkg-1.0.whl``).

    Returns ``None`` when *url* has no path component or ends in a trailing
    slash. Handles both POSIX and Windows-style path separators.
    """
    clean_url = url.split("?", 1)[0].split("#", 1)[0]
    path = urlparse(clean_url).path
    if not path or path.endswith(("/", "\\")):
        return None
    return PureWindowsPath(path).name or None
