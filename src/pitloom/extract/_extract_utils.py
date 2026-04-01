# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic utility functions for metadata extractors."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any


def get_first(d: dict[str, Any], *keys: str) -> Any:
    """Return the value for the first matching key in *d*, or ``None``."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def to_str_list(value: Any) -> list[str]:
    """Normalise *value* to a non-empty list of strings.

    Handles:

    - ``None`` → ``[]``
    - a single string → ``[value]`` (splits on commas when the string looks
      like a CSV: contains a comma, no semicolons, and is short enough to be
      a keyword list rather than a sentence)
    - a list → each element converted to ``str``, ``None`` elements dropped
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
