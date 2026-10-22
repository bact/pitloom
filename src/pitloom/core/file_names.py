# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeping an SBOM file name a name, not a path: ``is_plain_file_name``
(shared by ``sbom-basename`` and the embed), ``sbom_base_name`` (drops a
stray ``.spdx3.json``), ``escape_file_name_part`` and
``default_sbom_basename`` (the default name, for the CLI, the hook and the
embed).
"""

from __future__ import annotations

import logging
import unicodedata

from pitloom.core.untrusted_text import DISPLAY_CONTROLS
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import warn_once

log = logging.getLogger(__name__)

#: How ``sbom-basename`` is named in a message, by config and by every
#: consumer, so one value warns once.
CONFIG_BASENAME_LABEL = "[tool.pitloom] sbom-basename"

#: A path separator (either platform), a Windows drive or alternate-data-
#: stream colon, or NUL.
_NOT_IN_A_FILE_NAME = frozenset({"/", "\\", ":", "\x00"})

#: Names Windows opens as a device whatever follows the first dot
#: (``con.spdx3.json`` is the console).
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"{device}{n}" for device in ("COM", "LPT") for n in range(1, 10)}
)


def _is_unsafe_character(char: str) -> bool:
    """A character no file name may hold: a separator, colon or NUL, a
    control character (Unicode category ``C*``) or a display control."""
    return (
        char in _NOT_IN_A_FILE_NAME
        or char in DISPLAY_CONTROLS
        or unicodedata.category(char).startswith("C")
    )


def is_plain_file_name(name: str) -> bool:
    """Whether *name* (surrounding whitespace ignored) is a non-empty file
    name that cannot name another directory or a device: no separator,
    colon, NUL, control or display-control character; not ``.``/``..``; not
    ending in a dot (Windows drops it); not a Windows device name (``CON``,
    ``NUL``, ``COM1``... with or without an extension)."""
    clean = name.strip()
    return (
        bool(clean)
        and clean not in (".", "..")
        and not clean.endswith(".")
        and not any(map(_is_unsafe_character, clean))
        and clean.split(".", 1)[0].rstrip().upper() not in _WINDOWS_DEVICES
    )


def sbom_base_name(value: str, label: str) -> str:
    """*value*, a base name (``sbom-basename``/``--sbom-basename``), without
    one trailing ``.spdx3.json`` (any case), which every writer appends
    itself. A strip is announced with one ``WARNING:`` naming *label*, however
    often the same value is read in a run (config is parsed more than once).

    The result is trimmed of surrounding whitespace, which is announced the
    same way; a value that needs neither is returned as given.

    Raises:
        ValueError: what is left is not a plain file name (nothing, ``.``,
            ``..``, a path): the extension was all that named the file.
    """
    clean = value.strip()
    if clean.lower().endswith(SPDX3_JSONLD_EXTENSION):
        base = clean[: -len(SPDX3_JSONLD_EXTENSION)].strip()
    else:
        base = clean
    if base == value:
        return value
    if not is_plain_file_name(base):
        raise ValueError(
            f"{label} must be a file name without {SPDX3_JSONLD_EXTENSION}: {value!r}"
        )
    warn_once(
        log,
        f"{label} {value!r}",
        "%s %r is not a bare file name (surrounding white space or a trailing "
        "%s); using %r",
        label,
        value,
        SPDX3_JSONLD_EXTENSION,
        base,
    )
    return base


def sbom_file_name(sbom_basename: str, label: str = CONFIG_BASENAME_LABEL) -> str:
    """The SBOM file name for *sbom_basename*: :func:`sbom_base_name` plus
    ``.spdx3.json``. The one place a base name becomes a file name, so a
    config built in code (never parsed) cannot double the extension.

    Raises:
        ValueError: as :func:`sbom_base_name`.
    """
    return f"{sbom_base_name(sbom_basename, label)}{SPDX3_JSONLD_EXTENSION}"


def escape_file_name_part(part: str) -> str:
    """*part* (a project name or version) with each character that is unsafe
    in a file name replaced by ``_``: a control character (Unicode category
    ``C*``: ESC, newline, DEL, C1, format characters), a code point of
    :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS`, whitespace, and
    what :func:`is_plain_file_name` refuses (a separator, a colon). Every
    other character stays, ``-``, ``+`` and ``.`` included, so a name that is
    already safe is unchanged."""
    return "".join(
        "_" if _is_unsafe_character(char) or char.isspace() else char for char in part
    )


def default_sbom_basename(name: str | None, version: str | None) -> str:
    """The default SBOM base name of a project: ``<name>-<version>``, or
    ``<name>`` without a version, each part through
    :func:`escape_file_name_part`; ``sbom`` for a missing name, and ``sbom``
    alone when the result would not be a plain file name (``con``)."""
    parts = [escape_file_name_part(part) for part in (name or "sbom", version) if part]
    base = "-".join(parts)
    return base if is_plain_file_name(f"{base}{SPDX3_JSONLD_EXTENSION}") else "sbom"


__all__ = [
    "CONFIG_BASENAME_LABEL",
    "default_sbom_basename",
    "escape_file_name_part",
    "is_plain_file_name",
    "sbom_base_name",
    "sbom_file_name",
]
