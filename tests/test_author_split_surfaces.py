# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One author reading on every surface, by field kind.

A free-text author field (``setup.cfg`` ``author``, ``setup.py``
``setup(author=...)``, core-metadata ``Author`` in a wheel or sdist
``PKG-INFO``, a dependency's installed or PyPI record) is split on ``,`` /
``;`` / ``and`` with one ``WARNING:``; its address field on ``,`` / ``;``
only. A structured one-entry-per-author table (``[project].authors``,
Poetry ``authors``, a quoted ``Author-email`` display name, an unquoted
one as backends write ``Ann and Bob <t@x.org>``) never is.

See also: tests/test_author_split_warnings.py (when a split is warned
about), tests/test_author_surfaces.py (order and assembly on every route),
tests/extract/project/test_setuptools_build_parity.py (the real setuptools
build drift guard).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble.spdx3.deps_originator import _resolve_author_or_maintainer
from pitloom.assemble.spdx3.deps_pypi import _extract_pypi_originator
from pitloom.assemble.spdx3.document import build
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.extract.authors import dependency_author_splits
from pitloom.extract.project import read_project
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel
from tests._author_routes import (
    CREATED,
    SPLIT_MARK,
    core_headers,
    hook_sbom,
    isolate,
    write_wheel,
)
from tests.assemble.conftest import _FakeMetadata, _make_sdist

#: Reads (author, author_email) through one surface: its authors.
_Surface = Callable[[Path, str | None, str | None], list[dict[str, str]]]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _read_dir(tmp_path: Path) -> list[dict[str, str]]:
    return read_project(
        tmp_path, include_locked_dependencies=False, include_installed_metadata=False
    )[0].authors


def _setup_cfg(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    fields = {"author": author, "author_email": email_}
    stated = "".join(f"{k} = {v}\n" for k, v in fields.items() if v is not None)
    (tmp_path / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\n{stated}", encoding="utf-8"
    )
    return _read_dir(tmp_path)


def _setup_py(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    fields = {"author": author, "author_email": email_}
    stated = "".join(f", {k}={v!r}" for k, v in fields.items() if v is not None)
    (tmp_path / "setup.py").write_text(
        f"from setuptools import setup\nsetup(name='demo', version='1.0'{stated})\n",
        encoding="utf-8",
    )
    return _read_dir(tmp_path)


def _wheel(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    return read_wheel(write_wheel(tmp_path, core_headers(author, email_)))[0].authors


def _sdist(tmp_path: Path, author: str | None, email_: str | None) -> Any:
    members: dict[str, bytes | None] = {
        "PKG-INFO": core_headers(author, email_).encode(),
        "pyproject.toml": None,
    }
    return read_sdist(_make_sdist(tmp_path, members=members)).metadata.authors


def _as_dicts(pairs: list[tuple[str | None, str | None]]) -> list[dict[str, str]]:
    return [
        {k: v for k, v in (("name", name), ("email", addr)) if v}
        for name, addr in pairs
    ]


def _dep_installed(_tmp: Path, author: str | None, email_: str | None) -> Any:
    named = {"Author": author, "Author-email": email_}
    fields = {k: v for k, v in named.items() if v is not None}
    with dependency_author_splits():
        return _as_dicts(_resolve_author_or_maintainer(_FakeMetadata(fields), "dep"))


def _dep_pypi(_tmp: Path, author: str | None, email_: str | None) -> Any:
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
_ANN_AND_BOB = {"name": "Ann and Bob", "email": "t@x.org"}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize(
    ("author", "email_", "expected"),
    [
        ("Ann Lee, Bob Ray", "a@x.org", [_ANN, _BOB, {"email": "a@x.org"}]),
        ("Ann Lee and Bob Ray", None, [_ANN, _BOB]),
        # documented limit: names and addresses are never paired by
        # position, which a reordered or partial field would mis-pair
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
        # the address field is split on ',' as the name field: Doe is kept
        # (never on 'and': see test_and_in_address_entry_one_author...)
        (
            "Ann Lee",
            "Doe, Jane <j@x.org>",
            [{"name": "Doe"}, {"name": "Jane", "email": "j@x.org"}, _ANN],
        ),
        ('"Lee, Ann"', None, [{"name": "Lee, Ann"}]),
    ],
    ids=[
        "list-one-address",
        "and",
        "two-names-two-addresses-limit",
        "one-author",
        "group",
        "unquoted-comma-address",
        "quoted-name",
    ],
)
def test_free_text_author_same_on_every_surface(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    surface: str,
    author: str | None,
    email_: str | None,
    expected: list[dict[str, str]],
) -> None:
    """The same ``author``/``author_email`` gives the same authors on every
    surface, and one split warning exactly when the names were split."""
    with caplog.at_level(logging.WARNING):
        assert _SURFACES[surface](tmp_path, author, email_) == expected
    splits = [m for m in caplog.messages if SPLIT_MARK in m]
    assert len(splits) == (0 if len(expected) == 1 else 1)


_STRUCTURED_PEP621 = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0"
authors = [
    {name = "Doe, Jane", email = "j@x.org"},
    {name = "Lee, Ann"},
    {name = "Ann and Bob", email = "t@x.org"},
]
"""
#: One structured author whose name holds ``and``: backends write it
#: unquoted, ``Author-email: Ann and Bob <t@x.org>``.
_ONE_AND_PEP621 = _STRUCTURED_PEP621.replace(
    """    {name = "Doe, Jane", email = "j@x.org"},
    {name = "Lee, Ann"},
""",
    "",
)
_STRUCTURED_POETRY = """\
[tool.poetry]
name = "demo"
version = "1.0"
description = "d"
authors = ["Doe, Jane <j@x.org>", "Lee, Ann", "Ann and Bob <t@x.org>"]
"""
_WHOLE = [
    {"name": "Doe, Jane", "email": "j@x.org"},
    {"name": "Lee, Ann"},
    _ANN_AND_BOB,
]


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
    assert not [m for m in caplog.messages if SPLIT_MARK in m]


def _structured(read: Callable[[Path], list[dict[str, str]]]) -> _Surface:
    """*read* of a project declaring only :data:`_ONE_AND_PEP621`."""

    def surface(tmp_path: Path, _author: str | None, _email: str | None) -> Any:
        (tmp_path / "pyproject.toml").write_text(_ONE_AND_PEP621, encoding="utf-8")
        return read(tmp_path)

    return surface


_ONE_AND_SURFACES = {
    **_SURFACES,
    "pep621-directory": _structured(_read_dir),
    "pep621-hatchling-hook": _structured(_hook),
}


@pytest.mark.parametrize("surface", sorted(_ONE_AND_SURFACES))
def test_and_in_address_entry_one_author_on_every_surface(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, surface: str
) -> None:
    """``{name = "Ann and Bob", email = "t@x.org"}`` is one author on the
    directory and hook routes (structured) and on every route reading the
    ``Author-email: Ann and Bob <t@x.org>`` backends write for it, with no
    split warning."""
    read = _ONE_AND_SURFACES[surface]
    with caplog.at_level(logging.WARNING):
        assert read(tmp_path, None, "Ann and Bob <t@x.org>") == [_ANN_AND_BOB]
    assert not [m for m in caplog.messages if SPLIT_MARK in m]


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
        # the same backends leave a name holding "and" unquoted (Hatchling
        # 1.32, setuptools 84, flit_core 4, pdm 2.4): an address entry is
        # never split on "and"
        ("Author-email: Ann and Bob <t@x.org>\n", [_ANN_AND_BOB], False),
    ],
    ids=[
        "quoted-address-whole",
        "name-only-entry-limit",
        "poetry-core-limit",
        "name-only-group-limit",
        "and-in-address-entry-whole",
    ],
)
def test_wheel_of_structured_entry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    headers: str,
    expected: list[dict[str, str]],
    warned: bool,
) -> None:
    """What backends write for ``{name = "Doe, Jane", ...}``: an
    ``Author-email`` entry, quoted or with ``and``, stays whole; a name a
    backend writes into the free-text ``Author`` is split (the inherent
    limit; ``--project-dir`` or an sdist with ``pyproject.toml`` has the
    declared names)."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n" + headers
    with caplog.at_level(logging.WARNING):
        assert read_wheel(write_wheel(tmp_path, text))[0].authors == expected
    assert len([m for m in caplog.messages if SPLIT_MARK in m]) == int(warned)
