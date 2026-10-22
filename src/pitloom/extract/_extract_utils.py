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

from pitloom.core.untrusted_text import escape_display_controls
from pitloom.logging_config import Cap

if TYPE_CHECKING:
    #: An installed or archived package's Core Metadata: parsed from its raw
    #: text (``email``), or :mod:`importlib.metadata`'s view of it.
    CoreMetadata = email.message.Message[str, str] | PackageMetadata


def sanitize_provenance_text(text: str) -> str:
    """Escape ``|`` and the invisible and bidi controls in untrusted text
    destined for a provenance string.

    :func:`~pitloom.core.provenance.parse_provenance_value` splits a
    provenance string on ``|`` to find its ``Source:``/``Field:``/``Method:``
    segments. Any untrusted text interpolated into a provenance string --
    a model filename, a binary artifact's internal key name -- can contain
    ``|`` and inject a fake segment when the string is later re-parsed (e.g.
    misattributing the source to a transparent manifest, which silently drops
    the entry in minimal detail mode). Apply this to every untrusted string
    *before* it is embedded in a ``"Source: ..."`` / ``"Field: ..."`` string,
    not just to dict keys passed to :func:`record_dict_field_provenance` --
    the same untrusted filename also flows directly into scalar-field
    provenance (``name``, ``version``, ...) built without that helper.

    A provenance string is shown to a reader (an Annotation ``statement``,
    the element's ``comment``), so the controls are written as text, as in
    every other display string
    (:func:`~pitloom.core.untrusted_text.escape_display_controls`).
    """
    return escape_display_controls(text.replace("|", "/"))


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

    *keys* come from the metadata artifact itself, not from Pitloom -- see
    :func:`sanitize_provenance_text` for why they (and *source*, when a
    caller hasn't already sanitized it) are escaped before interpolation.

    Args:
        provenance: The metadata object's provenance map, updated in place.
        field_name: The dict field's name (``"properties"``, ``"hyperparameters"``).
        keys: The dict's keys (each becomes its own provenance entry).
        source: The base source string, e.g. ``"Source: model.gguf"``.
        location_prefix: Prepended to each key to form the ``Field:`` location.
    """
    safe_source = sanitize_provenance_text(source)
    # Sorted: the source's own key order (a file header, a JSON object)
    # must not change the output bytes.
    for key in sorted(keys, key=str):
        safe_key = sanitize_provenance_text(str(key))
        provenance[f"{field_name}.{key}"] = (
            f"{safe_source} | Field: {location_prefix}{safe_key}"
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
# end, so it is scanned once) or a bracket.
_JSON_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"?|[\[\]{}]', re.DOTALL)


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


_UNPRINTABLE = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff]")


def quote_source(source: str | Path) -> str:
    """*source* in quotes, written as the OS writes it, on one line.

    ``repr()`` of a :class:`~pathlib.Path` shows ``WindowsPath('D:/a/b')``
    (forward slashes) and of a ``str`` doubles each backslash; neither matches
    ``str(path)``, which a reader of the message looks for. Only control
    characters and lone surrogates are escaped (``\\n``-style), so a name with
    a newline cannot split the message over two lines.
    """
    text = _UNPRINTABLE.sub(lambda match: ascii(match.group())[1:-1], str(source))
    return f"'{text}'"


#: Largest file or response read whole for parsing (JSON sources, lock/pin
#: files); a caller over it fails with its own ``WARNING:``/error.
FETCH_MAX_BYTES = 50 * 1024 * 1024


def fetch_json(
    source: str | Path,
    timeout: float = 30.0,
    max_bytes: int = FETCH_MAX_BYTES,
    max_nesting: Cap | None = None,
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

    Returns:
        Parsed JSON as a ``dict``.

    Raises:
        ValueError: If the data cannot be fetched, is not valid JSON or is
            over *max_nesting*, or if the top-level value is not a JSON
            object.
    """
    where = quote_source(source)
    try:
        if isinstance(source, str) and source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=timeout) as resp:  # nosec B310
                raw = resp.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise ValueError(
                        f"Source {where} response exceeds maximum limit of "
                        f"{max_bytes} bytes"
                    )
        else:
            # A FIFO or device would block the open or the read.
            if not stat.S_ISREG(os.stat(source).st_mode):
                raise ValueError(f"Source {where} is not a regular file")
            with Path(source).open("rb") as fh:
                raw = fh.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError(
                    f"Source {where} exceeds maximum limit of {max_bytes} bytes"
                )
    except (OSError, http.client.HTTPException) as exc:
        close_http_error(exc)
        # http.client.HTTPException (e.g. IncompleteRead on a connection that
        # closes mid-response) is not an OSError subclass, so it needs its
        # own arm here -- without it, a transient network glitch would raise
        # out of what every caller treats as a "fetch failed" ValueError path.
        raise ValueError(f"Cannot read source {where}: {exc}") from exc

    if max_nesting is not None and json_nests_over(raw, max_nesting.limit):
        raise ValueError(f"Source {where} is {max_nesting.reason}")

    try:
        data = json.loads(raw)
    # Any ValueError: a JSONDecodeError, bytes that are not UTF-8 (or
    # -16/-32), an integer over Python's digit limit; a RecursionError:
    # nesting too deep to parse.
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"Source {where} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Source {where}: expected a JSON object, got {type(data).__name__}"
        )
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
