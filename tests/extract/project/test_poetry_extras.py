# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``[tool.poetry.extras]``: an ``optional = true`` dependency is
listed once per extra that names it, tagged ``extra == "x"`` like a built
wheel's ``Requires-Dist``.

See also: test_poetry_parsing.py (low-level helpers), test_poetry_extract.py.
"""

import logging
from pathlib import Path
from typing import Any

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.plugin.manager import PluginManager

from pitloom.core.project import ProjectMetadata
from pitloom.extract.project._poetry_extras import defer_to_poetry_lists
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject import read_pyproject

_OPT = {"optional": True}
_PROV = {"dependencies": "X"}


def _extract(
    deps: dict[str, Any], extras: Any = None, **poetry: Any
) -> tuple[list[str], str]:
    """Return ``(dependencies, dependencies provenance)``."""
    table: dict[str, Any] = {"name": "p", "dependencies": deps, **poetry}
    if extras is not None:
        table["extras"] = extras
    meta = extract_poetry_metadata({"tool": {"poetry": table}}, Path("."))
    return meta.dependencies, meta.provenance["dependencies"]


@pytest.mark.parametrize(
    ("deps", "extras", "expected"),
    [
        pytest.param(
            {"python": "^3.9", "req": "^2.0", "attrs": {"version": ">=23", **_OPT}},
            {"full": ["attrs"]},
            ["req>=2.0,<3.0.0", 'attrs>=23; extra == "full"'],
            id="basic",
        ),
        pytest.param(
            {"attrs": {"version": "~1.2", **_OPT}},
            {"b": ["attrs"], "a": ["attrs"]},
            ['attrs<1.3.0,>=1.2; extra == "a"', 'attrs<1.3.0,>=1.2; extra == "b"'],
            id="two-extras",
        ),
        pytest.param(
            {"Foo_Bar": {"version": "^1.0", **_OPT}},
            {"x": ["foo-bar"]},
            ['foo-bar<2.0.0,>=1.0; extra == "x"'],
            id="name-spelling",
        ),
        pytest.param(
            {"foo-bar": {"version": "^1.0", **_OPT}},
            {"x": ["Foo_Bar"]},
            ['foo-bar<2.0.0,>=1.0; extra == "x"'],
            id="extra-entry-spelling",
        ),
        # Limit: the `python`/`markers` keys are dropped; poetry-core writes
        # `six (==1.16) ; (python_version < "3.12") and (extra == "x")`.
        pytest.param(
            {"six": {"version": "1.16", "python": "<3.12", **_OPT}},
            {"x": ["six"]},
            ['six==1.16; extra == "x"'],
            id="dict-extra-keys-limit",
        ),
        pytest.param(
            {"b": {"version": "1", **_OPT}, "P": {"version": "*", **_OPT}},
            {"dev": ["b"], "all": ["p"]},
            ['b==1; extra == "dev"'],
            id="self-reference-adds-nothing",
        ),
        pytest.param(
            {"req": "*", "attrs": _OPT, "six": "*"},
            {"x": ["attrs", "six"]},
            ["req", 'attrs; extra == "x"', 'six; extra == "x"'],
            id="non-optional-listed-is-extra-only",
        ),
        # Limit: as above, each table's `python` key is dropped; poetry-core
        # writes `sc (>=1) ; (python_version < "3.11") and (extra == "x")`.
        pytest.param(
            {
                "sc": [
                    {"version": ">=1", "python": "<3.11", **_OPT},
                    {"version": ">=2", "python": ">=3.11", **_OPT},
                ],
                "req": "*",
            },
            {"x": ["sc"]},
            ["req", 'sc>=1; extra == "x"', 'sc>=2; extra == "x"'],
            id="list-form-optional-limit",
        ),
        pytest.param(
            {"sc": [{"version": ">=1"}, {"version": ">=2"}, {"version": ">=2"}]},
            {"x": []},
            ["sc>=1", "sc>=2"],
            id="list-form-required",
        ),
        pytest.param(
            {"sc": [{"version": ">=1", "python": "<3.11", **_OPT}, {"version": ">=2"}]},
            {"x": []},
            ["sc>=2"],
            id="list-form-partly-optional",
        ),
        # Limit: skipped with a WARNING:; poetry-core writes the direct
        # reference `attrs @ git+https://x/y ; extra == "x"`.
        pytest.param(
            {"attrs": {**_OPT, "git": "https://x/y"}},
            {"x": ["attrs"]},
            [],
            id="unrepresentable-optional-limit",
        ),
    ],
)
def test_optional_dependency_tagged_per_extra(
    deps: dict[str, Any],
    extras: Any,
    expected: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Expected as poetry-core 2.4.1 writes ``Requires-Dist``, but the
    ``limit`` rows."""
    with caplog.at_level(logging.WARNING):
        got, _ = _extract(deps, extras)
    assert got == expected
    assert "listed in no" not in caplog.text


