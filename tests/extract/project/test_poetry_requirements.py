# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for one Poetry dependency table as the requirement poetry-core
writes (:mod:`pitloom.extract.project._poetry_requirements`), checked
against a real poetry-core build through the directory, sdist and wheel
routes.

The poetry-core internals used are drift-guarded here
(:func:`test_poetry_core_internals_drift_guard`).

See also: test_poetry_extras.py (extras, ignored tables, build backend),
test_poetry_parsing.py.
"""

import logging
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement
from poetry.core.constraints.generic import (
    parse_constraint as parse_generic_constraint,
)
from poetry.core.constraints.version import (
    parse_constraint as parse_version_constraint,
)
from poetry.core.factory import Factory
from poetry.core.packages.dependency import Dependency
from poetry.core.packages.utils.utils import create_nested_marker
from poetry.core.version.markers import parse_marker

from pitloom.core.requirements import normalize_dependency_specifier
from pitloom.extract.project import read_project
from pitloom.extract.project._poetry_requirements import (
    _poetry_core,
    poetry_requirement,
)
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "real-world-extras"
_HEAD = (
    '[build-system]\nbuild-backend = "poetry.core.masonry.api"\n'
    '[tool.poetry]\nname = "p"\nversion = "1"\ndescription = ""\nauthors = []\n'
)
_DEPS = '[tool.poetry.dependencies]\npython = "^3.8"\n'
_X = '\n[tool.poetry.extras]\nx = ["a"]\n'
_GIT = 'git = "https://github.com/x/a.git"'
_PROJECT = (
    '[build-system]\nbuild-backend = "poetry.core.masonry.api"\n'
    '[project]\nname = "p"\nversion = "1"\n'
)
_PG = '[project.optional-dependencies]\npg = ["psycopg2>=2"]\n'
_POETRY_DEPS = (
    '[tool.poetry.dependencies]\nreq = "^2.1"\n'
    'a = {version = "*", optional = true}\n[tool.poetry.extras]\nx = ["a"]\n'
)

#: id -> pyproject.toml whose requirements each route must list alike, as
#: poetry-core writes them. Shapes of the `python`/`markers` keys, sources,
#: per-dependency extras and the [project] precedence rules.
_EXACT = {
    "python-range": 'a = {version = ">=1", python = ">=3.9,<3.12"}',
    "python-caret": 'a = {version = ">=1", python = "^3.10"}',
    "python-tilde": 'a = {version = ">=1", python = "~3.9"}',
    "python-star": 'a = {version = ">=1", python = "3.9.*"}',
    "python-any": 'a = {version = ">=1", python = "*"}',
    "python-full": 'a = {version = ">=1", python = ">=3.9.1"}',
    "python-not": 'a = {version = ">=1", python = "!=3.9"}',
    "python-or": 'a = {version = ">=1", python = "<3.8 || >=3.10"}',
    "markers": 'a = {version = ">=1", markers = "sys_platform == \'win32\'"}',
    "both": (
        'a = {version = ">=1", python = ">=3.9", '
        "markers = \"sys_platform == 'win32' or os_name == 'nt'\"}"
    ),
    "alternatives": (
        'a = [{version = ">=1", python = "<3.11"}, '
        '{version = ">=2", markers = "sys_platform != \'win32\'"}]'
    ),
    "platform": 'a = {version = ">=1", platform = "linux || darwin"}',
    "optional": 'a = {version = "^0.0.3", python = "~3.9", optional = true}' + _X,
    "optional-alternatives": (
        'a = [{version = ">=1", python = "<3.11", optional = true}, '
        '{version = ">=2", python = ">=3.11", optional = true}]' + _X
    ),
    "git-rev": f'a = {{{_GIT}, rev = "abc123"}}',
    "git-tag": f'a = {{{_GIT}, tag = "v1.0"}}',
    "git-branch": f'a = {{{_GIT}, branch = "main"}}',
    "git-subdirectory": f'a = {{{_GIT}, rev = "abc", subdirectory = "sub"}}',
    "git-ssh": 'a = {git = "git@github.com:x/a.git"}',
    "git-extras-python": f'a = {{{_GIT}, extras = ["e2", "e1"], python = ">=3.9"}}',
    "git-optional": f"a = {{{_GIT}, optional = true}}" + _X,
    "url-extras": 'a = {url = "https://x.org/a-1.0.tar.gz", extras = ["e"]}',
    "extras": 'a = {version = "^1.0", extras = ["sec", "Foo_Bar"]}',
}
#: id -> whole pyproject.toml: which table poetry-core builds the lists from.
_TABLES = {
    "project-extras-only": _PROJECT + _PG + _POETRY_DEPS,
    "project-extras-dynamic-deps": (
        _PROJECT + 'dynamic = ["dependencies"]\n' + _PG + _POETRY_DEPS
    ),
    "project-extra-empty": (
        _PROJECT + "[project.optional-dependencies]\npg = []\n" + _POETRY_DEPS
    ),
    "project-deps-declared-empty": (
        _PROJECT + "dependencies = []\n" + _PG + _POETRY_DEPS
    ),
}
#: Two or more of `markers`/`python`/`platform`: poetry-core simplifies
#: and reorders the joined marker; Pitloom's is equivalent.
_EQUIVALENT = {
    "simplified": (
        'a = {version = ">=1", python = ">=3.9", '
        "markers = \"python_version >= '3.8' and sys_platform == 'linux'\"}"
    ),
    "reordered": (
        'a = {version = ">=1", platform = "win32", python = "^3.9", '
        "markers = \"os_name == 'nt'\"}"
    ),
}
_ENVIRONMENTS = [
    {
        "python_version": version,
        "python_full_version": f"{version}.0",
        "sys_platform": platform,
        "os_name": os_name,
    }
    for version in ("3.7", "3.8", "3.9", "3.10", "3.12", "4.0")
    for platform in ("linux", "win32")
    for os_name in ("nt", "posix")
]


def _toml(case: str) -> str:
    """The whole ``pyproject.toml`` of a :data:`_EXACT` or
    :data:`_EQUIVALENT` row."""
    return _HEAD + _DEPS + {**_EXACT, **_EQUIVALENT}[case] + "\n"


def _routes(
    tmp_path: Path, toml: str, packages: tuple[str, ...] = ("p",)
) -> list[list[str]]:
    """Each route's requirements of the project *toml* (its *packages*
    empty), normalised and sorted: the directory, then the sdist and the
    wheel poetry-core builds."""
    factory = pytest.importorskip("poetry.core.factory")
    sdist = pytest.importorskip("poetry.core.masonry.builders.sdist")
    wheel = pytest.importorskip("poetry.core.masonry.builders.wheel")
    project, dist = tmp_path / "project", tmp_path / "dist"
    for package in packages:
        (project / package).mkdir(parents=True, exist_ok=True)
        (project / package / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(toml, encoding="utf-8")
    poetry = factory.Factory().create_poetry(project)
    built_sdist = sdist.SdistBuilder(poetry).build(dist)
    built_wheel = dist / wheel.WheelBuilder.make_in(poetry, dist)
    return [
        sorted(normalize_dependency_specifier(dep) for dep in deps)
        for deps in (
            read_project(project)[0].dependencies,
            read_sdist(built_sdist).metadata.dependencies,
            read_wheel(built_wheel)[0].dependencies,
        )
    ]


@pytest.mark.parametrize(
    "toml",
    [_toml(case) for case in _EXACT] + list(_TABLES.values()),
    ids=[*_EXACT, *_TABLES],
)
def test_routes_list_what_poetry_core_writes(tmp_path: Path, toml: str) -> None:
    """The directory lists byte for byte (normalised) what poetry-core
    writes in the sdist's and the wheel's metadata."""
    directory, sdist, wheel = _routes(tmp_path, toml)
    assert directory == sdist == wheel
    assert directory


def test_real_world_cachy_routes_agree(tmp_path: Path) -> None:
    """The real cachy 0.3.0 ``pyproject.toml`` (legacy ``[tool.poetry]``,
    ``[tool.poetry.extras]``, no ``[build-system]``) through every route."""
    fixture = FIXTURES / "poetry" / "cachy-0.3.0"
    (tmp_path / "project").mkdir()
    for name in ("README.rst", "LICENSE"):
        shutil.copy(fixture / name, tmp_path / "project" / name)
    toml = (fixture / "pyproject.toml").read_text(encoding="utf-8")
    directory, sdist, wheel = _routes(tmp_path, toml, ("cachy", "tests"))
    assert directory == sdist == wheel
    assert len(directory) == 3


@pytest.mark.parametrize("case", list(_EQUIVALENT))
def test_joined_marker_equivalent(tmp_path: Path, case: str) -> None:
    """Limit: poetry-core simplifies and reorders a marker joined from two
    or more keys; Pitloom keeps poetry-core's key order, and the marker
    selects the same environments."""
    directory, sdist, wheel = _routes(tmp_path, _toml(case))
    assert sdist == wheel
    ours, theirs = Requirement(directory[0]), Requirement(sdist[0])
    assert str(ours) != str(theirs)
    assert (ours.name, ours.specifier) == (theirs.name, theirs.specifier)
    assert isinstance(ours.marker, Marker) and isinstance(theirs.marker, Marker)
    for env in _ENVIRONMENTS:
        assert ours.marker.evaluate(env) == theirs.marker.evaluate(env), env


@pytest.mark.parametrize(
    ("constraint", "reason"),
    [
        ({"path": "../a"}, "a local path source is not portable"),
        ({"file": "a.whl", "version": "1"}, "a local file source is not portable"),
        ({"version": 3}, "not convertible to PEP 508"),
        ("", "not convertible to PEP 508"),
        ({"version": "1", "python": "py3"}, "not convertible to PEP 508"),
        ({"version": "1", "markers": ["os_name == 'nt'"]}, "expected a string"),
        ({"version": "1", "markers": "os_name =="}, "not convertible to PEP 508"),
        ({"git": ""}, "not convertible to PEP 508"),
    ],
    ids=[
        "path",
        "file",
        "version-type",
        "version-empty",
        "python",
        "markers-type",
        "markers-invalid",
        "git-empty",
    ],
)
def test_unconvertible_skipped_with_warning(
    constraint: Any, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert poetry_requirement("a", constraint) is None
    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith("Skipping dependency 'a' (Poetry): ")
    assert reason in caplog.messages[0]


def test_unconvertible_quiet(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert poetry_requirement("a", {"path": "."}, quiet=True) is None
        assert poetry_requirement("a", {"version": 3}, quiet=True) is None
    assert not caplog.records


def test_deeply_nested_markers_refused(caplog: pytest.LogCaptureFixture) -> None:
    """The ``markers`` text goes through the shared nesting cap."""
    markers = "(" * 100 + "os_name == 'nt'" + ")" * 100
    with caplog.at_level(logging.WARNING):
        assert poetry_requirement("a", {"version": "1", "markers": markers}) is None
    assert "marker-nesting" in caplog.text
    assert "Skipping dependency 'a' (Poetry)" in caplog.text


@pytest.fixture(name="fresh_core")
def _fresh_core() -> Iterator[None]:
    """poetry-core's functions looked up afresh, and again after."""
    _poetry_core.cache_clear()
    yield
    _poetry_core.cache_clear()


