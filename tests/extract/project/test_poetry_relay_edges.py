# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the Poetry gap-fill relay found by mutation testing.

See also: ``tests/messages/test_metadata_relays.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.project.poetry import extract_poetry_metadata
from pitloom.extract.project.pyproject import read_pyproject
from pitloom.messages import code_of
from tests._code_records import coded

pytestmark = pytest.mark.platform

_LOCK = (
    '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
    '[metadata]\nlock-version = "2.1"\n'
)


def test_a_failed_poetry_gap_fill_is_said_once_by_the_quiet_lock_reread(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``use-lockfile`` from ``[tool.pitloom]`` makes the lock read a second,
    ``quiet`` read of the file. The peek reads no lock, so it never reaches
    the failed ``[tool.poetry]`` gap-fill: this reread is the one place the
    relay can say it, ``quiet`` or not."""
    root = tmp_path / "p"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[tool.pitloom]\nuse-lockfile = true\n[tool.poetry]\nversion = "1"\n',
        encoding="utf-8",
    )
    (root / "poetry.lock").write_text(_LOCK, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _, _ = resolve_project_with_lockfile(root, None)
    assert metadata.locked_dependencies == ["requests==2.31.0"]  # the reread ran
    assert [c for c, _ in coded(caplog)] == ["project-name-missing"]


def test_a_poetry_table_that_is_no_table_is_an_error_naming_field_and_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The error's own line (the relay never says it twice): the field, what
    was found and what was expected; ``quiet`` silences the warning only."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        with pytest.raises(ValueError) as exc:
            extract_poetry_metadata({"tool": {"poetry": "x"}}, tmp_path, quiet=True)
    assert code_of(exc.value) == "metadata-invalid"
    assert str(exc.value).endswith("[tool.poetry] is a string 'x', expected a table")
    assert not caplog.records  # quiet: not even the wrong-type warning


@pytest.mark.parametrize(
    ("poetry", "project"),
    [
        ({"name": "  "}, None),
        ({"version": "1"}, "x"),
    ],
    ids=["blank-poetry-name", "project-not-a-table"],
)
def test_a_name_that_is_blank_or_in_no_table_is_project_name_missing(
    poetry: dict[str, object], project: object, tmp_path: Path
) -> None:
    data: dict[str, object] = {"tool": {"poetry": poetry}}
    if project is not None:
        data["project"] = project
    with pytest.raises(ValueError) as exc:
        extract_poetry_metadata(data, tmp_path, quiet=True)
    assert code_of(exc.value) == "project-name-missing"


def test_a_blank_poetry_name_defers_to_the_stripped_project_name(
    tmp_path: Path,
) -> None:
    data = {
        "tool": {"poetry": {"name": "  ", "version": "1"}},
        "project": {"name": " real "},
    }
    metadata = extract_poetry_metadata(data, tmp_path, quiet=True)
    assert metadata.name == "real"
    assert metadata.provenance["name"].endswith("Field: project.name")


@pytest.mark.parametrize(
    "text",
    [
        '[project]\nname = "demo"\nversion = "1"\n[tool.poetry]\n',
        "[tool.poetry]\n",
    ],
    ids=["beside-project", "alone"],
)
def test_an_empty_poetry_table_is_no_poetry_table_at_all(
    text: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An empty ``[tool.poetry]`` is declared and empty, not unreadable: no
    gap-fill, no warning, and never the programming-error path of
    ``extract_poetry_metadata`` (which only a non-empty table reaches)."""
    path = tmp_path / "pyproject.toml"
    path.write_text(text, encoding="utf-8")
    # A lock file makes a wrongly read empty table reach the relay; without
    # one the same fault is swallowed (``InternalError`` is a ``ValueError``).
    (tmp_path / "poetry.lock").write_text(_LOCK, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        metadata, _ = read_pyproject(path)
    assert metadata.name in ("demo", "")
    assert not caplog.records
