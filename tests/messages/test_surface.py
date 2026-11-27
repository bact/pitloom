# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The surface that runs and the wording each surface gets: the context
the entry points open, :class:`~pitloom.messages.Twins` resolved where a
line is said, and every twin of the catalogue held to one shape.

See also: tests/core/test_option_names.py (an option as each surface
spells it) and tests/messages/test_surface_lines.py (each surface's line,
said end to end).
"""

from __future__ import annotations

import ast
import contextvars
import importlib
import logging
import pkgutil
import sys
import threading
from collections.abc import Mapping
from typing import Any

import pytest

import pitloom.messages
from pitloom.core.internal_error import InternalError
from pitloom.messages import (
    MESSAGES,
    SUMMARIES,
    SURFACE_CLI,
    SURFACE_HOOK,
    SURFACE_LIBRARY,
    SURFACES,
    CodedValueError,
    Line,
    Summary,
    Twins,
    advice_surface,
    current_surface,
    emit,
    say_summary,
    strict_surfaces,
)
from pitloom.messages.models import USAGE_HINTS, USAGE_TARGET_PROJECT
from pitloom.messages.pypi import NO_WHEEL_LINES, RELEASE_FILE_NOT_FOUND
from tests._message_drift import SRC_ROOT

_A = Line(level="ERROR", template="FILE=%(file)s: a; pass --a")
_B = Line(level="ERROR", template="FILE=%(file)s: a; pass a=True")
_C = Line(level="ERROR", template="FILE=%(file)s: a; set a in [tool.pitloom]")


def test_the_library_is_the_default_and_each_block_restores_the_last() -> None:
    assert current_surface() == SURFACE_LIBRARY
    with advice_surface(SURFACE_CLI):
        assert current_surface() == SURFACE_CLI
        with pytest.raises(KeyError), advice_surface(SURFACE_HOOK):
            assert current_surface() == SURFACE_HOOK
            raise KeyError
        assert current_surface() == SURFACE_CLI
    assert current_surface() == SURFACE_LIBRARY


@pytest.mark.parametrize("surface", ["config", "CLI", ""], ids=["old", "case", "empty"])
def test_an_unknown_surface_is_a_programming_error(surface: str) -> None:
    with pytest.raises(InternalError), advice_surface(surface):
        pass  # pragma: no cover -- never entered
    with pytest.raises(InternalError):
        Twins(cli=_A, library=_B, hook=_C).for_surface(surface)


@pytest.mark.parametrize(
    ("surface", "line"),
    [(SURFACE_CLI, _A), (SURFACE_LIBRARY, _B), (SURFACE_HOOK, _C)],
    ids=["cli", "library", "hook"],
)
def test_twins_say_the_wording_of_the_surface_that_runs(
    surface: str, line: Line
) -> None:
    twins = Twins(cli=_A, library=_B, hook=_C)
    with advice_surface(surface):
        assert twins.current() is line
    assert twins.members == (_A, _B, _C)


def test_twins_list_a_shared_wording_once_in_surface_order() -> None:
    assert Twins(cli=_A, library=_B, hook=_A).members == (_A, _B)
    assert Twins.no_hook(cli=_A, library=_B).members == (_A, _B)
    assert SURFACES == (SURFACE_CLI, SURFACE_LIBRARY, SURFACE_HOOK)


@pytest.mark.parametrize(
    "other",
    [
        Line(level="WARNING", template="FILE=%(file)s: a; pass a=True"),
        Line(level="ERROR", template="DIR=%(dir)s: a; pass a=True"),
    ],
    ids=["level", "fields"],
)
def test_twins_of_another_level_or_fields_are_refused(other: Line) -> None:
    with pytest.raises(ValueError, match="different levels or fields"):
        Twins(cli=_A, library=other, hook=_A)


def test_summary_twins_naming_other_fields_are_refused() -> None:
    """A summary has no level: its fields alone tell the shapes apart."""

    def summary(template: str) -> Summary:
        return Summary(template=template, meaning="A test.", topic="models")

    one = summary("Found %(number)s things.")
    with pytest.raises(ValueError, match="different levels or fields"):
        Twins.no_hook(cli=one, library=summary("Found %(count)s things."))
    assert Twins.no_hook(cli=one, library=summary("%(number)s found.")).members


def test_a_line_the_hook_cannot_reach_raises_only_when_strict() -> None:
    twins = Twins.no_hook(cli=_A, library=_B)
    assert twins.hook is _B and not twins.hook_reachable
    with advice_surface(SURFACE_HOOK):
        with pytest.raises(InternalError, match="cannot reach"):
            twins.current()  # the suite runs strict (tests/conftest.py)
        context = contextvars.Context()
        # Outside the suite's strict block: the library's wording, never a
        # failed build over a line's wording.
        assert context.run(lambda: twins.for_surface(SURFACE_HOOK)) is _B
        with strict_surfaces():
            with pytest.raises(InternalError):
                twins.for_surface(SURFACE_HOOK)

        def after_a_strict_block() -> Line:
            """A strict block ends: the library's wording again."""
            with strict_surfaces():
                pass
            return twins.for_surface(SURFACE_HOOK)

        assert contextvars.Context().run(after_a_strict_block) is _B


