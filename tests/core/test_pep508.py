# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.pep508`: the one parse of a PEP 508
requirement or marker, its nesting cap and its ``RecursionError``, whether
a requirement is a direct reference, and a drift guard that no other module
calls ``packaging``'s parsers.

See also: tests/test_deep_marker_surfaces.py (every route, end to end),
tests/test_direct_reference_surfaces.py (a direct reference on every route).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=protected-access

from __future__ import annotations

import ast
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest
from packaging.markers import InvalidMarker
from packaging.requirements import InvalidRequirement

from pitloom.core import extra_gate, pep508
from pitloom.core.extra_gate import MarkerShapeError, parse_gate
from pitloom.core.pep508 import (
    MAX_MARKER_NESTING,
    is_direct_reference,
    marker_nesting,
    parse_marker,
    parse_requirement,
)
from tests._deep_marker import nested_marker

_SRC = Path(__file__).resolve().parents[2] / "src" / "pitloom"


@pytest.mark.parametrize(
    ("text", "marker", "depth"),
    [
        ("a", False, 0),
        ('a; (os_name == "x")', False, 1),
        ('a; os_name == "((((("', False, 0),
        # A quoted ")" closes nothing.
        ('a; (os_name == ")" and (os_name == ")" and (x', False, 3),
        ("a; os_name == 'x\" ((' and (y)", False, 1),
        # A direct reference's URL may hold quotes and parentheses.
        ("a [b, c] @ https://h/'((((( ; (os_name == 'x')", False, 1),
        ("a @ ((y", False, 0),
        ("a @ ((y", True, 2),
        ('a; os_name == "@" and (b)', False, 1),
        ("a; ) ((x", False, 2),
        ("a; 'open ((", False, 0),
    ],
    ids=["none", "one", "quoted-open", "quoted-close", "other-quote", "url",
         "url-only", "marker-no-url", "at-in-marker", "stray-close", "unclosed"],
)  # fmt: skip
def test_marker_nesting(text: str, marker: bool, depth: int) -> None:
    assert marker_nesting(text, marker=marker) == depth


def test_nesting_counts_at_least_what_packaging_nests() -> None:
    """Each level of :func:`_nested` is one level of the parsed marker."""
    assert marker_nesting(str(parse_marker(nested_marker(5))), marker=True) == 5


_DIGIT_TEXTS = [
    (parse_requirement, "a>=" + "1" * 641, InvalidRequirement, "REQUIREMENT"),
    (parse_marker, "python_version >= '" + "1" * 641 + "'", InvalidMarker, "MARKER"),
]


@pytest.mark.parametrize(
    ("parse", "over", "error", "subject"), _DIGIT_TEXTS, ids=["requirement", "marker"]
)
def test_digits_over_the_cap_are_refused_once(
    caplog: pytest.LogCaptureFixture,
    parse: Callable[..., Any],
    over: str,
    error: type[Exception],
    subject: str,
) -> None:
    """A 641-digit number is refused with the parser's own error, one
    ``WARNING:`` per text; *quiet* silences it."""
    with caplog.at_level(logging.DEBUG, logger="pitloom.core.pep508"):
        for quiet in (True, False, False):
            with pytest.raises(error, match="640-digit version-number cap"):
                parse(over, quiet=quiet)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage().startswith(f"{subject}=")


_PARSERS: list[tuple[Callable[..., Any], str, type[Exception], str]] = [
    (parse_requirement, "a; ", InvalidRequirement, "REQUIREMENT"),
    (parse_marker, "", InvalidMarker, "MARKER"),
]


@pytest.mark.parametrize(
    ("parse", "prefix", "error", "subject"), _PARSERS, ids=["requirement", "marker"]
)
def test_nesting_over_the_cap_is_refused_once(
    caplog: pytest.LogCaptureFixture,
    parse: Callable[..., Any],
    prefix: str,
    error: type[Exception],
    subject: str,
) -> None:
    """At the cap it parses; one level over, it is refused with the
    parser's own error before parsing, one ``WARNING:`` per text, the text
    shown cut; *quiet* silences it."""
    parse(prefix + nested_marker(MAX_MARKER_NESTING))
    over = prefix + nested_marker(MAX_MARKER_NESTING + 1)
    with caplog.at_level(logging.DEBUG, logger="pitloom.core.pep508"):
        for quiet in (True, False, False):
            with pytest.raises(error, match="64-level marker-nesting cap"):
                parse(over, quiet=quiet)
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.DEBUG]
    assert caplog.messages[0] == (
        f"{subject}={over[:60]}...: larger than the 64-level marker-nesting cap;"
        " not parsed"
    )


@pytest.mark.parametrize(
    ("parse", "prefix", "error", "subject"), _PARSERS, ids=["requirement", "marker"]
)
def test_a_recursion_error_is_the_invalid_input_error(
    monkeypatch: pytest.MonkeyPatch,
    parse: Callable[..., Any],
    prefix: str,
    error: type[Exception],
    subject: str,
) -> None:
    """Under the cap, a ``RecursionError`` (a smaller stack) still fails
    as text that is not PEP 508 does."""

    def _recurse(_text: str) -> NoReturn:
        raise RecursionError

    monkeypatch.setattr(pep508, subject.title(), _recurse)
    with pytest.raises(error, match="nested too deep") as raised:
        parse(prefix + "os_name == 'a'")
    assert isinstance(raised.value.__cause__, RecursionError)