@pytest.mark.parametrize(
    ("extras", "needle", "prefix"),
    [
        pytest.param(None, "attrs", "Skipping Poetry dependency", id="no-extras-table"),
        pytest.param(
            {}, "attrs", "Skipping Poetry dependency", id="empty-extras-table"
        ),
        pytest.param({"x": []}, "attrs", "Skipping Poetry dependency", id="not-listed"),
        pytest.param(
            {"x": ["ghost"]}, "ghost", "Skipping extra entry", id="undeclared"
        ),
    ],
)
def test_unlisted_or_undeclared_warns_once(
    extras: Any, needle: str, prefix: str, caplog: pytest.LogCaptureFixture
) -> None:
    deps = {"attrs": {"version": "1", **_OPT}, "other": "1"}
    with caplog.at_level(logging.WARNING):
        got, _ = _extract(deps, extras)
    assert got == ["other==1"]
    warned = [r for r in caplog.records if needle in r.getMessage()]
    assert len(warned) == 1
    assert warned[0].getMessage().startswith(prefix)


@pytest.mark.parametrize(
    "deps",
    [
        pytest.param({"attrs": {"version": "1", **_OPT}}, id="optional"),
        pytest.param({"attrs": {**_OPT, "git": "https://x/y"}}, id="unrepresentable"),
    ],
)
def test_listed_entry_not_warned_as_unlisted_or_undeclared(
    deps: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        _extract(deps, {"x": ["attrs"]})
    assert "listed in no" not in caplog.text
    assert "not declared" not in caplog.text


@pytest.mark.parametrize(
    ("project", "expected"),
    [
        pytest.param({"dependencies": []}, ['a; extra == "x"'], id="empty-deps"),
        pytest.param(
            {"optional-dependencies": {}}, ['a; extra == "x"'], id="empty-extras"
        ),
        pytest.param({"dependencies": ["d"]}, [], id="deps"),
        pytest.param({"optional-dependencies": {"y": ["z"]}}, [], id="extras"),
    ],
)
def test_poetry_extras_ignored_only_for_non_empty_project_list(
    caplog: pytest.LogCaptureFixture, project: dict[str, Any], expected: list[str]
) -> None:
    """poetry-core 2.4 ignores ``[tool.poetry.extras]`` when a ``[project]``
    list is non-empty, with the one ``WARNING:``; one declared empty counts
    as absent (measured: ``Requires-Dist: a ; extra == "x"``)."""
    poetry = {"name": "p", "dependencies": {"a": _OPT}, "extras": {"x": ["a"]}}
    data = {"project": project, "tool": {"poetry": poetry}}
    with caplog.at_level(logging.WARNING):
        meta = extract_poetry_metadata(data, Path("."))
    assert meta.dependencies == expected
    ignored = [m for m in caplog.messages if "Ignoring [tool.poetry.extras]" in m]
    assert len(ignored) == (not expected)


def test_non_empty_primary_list_not_deferred() -> None:
    """A list another source filled (a setuptools requirements file) stays,
    with its provenance."""
    meta = ProjectMetadata(name="p", dependencies=["d"], provenance=dict(_PROV))
    poetry = ProjectMetadata(name="p", provenance={"dependencies": "Y"})
    assert not defer_to_poetry_lists(meta, poetry, {"project": {}})
    assert meta.provenance == _PROV


def test_quiet_suppresses_warnings(caplog: pytest.LogCaptureFixture) -> None:
    table = {"name": "p", "dependencies": {"a": _OPT}, "extras": {"x": ["ghost"]}}
    with caplog.at_level(logging.WARNING):
        meta = extract_poetry_metadata(
            {"tool": {"poetry": table}}, Path("."), quiet=True
        )
    assert not meta.dependencies
    assert not caplog.records


@pytest.mark.parametrize(
    ("extras", "expected"),
    [
        pytest.param(None, "tool.poetry.dependencies", id="absent"),
        pytest.param({}, "tool.poetry.dependencies, tool.poetry.extras", id="empty"),
        pytest.param(
            {"x": []}, "tool.poetry.dependencies, tool.poetry.extras", id="empty-extra"
        ),
    ],
)
def test_provenance_keyed_on_extras_presence(extras: Any, expected: str) -> None:
    _, prov = _extract({"req": "*"}, extras)
    assert prov == f"Source: pyproject.toml | Field: {expected}"


def test_extras_wrong_type_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        got, prov = _extract({"a": "*"}, extras=["a"])
    assert got == ["a"]
    assert "'extras' is list, expected a table" in caplog.text
    assert prov.endswith("tool.poetry.dependencies")


def test_groups_not_listed_debug_only(caplog: pytest.LogCaptureFixture) -> None:
    group = {"group": {"dev": {"dependencies": {"pytest": "*"}}}}
    # The "pitloom" logger carries its own level once any test configures
    # logging, so the root-level default of at_level() is not enough.
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        got, _ = _extract({"req": "*"}, **group)
    assert got == ["req"]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert "not listed" in caplog.text


_POETRY = (
    '[tool.poetry]\nname = "p"\n[tool.poetry.dependencies]\nreq = "^2.1"\n'
    'attrs = {version = "*", optional = true}\n'
)
_POETRY_EXTRAS = '[tool.poetry.extras]\nx = ["attrs"]\n'
_DYNAMIC = 'dynamic = ["dependencies"]\n'
#: Poetry 2: the name is ``[project]``'s alone.
_POETRY_UNNAMED = _POETRY.replace('name = "p"\n', "")
_PG = '[project.optional-dependencies]\npg = ["psycopg2>=2"]\n'


@pytest.mark.parametrize(
    ("project", "poetry", "expected", "fields"),
    [
        pytest.param(
            _DYNAMIC + _PG,
            _POETRY,
            ["req>=2.1,<3.0.0", 'psycopg2>=2; extra == "pg"'],
            "tool.poetry.dependencies, project.optional-dependencies",
            id="poetry-base-project-extras",
        ),
        pytest.param(
            _DYNAMIC + _PG,
            _POETRY + _POETRY_EXTRAS,
            ["req>=2.1,<3.0.0", 'psycopg2>=2; extra == "pg"'],
            "tool.poetry.dependencies, project.optional-dependencies",
            id="poetry-extras-ignored",
        ),
        pytest.param(
            'dependencies = ["req"]\n[project.optional-dependencies]\nx = ["attrs"]\n',
            _POETRY + _POETRY_EXTRAS,
            ["req", 'attrs; extra == "x"'],
            "project.dependencies, project.optional-dependencies",
            id="project-tables-win",
        ),
        pytest.param(
            _DYNAMIC,
            _POETRY + _POETRY_EXTRAS,
            ["req>=2.1,<3.0.0", 'attrs; extra == "x"'],
            "tool.poetry.dependencies, tool.poetry.extras",
            id="poetry-only",
        ),
        pytest.param(
            _DYNAMIC,
            _POETRY_UNNAMED + _POETRY_EXTRAS,
            ["req>=2.1,<3.0.0", 'attrs; extra == "x"'],
            "tool.poetry.dependencies, tool.poetry.extras",
            id="poetry2-unnamed",
        ),
        pytest.param(
            "dependencies = []\n",
            _POETRY + _POETRY_EXTRAS,
            ["req>=2.1,<3.0.0", 'attrs; extra == "x"'],
            "tool.poetry.dependencies, tool.poetry.extras",
            id="declared-empty-deps",
        ),
        pytest.param(
            "dependencies = []\noptional-dependencies = {}\n",
            _POETRY + _POETRY_EXTRAS,
            ["req>=2.1,<3.0.0", 'attrs; extra == "x"'],
            "tool.poetry.dependencies, tool.poetry.extras",
            id="declared-empty-both",
        ),
        pytest.param(
            "dependencies = []\n",
            '[tool.poetry]\nname = "p"\n',
            [],
            "project.dependencies",
            id="declared-empty-no-poetry-deps",
        ),
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_project_and_poetry_tables(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    project: str,
    poetry: str,
    expected: list[str],
    fields: str,
) -> None:
    """Base list and extras each come from the table declaring them, as
    Poetry reads them; the CLI and the Hatchling hook gap-fill alike."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "p"\nversion = "1"\n{project}{poetry}', encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING):
        cli, _ = read_pyproject(tmp_path / "pyproject.toml")
    warned = [r.getMessage() for r in caplog.records]  # the CLI's only
    core = hatchling_metadata_core.ProjectMetadata(str(tmp_path), PluginManager())
    hook = metadata_from_hatchling(core, tmp_path)
    for meta in (cli, hook):
        assert meta.dependencies == expected
        assert meta.provenance["dependencies"].rpartition("Field: ")[2] == fields
    ignored = [m for m in warned if m.startswith("Ignoring [tool.poetry.extras]")]
    declares = '= ["' in project.replace(_DYNAMIC, "")  # a non-empty list
    assert len(ignored) == ("tool.poetry.extras" in poetry and declares)
    if ignored:
        assert not [m for m in warned if "listed in no" in m]
    if "name" not in poetry:
        assert not warned
