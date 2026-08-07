# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic utility functions for metadata extractors."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def sanitize_provenance_text(text: str) -> str:
    """Escape ``|`` in untrusted text destined for a provenance string.

    :func:`~pitloom.assemble.spdx3.provenance.parse_provenance_value` splits a
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
    """
    return text.replace("|", "/")


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
    through both the Annotation ``statement`` and the ``comment``.

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
    for key in keys:
        safe_key = sanitize_provenance_text(str(key))
        provenance[f"{field_name}.{key}"] = (
            f"{safe_source} | Field: {location_prefix}{safe_key}"
        )


def get_first(d: dict[str, Any], *keys: str) -> Any:
    """Return the value for the first matching key in *d*, or ``None``."""
    for k in keys:
        if k in d:
            return d[k]
    return None


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


def fetch_json(source: str | Path) -> dict[str, Any]:
    """Load and parse JSON from an HTTP/HTTPS URL or a local ``Path``.

    Args:
        source: A URL string (``http://`` or ``https://``) or a
            :class:`~pathlib.Path` to a local file.

    Returns:
        Parsed JSON as a ``dict``.

    Raises:
        ValueError: If the data cannot be fetched or is not valid JSON, or if
            the top-level value is not a JSON object.
    """
    try:
        if isinstance(source, str) and source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=30) as resp:  # nosec B310
                raw = resp.read()
        else:
            raw = Path(source).read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read source {source!r}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Source {source!r} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Source {source!r}: expected a JSON object, got {type(data).__name__}"
        )
    return data
