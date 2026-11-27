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
import dataclasses
import importlib
import logging
import pkgutil
import re
import sys
import threading
from collections.abc import Mapping
from typing import Any

import pytest

import pitloom.messages
from pitloom.core.config_cascade import ConfigOverrides
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
    overrides_route,
    say_summary,
    strict_surfaces,
)
from pitloom.messages.models import USAGE_HINTS, USAGE_TARGET_PROJECT
from pitloom.messages.pypi import NO_WHEEL_LINES, RELEASE_FILE_NOT_FOUND
from tests._message_drift import SRC_ROOT

_A = Line(level="ERROR", template="FILE=%(file)s: a; pass --a")
_B = Line(level="ERROR", template="FILE=%(file)s: a; pass a=True")
_C = Line(level="ERROR", template="FILE=%(file)s: a; set a in [tool.pitloom]")
_D = Line(level="ERROR", template="FILE=%(file)s: a; set ConfigOverrides.a=True")


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


@pytest.mark.parametrize(
    ("surface", "line"),
    [(SURFACE_CLI, _A), (SURFACE_LIBRARY, _D), (SURFACE_HOOK, _C)],
    ids=["cli", "library", "hook"],
)
def test_the_overrides_route_changes_the_library_s_wording_only(
    surface: str, line: Line
) -> None:
    twins = Twins(cli=_A, library=_B, hook=_C, overrides=_D)
    without = Twins(cli=_A, library=_B, hook=_C)
    assert twins.members == (_A, _B, _C, _D)
    with advice_surface(surface):
        assert twins.current() is (_B if surface == SURFACE_LIBRARY else line)
        with overrides_route():
            assert twins.current() is line
            assert without.current() is without.for_surface(surface)
        assert twins.current() is (_B if surface == SURFACE_LIBRARY else line)


def test_the_overrides_route_ends_with_its_block_or_function() -> None:
    twins = Twins.no_hook(cli=_A, library=_B, overrides=_D)

    @overrides_route()
    def said() -> Line:
        return twins.current()

    with pytest.raises(KeyError), overrides_route():
        assert twins.current() is _D
        raise KeyError
    assert twins.current() is _B
    assert said() is _D and twins.current() is _B


def test_an_overrides_wording_of_another_shape_is_refused() -> None:
    other = Line(level="ERROR", template="DIR=%(dir)s: a; set ConfigOverrides.a=True")
    with pytest.raises(ValueError, match="different levels or fields"):
        Twins.no_hook(cli=_A, library=_B, overrides=other)


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
    attributes = {"cli", "library", "hook", "overrides"}
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


#: Twins the overrides route (``embed_wheel_sbom()``) never says, by name:
#: it reads neither a Git URL nor a PyPI URL.
_OFF_THE_OVERRIDES_ROUTE = frozenset(
    {"_model_stub.READER_UNSAFE_PYPI_LINES", "_model_stub.READER_UNSAFE_REMOTE_LINES"}
)


def test_a_library_action_naming_an_overrides_setting_has_an_overrides_twin() -> None:
    """A library wording that says to set a ``ConfigOverrides`` field by
    its keyword name (``set trust_model_files=True``) has a wording for the
    route that takes it as a field, unless that route never says it."""
    fields = "|".join(field.name for field in dataclasses.fields(ConfigOverrides))
    keyword = re.compile(rf"\bset ({fields})=")
    flagged = {
        name
        for name, pair in _twins()
        if keyword.search(getattr(pair.library, "template", ""))
    }
    assert flagged >= _OFF_THE_OVERRIDES_ROUTE
    for name, pair in _twins():
        if name in flagged - _OFF_THE_OVERRIDES_ROUTE:
            assert pair.overrides is not None, name
            assert not keyword.search(pair.overrides.template), name
            assert "set ConfigOverrides." in pair.overrides.template, name
        if name in _OFF_THE_OVERRIDES_ROUTE:
            assert pair.overrides is None, name


#: Entries the overrides route never says, by code: it reads neither a Git
#: URL nor a PyPI URL.
_OFF_THE_ROUTE_CODES = frozenset({"reader-unsafe/remote"})


def test_a_line_naming_an_overrides_setting_as_a_keyword_has_its_field_twin() -> None:
    """Every catalogue line that names a ``ConfigOverrides`` field as a
    keyword (``credentials=CredentialPolicy(...)``, ``set
    trust_model_files=True``), however it is picked, has a sibling line of
    its entry naming the field (``ConfigOverrides.credentials=``) for
    ``embed_wheel_sbom()``, unless that route never says the entry."""
    names = [field.name for field in dataclasses.fields(ConfigOverrides)]
    missing = []
    for code, message in sorted(MESSAGES.items()):
        templates = " ".join(line.template for line in message.lines)
        for name in names:
            if not re.search(rf"(?<![.\w]){name}=", templates):
                continue
            if code in _OFF_THE_ROUTE_CODES:
                assert f"ConfigOverrides.{name}=" not in templates, code
            elif f"ConfigOverrides.{name}=" not in templates:
                missing.append(f"{code}: {name}")
    assert not missing, missing


def test_a_module_saying_an_overrides_line_asks_for_the_route() -> None:
    """A line picked by its own branch per surface, not a :class:`Twins`,
    is said on the overrides route only where its module asks
    ``on_overrides_route()``."""
    unasked = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_bytes())
        # Read, not defined: a module that says the line, not the entry's.
        names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        if any(name.endswith("_OVERRIDES_LINE") for name in names) and (
            "on_overrides_route" not in names
        ):
            unasked.append(str(path.relative_to(SRC_ROOT)))
    assert not unasked, unasked
