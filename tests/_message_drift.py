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
import functools
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pitloom.messages as catalogue
from pitloom.logging_config import CODE_ATTR, CODE_PATTERN, escape_controls
from pitloom.messages import (
    FIELDS,
    FRAMES,
    MESSAGES,
    Message,
    code_of,
    trusted_message,
)
from pitloom.messages._fields import PLACEHOLDER
from tests._docs_scan import REPO_ROOT

SRC_ROOT = REPO_ROOT / "src" / "pitloom"

#: A logger named like this belongs to a test that feeds the catalogue odd
#: text on purpose; its records are not checked.
TEST_LOGGER_PREFIX = "pitloom.test_"

#: A value of each field, as a caller passes it.
SAMPLES: dict[str, object] = {
    "amount": "512 MiB",
    "command": "clone",
    "count": 2,
    "dir": "m/sub",
    "error": "Error while deserializing header: invalid header length",
    "failure": PermissionError(13, "Permission denied", "/abs/m/a.bin"),
    "field": "project.readme",
    "file": "m/a.bin",
    "format": "gguf",
    "formats": ["gguf", "onnx"],
    "key": "FIELD",
    "limit": 1024,
    "module": "h5py",
    "name": "a.txt",
    "oid": "0f" * 32,
    "outcome": "skipped",
    "path": "m.gguf",
    "purpose": "per-wheel model-scan budget",
    "reason": "GGUF header declares 1000000 tensors",
    "requirement": "pitloom[gguf]",
    "size": 3,
    "unit": "byte",
    "use": "for file scanning",
    "value": "-1",
}


def record_problem(record: logging.LogRecord) -> str | None:
    """What is wrong with *record* as a catalogued one, or ``None``: it has
    no :data:`~pitloom.logging_config.CODE_ATTR`, it is a ``DEBUG`` record
    (printed without its code: a message said once repeats at ``DEBUG``), or
    its code is catalogued and its text one of the entry's lines at its
    level."""
    code = getattr(record, CODE_ATTR, None)
    if (
        code is None
        or record.levelno <= logging.DEBUG
        or record.name.startswith(TEST_LOGGER_PREFIX)
    ):
        return None
    if not isinstance(code, str) or code not in MESSAGES:
        return f"uncatalogued code {code!r}"
    text = escape_controls(record.getMessage())
    line = f"{record.levelname}: {text} [{code}]"
    if trusted_message(line) is not MESSAGES[code]:
        return f"{line!r} is not the text or level of {code!r}"
    return None


def raised_as(exc: BaseException, message: Message) -> bool:
    """Whether *exc* says *message*: it carries the code
    (:func:`~pitloom.messages.code_of`), and its text, printed as the
    command line prints an error, is one of the entry's ``ERROR`` lines."""
    printed = f"ERROR: {escape_controls(str(exc))} [{message.code}]"
    return code_of(exc) == message.code and trusted_message(printed) is message


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


_VALUE = re.compile(r"%\([a-z_]+\)s|%s")


def cores(text: str) -> list[str]:
    """The literal pieces of *text* (a template, or a string of the source)
    between its values (``%(name)s``, ``%s``), trimmed of edge punctuation,
    20 characters or more."""
    pieces = (piece.strip(_EDGE) for piece in _VALUE.split(text))
    return [piece for piece in pieces if len(piece) >= 20]


def family_cores() -> dict[str, set[str]]:
    """Each family to the cores of its entries' lines."""
    found: dict[str, set[str]] = {}
    for entry in MESSAGES.values():
        for line in entry.lines:
            found.setdefault(entry.family, set()).update(cores(line.template))
    return found


def families_said_by(texts: list[str], *, whole: bool = False) -> set[str]:
    """The families whose line text any of *texts* holds, or is part of;
    with *whole*, only those whose text one of *texts* holds whole."""
    said = family_cores()
    return {
        family
        for family, family_texts in said.items()
        for text in texts
        for piece in cores(text)
        for core in family_texts
        if core in piece or (not whole and piece in core)
    }


