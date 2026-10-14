# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for an sdist's authors: ``[project].authors`` of its
``pyproject.toml`` in declared order, else its ``[tool.poetry].authors``,
else ``PKG-INFO``'s.

See also: tests/test_author_surfaces.py (the same authors on every route).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.extract.project._sdist_scan import CONFIG_MEMBER_MAX_BYTES
from pitloom.extract.project.sdist import _declared_authors, read_sdist
from tests.assemble.conftest import _make_sdist

_PKG_INFO = (
    b"Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\nAuthor: Bob\n"
    b"Author-email: Ann <ann@example.com>\n"
)
_ANN = {"name": "Ann", "email": "ann@example.com"}
_POETRY = "Source: pyproject.toml | Field: tool.poetry.authors"


@pytest.mark.parametrize(
    ("pyproject", "expected"),
    [
        (
            {"project": {"authors": [{"name": "Bob"}, _ANN, {}]}},
            [{"name": "Bob"}, _ANN],
        ),
        ({"project": {"authors": [{"name": "", "email": "a@x"}]}}, [{"email": "a@x"}]),
        ({"project": {"authors": []}}, []),
        ({"project": {"name": "demo"}}, None),
        ({"project": {"authors": "Ann"}}, None),
        ({"project": {"authors": ["Ann"]}}, None),
        ({"project": {"authors": [{"name": 1}]}}, None),
        ({"project": "x"}, None),
        (None, None),
        # [tool.poetry] fills the gap, as for a directory; never split
        (
            {"tool": {"poetry": {"authors": ["Doe, Jane <j@x.org>", "Lee, Ann"]}}},
            [{"name": "Doe, Jane", "email": "j@x.org"}, {"name": "Lee, Ann"}],
        ),
        (
            {"project": {"authors": []}, "tool": {"poetry": {"authors": ["Bob"]}}},
            [],
        ),
        ({"tool": {"poetry": {"authors": "Bob"}}}, None),
        ({"tool": {"poetry": {"authors": [1]}}}, None),
        ({"tool": {"poetry": []}}, None),
        ({"tool": []}, None),
    ],
    ids=[
        "declared",
        "blank-name",
        "declared-empty",
        "absent",
        "not-list",
        "not-table",
        "not-string",
        "project-not-table",
        "no-pyproject",
        "poetry",
        "project-wins",
        "poetry-not-list",
        "poetry-not-string",
        "poetry-not-table",
        "tool-not-table",
    ],
)
def test_declared_authors(
    pyproject: Any, expected: list[dict[str, str]] | None
) -> None:
    declared = _declared_authors(pyproject)
    assert (None if declared is None else declared.authors) == expected
    if declared is not None:
        poetry = "project" not in pyproject
        assert (declared.source == _POETRY) is poetry


def test_poetry_sdist_keeps_every_declared_author(tmp_path: Path) -> None:
    """Regression: poetry-core writes only the first author to
    ``PKG-INFO``; the archive's ``[tool.poetry].authors`` has them all."""
    pyproject = (
        b'[tool.poetry]\nname = "demo"\nversion = "1.0.0"\n'
        b'authors = ["Doe, Jane <j@x.org>", "Lee, Ann <a@x.org>"]\n'
    )
    pkg_info = (
        b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
        b"Author: Doe, Jane\nAuthor-email: j@x.org\n"
    )
    sdist = _make_sdist(
        tmp_path, members={"PKG-INFO": pkg_info, "pyproject.toml": pyproject}
    )
    metadata = read_sdist(sdist).metadata
    assert metadata.authors == [
        {"name": "Doe, Jane", "email": "j@x.org"},
        {"name": "Lee, Ann", "email": "a@x.org"},
    ]
    assert metadata.provenance["authors"] == _POETRY


