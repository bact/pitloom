# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for a fully pinned ``requirements.txt``.

See also: :mod:`pitloom.extract._pipfile_lock` (the sibling extractor
this module mirrors its PEP 440 exact-pin validation from --
:func:`pitloom.extract._lock_common.single_exact_pin`) and
:mod:`pitloom.extract._locked_dependencies` (the cascade module that
calls this extractor and overlays its output onto
``ProjectMetadata.locked_dependencies``, ranked lowest of every source
there -- see the module-level docstring below for why).

``requirements.txt`` is source-stage-only, the same class as every
sibling lock format: appropriate for ``loom project``/``loom generate``,
never for ``loom wheel``/``embed-wheel`` (the real wheel's own metadata
is ground truth) or ``loom env`` (live introspection is strictly more
authoritative).

**Not a real lock file, and ranked accordingly.** Every other source in
the cascade is a resolver-generated artifact carrying real resolution
metadata (often hashes); a plain ``requirements.txt`` is just a list of
lines a human or ``pip freeze`` wrote, with no such guarantee. Pitloom
only trusts it as a resolved-dependency source when it can prove, line
by line, that *every* real dependency line is already an exact ``==``
pin -- if even one line isn't, the **entire file** is ignored with one
``WARNING:`` naming the first disqualifying line, never partially
included. The same whole-file rejection applies if one name (compared
PEP 503-canonicalized, so ``Flask`` and ``flask`` count as the same
name) repeats with two different pinned versions; a repeat with the
same version is silently collapsed to one entry. Its provenance
``Method`` tag is ``"pinned_requirements"``, distinct from
every other source's ``"resolved_lockfile"``, so a reader of the
generated SBOM can tell the two kinds of evidence apart.

