# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The main package's authors and dependency edges on every route:
directory, sdist (with ``PKG-INFO``, with an explicit config,
``pyproject.toml`` only), bare wheel, ``embed-wheel --project-dir`` (CLI,
as the GitHub Action runs it, and library) and the Hatchling build hook
(its real ``initialize()``).

Each names every author in ``originatedBy``. A route with the project's
``pyproject.toml`` keeps the declared order; a bare wheel's ``METADATA``
cannot, and lists the authors with an address first. Every route gives
the same dependency edges, an extra's self-reference expanded.

See also: tests/assemble/test_main_authors.py (assembly),
tests/extract/test_core_metadata_authors.py (the ``METADATA`` parser),
tests/test_copyright_surfaces.py (the copyright text, never the authors').
"""

# pylint: disable=missing-function-docstring
# pylint: disable=protected-access

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom._embed_build_sbom import _adopt_project_authors
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.project import ProjectMetadata
from pitloom.embed import embed_wheel_sbom
from tests._author_routes import CREATED, hook_sbom, isolate, write_wheel
from tests.assemble.conftest import _make_sdist

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"
authors = [
  {name = "Ann", email = "ann@example.com"},
  {name = "Bob"},
  {name = "Cee", email = "cee@example.com"},
  {name = "Dan"},
  {email = "eve@example.com"},
]
dependencies = ["alpha>=1"]

[project.optional-dependencies]
dev = ["beta"]
all = ["demo[dev]"]
"""
#: What hatchling 1.32 writes for that project (sdist PKG-INFO and wheel
#: METADATA alike): addressed authors in Author-email, the others in Author;
#: the self-reference expanded.
_CORE_METADATA = (
    "Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\nAuthor: Bob, Dan\n"
    "Author-email: Ann <ann@example.com>, Cee <cee@example.com>, eve@example.com\n"
    "Requires-Dist: alpha>=1\nRequires-Dist: beta; extra == 'all'\n"
    "Requires-Dist: beta; extra == 'dev'\nProvides-Extra: all\n"
    "Provides-Extra: dev\n"
)
#: An author with an address and no name is named by the address.
_DECLARED = ["Ann", "Bob", "Cee", "Dan", "eve@example.com"]
_WHEEL_ORDER = ["Ann", "Cee", "eve@example.com", "Bob", "Dan"]
#: Builds a route's SBOM in a scratch directory.
_Route = Callable[[Path, pytest.MonkeyPatch], str]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return project


def _wheel(tmp_path: Path, metadata: str = _CORE_METADATA) -> Path:
    return write_wheel(tmp_path, metadata, "1.0.0")


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _directory(tmp_path: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(
        _project(tmp_path), creation_metadata=CREATED, offline=True
    )


def _sdist(
    members: dict[str, bytes | None], *, explicit_config: bool = False
) -> _Route:
    def run(tmp_path: Path, _mp: pytest.MonkeyPatch) -> str:
        sdist = _make_sdist(tmp_path, members=members)
        return generate_project_sbom(
            sdist,
            creation_metadata=CREATED,
            offline=True,
            pitloom_config=PitloomConfig() if explicit_config else None,
        )

    return run


_PKG_INFO_AND_PYPROJECT: dict[str, bytes | None] = {
    "PKG-INFO": _CORE_METADATA.encode(),
    "pyproject.toml": _PYPROJECT.encode(),
}


def _bare_wheel(tmp_path: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_wheel_sbom(_wheel(tmp_path), creation_metadata=CREATED)


def _cli_embed(tmp_path: Path, mp: pytest.MonkeyPatch) -> str:
    wheel, project = _wheel(tmp_path), _project(tmp_path)
    mp.setattr(
        sys, "argv", ["loom", "embed-wheel", str(wheel), "--project-dir", str(project)]
    )
    assert __main__.main() == 0
    return _embedded(wheel)


def _lib_embed(tmp_path: Path, _mp: pytest.MonkeyPatch) -> str:
    wheel = embed_wheel_sbom(
        _wheel(tmp_path), project_dir=_project(tmp_path), creation_metadata=CREATED
    )[0]
    return _embedded(wheel)


def _hook(tmp_path: Path, _mp: pytest.MonkeyPatch) -> str:
    return hook_sbom(_project(tmp_path))


#: route -> (build the SBOM, its author order)
_ROUTES: dict[str, tuple[_Route, list[str]]] = {
    "directory": (_directory, _DECLARED),
    "sdist": (_sdist(_PKG_INFO_AND_PYPROJECT), _DECLARED),
    "sdist-explicit-config": (
        _sdist(_PKG_INFO_AND_PYPROJECT, explicit_config=True),
        _DECLARED,
    ),
    "sdist-pyproject-only": (
        _sdist({"PKG-INFO": None, "pyproject.toml": _PYPROJECT.encode()}),
        _DECLARED,
    ),
    "bare-wheel": (_bare_wheel, _WHEEL_ORDER),
    "cli-embed-wheel-project-dir": (_cli_embed, _DECLARED),
    "lib-embed-wheel-project-dir": (_lib_embed, _DECLARED),
    "hatchling-hook": (_hook, _DECLARED),
}


def _main_authors(sbom: str, package: str = "demo") -> list[str]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    by_id = {e.get("spdxId"): e for e in graph}
    main = next(
        e for e in graph if e["type"] == "software_Package" and e["name"] == package
    )
    return [by_id[i]["name"] for i in main.get("originatedBy", [])]


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_authors_on_every_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    run, order = _ROUTES[route]
    assert _main_authors(run(tmp_path, monkeypatch)) == order


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_dependency_edges_on_every_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    graph: list[dict[str, Any]] = json.loads(_ROUTES[route][0](tmp_path, monkeypatch))[
        "@graph"
    ]
    names = {e.get("spdxId"): e.get("name") for e in graph}
    edges = {
        (names[e["to"][0]], e["relationshipType"], e.get("scope"), e.get("comment"))
        for e in graph
        if e.get("relationshipType") in {"dependsOn", "hasOptionalDependency"}
        and names[e["from"]] == "demo"
    }
    assert edges == {
        ("alpha", "dependsOn", "runtime", None),
        ("beta", "hasOptionalDependency", None, "extras: all, dev"),
    }


@pytest.mark.parametrize(
    "header", ["dee@example.com", "Unknown <dee@example.com>"], ids=["bare", "unknown"]
)
def test_bare_wheel_email_only_author(tmp_path: Path, header: str) -> None:
    """An author with an address and no name (or pdm-backend's ``Unknown``)
    is named by the address."""
    wheel = _wheel(
        tmp_path,
        f"Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\nAuthor-email: {header}\n",
    )
    sbom = generate_wheel_sbom(wheel, creation_metadata=CREATED)
    assert _main_authors(sbom) == ["dee@example.com"]


def test_embed_project_dir_without_metadata_keeps_wheel_authors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A project directory with no metadata to read (here: none at all,
    with the config given) leaves the wheel's authors, with one
    ``WARNING:`` saying so."""
    empty = tmp_path / "empty"
    empty.mkdir()
    wheel = embed_wheel_sbom(
        _wheel(tmp_path),
        project_dir=empty,
        pitloom_config=PitloomConfig(),
        creation_metadata=CREATED,
    )[0]
    assert _main_authors(_embedded(wheel)) == _WHEEL_ORDER
    err = capsys.readouterr().err
    assert err.count("authors from the wheel METADATA") == 1


@pytest.mark.parametrize(
    ("project_name", "wheel_name", "adopted"),
    [
        ("demo", "demo", True),
        ("foo-bar", "Foo_Bar", True),
        ("other", "demo", False),
    ],
    ids=["same", "spelling", "different"],
)
def test_embed_project_dir_adopts_authors_of_same_project_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    project_name: str,
    wheel_name: str,
    adopted: bool,
) -> None:
    """The project's authors replace the wheel's only when the project is
    the wheel's (names compared per PEP 503); otherwise one ``WARNING:``
    names both and the wheel's authors stay."""
    project = _project(tmp_path)
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        _PYPROJECT.replace('name = "demo"', f'name = "{project_name}"'),
        encoding="utf-8",
    )
    wheel = _wheel(
        tmp_path, _CORE_METADATA.replace("Name: demo", f"Name: {wheel_name}")
    )
    embed_wheel_sbom(wheel, project_dir=project, creation_metadata=CREATED)
    names = _main_authors(_embedded(wheel), wheel_name)
    assert names == (_DECLARED if adopted else _WHEEL_ORDER)
    err = capsys.readouterr().err
    assert err.count("is not the wheel's") == (0 if adopted else 1)


@pytest.mark.parametrize(
    ("pyproject", "adopted"),
    [(_PYPROJECT, True), ("[project\n", False)],
    ids=["adopted", "invalid-toml"],
)
def test_adopt_project_authors_with_provenance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pyproject: str, adopted: bool
) -> None:
    """Adopted authors carry the project's provenance; a ``pyproject.toml``
    that cannot be read leaves the wheel's, with one ``WARNING:``."""
    project = _project(tmp_path)
    (project / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    wheel_source = "Source: wheel METADATA"
    metadata = ProjectMetadata(
        name="demo", authors=[{"name": "W"}], provenance={"authors": wheel_source}
    )
    _adopt_project_authors(metadata, project)
    assert [a.get("name", a.get("email")) for a in metadata.authors] == (
        _DECLARED if adopted else ["W"]
    )
    assert metadata.provenance["authors"] == (
        "Source: pyproject.toml | Field: project.authors" if adopted else wheel_source
    )
    assert len(caplog.records) == (0 if adopted else 1)
