# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the lock/pin priority cascade
(:mod:`pitloom.extract._locked_dependencies`) as a mechanism: priority
ordering, the override provenance note, and -- most importantly -- that
``read_project()`` applies it uniformly regardless of which metadata
source (``pyproject.toml`` or bare ``setup.py``/``setup.cfg``) resolved
the project's name/version.

Per-format parsing correctness lives in each format's own
``test_<format>.py`` (e.g. test_pylock.py, test_poetry_lock.py); this
file only exercises the cascade and wiring, using ``pylock.toml`` and
``poetry.lock`` as the two currently-registered/available sources.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from pitloom.core.project import ProjectMetadata
from pitloom.extract._locked_dependencies import apply_locked_dependencies
from pitloom.extract.project import read_project


def _write_pylock(tmp_dir: Path, name: str, version: str) -> None:
    (tmp_dir / "pylock.toml").write_text(
        f'lock-version = "1.0"\ncreated-by = "test"\n'
        f'[[packages]]\nname = "{name}"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def test_apply_locked_dependencies_sets_provenance_when_no_prior_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock(tmp_path, "requests", "2.31.0")
        metadata = ProjectMetadata(name="pkg")

        apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


def test_apply_locked_dependencies_no_source_present_leaves_metadata_untouched() -> (
    None
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        metadata = ProjectMetadata(name="pkg")

        apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance


def test_apply_locked_dependencies_overrides_prior_source_with_note(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A source already recorded in `metadata.provenance` (e.g. by
    `poetry.lock` via `_try_read_poetry()`, which runs before this
    cascade in `read_pyproject()`) is overridden by a higher-priority
    cascade entry -- logged, and recorded in the provenance string
    itself, not only logged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock(tmp_path, "httpx", "0.27.0")
        metadata = ProjectMetadata(
            name="pkg",
            locked_dependencies=["requests==2.31.0"],
            provenance={
                "locked_dependencies": "Source: poetry.lock | Method: resolved_lockfile"
            },
        )

        with caplog.at_level(logging.WARNING):
            apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile "
            "| Note: supersedes poetry.lock"
        )
        assert "poetry.lock and pylock.toml" in caplog.text
        assert "pylock.toml takes priority" in caplog.text


def test_apply_locked_dependencies_unrecognized_previous_source_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A `provenance["locked_dependencies"]` source name that doesn't
    match any entry in `_LOCK_SOURCES` (a bug, e.g. after a future rename
    drifts the two apart) can't be ranked -- warn, rather than silently
    letting every cascade-tried format skip the override check."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock(tmp_path, "requests", "2.31.0")
        metadata = ProjectMetadata(
            name="pkg",
            locked_dependencies=["mystery==1.0.0"],
            provenance={
                "locked_dependencies": (
                    "Source: mystery-tool | Method: resolved_lockfile"
                )
            },
        )

        with caplog.at_level(logging.WARNING):
            apply_locked_dependencies(metadata, tmp_path)

        assert "doesn't match any known lock source" in caplog.text
        assert metadata.locked_dependencies == ["requests==2.31.0"]


def test_apply_locked_dependencies_valid_empty_source_wins_over_lower_priority() -> (
    None
):
    """Regression: a valid, higher-priority lock that resolves to zero
    runtime dependencies must still win outright over a lower-priority
    source that *does* have dependencies -- an empty result is a real,
    authoritative answer ("this lock says there are none"), not the same
    as "this source doesn't apply here". Without distinguishing the two,
    the lower-priority ``uv.lock`` here would incorrectly add dependencies
    the winning ``pylock.toml`` says don't exist."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pylock.toml").write_text(
            'lock-version = "1.0"\ncreated-by = "test"\n', encoding="utf-8"
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
        metadata = ProjectMetadata(name="demo")

        apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependencies == []
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


def test_read_project_applies_cascade_for_setup_py_only_project() -> None:
    """Regression: a project with no `pyproject.toml` at all -- just a
    bare `setup.py`, the realistic pairing for `Pipfile.lock`/pinned
    `requirements.txt` in real projects -- still gets
    `locked_dependencies` populated via `read_project()`'s cascade. This
    is exactly the gap the cascade's `read_project()`-level call site
    (rather than being wired only inside `read_pyproject()`) exists to
    close."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='pkg', version='1.0')\n",
            encoding="utf-8",
        )
        _write_pylock(tmp_path, "requests", "2.31.0")

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.name == "pkg"
        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )


def test_read_project_no_metadata_source_never_reaches_cascade() -> None:
    """A directory with neither `pyproject.toml` nor `setup.cfg`/
    `setup.py` still raises before the cascade runs -- a lock file alone
    is optional enrichment, never a metadata source of record."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock(tmp_path, "requests", "2.31.0")

        with pytest.raises(FileNotFoundError):
            read_project(tmp_path)