_DEEP_URL = "a @ https://h/x.whl ; " + "(" * 900 + "os_name == 'b'" + ")" * 900


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a==1.0", False),
        ("A_b.C>=1 ; os_name == 'x @ y'", False),
        ("a; os_name == '@'", False),
        ("a >= = 1", False),
        ("a @ git+https://h/r.git@v1", True),
        ("A_b[x,y]@https://h/a;b.whl ; python_version >= '3.8'", True),
        ("a @ file:///C:/w/a-1.0-py3-none-any.whl", True),
        ("a @ C:\\w\\a.whl", True),
        ("a @ https://h/x @ y", True),
        (_DEEP_URL, True),
    ],
    ids=["pin", "at-in-marker", "at-only-in-marker", "bad-no-url", "git",
         "extras-semicolon-marker", "windows-file-url", "windows-path",
         "bad-url-at", "deep-url"],
)  # fmt: skip
def test_is_direct_reference(
    text: str, expected: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """``packaging``'s reading, or the URL prefix when it cannot parse the
    text; a text refused for its nesting is not warned of here."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        assert is_direct_reference(text) is expected
    assert not caplog.records


@pytest.mark.parametrize(
    "parse", [parse_requirement, parse_marker, is_direct_reference]
)
def test_a_non_string_raises_type_error(parse: Callable[..., Any]) -> None:
    with pytest.raises(TypeError):
        parse(None)


def test_parse_gate_refuses_a_marker_over_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate reader recurses too: over the cap, or on a
    ``RecursionError``, the gate cannot be isolated."""
    assert parse_gate(nested_marker(MAX_MARKER_NESTING)) is None
    with pytest.raises(MarkerShapeError, match="nested too deep"):
        parse_gate(nested_marker(MAX_MARKER_NESTING + 1))

    def _recurse(_self: object) -> NoReturn:
        raise RecursionError

    monkeypatch.setattr(extra_gate._GateParser, "parse", _recurse)
    with pytest.raises(MarkerShapeError, match="nested too deep"):
        parse_gate('extra == "a"')


#: ``packaging``'s parsers: what no module but :mod:`pitloom.core.pep508`
#: may call.
_PARSER_MODULES = {
    "packaging.requirements": "Requirement",
    "packaging.markers": "Marker",
}


#: ``packaging``'s version parsers: what no module but
#: :mod:`pitloom.core.pep440` may call on input.
_VERSION_MODULES = {
    "packaging.version": "Version",
    "packaging.specifiers": "SpecifierSet",
}


def _direct_parses(
    tree: ast.Module, parsers: dict[str, str] | None = None
) -> list[int]:
    """The lines of *tree* calling one of *parsers* (module -> name;
    default ``packaging``'s ``Requirement`` and ``Marker``): by a name
    imported from its module, or by attribute."""
    parsers = _PARSER_MODULES if parsers is None else parsers
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {
        alias.asname or alias.name
        for node in imports
        if isinstance(node, ast.ImportFrom) and node.module in parsers
        for alias in node.names
        if alias.name == parsers[node.module]
    }
    # ``packaging`` or one of its modules, under any name.
    modules = {"packaging"} | {
        alias.asname or alias.name
        for node in imports
        for alias in node.names
        if (getattr(node, "module", None) or alias.name).startswith("packaging")
    }
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in names)
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in parsers.values()
                and ast.unparse(node.func.value).split(".", maxsplit=1)[0] in modules
            )
        )
    ]


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        ("from packaging.requirements import Requirement\nRequirement('a')", [2]),
        ("from packaging.markers import Marker as M\nM('a')", [2]),
        ("import packaging.markers\npackaging.markers.Marker('a')", [2]),
        ("from packaging import requirements\nrequirements.Requirement('a')", [2]),
        ("import packaging.markers as pm\npm.Marker('a')", [2]),
        ("from x import requirements\nrequirements.Requirement('a')", []),
        ("from packaging.requirements import Requirement\nx: Requirement", []),
        ("Requirement('a')", []),  # not packaging's
    ],
    ids=[
        "name",
        "alias",
        "attribute",
        "module-from",
        "module-as",
        "not-packaging",
        "annotation",
        "other",
    ],
)
def test_direct_parses(source: str, lines: list[int]) -> None:
    """The guard's own rows."""
    assert _direct_parses(ast.parse(source)) == lines


def test_only_the_helper_calls_packaging_parsers() -> None:
    """Every parse goes through :mod:`pitloom.core.pep508`, so its cap and
    its ``RecursionError`` handling cover every caller."""
    found = {
        path.relative_to(_SRC).as_posix(): lines
        for path in sorted(_SRC.rglob("*.py"))
        if (lines := _direct_parses(ast.parse(path.read_text(encoding="utf-8"))))
    }
    assert set(found) == {"core/pep508.py"}


def test_only_the_helper_parses_versions() -> None:
    """Every ``Version`` and ``SpecifierSet`` goes through
    :mod:`pitloom.core.pep440`, so its digit cap covers every caller; the
    Hatchling hook checks the installed Hatchling's own version."""
    found = {
        path.relative_to(_SRC).as_posix()
        for path in sorted(_SRC.rglob("*.py"))
        if _direct_parses(ast.parse(path.read_text(encoding="utf-8")), _VERSION_MODULES)
    }
    assert found == {"core/pep440.py", "plugins/hatch.py"}
