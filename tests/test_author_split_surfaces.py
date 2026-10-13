# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One author reading on every surface, by field kind.

A free-text author field (``setup.cfg`` ``author``, ``setup.py``
``setup(author=...)``, core-metadata ``Author`` in a wheel or sdist
``PKG-INFO``, a dependency's installed or PyPI record) is split on ``,`` /
``and`` with one ``WARNING:``; a structured one-entry-per-author table
(``[project].authors``, Poetry ``authors``, a quoted ``Author-email`` display
name) never is. ``embed-wheel`` warns only when the wheel's authors are used.

See also: tests/test_author_surfaces.py (order and assembly on every route),
tests/extract/project/test_setuptools_build_parity.py (the real setuptools
build drift guard).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3._document_deployed import build_deployed
from pitloom.assemble.spdx3.deps_originator import _resolve_author_or_maintainer
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_originator
from pitloom.assemble.spdx3.document import build
from pitloom.core.config import PitloomConfig
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.embed import embed_wheel_sbom
from pitloom.extract.authors import dependency_author_splits
from pitloom.extract.project import read_project
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel
from tests._author_routes import CREATED, hook_sbom, isolate, write_wheel
from tests.assemble.conftest import _FakeMetadata, _make_sdist

_SPLIT_MARK = "names on ',' / 'and'"
#: Reads (author, author_email) through one surface: its authors.
_Surface = Callable[[Path, str, str | None], list[dict[str, str]]]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _headers(author: str, email_: str | None) -> str:
    text = f"Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nAuthor: {author}\n"
    return text + (f"Author-email: {email_}\n" if email_ else "")


def _read_dir(tmp_path: Path) -> list[dict[str, str]]:
    return read_project(
        tmp_path, include_locked_dependencies=False, include_installed_metadata=False
    )[0].authors


def _setup_cfg(tmp_path: Path, author: str, email_: str | None) -> Any:
    extra = f"author_email = {email_}\n" if email_ else ""
    (tmp_path / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\nauthor = {author}\n{extra}",
        encoding="utf-8",
    )
    return _read_dir(tmp_path)


def _setup_py(tmp_path: Path, author: str, email_: str | None) -> Any:
    extra = f", author_email={email_!r}" if email_ else ""
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\n"
        f"setup(name='demo', version='1.0', author={author!r}{extra})\n",
        encoding="utf-8",
    )
    return _read_dir(tmp_path)


def _wheel(tmp_path: Path, author: str, email_: str | None) -> Any:
    return read_wheel(write_wheel(tmp_path, _headers(author, email_)))[0].authors


def _sdist(tmp_path: Path, author: str, email_: str | None) -> Any:
    members: dict[str, bytes | None] = {
        "PKG-INFO": _headers(author, email_).encode(),
        "pyproject.toml": None,
    }
    return read_sdist(_make_sdist(tmp_path, members=members)).metadata.authors


def _as_dicts(pairs: list[tuple[str | None, str | None]]) -> list[dict[str, str]]:
    return [
        {k: v for k, v in (("name", name), ("email", addr)) if v}
        for name, addr in pairs
    ]


def _dep_installed(_tmp: Path, author: str, email_: str | None) -> Any:
    fields = {"Author": author, **({"Author-email": email_} if email_ else {})}
    with dependency_author_splits():
        return _as_dicts(_resolve_author_or_maintainer(_FakeMetadata(fields), "dep"))


def _dep_pypi(_tmp: Path, author: str, email_: str | None) -> Any:
    with dependency_author_splits():
        info = {"author": author, "author_email": email_}
        return _as_dicts(_extract_pypi_originator(info, "dep"))


_SURFACES: dict[str, _Surface] = {
    "setup-cfg": _setup_cfg,
    "setup-py": _setup_py,
    "wheel-metadata": _wheel,
    "sdist-pkg-info": _sdist,
    "dependency-installed": _dep_installed,
    "dependency-pypi": _dep_pypi,
}