#: What a quote leaves out or fills in: an ellipsis, ``<placeholder>``, a
#: ``%s`` value, ``(N files)`` or ``byte(s)``, space around it too; or a bare
#: ``N`` before a hyphen (``N-byte``).
_WILD = re.compile(
    r"\s*(?:\.\.\.|…|<[^<>]*>|%s|\(N [^)]*\)|byte\(s\))\s*|(?<![\w-])N(?=-)"
)
_LEVEL = re.compile(r"^(ERROR|WARNING|INFO): ")
_CODE = re.compile(rf" \[({CODE_PATTERN})\]$")

#: A quote's wildcard (:data:`_WILD`) as one token; a quote's other tokens
#: are its characters.
_ANY = object()


def _quote_tokens(text: str) -> tuple[object, ...]:
    """*text* as its characters, each wildcard of :data:`_WILD` one
    :data:`_ANY`."""
    tokens: list[object] = []
    end = 0
    for found in _WILD.finditer(text):
        tokens += text[end : found.start()]
        tokens.append(_ANY)
        end = found.end()
    return (*tokens, *text[end:])


def _line_tokens(template: str) -> tuple[str, ...]:
    """*template* as its characters, each ``%(name)s`` the field's name (a
    token longer than one character)."""
    tokens: list[str] = []
    end = 0
    for found in PLACEHOLDER.finditer(template):
        tokens += template[end : found.start()]
        tokens.append(found.group(1))
        end = found.end()
    return (*tokens, *template[end:])


def _takes(name: str, run: tuple[object, ...], marker: str) -> bool:
    """Whether field *name* can print as the quote's *run*, which starts
    with text (:func:`_piece_of` reads a wildcard standing for the field):
    the value as the reference shows it (``'<path>'``); for a free field,
    any text without the family's *marker*; for any other, text of its own
    shape."""
    field = FIELDS[name]
    if run == _quote_tokens(field.shown):
        return True
    text = "".join(t for t in run if isinstance(t, str))
    if field.free:
        return marker not in text
    return _ANY not in run and re.fullmatch(field.pattern, text) is not None


def _piece_of(quote: tuple[object, ...], line: tuple[str, ...], marker: str) -> bool:
    """Whether some printing of the template *line* holds *quote*, a
    wildcard of it standing for any text."""
    size, width = len(quote), len(line)

    @functools.cache
    def placed(i: int, j: int) -> bool:
        """Whether ``quote[i:]`` is printed from ``line[j:]`` on."""
        if i == size:
            return True
        if j == width:
            return all(t is _ANY for t in quote[i:])
        here, there = quote[i], line[j]
        if here is _ANY:
            return placed(i + 1, j) or placed(i, j + 1)
        if len(there) > 1:  # a field
            if re.fullmatch(FIELDS[there].pattern, "") and placed(i, j + 1):
                return True
            return any(
                _takes(there, quote[i:k], marker) and placed(k, j + 1)
                for k in range(i + 1, size + 1)
            )
        return here == there and placed(i + 1, j + 1)

    return any(placed(0, j) for j in range(width))


def quote_matches(quote: str, family: str, marker: str) -> bool:
    """Whether *quote* (a backticked line or piece of one, optionally with
    its ``LEVEL: `` and its `` [code]``) is part of a line of *family*, at
    that line's level and with its entry's code, a frame of that level
    before it or not. A value stands in the quote as a wildcard, as the
    reference shows it, or as itself (``10000`` for ``<limit>``); a free
    value never holds the family's *marker*, so a quote cannot be all
    value."""
    level = _LEVEL.match(quote)
    text = quote[level.end() :] if level else quote
    coded = _CODE.search(text)
    tokens = _quote_tokens(text[: coded.start()] if coded else text)
    return any(
        _piece_of(tokens, _line_tokens(head + line.template), marker)
        for entry in MESSAGES.values()
        if entry.family == family and (coded is None or coded.group(1) == entry.code)
        for line in entry.lines
        if level is None or level.group(1) == line.level
        for head in ["", *(f.template for f in FRAMES if line.level in f.levels)]
    )


def relative(path: Path) -> str:
    """*path* under the repository, POSIX."""
    return path.relative_to(REPO_ROOT).as_posix()