@pytest.mark.parametrize(
    ("surface", "end"),
    [
        (SURFACE_CLI, "'loom project https://pypi.org/project/x/' reads its sdist"),
        (
            SURFACE_LIBRARY,
            "generate_pypi_sbom('https://pypi.org/project/x/', kind='sdist') "
            "reads its sdist",
        ),
    ],
    ids=["cli", "library"],
)
def test_an_error_and_a_record_resolve_the_twins_where_they_are_said(
    surface: str, end: str, caplog: pytest.LogCaptureFixture
) -> None:
    url = "https://pypi.org/project/x/"
    with advice_surface(surface):
        error = CodedValueError(
            RELEASE_FILE_NOT_FOUND, line=NO_WHEEL_LINES, name="x", version="1", url=url
        )
        with caplog.at_level(logging.ERROR, logger="pitloom"):
            emit(
                logging.getLogger("pitloom.test_surface"),
                RELEASE_FILE_NOT_FOUND,
                logging.ERROR,
                line=NO_WHEEL_LINES,
                name="x",
                version="1",
                url=url,
            )
    assert str(error).endswith(f"; {end}")
    assert caplog.records[-1].getMessage() == str(error)


def test_a_summary_twin_is_resolved_where_it_is_said(
    caplog: pytest.LogCaptureFixture,
) -> None:
    twins = USAGE_HINTS[USAGE_TARGET_PROJECT]
    log = logging.getLogger("pitloom.test_surface")
    with caplog.at_level(logging.INFO, logger="pitloom"):
        for surface in SURFACES:
            with advice_surface(surface):
                say_summary(log, twins, number=1)
    said = [r.getMessage() for r in caplog.records]
    expected = [twins.for_surface(s).template for s in SURFACES]
    assert said == [s.replace("%(number)s", "1") for s in expected]
    assert len(set(said)) == 3


def test_a_thread_does_not_inherit_the_surface() -> None:
    """Why a twinned line is said on the thread that entered the surface
    (Python's default; the free-threaded build may inherit it)."""
    seen: list[str] = []
    with advice_surface(SURFACE_CLI):
        worker = threading.Thread(target=lambda: seen.append(current_surface()))
        worker.start()
        worker.join(timeout=30)
    inherits = getattr(sys.flags, "thread_inherit_context", 0)
    assert seen == [SURFACE_CLI if inherits else SURFACE_LIBRARY]


def _twins() -> list[tuple[str, Twins[Any]]]:
    """Every :class:`Twins` a module of :mod:`pitloom.messages` holds, as a
    module attribute or a mapping value, with its name."""
    found: dict[int, tuple[str, Twins[Any]]] = {}
    for info in pkgutil.iter_modules(pitloom.messages.__path__):
        module = importlib.import_module(f"pitloom.messages.{info.name}")
        for name, value in vars(module).items():
            values = list(value.values()) if isinstance(value, Mapping) else [value]
            for item in values:
                if isinstance(item, Twins):
                    found.setdefault(id(item), (f"{info.name}.{name}", item))
    return sorted(found.values(), key=lambda pair: pair[0])


def test_every_twin_is_an_entry_s_line_and_says_another_wording() -> None:
    twins = _twins()
    assert len(twins) >= 20
    lines = {line for message in MESSAGES.values() for line in message.lines}
    for name, pair in twins:
        assert len(pair.members) >= 2, name
        for member in pair.members:
            assert member in lines or member in SUMMARIES, name
        assert pair.cli.template != pair.library.template, name


def test_no_twin_member_is_rendered_outside_the_resolution() -> None:
    """A call site that renders a twin's member itself would pick a
    surface: every one goes through ``line_for`` (or ``.current()``)."""
    attributes = {"cli", "library", "hook"}
    found = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in attributes
                and isinstance(node.value, ast.Name)
                and node.value.id.endswith("_LINES")
            ):
                found.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")
    assert not found, found