_ANN, _BOB = {"name": "Ann Lee"}, {"name": "Bob Ray"}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize(
    ("author", "email_", "expected"),
    [
        ("Ann Lee, Bob Ray", "a@x.org", [_ANN, _BOB, {"email": "a@x.org"}]),
        ("Ann Lee and Bob Ray", None, [_ANN, _BOB]),
        (
            "Ann Lee, Bob Ray",
            "a@x.org, b@x.org",
            [{"email": "a@x.org"}, {"email": "b@x.org"}, _ANN, _BOB],
        ),
        ("Ann Lee", "a@x.org", [{"name": "Ann Lee", "email": "a@x.org"}]),
        # the group test is per comma-separated part
        (
            "Ann Lee, Bob Ray and others",
            None,
            [_ANN, {"name": "Bob Ray and others"}],
        ),
    ],
    ids=["list-one-address", "and", "list-two-addresses", "one-author", "group"],
)
def test_free_text_author_same_on_every_surface(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    surface: str,
    author: str,
    email_: str | None,
    expected: list[dict[str, str]],
) -> None:
    """The same ``author``/``author_email`` gives the same authors on every
    surface, and one split warning exactly when the names were split."""
    with caplog.at_level(logging.WARNING):
        assert _SURFACES[surface](tmp_path, author, email_) == expected
    splits = [m for m in caplog.messages if _SPLIT_MARK in m]
    assert len(splits) == (0 if len(expected) == 1 else 1)


_STRUCTURED_PEP621 = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0"
authors = [{name = "Doe, Jane", email = "j@x.org"}, {name = "Lee, Ann"}]
"""
_STRUCTURED_POETRY = """\
[tool.poetry]
name = "demo"
version = "1.0"
description = "d"
authors = ["Doe, Jane <j@x.org>", "Lee, Ann"]
"""
_WHOLE = [{"name": "Doe, Jane", "email": "j@x.org"}, {"name": "Lee, Ann"}]


def _hook(project: Path) -> list[dict[str, str]]:
    """The main package's ``originatedBy`` Agents in the hook's SBOM, as
    authors."""
    graph = json.loads(hook_sbom(project))["@graph"]
    by_id = {e.get("spdxId"): e for e in graph}
    main = next(e for e in graph if e.get("name") == "demo" and "originatedBy" in e)
    authors = []
    for agent in (by_id[i] for i in main["originatedBy"]):
        emails = [
            x["identifier"]
            for x in agent.get("externalIdentifier", [])
            if x["externalIdentifierType"] == "email"
        ]
        authors.append(
            {"name": agent["name"], **({"email": emails[0]} if emails else {})}
        )
    return authors


def _originator_agents(authors: list[dict[str, str]]) -> list[tuple[str, str]]:
    """``(type, name)`` of each ``originatedBy`` Agent of *authors*."""
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0", authors=authors),
        creation_metadata=CREATED,
    )
    graph = json.loads(build(doc, offline=True).to_json(pretty=False))["@graph"]
    by_id = {e.get("spdxId"): e for e in graph}
    main = next(e for e in graph if e.get("name") == "demo" and "originatedBy" in e)
    return [(by_id[i]["type"], by_id[i]["name"]) for i in main["originatedBy"]]


@pytest.mark.parametrize(
    "group", ["Jane and others", "J. Smith et al."], ids=["and-others", "et-al"]
)
def test_contributor_group_same_agents_on_table_and_free_text(
    tmp_path: Path, group: str
) -> None:
    """One contributor-group string gives one Organization whether it is a
    ``[project].authors`` entry or a free-text ``author``."""
    table, free = tmp_path / "table", tmp_path / "free"
    table.mkdir()
    free.mkdir()
    (table / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "1.0"\n'
        f'authors = [{{name = "{group}"}}]\n',
        encoding="utf-8",
    )
    agents = [_originator_agents(_read_dir(table))]
    agents.append(_originator_agents(_setup_cfg(free, group, None)))
    assert agents == [[("Organization", group)]] * 2


@pytest.mark.parametrize(
    ("pyproject", "read"),
    [
        (_STRUCTURED_PEP621, _read_dir),
        (_STRUCTURED_PEP621, _hook),
        (_STRUCTURED_POETRY, _read_dir),
    ],
    ids=["pep621-directory", "pep621-hatchling-hook", "poetry-directory"],
)
def test_structured_entries_never_split(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    pyproject: str,
    read: Callable[[Path], list[dict[str, str]]],
) -> None:
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert read(tmp_path) == _WHOLE
    assert not [m for m in caplog.messages if _SPLIT_MARK in m]


@pytest.mark.parametrize(
    ("headers", "expected", "warned"),
    [
        # hatchling, flit, setuptools, pdm, pyproject-metadata: one quoted name
        (
            'Author-email: "Doe, Jane" <j@x.org>\n',
            [{"name": "Doe, Jane", "email": "j@x.org"}],
            False,
        ),
        # the same backends, a name-only entry: joined into free text
        ("Author: Lee, Ann\n", [{"name": "Lee"}, {"name": "Ann"}], True),
        # poetry-core: the first author, name and address apart
        (
            "Author: Doe, Jane\nAuthor-email: j@x.org\n",
            [{"name": "Doe"}, {"name": "Jane"}, {"email": "j@x.org"}],
            True,
        ),
        # hatchling, two name-only entries: the group stays a part of its
        # own, never one Organization of every name
        (
            "Author: Lee, Ann, Bob and others\n",
            [{"name": "Lee"}, {"name": "Ann"}, {"name": "Bob and others"}],
            True,
        ),
    ],
    ids=[
        "quoted-address-whole",
        "name-only-entry-limit",
        "poetry-core-limit",
        "name-only-group-limit",
    ],
)
def test_wheel_of_structured_entry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    headers: str,
    expected: list[dict[str, str]],
    warned: bool,
) -> None:
    """What backends write for ``{name = "Doe, Jane", ...}``: a quoted
    ``Author-email`` name stays whole; a name a backend writes into the
    free-text ``Author`` is split (the inherent limit; ``--project-dir``
    or an sdist with ``pyproject.toml`` has the declared names)."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n" + headers
    with caplog.at_level(logging.WARNING):
        assert read_wheel(write_wheel(tmp_path, text))[0].authors == expected
    assert len([m for m in caplog.messages if _SPLIT_MARK in m]) == int(warned)