@pytest.mark.parametrize(
    ("tail", "key"),
    [
        ("dependencies = 1\n", "'project.dependencies' is int"),
        ("optional-dependencies = 1\n", "'project.optional-dependencies' is int"),
        (
            '[project.optional-dependencies]\n"x\\n::error::y" = 1\n',
            "'project.optional-dependencies.x\\n::error::y' is int",
        ),
    ],
    ids=["dependencies", "optional-table", "extra-name-escaped"],
)
def test_pyproject_fallback_warning_names_the_member(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, tail: str, key: str
) -> None:
    """With no ``PKG-INFO``, an ignored ``pyproject.toml`` field is warned
    about as ``<archive>:pyproject.toml``, as its sibling warnings are; an
    extra name cannot forge a second line."""
    pyproject = f'[project]\nname = "demo"\nversion = "1.0.0"\n{tail}'
    sdist = _make_sdist(
        tmp_path, members={"PKG-INFO": None, "pyproject.toml": pyproject.encode()}
    )
    with caplog.at_level(logging.WARNING):
        read_sdist(sdist, read_config=False)
    (line,) = caplog.messages
    assert line.startswith(f"{sdist}:pyproject.toml: {key}, expected ")
    assert "\n" not in line


@pytest.mark.parametrize(
    ("pyproject", "key", "start", "end"),
    [
        (b"[project\n", "", " project metadata not read (", "); authors"),
        (
            b"#" * (CONFIG_MEMBER_MAX_BYTES + 1),
            "FILE=",
            f" larger than the {CONFIG_MEMBER_MAX_BYTES}-byte config-member cap;"
            " project metadata not read,",
            " authors",
        ),
    ],
    ids=["invalid-toml", "over-cap"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_unreadable_pyproject_keeps_pkg_info_authors(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    pyproject: bytes,
    key: str,
    start: str,
    end: str,
) -> None:
    """With the config replaced (``read_config=False``), a ``pyproject.toml``
    read only for the declared authors that cannot be read leaves
    ``PKG-INFO``'s, with one ``WARNING:`` worded as ``embed-wheel
    --project-dir``'s (or, over its cap, as every cap): the declared order
    is lost, and name-only authors joined into one ``Author`` read as one."""
    sdist = _make_sdist(
        tmp_path, members={"PKG-INFO": _PKG_INFO, "pyproject.toml": pyproject}
    )
    with caplog.at_level(logging.WARNING):
        metadata = read_sdist(sdist, read_config=False).metadata
    assert metadata.authors == [_ANN, {"name": "Bob"}]
    assert "PKG-INFO" in metadata.provenance["authors"]
    (line,) = caplog.messages
    assert line.startswith(f"{key}{sdist}:pyproject.toml:{start}")
    assert line.endswith(f"{end} from the PKG-INFO")


@pytest.mark.parametrize(
    "author", ["Ann, Bob", "Ann, " + "q" * 70000], ids=["split", "over-cap"]
)
@pytest.mark.parametrize(
    ("pyproject", "warnings"),
    [
        (None, 1),
        (b'[project]\nname = "demo"\nauthors = [{name = "Ann"}]\n', 0),
        (b'[tool.poetry]\nname = "demo"\nauthors = ["Ann"]\n', 0),
    ],
    ids=["pkg-info-only", "project-declares", "poetry-declares"],
)
def test_sdist_warns_only_when_pkg_info_authors_are_used(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    author: str,
    pyproject: bytes | None,
    warnings: int,
) -> None:
    """Regression: the archive's declared authors replace ``PKG-INFO``'s,
    so neither a split nor a cap is warned about for the discarded read;
    used, ``PKG-INFO``'s ``Author-email`` warns once."""
    head = "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n"
    pkg_info = f"{head}Author-email: {author}\n"
    sdist = _make_sdist(
        tmp_path,
        members={"PKG-INFO": pkg_info.encode(), "pyproject.toml": pyproject},
    )
    with caplog.at_level(logging.WARNING):
        read_sdist(sdist)
    keys = ("AUTHOR_EMAIL=", "FIELD=AUTHOR_EMAIL")
    about = [m for m in caplog.messages if m.startswith(keys)]
    assert len(about) == warnings
