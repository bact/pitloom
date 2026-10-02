# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Keeping an SBOM file name a name, not a path: ``is_plain_file_name``
(shared by ``sbom-basename`` and the embed) and ``escape_file_name_part``
(the default embedded name).
"""

from __future__ import annotations

import unicodedata

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


__all__ = ["escape_file_name_part", "is_plain_file_name"]
