# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeping an SBOM file name a name, not a path: ``is_plain_file_name``
(shared by ``sbom-basename`` and the embed), ``sbom_base_name`` (drops a
stray ``.spdx3.json``) and ``escape_file_name_part`` (the default embedded
name).
"""

from __future__ import annotations

import logging
import unicodedata

from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import warn_once

log = logging.getLogger(__name__)

#: How ``sbom-basename`` is named in a message, by config and by every
#: consumer, so one value warns once.
CONFIG_BASENAME_LABEL = "[tool.pitloom] sbom-basename"

#: A path separator (either platform), a Windows drive or alternate-data-
#: stream colon, or NUL.
_NOT_IN_A_FILE_NAME = frozenset({"/", "\\", ":", "\x00"})


def is_plain_file_name(name: str) -> bool:
    """Whether *name* (surrounding whitespace ignored) is a non-empty file
    name that cannot name another directory: no separator, colon or NUL,
    and not ``.``/``..``."""
    clean = name.strip()
    return (
        bool(clean)
        and clean not in (".", "..")
        and not any(c in clean for c in _NOT_IN_A_FILE_NAME)
    )


def sbom_base_name(value: str, label: str) -> str:
    """*value*, a base name (``sbom-basename``/``--sbom-basename``), without
    one trailing ``.spdx3.json`` (any case), which every writer appends
    itself. A strip is announced with one ``WARNING:`` naming *label*, however
    often the same value is read in a run (config is parsed more than once).

    The stripped base is trimmed of whitespace; a value without the extension
    is returned as given.

    Raises:
        ValueError: what is left is not a plain file name (nothing, ``.``,
            ``..``, a path): the extension was all that named the file.
    """
    clean = value.strip()
    if not clean.lower().endswith(SPDX3_JSONLD_EXTENSION):
        return value
    base = clean[: -len(SPDX3_JSONLD_EXTENSION)].strip()
    if not is_plain_file_name(base):
        raise ValueError(
            f"{label} must be a file name without {SPDX3_JSONLD_EXTENSION}: {value!r}"
        )
    warn_once(
        log,
        f"{label} {value!r}",
        "%s %r ends in %s; using %r",
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
    ``C*``: ESC, newline, DEL, C1, format characters), whitespace, and what
    :func:`is_plain_file_name` refuses (a separator, a colon). Every other
    character stays, ``-``, ``+`` and ``.`` included, so a name that is already
    safe is unchanged."""
    return "".join(
        "_"
        if char in _NOT_IN_A_FILE_NAME
        or char.isspace()
        or unicodedata.category(char).startswith("C")
        else char
        for char in part
    )


__all__ = [
    "CONFIG_BASENAME_LABEL",
    "escape_file_name_part",
    "is_plain_file_name",
    "sbom_base_name",
    "sbom_file_name",
]
