# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``setup.cfg`` value directives: ``file:`` and ``attr:``.

See also: :mod:`pitloom.extract.project.setuptools_cfg` (the reader).
"""

from __future__ import annotations

import ast
import io
import logging
import posixpath
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from pitloom.core.path_confine import open_inside
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING, is_missing_errno
from pitloom.core.project import project_relative_or_fallback
from pitloom.extract._license_detect import decode_text
from pitloom.logging_config import Cap, loggable, warn_once, warn_over_cap

log = logging.getLogger(__name__)

# Matches "file: some/path" or "attr: module.attribute"; a "file:" list may
# be wrapped across lines, as setuptools reads it.
_DIRECTIVE_RE = re.compile(r"^(file|attr):\s*(.+)$", re.DOTALL)
#: Largest file a ``file:`` directive reads (``setup.cfg``, and the
#: ``pyproject.toml`` dynamic version); a larger one is skipped, warned.
MAX_LISTED_FILE_BYTES = 1024 * 1024
#: Longest logical line assigning an ``attr:`` directive's attribute that
#: is parsed, its physical lines joined: a version literal needs far fewer
#: characters, and a longer line could nest deep enough to exhaust the
#: parser (a C stack overflow on 3.10).
MAX_ATTR_LINE_CHARS = 256


def _read_listed_bytes(
    project_dir: Path, name: str, what: str
) -> tuple[bool, bytes | None]:
    """``(found, content)`` for the file *name* a directive lists, opened as
    written and only inside *project_dir*
    (:func:`~pitloom.core.path_confine.open_inside`). A missing one (a
    dangling symlink too) is ``(False, None)``, silently, as setuptools
    skips it; one that is not read (outside the project, not a regular
    file, no permission, over :data:`MAX_LISTED_FILE_BYTES`) is ``(True,
    None)`` with one ``WARNING:`` per file and *what* (e.g. ``"setup.cfg
    metadata.version"``) per process, since one run reads a project more
    than once, naming the file as written."""
    path = project_dir / name
    try:
        with open_inside(path, project_dir) as handle:
            raw = handle.read(MAX_LISTED_FILE_BYTES + 1)
    except OSError as exc:
        if is_missing_errno(exc):
            return False, None
        _warn_unread(path, name, what, exc)
        return True, None
    except ValueError:
        # An embedded NUL names no file; os.path.isfile is False too.
        return False, None
    if len(raw) > MAX_LISTED_FILE_BYTES:
        cap = Cap(MAX_LISTED_FILE_BYTES, "byte", "file-directive")
        once = _once_key(path, what)
        outcome = f"skipped for {what}"
        warn_over_cap(log, cap, name, outcome, once=True, key=once)
        return True, None
    return True, raw


def _once_key(path: Path, what: str) -> str:
    return f"setup-cfg-file:{path}\x00{what}"


def _warn_unread(path: Path, name: str, what: str, exc: Exception) -> None:
    """One ``WARNING:`` per *path* and *what*, per process, that the listed
    file *name* was not read for *what* (*exc*)."""
    warn_once(
        log,
        _once_key(path, what),
        UNREADABLE_FILE_WARNING,
        loggable(name),
        f"for {what}",
        loggable(str(exc)),
    )


def read_listed_file(
    project_dir: Path, name: str, what: str
) -> tuple[bool, str | None]:
    """``(found, text)`` for the file *name* a directive lists, as
    :func:`_read_listed_bytes` reads it, its newlines read as setuptools
    reads them; one that is not UTF-8 is ``(True, None)``, warned alike."""
    found, raw = _read_listed_bytes(project_dir, name, what)
    if raw is None:
        return found, None
    try:
        return True, decode_text(raw)
    except UnicodeDecodeError as exc:
        _warn_unread(project_dir / name, name, what, exc)
        return True, None


def listed_file_readable(project_dir: Path, name: str, what: str) -> bool:
    """Whether a build backend may read the file *name* (a dynamic
    version's source) for *what*: missing (the backend reports that), or
    inside *project_dir*, a regular file and within
    :data:`MAX_LISTED_FILE_BYTES` (:func:`_read_listed_bytes`, which warns
    otherwise). Its encoding is the backend's to read (PEP 263)."""
    found, raw = _read_listed_bytes(project_dir, name, what)
    return not found or raw is not None


def _resolve_cfg_version_file_directive(
    value: str, project_dir: Path, what: str
) -> tuple[str | None, str | None]:
    """Resolve a ``file:`` directive for the version, read for *what*: no
    version for a missing, unreadable (warned) or multi-line file."""
    _, text = read_listed_file(project_dir, value, what)
    content = (text or "").strip()
    if content and "\n" not in content and not content.startswith("#"):
        return content, f"Source: {source_name(value)} | Method: file_directive"
    return None, None


def _resolve_cfg_attr_directive(
    value: str, project_dir: Path, what: str
) -> tuple[str | None, str | None]:
    """Resolve an ``attr:`` directive, read for *what*: each candidate
    module file read as :func:`read_listed_file` reads one (inside
    *project_dir* only, capped, warned when present but not read)."""
    parts = value.rsplit(".", 1)
    if len(parts) != 2:
        return None, None
    module_path, attr_name = parts
    module_rel = module_path.replace(".", "/")
    for name in (
        f"{module_rel}.py",
        f"{module_rel}/__init__.py",
        f"src/{module_rel}.py",
        f"src/{module_rel}/__init__.py",
    ):
        _, text = read_listed_file(project_dir, name, what)
        version = _read_version_attr(text, attr_name, name, what) if text else None
        if version:
            return version, f"Source: {source_name(name)} | Method: attr_directive"
    return None, None


def source_name(name: str) -> str:
    """*name*, a file read inside the project, as a provenance ``Source``:
    project-relative in POSIX form, or its base name when written absolute
    (:func:`~pitloom.core.project.project_relative_or_fallback`)."""
    path = Path(name)
    return project_relative_or_fallback(posixpath.normpath(path.as_posix()), path.name)


def _resolve_cfg_version(
    raw: str,
    project_dir: Path,
) -> tuple[str | None, str | None]:
    """Resolve a version string from ``setup.cfg``, handling directives.

    Supports:
    * Literal values: ``version = 1.2.3``
    * File directive: ``version = file: VERSION``
    * Attr directive (best-effort): ``version = attr: package.__version__``
    """
    if not raw:
        return None, None

    m = _DIRECTIVE_RE.match(raw)
    if not m:
        return raw, "Source: setup.cfg | Field: metadata.version"

    directive, value = m.group(1), m.group(2).strip()
    if directive == "file":
        return _resolve_cfg_version_file_directive(
            value, project_dir, "setup.cfg metadata.version"
        )
    # _DIRECTIVE_RE only captures "file" or "attr" in this group, so
    # "attr" is the only remaining case.
    return _resolve_cfg_attr_directive(value, project_dir, "setup.cfg metadata.version")


def _resolve_cfg_file_directive(raw: str, project_dir: Path, field: str) -> str | None:
    """*raw*, or for ``file: a.txt, b.txt`` the text of each listed file,
    joined with ``\n`` (setuptools' ``read_files``); the list may be wrapped
    across lines, and a blank entry is left out. A listed file that does not
    exist is skipped, and when none exists the list itself is returned as a
    filename hint. One that exists but cannot be read is skipped with one
    ``WARNING:`` naming it and the setup.cfg *field*
    (:func:`read_listed_file`); ``None`` when nothing was read."""
    if not raw:
        return None
    m = _DIRECTIVE_RE.match(raw)
    if not (m and m.group(1) == "file"):
        return raw
    names = [n for n in (part.strip() for part in m.group(2).split(",")) if n]
    texts: list[str] = []
    found = False
    for name in names:
        exists, text = read_listed_file(project_dir, name, f"setup.cfg {field}")
        found = found or exists
        if text is not None:
            texts.append(text)
    if texts:
        return "\n".join(texts)
    return None if found or not names else ", ".join(names)


def _assignment_starts(source: str, attr_name: str) -> Iterator[int]:
    """Where each line assigning *attr_name* starts, its indentation left
    out, in order: a plain, annotated (``__version__: str = ...``) or
    chained (``version = __version__ = ...``) target, after a ``;`` too."""
    assigned = re.compile(rf"(?<![\w.]){re.escape(attr_name)}[ \t]*(?::[^=\n]*)?=(?!=)")
    last = -1  # where the last line yielded starts
    for found in assigned.finditer(source):
        line = source.rfind("\n", 0, found.start()) + 1
        if line > last:
            last = line
            before = source[line : found.start()]  # each line's once
            yield found.start() - len(before.lstrip(" \t"))


def _logical_line(source: str, start: int) -> str | None:
    """The logical line of *source* from *start*: physical lines joined
    while a bracket is open or a line ends with ``\\``, as the tokenizer
    reads them, at most :data:`MAX_ATTR_LINE_CHARS` characters of it
    looked at; ``None`` when it does not end within them (or the text there
    does not tokenize, which only the source's end can make shorter)."""
    window = source[start : start + MAX_ATTR_LINE_CHARS + 1]
    lines = io.StringIO(window).readlines()
    tokens = tokenize.generate_tokens(iter(lines).__next__)
    try:
        end = next(t for t in tokens if t.type == tokenize.NEWLINE)
    except (tokenize.TokenError, SyntaxError, StopIteration):
        return None
    row, col = end.start
    line = "".join(lines[: row - 1]) + lines[row - 1][:col]
    return line if len(line) <= MAX_ATTR_LINE_CHARS else None


def _read_version_attr(source: str, attr_name: str, name: str, what: str) -> str | None:
    """The string first assigned to *attr_name* in the Python *source* (the
    file *name*, read for *what*), never the whole file parsed: only each
    logical line assigning it (:func:`_assignment_starts`,
    :func:`_logical_line`), one at a time (:func:`_assigned_string`). One
    longer than :data:`MAX_ATTR_LINE_CHARS` is skipped with one
    ``WARNING:`` per file and *what*, per process."""
    for start in _assignment_starts(source, attr_name):
        line = _logical_line(source, start)
        if line is None:
            if len(source) - start > MAX_ATTR_LINE_CHARS:
                cap = Cap(MAX_ATTR_LINE_CHARS, "character", "attr-directive-line")
                outcome = f"{attr_name} line skipped for {what}"
                warn_over_cap(log, cap, name, outcome, once=True)
            continue
        value = _assigned_string(line, attr_name, name, what)
        if value is not None:
            return value
    return None


def _targets(node: ast.AST) -> list[ast.expr]:
    """The targets of an assignment *node* given a value: each of a chained
    ``a = b = ...``, or an annotated one's; none for any other node."""
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target]
    return []


def _assigned_string(line: str, attr_name: str, name: str, what: str) -> str | None:
    """The string *line* (from the file *name*) assigns to *attr_name*, as
    one target of an assignment or an annotated one, or ``None``; a line
    the parser cannot hold (``RecursionError``, ``MemoryError``) is skipped
    with one ``WARNING:``."""
    try:
        tree = ast.parse(line)
    except (SyntaxError, ValueError):  # ValueError: a NUL, before 3.12
        return None
    except (RecursionError, MemoryError) as exc:
        reason = f"{type(exc).__name__} parsing the {attr_name} line"
        warn_once(
            log,
            f"attr-line:{name}\x00{what}",
            UNREADABLE_FILE_WARNING,
            loggable(name),
            f"for {what}",
            reason,
        )
        return None
    for node in ast.walk(tree):
        value = getattr(node, "value", None)
        if (
            any(isinstance(t, ast.Name) and t.id == attr_name for t in _targets(node))
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            return value.value
    return None
