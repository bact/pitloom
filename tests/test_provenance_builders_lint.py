# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: a provenance string is built through
:func:`~pitloom.core.provenance.provenance_source` and
:func:`~pitloom.core.provenance.provenance_segment`, which sanitise what they
are given, so a ``|`` in a file, label or archive name cannot add a segment.

It reads the source of ``src/pitloom`` (not ``core/provenance.py``, where the
helpers live) for f-strings and ``+`` concatenations:

- R1 (strict): a string whose literal text holds a segment key other than
  ``Field:`` and ``Method:`` (``Source:``, ``File:``, ``Package:``,
  ``Normalized-From:``, ``Resolution-``, every other key of
  :data:`~pitloom.core.provenance.PROVENANCE_SEGMENT_KEYS`, ``Evidence:``,
  ``Reason:``) or ``Fetched from`` interpolates only a literal, an
  ``UPPER_CASE`` constant or a call of an approved builder.
- R2 (heuristic): a string holding ``Field:`` or ``Method:`` interpolates no
  name that looks like external text (``entry``, ``prefix``, ``member``,
  ``label``, ``path``, ``raw``, ``url``, ``archive``, ``name``) outside an
  approved call.
- R3: a ``" | ".join(...)`` (a separator holding `` | ``, not a regex
  alternation's ``"|"``) joins only what a comprehension passes through
  the sanitiser or an approved builder.

See also: tests/test_messages_quote_paths.py (the same kind of scan for
paths in messages), tests/test_provenance_key_sets.py (the runtime net).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from pitloom.core.provenance import PROVENANCE_SEGMENT_KEYS

_SRC = Path(__file__).parent.parent / "src" / "pitloom"
_HELPERS = "core/provenance.py"

#: Literal text that makes a string a provenance segment (R2).
_SEGMENT_MARKERS = ("Field:", "Method:")
#: Literal text that makes a string a provenance source or a segment whose
#: value names one (R1).
_SOURCE_MARKERS = (
    "Source:",
    "Resolution-",
    "Expansion-",
    "Evidence:",
    "Reason:",
    "Fetched from",
    *(
        f"{key}:"
        for key in sorted(PROVENANCE_SEGMENT_KEYS)
        if key not in ("Field", "Method")
    ),
)
#: Names that look like text read from outside (R2).
_EXTERNAL = re.compile(r"entry|prefix|member|label|path|raw|url|archive|name")
_CONSTANT = re.compile(r"^_*[A-Z][A-Z0-9_]*$")

#: Calls whose result is a provenance string built from sanitised parts:
#: the two builders and the module wrappers around them.
_APPROVED = frozenset(
    {
        "provenance_source",
        "provenance_segment",
        "provenance_note",
        "evidence_segment",
        "field_provenance",
        "member_source",
        "directive_source",
        "package_provenance_source",
    }
)

#: Calls that sanitise what a ``" | ".join(...)`` joins (R3).
_SANITISING = _APPROVED | {"sanitize_provenance_text"}

#: (file relative to src/pitloom, interpolated expression) -> why it is safe.
_ALLOWED: dict[tuple[str, str], str] = {
    ("assemble/spdx3/deps_originator.py", "repo_url"): (
        "the text of a note: provenance_note() sanitises it and writes it "
        "after 'Note: ', so the URL's ':' is no key"
    ),
    # The writer of the Evidence segment: both values are checked against
    # its closed vocabulary before they are written.
    ("core/evidence.py", "level"): "a level of the closed vocabulary",
    ("core/evidence.py", "reason"): "a reason code of the closed vocabulary",
}


def _called_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def _is_safe(node: ast.expr) -> bool:
    """R1: a literal, an ``UPPER_CASE`` constant or an approved call."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return _CONSTANT.match(node.id) is not None
    if isinstance(node, ast.Attribute):
        return _CONSTANT.match(node.attr) is not None
    return _called_name(node) in _APPROVED


def _external_names(node: ast.AST) -> list[str]:
    """R2: the names and attributes in *node* that look like external text,
    not counting what an approved call takes."""
    if _called_name(node) in _APPROVED:
        return []
    found: list[str] = []
    if isinstance(node, ast.Name) and _EXTERNAL.search(node.id):
        found.append(node.id)
    elif isinstance(node, ast.Attribute) and _EXTERNAL.search(node.attr):
        found.append(node.attr)
    for child in ast.iter_child_nodes(node):
        found += _external_names(child)
    return found


def _operands(node: ast.expr) -> list[ast.expr]:
    """The operands of a ``+`` chain, left to right."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _operands(node.left) + _operands(node.right)
    return [node]


def _parts(node: ast.expr) -> tuple[str, list[ast.expr]] | None:
    """The literal text and the interpolated expressions of a string
    expression (an f-string or a ``+`` chain with a string in it), else
    ``None``."""
    if isinstance(node, ast.BinOp):
        pieces = _operands(node)
    elif isinstance(node, ast.JoinedStr):
        pieces = [node]
    else:
        return None
    text, values, stringy = "", [], False
    for piece in pieces:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            text, stringy = text + piece.value, True
        elif isinstance(piece, ast.JoinedStr):
            stringy = True
            for value in piece.values:
                if isinstance(value, ast.FormattedValue):
                    values.append(value.value)
                elif isinstance(value, ast.Constant):
                    text += str(value.value)
        else:
            values.append(piece)
    return (text, values) if stringy else None


def _unsanitised_join(node: ast.AST) -> str | None:
    """R3: the joined argument of a ``"<...|...>".join(...)`` that does not
    pass each item through :data:`_SANITISING`, else ``None``."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and isinstance(node.func.value, ast.Constant)
        and " | " in str(node.func.value.value)
        and node.args
    ):
        return None
    joined = node.args[0]
    comprehension = (ast.GeneratorExp, ast.ListComp, ast.SetComp)
    if isinstance(joined, comprehension) and _called_name(joined.elt) in _SANITISING:
        return None
    return ast.unparse(joined)


def _flagged(node: ast.AST) -> list[str]:
    """What *node* interpolates or joins against R1, R2 or R3."""
    joined = _unsanitised_join(node)
    if joined is not None:
        return [joined]
    parts = _parts(node) if isinstance(node, ast.expr) else None
    if parts is None:
        return []
    text, values = parts
    flagged: list[str] = []
    if any(marker in text for marker in _SOURCE_MARKERS):
        flagged += [ast.unparse(v) for v in values if not _is_safe(v)]
    if any(marker in text for marker in _SEGMENT_MARKERS):
        flagged += [
            ast.unparse(v) for v in values if _external_names(v) and not _is_safe(v)
        ]
    return flagged


def _all_flagged(tree: ast.AST) -> set[tuple[int, str]]:
    """``(line, expression)`` of every flagged part of *tree*, allowed or not."""
    return {
        (getattr(node, "lineno", 0), shown)
        for node in ast.walk(tree)
        for shown in _flagged(node)
    }


def _offenders(relative: str, tree: ast.AST) -> list[str]:
    return [
        f"{relative}:{line}: {shown}"
        for line, shown in sorted(_all_flagged(tree))
        if (relative, shown) not in _ALLOWED
    ]


def _trees() -> list[tuple[str, ast.AST]]:
    """``(path relative to src/pitloom, tree)`` of every module but the
    helpers'."""
    found: list[tuple[str, ast.AST]] = []
    for path in sorted(_SRC.rglob("*.py")):
        relative = path.relative_to(_SRC).as_posix()
        if relative != _HELPERS:
            found.append((relative, ast.parse(path.read_text(encoding="utf-8"))))
    return found


def test_provenance_strings_go_through_the_builders() -> None:
    offenders = [
        line for relative, tree in _trees() for line in _offenders(relative, tree)
    ]
    assert not offenders, (
        "build with provenance_source()/provenance_segment():\n" + "\n".join(offenders)
    )


def test_every_allowed_entry_is_still_flagged() -> None:
    """An entry whose code is gone or fixed is removed, so it cannot hide a
    new one."""
    flagged = {
        (relative, shown)
        for relative, tree in _trees()
        for _, shown in _all_flagged(tree)
    }
    assert set(_ALLOWED) <= flagged, set(_ALLOWED) - flagged


def test_the_guard_sees_a_raw_name() -> None:
    """The scan is not vacuous: it flags each raw interpolation and passes
    the builders, literals and constants."""
    source = (
        "a = f'Source: {label}'\n"
        "a = f'Source: {provenance_source(label)}'\n"
        "a = provenance_source(label)\n"
        "a = 'Source: ' + label\n"
        "a = f'Source: {POETRY_LOCK} | Method: x'\n"
        "a = f'{source} | File: {archive}'\n"
        "a = f'{source} | Field: {member}'\n"
        "a = f'{source} | Field: {key}'\n"
        "a = f'{source} | Method: {raw.strip()}'\n"
        "a = f'{source} | Field: graph.name'\n"
        "a = f'Source: {sanitize_provenance_text(label)}'\n"
        "a = f'{base} | Normalized-From: {value}'\n"
        "a = f'Fetched from AUTHORS at {mod.REPO_URL}'\n"
        "a = 'Source: x | Field: ' + f'{entry}'\n"
        "a = f'path {label}'\n"
        "a = 1 + label\n"
        "a = ' | '.join(sorted(constraints))\n"
        "a = ' | '.join(sanitize_provenance_text(c) for c in constraints)\n"
        "a = ' | '.join(provenance_note(c) for c in constraints)\n"
        "a = f'{base} | Deprecated-License-Id: {ids}'\n"
        "a = ', '.join(names)\n"
    )
    found = {line.split(":")[1] for line in _offenders("x.py", ast.parse(source))}
    assert found == {"1", "4", "6", "7", "9", "11", "12", "14", "17", "20"}