def _stub_split_authors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every installed dependency *x* has the authors ``x One, x Two``."""
    monkeypatch.setattr(
        deps_installed,
        "get_pkg_metadata",
        lambda name: _FakeMetadata({"Author": f"{name} One, {name} Two"}),
    )


def _split_document(_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _stub_split_authors(monkeypatch)
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0", dependencies=["a", "b"]),
        creation_metadata=CREATED,
    )
    return build(doc, offline=True)


def _split_environment(_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    _stub_split_authors(monkeypatch)
    tree = [
        {"package": {"key": k, "package_name": k, "installed_version": "1"}}
        for k in ("a", "b")
    ]
    doc = DocumentModel(
        project=ProjectMetadata(name="env", version="1"), creation_metadata=CREATED
    )
    return build_deployed(doc, tree, offline=True)


@pytest.mark.parametrize(
    "run", [_split_document, _split_environment], ids=["project", "environment"]
)
def test_dependency_splits_warn_once_per_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    run: Callable[[Path, pytest.MonkeyPatch], Any],
) -> None:
    with caplog.at_level(logging.WARNING):
        run(tmp_path, monkeypatch)
    (line,) = [m for m in caplog.messages if _SPLIT_MARK in m]
    assert line.startswith("AUTHOR='a One, a Two': split into 2 names")
    assert "2 dependencies split in all" in line


_PROJECT_WITH_AUTHORS = {
    "pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n'
    'authors = [{name = "Ann Lee"}, {name = "Bob Ray"}]\n'
}
#: A project whose own free-text author splits.
_SPLIT_SETUP_CFG = {
    "setup.cfg": "[metadata]\nname = demo\nversion = 1.0\nauthor = Ann Lee, Bob Ray\n"
}


def _embed(
    tmp_path: Path,
    project: dict[str, str] | None,
    *,
    cli: bool = False,
    config: bool = False,
) -> None:
    """Embed into a wheel whose ``Author`` splits, from *project* (file name
    to text) if given; *config*: an explicit config replaces the
    project's."""
    wheel = write_wheel(tmp_path, _headers("Ann Lee, Bob Ray", None))
    project_dir = None
    if project is not None:
        project_dir = tmp_path / "project"
        (project_dir / "demo").mkdir(parents=True)
        (project_dir / "demo" / "__init__.py").write_text("", encoding="utf-8")
        for name, text in project.items():
            (project_dir / name).write_text(text, encoding="utf-8")
    config_file = tmp_path / "config.toml"
    config_file.write_text("[tool.pitloom]\n", encoding="utf-8")
    if not cli:
        embed_wheel_sbom(
            wheel,
            project_dir=project_dir,
            creation_metadata=CREATED,
            pitloom_config=PitloomConfig() if config else None,
        )
        return
    argv = ["loom", "embed-wheel", str(wheel)]
    argv += [] if project_dir is None else ["--project-dir", str(project_dir)]
    argv += ["--config", str(config_file)] if config else []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", argv)
        assert __main__.main() == 0


