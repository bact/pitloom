# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``pdm.lock``'s overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract.lock.cascade`), and real-world fixture
coverage.

See also: test_pdm.py (core extraction unit tests); test_cascade.py for the
cascade mechanism's own tests.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent.parent / "fixtures" / "real-world-locks" / "pdm"
)

_METADATA = '[metadata]\nlock_version = "4.5.1"\n'


def _write_lock(tmp_dir: Path, body: str) -> None:
    (tmp_dir / "pdm.lock").write_text(body + _METADATA, encoding="utf-8")


# --- read_project() cascade integration -----------------------------------


def test_read_project_populates_locked_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'groups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


def test_read_project_pdm_lock_never_overrides_poetry_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`pdm.lock` ranks *below* `poetry.lock` in the shared priority order: when
    both are present, `poetry.lock`'s already-applied result wins and
    `pdm.lock` never silently overrides it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        with caplog.at_level(logging.WARNING):
            metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: poetry.lock | Method: resolved_lockfile"
        )
        assert "supersedes" not in caplog.text


def test_read_project_pdm_lock_used_when_no_poetry_lock_present() -> None:
    """A non-Poetry project (no `[tool.poetry]` at all, so `poetry.lock`
    was never applied) still gets `pdm.lock`'s data normally -- the
    priority-order gate only blocks *actual* higher-ranked data, not the
    mere possibility of it."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.28.1"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


def test_read_project_uv_lock_still_overrides_pdm_lock() -> None:
    """`uv.lock` outranks `pdm.lock` -- confirm adding `pdm.lock` to the
    cascade didn't disturb the existing higher-priority entries."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "uv.lock").write_text(
            'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
            '[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
            encoding="utf-8",
        )
        _write_lock(
            tmp_path,
            '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n',
        )

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: uv.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures ---------------------------------------------------


def test_real_world_pdm() -> None:
    """`pdm-project/pdm` -- PDM's own package (self-hosting case)."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "pdm-2.29.0")

    assert metadata.name == "pdm"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert "httpx" in names
    assert "coverage" not in names  # test-group only
    assert metadata.provenance["locked_dependencies"] == (
        "Source: pdm.lock | Method: resolved_lockfile"
    )


def test_real_world_unearth() -> None:
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / "unearth-0.18.3")

    assert metadata.name == "unearth"
    names = {dep.split("==", maxsplit=1)[0] for dep in metadata.locked_dependencies}
    assert "anyio" in names
    assert "sphinx" not in names  # doc-group only, per the unearth pdm.lock sample


@pytest.mark.parametrize(
    ("project", "name", "locked"),
    [
        ("findpython-0.8.0", "findpython", ["packaging==24.2", "platformdirs==4.3.6"]),
        ("dep-logic-0.7.2", "dep-logic", ["packaging==23.2"]),
    ],
    ids=["findpython", "dep-logic"],
)
def test_real_world_no_extras_pins_default_group_only(
    project: str, name: str, locked: list[str]
) -> None:
    """Negative case: no `[project.optional-dependencies]`, so nothing but
    the default group is pinned, never the dev groups. It does not reach
    the extras' group filter (see test_extra_pins.py)."""
    metadata, _config, _path = read_project(REAL_WORLD_LOCKS / project)

    assert metadata.name == name
    assert sorted(metadata.locked_dependencies) == locked