@pytest.mark.usefixtures("fresh_core")
def test_poetry_core_internals_drift_guard() -> None:
    """Drift guard: the poetry-core internals the conversion calls (no
    upper version bound) are the ones this module imports, and they
    convert one table of every key they handle; a release that moves one
    fails here (at import, or on the result), not quietly at run time."""
    assert _poetry_core() == (
        Factory.create_dependency,
        parse_version_constraint,
        parse_generic_constraint,
        create_nested_marker,
        parse_marker,
    )
    assert isinstance(Dependency.__dict__["base_pep_508_name"], property)
    table = {
        "version": "^1.2",
        "extras": ["B", "a"],
        "python": "~3.9",
        "platform": "linux",
        "markers": "os_name == 'posix'",
    }
    assert poetry_requirement("Foo_Bar", table) == (
        'foo-bar[a,b]<2.0,>=1.2; (os_name == "posix" and python_version == "3.9")'
        ' and sys_platform == "linux"'
    )


@pytest.mark.usefixtures("fresh_core")
@pytest.mark.parametrize("moved", ["module", "attribute"])
def test_moved_poetry_core_internal_skips_with_one_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, moved: str
) -> None:
    """A poetry-core release that moves a module or attribute the
    conversion uses: every Poetry table skipped, one ``WARNING:``, no
    crash."""
    if moved == "module":
        monkeypatch.setitem(sys.modules, "poetry.core.factory", None)
    else:
        monkeypatch.delattr(Dependency, "base_pep_508_name")
    with caplog.at_level(logging.WARNING):
        assert poetry_requirement("a", "^1") is None
        assert poetry_requirement("b", {"version": "1"}) is None
    (line,) = caplog.messages
    assert line.startswith("poetry-core: API not found (")