**A URL-based line (``name @ https://...`` or ``git+https://...``) is a
PEP 508 direct reference, not a PEP 440 version specifier, and always
disqualifies the whole file -- even one that looks like a tagged
release.** Neither spec defines deriving a normalized version from a
URL, and a git tag/filename is an arbitrary string with no guaranteed
relationship to the package's real version. Confirming it would mean
fetching the URL, which conflicts with this repo's "prevent excessive
network access" principle -- every sibling lock format skips its own
VCS/path/URL-sourced entries the same way.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from pitloom.extract._lock_common import (
    group_versions_by_canonical_name,
    single_exact_pin,
)

log = logging.getLogger(__name__)

__all__ = ["extract_pinned_requirements_dependencies"]

#: A comment starts at a ``#`` preceded by start-of-line or whitespace --
#: matches ``pip``'s own ``requirements.txt`` comment convention (a
#: literal ``#`` inside a URL's query string is rare, and a line where
#: one occurs is highly likely to be URL-sourced anyway, so still
#: disqualifying downstream regardless of how the comment strip lands).
_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")

#: A line beginning with any of these is a pip option (``-r``/``-e``/
#: ``--hash``/``--index-url``/etc.), not a plain dependency line -- an
#: option like ``-e``/``-r`` means this file isn't a simple, fully
#: pinned list, so its presence disqualifies the whole file rather than
#: being silently skipped.
_OPTION_LINE_PREFIX = "-"


def extract_pinned_requirements_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``requirements.txt`` next to ``pyproject.toml``/``setup.py``
    and return every dependency as an exact-pin PEP 508 string, but only
    when *every* real line in the file is already an exact ``==`` pin.

    Returns ``None`` when no ``requirements.txt`` is present, it can't be
    read/decoded, or any line disqualifies the whole file (an option
    line, a URL-based requirement, an unpinned/ranged specifier, a
    malformed line, or one name pinned to two conflicting versions) --
    see the module docstring for why this is all-or-nothing rather than
    including only the pinned lines. ``None`` (as opposed to a
    valid-but-empty ``[]``) distinguishes an absent/unusable file from a
    real, fully-pinned one that simply lists zero dependencies (e.g. all
    comments/blank lines). A leading UTF-8 BOM (common from Windows
    editors) and pip's backslash line-continuation syntax are both
    handled the same as pip itself handles them, not treated as
    malformed.
    """
    lock_path = project_dir / "requirements.txt"
    if not lock_path.exists():
        return None
    try:
        raw_text = lock_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("Failed to parse %s: %s", lock_path, exc)
        return None

    pins: list[tuple[str, str]] = []
    for lineno, joined_line in _join_continuation_lines(raw_text):
        line = _COMMENT_RE.sub("", joined_line).strip()
        if not line:
            continue
        pin = _pinned_name_version_for_line(lock_path, lineno, line)
        if pin is None:
            return None
        pins.append(pin)
    return _collapse_or_none(lock_path, pins)


def _join_continuation_lines(raw_text: str) -> list[tuple[int, str]]:
    """Join pip's backslash line-continuation syntax (a trailing ``\\``
    at end of physical line) into logical lines, each paired with the
    1-based line number of its *first* physical line -- so a long
    requirement or marker expression split across lines parses the same
    as if it were written on one line, instead of the trailing ``\\``
    disqualifying the whole file as a malformed line.

    Doesn't make a ``pip-compile --generate-hashes``-style file usable:
    joining a continuation still leaves any ``--hash=...`` token on it,
    which isn't part of PEP 508 grammar and correctly disqualifies the
    whole file the same as any other malformed line -- hash-annotated
    files stay unsupported, just for the right documented reason
    instead of failing on the raw backslash first.
    """
    logical_lines: list[tuple[int, str]] = []
    buffer: list[str] = []
    first_lineno = 1
    for lineno, raw_line in enumerate(raw_text.splitlines(), start=1):
        if not buffer:
            first_lineno = lineno
        trimmed = raw_line.rstrip()
        if trimmed.endswith("\\"):
            buffer.append(trimmed[:-1])
            continue
        buffer.append(raw_line)
        logical_lines.append((first_lineno, " ".join(buffer)))
        buffer = []
    if buffer:
        logical_lines.append((first_lineno, " ".join(buffer)))
    return logical_lines


def _collapse_or_none(lock_path: Path, pins: list[tuple[str, str]]) -> list[str] | None:
    """Collapse *pins* to one ``name==version`` entry per PEP
    503-canonicalized name, preserving first-seen literal name and file
    order -- or ``None`` (with a ``WARNING:`` naming the name and both
    versions) the moment one canonicalized name repeats with two
    *different* versions. A plain repeated line (same name, same
    version) is silently collapsed to one entry.
    """
    result: list[str] = []
    for group in group_versions_by_canonical_name(pins).values():
        name, version = group[0]
        conflicting = next((v for _, v in group if v != version), None)
        if conflicting is not None:
            log.warning(
                "%s: %r pinned to conflicting versions (%s, %s) -- "
                "ignoring requirements.txt",
                lock_path,
                name,
                version,
                conflicting,
            )
            return None
        result.append(f"{name}=={version}")
    return result


def _pinned_name_version_for_line(
    lock_path: Path, lineno: int, line: str
) -> tuple[str, str] | None:
    """Return ``(name, version)`` for a well-formed, exactly-pinned,
    non-URL requirement *line*, or ``None`` (having already logged the
    single ``WARNING:`` naming why) when it disqualifies the whole file."""
    if line.startswith(_OPTION_LINE_PREFIX):
        option = line.split()[0]
        log.warning(
            "%s:%d: option %r means this file isn't fully pinned -- "
            "ignoring requirements.txt",
            lock_path,
            lineno,
            option,
        )
        return None
    try:
        requirement = Requirement(line)
    except InvalidRequirement as exc:
        log.warning(
            "%s:%d: malformed requirement line: %s -- ignoring requirements.txt",
            lock_path,
            lineno,
            exc,
        )
        return None
    if requirement.url is not None:
        log.warning(
            "%s:%d: %r is a direct URL reference, not a version pin -- "
            "ignoring requirements.txt",
            lock_path,
            lineno,
            requirement.name,
        )
        return None
    pinned_version = single_exact_pin(requirement.specifier)
    if pinned_version is None:
        log.warning(
            "%s:%d: %r isn't pinned to a single exact version -- "
            "ignoring requirements.txt",
            lock_path,
            lineno,
            requirement.name,
        )
        return None
    return requirement.name, pinned_version
