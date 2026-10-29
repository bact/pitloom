# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Helpers of the catalogue's drift tests (tests/messages/test_drift_*.py and
the autouse record check in ``tests/conftest.py``): does a log record, a
source module or a quoted line still agree with :mod:`pitloom.messages`?

See also: tests/messages/test_drift_records.py, test_drift_sources.py and
test_drift_quotes.py.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pitloom.messages as catalogue
from pitloom.logging_config import CODE_ATTR, CODE_PATTERN, escape_controls
from pitloom.messages import MESSAGES, Message, trusted_message
from tests._docs_scan import REPO_ROOT

SRC_ROOT = REPO_ROOT / "src" / "pitloom"

#: A logger named like this belongs to a test that feeds the catalogue odd
#: text on purpose; its records are not checked.
TEST_LOGGER_PREFIX = "pitloom.test_"


def record_problem(record: logging.LogRecord) -> str | None:
    """What is wrong with *record* as a catalogued one, or ``None``: it has
    no :data:`~pitloom.logging_config.CODE_ATTR`, or its code is catalogued,
    its level is one of the entry's and its text matches a pattern."""
    code = getattr(record, CODE_ATTR, None)
    if code is None or record.name.startswith(TEST_LOGGER_PREFIX):
        return None
    if not isinstance(code, str) or code not in MESSAGES:
        return f"uncatalogued code {code!r}"
    text = escape_controls(record.getMessage())
    line = f"{record.levelname}: {text} [{code}]"
    if trusted_message(line) is not MESSAGES[code]:
        return f"{line!r} is not the text or level of {code!r}"
    return None


def family_names() -> dict[str, tuple[str, ...]]:
    """Each family to the names :mod:`pitloom.messages` exports for its
    entries (``LFS_POINTER``)."""
    found: dict[str, list[str]] = {}
    for name, value in vars(catalogue).items():
        if isinstance(value, Message):
            found.setdefault(value.family, []).append(name)
    return {family: tuple(sorted(names)) for family, names in found.items()}


def source_modules() -> Iterator[tuple[str, ast.Module]]:
    """Each module of ``src/pitloom`` but the catalogue's own, as its
    path under the package (POSIX) and its syntax tree."""
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if not rel.startswith("messages/"):
            yield rel, ast.parse(path.read_bytes())


def referenced_names(tree: ast.AST) -> set[str]:
    """Every name *tree* reads, imports or takes from a module."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found.update(a.name.rpartition(".")[2] for a in node.names)
    return found


def _docstring_ids(tree: ast.AST) -> set[int]:
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def string_constants(tree: ast.AST) -> list[str]:
    """Every string constant of *tree* but a docstring, with the literal
    parts of an f-string."""
    skip = _docstring_ids(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
    ]


_EDGE = " :;,()"


def cores(text: str) -> list[str]:
    """The literal pieces of *text* (a pattern or a template) between its
    ``%s`` values, trimmed of edge punctuation, 20 characters or more."""
    pieces = (piece.strip(_EDGE) for piece in text.split("%s"))
    return [piece for piece in pieces if len(piece) >= 20]


def family_cores() -> dict[str, set[str]]:
    """Each family to the cores of its entries' patterns."""
    found: dict[str, set[str]] = {}
    for entry in MESSAGES.values():
        for pattern in entry.patterns:
            found.setdefault(entry.family, set()).update(cores(pattern))
    return found


def families_said_by(texts: list[str]) -> set[str]:
    """The families whose pattern text any of *texts* holds, or is part of."""
    said = family_cores()
    return {
        family
        for family, family_texts in said.items()
        for text in texts
        for piece in cores(text)
        for core in family_texts
        if piece in core or core in piece
    }


#: What a quote leaves out or fills in: an ellipsis, ``<placeholder>``, a
#: ``%s`` value, ``(N files)`` or ``byte(s)``; space around it goes too.
_WILD = re.compile(r"\s*(?:\.\.\.|…|<[^<>]*>|%s|\(N [^)]*\)|byte\(s\))\s*")
_LEVEL = re.compile(r"^(ERROR|WARNING|INFO): ")
_CODE = re.compile(rf" \[({CODE_PATTERN})\]$")


def quote_matches(quote: str, family: str) -> bool:
    """Whether *quote* (a backticked line or piece of one, optionally with
    its ``LEVEL: `` and its `` [code]``) is part of a pattern of *family*,
    at that level and with that code."""
    level = _LEVEL.match(quote)
    text = quote[level.end() :] if level else quote
    coded = _CODE.search(text)
    text = text[: coded.start()] if coded else text
    regex = re.compile(".*".join(map(re.escape, _WILD.split(text))))
    return any(
        regex.search(pattern.replace("%s", "\x00"))
        for entry in MESSAGES.values()
        if entry.family == family
        and (level is None or level.group(1) in entry.levels)
        and (coded is None or coded.group(1) == entry.code)
        for pattern in entry.patterns
    )


def relative(path: Path) -> str:
    """*path* under the repository, POSIX."""
    return path.relative_to(REPO_ROOT).as_posix()