_NO_AUTHORS = {"pyproject.toml": '[project]\nname = "demo"\nversion = "1.0"\n'}
_OTHER = {
    "pyproject.toml": _PROJECT_WITH_AUTHORS["pyproject.toml"].replace("demo", "x")
}


@pytest.mark.parametrize(
    ("project", "cli", "config", "warnings"),
    [
        (_PROJECT_WITH_AUTHORS, False, False, 0),
        (_PROJECT_WITH_AUTHORS, True, False, 0),
        (_NO_AUTHORS, False, False, 1),
        (_OTHER, False, False, 1),
        (None, False, False, 1),
        (None, True, False, 1),
        # the project's own authors split: one warning, config given or not
        (_SPLIT_SETUP_CFG, False, False, 1),
        (_SPLIT_SETUP_CFG, False, True, 1),
        (_SPLIT_SETUP_CFG, True, False, 1),
        (_SPLIT_SETUP_CFG, True, True, 1),
    ],
    ids=[
        "lib-replaced",
        "cli-replaced",
        "project-without-authors",
        "other-project",
        "lib-standalone",
        "cli-standalone",
        "lib-project-split",
        "lib-project-split-config",
        "cli-project-split",
        "cli-project-split-config",
    ],
)
def test_embed_wheel_warns_only_when_wheel_authors_used(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    project: dict[str, str] | None,
    cli: bool,
    config: bool,
    warnings: int,
) -> None:
    """A split is warned about once, by the read whose authors are used:
    the wheel's, or the project's that replace them."""
    _embed(tmp_path, project, cli=cli, config=config)
    err = capsys.readouterr().err
    assert err.count(_SPLIT_MARK) == warnings


def test_embed_wheel_batch_warns_project_split_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every wheel of a batch adopts the project's authors; their split is
    warned about once for the batch."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "setup.cfg").write_text(
        _SPLIT_SETUP_CFG["setup.cfg"], encoding="utf-8"
    )
    wheels = [
        str(write_wheel(tmp_path, _headers("Ann Lee, Bob Ray", None), version))
        for version in ("1.0", "2.0")
    ]
    argv = ["loom", "embed-wheel", *wheels, "--project-dir", str(project_dir)]
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "argv", argv)
        assert __main__.main() == 0
    assert capsys.readouterr().err.count(_SPLIT_MARK) == 1


def test_embed_external_sbom_does_not_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An embedded external SBOM does not use the wheel's authors."""
    wheel = write_wheel(tmp_path, _headers("Ann Lee, Bob Ray", None))
    sbom = tmp_path / "sbom.spdx3.json"
    sbom.write_text(
        generate_wheel_sbom(wheel, creation_metadata=CREATED), encoding="utf-8"
    )
    capsys.readouterr()
    embed_wheel_sbom(wheel, sbom_path=sbom)
    assert _SPLIT_MARK not in capsys.readouterr().err
