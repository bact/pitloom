# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One author reading on every surface, by field kind.

A free-text name field (``setup.cfg`` ``author``, ``setup.py``
``setup(author=...)``, core-metadata ``Author`` in a wheel or sdist
``PKG-INFO``, a dependency's installed or PyPI record) is one author unless
it holds several complete mailboxes, cut only next to them; its address field
is split on ``,`` / ``;`` only; a cut gets one ``WARNING:``. A structured
one-entry-per-author table (``[project].authors``, Poetry ``authors``, a
quoted ``Author-email`` display name, an unquoted one as backends write
``Ann and Bob <t@x.org>``) never is.

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

from pitloom.assemble.spdx3.document import build
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.extract.wheel import read_wheel
from tests._author_routes import (
    CREATED,
    ONE_AUTHOR_HINTS,
    ONE_AUTHOR_LINE,
    SPLIT_MARK,
    SURFACES,
    Surface,
    hook_sbom,
    isolate,
    one_author_lines,
    read_dir,
    write_wheel,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


_ANN = {"name": "Ann Lee"}
_ANN_AND_BOB = {"name": "Ann and Bob", "email": "t@x.org"}


@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize(
    ("author", "email_", "expected", "told"),
    [
        ("Ann Lee", "a@x.org", [{"name": "Ann Lee", "email": "a@x.org"}], ""),
        ("Sandra Anders", None, [{"name": "Sandra Anders"}], ""),
        ("Ann; Bob", None, [{"name": "Ann; Bob"}], "one"),
        ("Ann <a;b@x.org>", None, [{"name": "Ann", "email": "a;b@x.org"}], ""),
        # a group after an address: not one author
        (
            "Ann, Bob <b@x.org> et al.",
            None,
            [{"name": "Ann, Bob", "email": "b@x.org"}, {"name": "et al."}],
            "",
        ),
        # a free-text list in one Author is one author, and pairs with one
        # bare address as any one name does
        (
            "Ann Lee, Bob Ray",
            "a@x.org",
            [{"name": "Ann Lee, Bob Ray", "email": "a@x.org"}],
            "one",
        ),
        # documented limit: a name and addresses are never paired by
        # position, which a reordered or partial field would mis-pair
        (
            "Ann Lee, Bob Ray",
            "a@x.org, b@x.org",
            [{"email": "a@x.org"}, {"email": "b@x.org"}, {"name": "Ann Lee, Bob Ray"}],
            "one",
        ),
        # a contributor group joined to names is one author
        (
            "Ann Lee, Bob Ray and others",
            None,
            [{"name": "Ann Lee, Bob Ray and others"}],
            "one",
        ),
        # the address field is split on ',': Doe is kept, with a warning
        # (never on 'and': see test_and_in_address_entry_one_author...)
        (
            "Ann Lee",
            "Doe, Jane <j@x.org>",
            [{"name": "Doe"}, {"name": "Jane", "email": "j@x.org"}, _ANN],
            "split",
        ),
        ('"Lee, Ann"', None, [{"name": "Lee, Ann"}], ""),
        # the name before a sole <address> is held together
        (
            "Doe, Jane <j@x.org>",
            None,
            [{"name": "Doe, Jane", "email": "j@x.org"}],
            "one",
        ),
        # several complete mailboxes are cut after each closed >
        (
            "Ann <a@x.org>, Bob <b@x.org>",
            None,
            [{"name": "Ann", "email": "a@x.org"}, {"name": "Bob", "email": "b@x.org"}],
            "split",
        ),
    ],
    ids=[
        "one-author",
        "and-in-a-word",
        "semicolon",
        "semicolon-in-address",
        "group-after-address",
        "one-list-legacy-pair",
        "name-two-addresses-limit",
        "one-group",
        "unquoted-comma-address",
        "quoted-name",
        "one-comma-name-address",
        "two-mailboxes",
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_free_text_author_same_on_every_surface(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    surface: str,
    author: str | None,
    email_: str | None,
    expected: list[dict[str, str]],
    told: str,
) -> None:
    """The same ``author``/``author_email`` gives the same authors on every
    surface, one split warning exactly when a field was split, and one
    ``INFO:`` when a project's own name field holding ``,``, ``;`` or
    ``and`` was read as one author (never for a dependency)."""
    with caplog.at_level(logging.INFO):
        assert SURFACES[surface](tmp_path, author, email_) == expected
    splits = [m for m in caplog.messages if SPLIT_MARK in m]
    assert len(splits) == int(told == "split")
    hint = ONE_AUTHOR_HINTS.get(surface)
    one = [ONE_AUTHOR_LINE.format(repr(author), hint)]
    assert one_author_lines(caplog) == (
        one if told == "one" and hint is not None else []
    )


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
    agents = [_originator_agents(read_dir(table))]
    agents.append(_originator_agents(SURFACES["setup-cfg"](free, group, None)))
    assert agents == [[("Organization", group)]] * 2


@pytest.mark.parametrize(
    ("pyproject", "read"),
    [
        (_STRUCTURED_PEP621, read_dir),
        (_STRUCTURED_PEP621, _hook),
        (_STRUCTURED_POETRY, read_dir),
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


#: A project whose one structured author is name-only, ``NAME``.
_NAME_ONLY_PEP621 = _STRUCTURED_PEP621.partition("authors = [")[0] + (
    'authors = [{name = "NAME"}]\n'
)
_NAME_ONLY_POETRY = (
    _STRUCTURED_POETRY.partition("authors = [")[0] + 'authors = ["NAME"]\n'
)


def _structured(
    read: Callable[[Path], list[dict[str, str]]], pyproject: str
) -> Surface:
    """*read* of a project whose ``pyproject.toml`` is *pyproject*, its
    ``"NAME"`` the author asked for (a TOML string, escaped as JSON)."""

    def surface(tmp_path: Path, author: str | None, _email: str | None) -> Any:
        text = pyproject.replace('"NAME"', json.dumps(author or ""))
        (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
        return read(tmp_path)

    return surface


_ONE_AND_SURFACES = {
    **SURFACES,
    "pep621-directory": _structured(read_dir, _ONE_AND_PEP621),
    "pep621-hatchling-hook": _structured(_hook, _ONE_AND_PEP621),
}
_NAME_ONLY_SURFACES = {
    **SURFACES,
    "pep621-directory": _structured(read_dir, _NAME_ONLY_PEP621),
    "pep621-hatchling-hook": _structured(_hook, _NAME_ONLY_PEP621),
    "poetry-directory": _structured(read_dir, _NAME_ONLY_POETRY),
}


@pytest.mark.parametrize("surface", sorted(_NAME_ONLY_SURFACES))
@pytest.mark.parametrize(
    "name", ["Jane, Bob", "Ann and Bob", "Doe, Jane"], ids=["comma", "and", "doe"]
)
def test_one_name_field_one_author_on_every_surface(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, surface: str, name: str
) -> None:
    """One ``Author``/``author`` value, or one name-only structured entry,
    is one author named as written on every route, with no split warning;
    a project's own free-text value gets one ``INFO:`` that it may list
    several, a structured entry and a dependency none."""
    with caplog.at_level(logging.INFO):
        assert _NAME_ONLY_SURFACES[surface](tmp_path, name, None) == [{"name": name}]
    assert not [m for m in caplog.messages if SPLIT_MARK in m]
    hint = ONE_AUTHOR_HINTS.get(surface)
    one = [] if hint is None else [ONE_AUTHOR_LINE.format(repr(name), hint)]
    assert one_author_lines(caplog) == one


@pytest.mark.parametrize("surface", sorted(_NAME_ONLY_SURFACES))
@pytest.mark.parametrize(
    "name", ["Ann\n        Lee", "Ann\r\n\tLee"], ids=["folded", "crlf-tab"]
)
def test_folded_name_one_spaced_on_every_surface(
    tmp_path: Path, surface: str, name: str
) -> None:
    """Regression: a folded ``Author`` kept its newline and indent in the
    wheel's name (``Ann\\n        Lee``) while ``setup.cfg`` gave
    ``Ann\\nLee``; every route reads one name, each run of white space one
    space."""
    assert _NAME_ONLY_SURFACES[surface](tmp_path, name, None) == [{"name": "Ann Lee"}]


@pytest.mark.parametrize("surface", sorted(_ONE_AND_SURFACES))
def test_and_in_address_entry_one_author_on_every_surface(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, surface: str
) -> None:
    """``{name = "Ann and Bob", email = "t@x.org"}`` is one author on the
    directory and hook routes (structured) and on every route reading the
    ``Author-email: Ann and Bob <t@x.org>`` backends write for it, with no
    split warning and no one-author ``INFO:``."""
    read = _ONE_AND_SURFACES[surface]
    with caplog.at_level(logging.INFO):
        assert read(tmp_path, None, "Ann and Bob <t@x.org>") == [_ANN_AND_BOB]
    assert not [m for m in caplog.messages if SPLIT_MARK in m]
    assert not one_author_lines(caplog)


@pytest.mark.parametrize(
    ("headers", "expected", "warned"),
    [
        # hatchling, flit, setuptools, pdm, pyproject-metadata: one quoted name
        (
            'Author-email: "Doe, Jane" <j@x.org>\n',
            [{"name": "Doe, Jane", "email": "j@x.org"}],
            False,
        ),
        # the same backends write a name-only entry into Author, read whole
        ("Author: Lee, Ann\n", [{"name": "Lee, Ann"}], False),
        # poetry-core, the first author, name and address apart, paired
        # again
        (
            "Author: Doe, Jane\nAuthor-email: j@x.org\n",
            [{"name": "Doe, Jane", "email": "j@x.org"}],
            False,
        ),
        # limit: hatchling joins two name-only entries into one Author, read
        # as one author (an Organization, for the group)
        (
            "Author: Lee, Ann, Bob and others\n",
            [{"name": "Lee, Ann, Bob and others"}],
            False,
        ),
        # the same backends leave a name holding "and" unquoted (Hatchling
        # 1.32, setuptools 84, flit_core 4, pdm 2.4): an address entry is
        # never split on "and"
        ("Author-email: Ann and Bob <t@x.org>\n", [_ANN_AND_BOB], False),
    ],
    ids=[
        "quoted-address-whole",
        "one-name-only-entry",
        "one-poetry-core-pair",
        "two-name-only-entries-limit",
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
    ``Author-email`` entry, quoted or with ``and``, stays whole, and so does
    a name a backend writes into ``Author``; several name-only entries
    joined there are one author (the inherent limit; ``--project-dir`` or an
    sdist with ``pyproject.toml`` has the declared names)."""
    text = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n" + headers
    with caplog.at_level(logging.WARNING):
        assert read_wheel(write_wheel(tmp_path, text))[0].authors == expected
    assert len([m for m in caplog.messages if SPLIT_MARK in m]) == int(warned)
