# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for a fully pinned ``requirements.txt``.

See also: :mod:`pitloom.extract.lock.pipfile` (the sibling extractor
this module mirrors its PEP 440 exact-pin validation from --
:func:`pitloom.extract.lock.common.single_exact_pin`) and
:mod:`pitloom.extract.lock.cascade` (the cascade module that
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
by line, that *every* real dependency line is already a single exact
``==``/``===`` pin (see :func:`pitloom.extract.lock.common.single_exact_pin`)
-- if even one line isn't, the **entire file** is ignored with one
``WARNING:`` naming the first disqualifying line, never partially
included. The same whole-file rejection applies if one name (compared
PEP 503-canonicalized, so ``Flask`` and ``flask`` count as the same
name) repeats with two versions that don't compare equal under PEP 440
(see :func:`pitloom.extract.lock.common.is_same_version`, e.g.
``"1.0"``/``"1.0.0"`` don't conflict but ``"1.0"``/``"1.0.1"`` do); a
repeat with the same PEP 440 version is silently collapsed to one
entry. Its provenance ``Method`` tag is ``"pinned_requirements"``,
distinct from every other source's ``"resolved_lockfile"``, so a
reader of the generated SBOM can tell the two kinds of evidence apart.

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

from packaging.requirements import InvalidRequirement

from pitloom.core.pep508 import parse_requirement
from pitloom.core.quote_source import quote_source
from pitloom.extract.lock.common import (
    read_lock_bytes,
    resolve_pinned_dependencies,
    single_exact_pin,
    warn_unreadable_lock_file,
)
from pitloom.logging_config import loggable, sanitize_url_credentials

log = logging.getLogger(__name__)

__all__ = ["extract_pinned_requirements_dependencies"]

#: A comment starts at a ``#`` preceded by start-of-line or whitespace --
#: matches ``pip``'s own ``requirements.txt`` comment convention (a
#: literal ``#`` inside a URL's query string is rare, and a line where
#: one occurs is highly likely to be URL-sourced anyway, so still
#: disqualifying downstream regardless of how the comment strip lands).
_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")

#: A line that is only a comment: pip never continues it with the next line.
_COMMENT_LINE_RE = re.compile(r"\s*#")

#: A line beginning with any of these is a pip option (``-r``/``-e``/
#: ``--hash``/``--index-url``/etc.), not a plain dependency line -- an
#: option like ``-e``/``-r`` means this file isn't a simple, fully
#: pinned list, so its presence disqualifies the whole file rather than
#: being silently skipped.
_OPTION_LINE_PREFIX = "-"


def extract_pinned_requirements_dependencies(project_dir: Path) -> list[str] | None:
    """Read ``requirements.txt`` next to ``pyproject.toml``/``setup.py``
    and return every dependency as an exact-pin PEP 508 string, but only
    when *every* real line in the file is already a single exact
    ``==``/``===`` pin.

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
    handled as pip handles them (see :func:`_join_continuation_lines` for the
    one difference), not treated as
    malformed.
    """
    lock_path = project_dir / "requirements.txt"
    try:
        raw_text = read_lock_bytes(lock_path).decode("utf-8-sig")
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warn_unreadable_lock_file(lock_path, exc)
        return None

    pins: list[tuple[str, str, str]] = []
    for lineno, joined_line in _join_continuation_lines(raw_text):
        line = _COMMENT_RE.sub("", joined_line).strip()
        if not line:
            continue
        pin = _pinned_name_version_for_line(lock_path, lineno, line)
        if pin is None:
            return None
        pins.append(pin)
    return resolve_pinned_dependencies(pins, lock_path, on_conflict="abort")


def _join_continuation_lines(raw_text: str) -> list[tuple[int, str]]:
    """Join pip's backslash line-continuation syntax (a trailing ``\\``
    at end of physical line) into logical lines, each paired with the
    1-based line number of its *first* physical line, as pip's own
    ``join_lines`` does: pieces join with nothing between them, and a
    comment line (``#`` first on the line) never continues, but ends an
    open continuation. Unlike pip, trailing white space after the ``\\``
    is ignored (pip does not continue such a line).

    Doesn't make a ``pip-compile --generate-hashes``-style file usable:
    a ``--hash=...`` token on a joined line is not PEP 508 and disqualifies
    the whole file like any other malformed line.
    """
    logical_lines: list[tuple[int, str]] = []
    buffer: list[str] = []
    first_lineno = 1
    for lineno, raw_line in enumerate(raw_text.splitlines(), start=1):
        trimmed = raw_line.rstrip()
        is_comment = _COMMENT_LINE_RE.match(trimmed) is not None
        if trimmed.endswith("\\") and not is_comment:
            if not buffer:
                first_lineno = lineno
            buffer.append(trimmed[:-1])
            continue
        if buffer:
            # pip keeps a comment apart from the text before it.
            buffer.append(f" {raw_line}" if is_comment else raw_line)
            logical_lines.append((first_lineno, "".join(buffer)))
            buffer = []
        else:
            logical_lines.append((lineno, raw_line))
    if buffer:
        logical_lines.append((first_lineno, "".join(buffer)))
    return logical_lines


def _pinned_name_version_for_line(
    lock_path: Path, lineno: int, line: str
) -> tuple[str, str, str] | None:
    """Return ``(name, op, version)`` for a well-formed, exactly-pinned,
    non-URL requirement *line*, or ``None`` (having already logged the
    single ``WARNING:`` naming why) when it disqualifies the whole file."""
    if line.startswith(_OPTION_LINE_PREFIX):
        option = line.split()[0].split("=")[0]
        log.warning(
            "%s:%d: option %r means this file isn't fully pinned -- "
            "ignoring requirements.txt",
            quote_source(lock_path),
            lineno,
            option,
        )
        return None
    try:
        requirement = parse_requirement(line)
    except InvalidRequirement as exc:
        # The message quotes the source line and a caret line: its first
        # line says what is wrong.
        exc_msg = loggable(sanitize_url_credentials(str(exc).split("\n", 1)[0]))
        log.warning(
            "%s:%d: malformed requirement line: %s -- ignoring requirements.txt",
            quote_source(lock_path),
            lineno,
            exc_msg,
        )
        return None
    if requirement.url is not None:
        log.warning(
            "%s:%d: %r is a direct URL reference, not a version pin -- "
            "ignoring requirements.txt",
            quote_source(lock_path),
            lineno,
            requirement.name,
        )
        return None
    pinned = single_exact_pin(requirement.specifier)
    if pinned is None:
        log.warning(
            "%s:%d: %r isn't pinned to a single exact version -- "
            "ignoring requirements.txt",
            quote_source(lock_path),
            lineno,
            requirement.name,
        )
        return None
    op, version = pinned
    return requirement.name, op, version
