# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every PEP 508 requirement and marker Pitloom parses goes through here.

``packaging`` parses a marker's parentheses recursively: about 900 nested
levels raise ``RecursionError``, not its invalid-input error, and where
that happens depends on the Python version and the stack. Text nesting
deeper than :data:`MAX_MARKER_NESTING` is refused before parsing, with one
``WARNING:``, and a ``RecursionError`` still raised is turned into the
invalid-input error: each caller's handling of text that is not PEP 508
covers both, the same on every Python version.

No Pitloom imports but :mod:`pitloom.logging_config`.

See also: :mod:`pitloom.core.requirements`, :mod:`pitloom.core.extra_gate`.
"""

from __future__ import annotations

import logging
import re

from packaging.markers import InvalidMarker, Marker
from packaging.requirements import InvalidRequirement, Requirement

from pitloom.logging_config import Cap, warn_over_cap

log = logging.getLogger(__name__)

__all__ = [
    "MAX_MARKER_NESTING",
    "is_over_nesting_cap",
    "marker_nesting",
    "parse_marker",
    "parse_requirement",
]

#: Most parentheses a requirement's or marker's text may nest. Real
#: markers nest a few; ``packaging`` parses 64 on every supported Python.
MAX_MARKER_NESTING = 64

#: Characters of the refused text a ``WARNING:`` shows.
_SHOWN_CHARS = 60

# A direct reference's ``name [extras] @ URL``: its URL is any run of
# characters but space and tab (``packaging``'s own rule), quotes and
# parentheses too, so the marker starts after it.
_URL_PREFIX = re.compile(r"\s*[^\s\[@;(]+\s*(?:\[[^\]]*\]\s*)?@[ \t]*[^ \t]*")


def marker_nesting(text: str, *, marker: bool = False) -> int:
    """How deep *text*, a requirement (a marker when *marker*), nests
    parentheses outside quoted strings: never less than ``packaging``
    nests parsing it. A direct reference's URL is skipped.

    Raises:
        TypeError: *text* is not a string.
    """
    url = None if marker else _URL_PREFIX.match(text)
    quote = None
    depth = deepest = 0
    for char in text[url.end() if url else 0 :]:
        if quote is not None:
            quote = None if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
            deepest = max(deepest, depth)
        elif char == ")":
            depth = max(depth - 1, 0)
    return deepest


def is_over_nesting_cap(
    text: str, *, marker: bool = False, quiet: bool = False
) -> bool:
    """Whether *text* nests deeper than :data:`MAX_MARKER_NESTING`
    (:func:`marker_nesting`); one ``WARNING:`` per text and process when it
    does, unless *quiet*.

    Raises:
        TypeError: *text* is not a string.
    """
    if marker_nesting(text, marker=marker) <= MAX_MARKER_NESTING:
        return False
    if not quiet:
        shown = text[:_SHOWN_CHARS] + ("..." if len(text) > _SHOWN_CHARS else "")
        warn_over_cap(log, _cap(marker), shown, "not parsed", once=True, key=text)
    return True


def parse_requirement(text: str, *, quiet: bool = False) -> Requirement:
    """*text* parsed as a PEP 508 requirement.

    Raises:
        packaging.requirements.InvalidRequirement: *text* is not one, or
            nests too deep (:func:`is_over_nesting_cap`, its ``WARNING:``
            silent when *quiet*).
        TypeError: *text* is not a string.
    """
    if is_over_nesting_cap(text, quiet=quiet):
        raise InvalidRequirement(_cap(False).reason)
    try:
        return Requirement(text)
    except RecursionError as exc:
        raise InvalidRequirement(_TOO_DEEP) from exc


def parse_marker(text: str, *, quiet: bool = False) -> Marker:
    """*text* parsed as a PEP 508 marker.

    Raises:
        packaging.markers.InvalidMarker: *text* is not one, or nests too
            deep (:func:`is_over_nesting_cap`, its ``WARNING:`` silent when
            *quiet*).
        TypeError: *text* is not a string.
    """
    if is_over_nesting_cap(text, marker=True, quiet=quiet):
        raise InvalidMarker(_cap(True).reason)
    try:
        return Marker(text)
    except RecursionError as exc:
        raise InvalidMarker(_TOO_DEEP) from exc


_TOO_DEEP = "nested too deep to parse"


def _cap(marker: bool) -> Cap:
    """The nesting cap, the input named a marker or a requirement."""
    subject = "MARKER" if marker else "REQUIREMENT"
    return Cap(MAX_MARKER_NESTING, "level", "marker-nesting", subject)
