# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Copyright notices found in a package's own licence files.

SPDX 3 ``copyrightText`` is the text of the copyright notices *found* for
a package: never generated. One rule decides what a notice line is
(:func:`find_copyright_notices`), for the main package on every route and
for a dependency's installed ``License-File``; the licence-text matcher
strips the same lines (:data:`COPYRIGHT_NOTICE_LINE_RE`).

See also: :mod:`pitloom.extract._license_detect` (which licence files are
read, and their size cap) and :mod:`pitloom.extract._license` (the
project readers' one call, ``apply_in_package_license_files``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from pitloom.core.project import ProjectMetadata
from pitloom.extract._license_detect import (
    decode_text,
    pick_license_names,
    read_license_file,
)

__all__ = [
    "COPYRIGHT_NOASSERTION",
    "COPYRIGHT_NOTICE_LINE_RE",
    "COPYRIGHT_NOTICE_METHOD",
    "apply_in_package_copyright",
    "copyright_from_members",
    "find_copyright_notices",
    "join_copyright_notices",
    "read_license_text",
]

#: ``copyrightText`` when no notice was found: no determination, never
#: ``NONE`` (the package may carry a notice in a file not read).
COPYRIGHT_NOASSERTION = "NOASSERTION"

#: Provenance method: notice lines of the named licence files, verbatim.
COPYRIGHT_NOTICE_METHOD = "copyright_notice_lines"

#: A line shaped as a copyright notice: ``Copyright`` with ``(c)``, a
#: copyright sign or a year, or ``(c)``/the sign with a year. Prose
#: (``the copyright holder``, ``COPYRIGHT HOLDERS AND CONTRIBUTORS``) is
#: not. The SPDX License List Matching Guidelines leave such a line out of
#: a licence match, templates included.
COPYRIGHT_NOTICE_LINE_RE = re.compile(
    r"^[ \t\ufeff]*(?:copyright[ \t:]*(?:\(c\)|\u00a9|\d)"
    r"|(?:\(c\)|\u00a9)[ \t]*\d).*$",
    re.IGNORECASE | re.MULTILINE,
)

#: A bracketed span with no bracket or ``@`` inside: where a licence
#: template's placeholder sits (``<year>``, ``[name of copyright owner]``,
#: ``{{ author }}``; an address in angle brackets is no placeholder). A run
#: ends at the first bracket, so every character is scanned once: linear.
_BRACKETED_RE = re.compile(r"[<\[{]([^<>\[\]{}@]*)[>\]}]")
#: A placeholder word inside a bracketed span.
_PLACEHOLDER_WORD_RE = re.compile(
    r"\b(?:yyyy|year|name|owner|author|holder)s?\b", re.IGNORECASE
)
#: A bare ``year`` after the marker (GPL-2.0's ``Copyright (C) year name
#: of author``).
_BARE_YEAR_RE = re.compile(r"(?:\(c\)|\u00a9)[ \t]*(?:yyyy|year)\b", re.IGNORECASE)

#: The title line of a GNU licence document (GPL, LGPL, LGPL-2.0's Library
#: GPL, AGPL, GFDL), any case, alone on its line but for white space, a
#: Markdown heading's ``#``s or emphasis; then its ``Version N, <date>``
#: line (after an RST title underline), then the FSF's own notice, before
#: the line ending the preamble notice block.
_GNU_LICENCE_TITLE_RE = re.compile(
    r"#{0,6}[ \t*_]*GNU (?:(?:(?:LESSER|LIBRARY|AFFERO) )?GENERAL PUBLIC"
    r"|FREE DOCUMENTATION) LICENSE[ \t*_#]*",
    re.IGNORECASE,
)
_GNU_LICENCE_VERSION_RE = re.compile(r"[*_]*Version \d+(?:\.\d+)?, ")
#: An RST title underline (or overline).
_UNDERLINE_RE = re.compile(r"([=\-~^*#])\1{2,}")
_GNU_LICENCE_NOTICE_END = "Everyone is permitted to copy and distribute verbatim"
_FSF = "Free Software Foundation"
#: Lines after a GNU licence title searched for the FSF notice block.
_GNU_LICENCE_HEAD_LINES = 8


def _is_placeholder(line: str) -> bool:
    """Whether the notice-shaped *line* is a licence template's."""
    return bool(_BARE_YEAR_RE.search(line)) or any(
        _PLACEHOLDER_WORD_RE.search(found.group(1))
        for found in _BRACKETED_RE.finditer(line)
    )


def _licence_document_notices(lines: list[str]) -> set[int]:
    """The indexes of *lines* holding the FSF's own notice of a GNU licence
    document: a notice naming the Free Software Foundation between the
    document's title line (:data:`_GNU_LICENCE_TITLE_RE`) and ``Version N,
    <date>`` lines and its ``Everyone is permitted to copy and distribute
    verbatim copies`` line. A project's own notice, before or after the
    licence text, or under a title written inside prose, is not one."""
    found: set[int] = set()
    for index, line in enumerate(lines):
        if not _GNU_LICENCE_TITLE_RE.fullmatch(line.strip()):
            continue
        head = lines[index + 1 : index + 1 + _GNU_LICENCE_HEAD_LINES]
        version = next(
            (
                text.strip()
                for text in head
                if text.strip() and not _UNDERLINE_RE.fullmatch(text.strip())
            ),
            "",
        )
        if not _GNU_LICENCE_VERSION_RE.match(version):
            continue
        ends = [n for n, text in enumerate(head) if _GNU_LICENCE_NOTICE_END in text]
        if ends:
            found.update(
                index + 1 + n for n, text in enumerate(head[: ends[0]]) if _FSF in text
            )
    return found


def find_copyright_notices(text: str) -> list[str]:
    """The copyright notice lines of *text*, in order, each stripped of
    surrounding white space and a byte order mark, exact repeats left out.

    A line is a notice when it is shaped as one
    (:data:`COPYRIGHT_NOTICE_LINE_RE`), is not a licence template's
    placeholder and is not the FSF's own notice heading a GNU licence
    document (:func:`_licence_document_notices`); the rest of the line
    (``All rights reserved.``) is kept as written. A notice continued on
    the next line keeps only the lines that are notices themselves. Linear
    in the length of *text*.
    """
    lines = text.splitlines()
    document = _licence_document_notices(lines)
    notices = (
        line.strip().lstrip("\ufeff").strip()
        for index, line in enumerate(lines)
        if COPYRIGHT_NOTICE_LINE_RE.match(line)
        and not _is_placeholder(line)
        and index not in document
    )
    return list(dict.fromkeys(notices))


def read_license_text(path: Path) -> str | None:
    """The text of the licence file *path*, read as a project's own
    (:func:`~pitloom.extract._license_detect.read_license_file`: capped, a
    present file that cannot be read warned about); ``None`` when not read."""
    raw = read_license_file(path)
    return None if raw is None else decode_text(raw, errors="replace")


def join_copyright_notices(
    named_texts: Iterable[tuple[str, str]],
) -> tuple[str, list[str]] | None:
    """``(copyrightText, names)`` from *named_texts*, ``(name, text)`` in
    order: every notice (:func:`find_copyright_notices`) joined by
    ``"\\n"`` in that order, a repeat across texts left out, and the names
    of the texts a kept notice came from. ``None`` when there is none."""
    notices: dict[str, None] = {}
    names: list[str] = []
    for name, text in named_texts:
        new = [n for n in find_copyright_notices(text) if n not in notices]
        if new:
            notices.update(dict.fromkeys(new))
            names.append(name)
    if not notices:
        return None
    return "\n".join(notices), names


def copyright_from_members(
    members: Mapping[str, bytes], archive: str | None = None
) -> tuple[str, str] | None:
    """``(copyrightText, provenance)`` from the licence files among
    *members* (basename to bytes, as
    :func:`~pitloom.extract._license_detect.license_candidates_from_members`
    takes them), read in the order
    :func:`~pitloom.extract._license_detect.pick_license_names` gives;
    *archive* names the archive they come from. ``None`` when no file
    holds a notice."""
    found = join_copyright_notices(
        (name, decode_text(members[name], errors="replace"))
        for name in pick_license_names(members)
    )
    if found is None:
        return None
    text, names = found
    within = "" if archive is None else f" | File: {archive}"
    source = f"Source: {', '.join(names)}{within}"
    return text, f"{source} | Method: {COPYRIGHT_NOTICE_METHOD}"


def apply_in_package_copyright(
    metadata: ProjectMetadata,
    members: Mapping[str, bytes],
    archive: str | None = None,
) -> None:
    """Set *metadata*'s ``copyright_text`` and its provenance from the
    notices in its own licence files (:func:`copyright_from_members`);
    unchanged when they hold none."""
    found = copyright_from_members(members, archive)
    if found is not None:
        text, provenance = found
        metadata.copyright_text = text
        metadata.provenance["copyright_text"] = provenance
