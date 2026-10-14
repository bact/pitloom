# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the lock/pin priority cascade
(:mod:`pitloom.extract.lock.cascade`) as a mechanism: priority
ordering, the override provenance note, and -- most importantly -- that
``read_project()`` applies it uniformly regardless of which metadata
source (``pyproject.toml`` or bare ``setup.py``/``setup.cfg``) resolved
the project's name/version.

Per-format parsing correctness lives in each format's own
``test_<format>.py`` (e.g. test_pylock.py, test_poetry.py); this
file only exercises the cascade and wiring, using ``pylock.toml`` and
``poetry.lock`` as the two currently-registered/available sources.
"""

import logging
import os
import tempfile
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock import apply_locked_dependencies, cascade
from pitloom.extract.project import read_project
from tests.assemble.embed_surfaces_shared import run_cli


def _write_pylock(tmp_dir: Path, name: str, version: str) -> None:
    (tmp_dir / "pylock.toml").write_text(
        f'lock-version = "1.0"\ncreated-by = "test"\n'
        f'[[packages]]\nname = "{name}"\nversion = "{version}"\n',
        encoding="utf-8",
    )


def _write_pylock_with_hash(
    tmp_dir: Path, name: str, version: str, sha256: str
) -> None:
    (tmp_dir / "pylock.toml").write_text(
        f'lock-version = "1.0"\ncreated-by = "test"\n'
        f'[[packages]]\nname = "{name}"\nversion = "{version}"\n'
        f'wheels = [{{ url = "{name}-{version}-py3-none-any.whl", '
        f'hashes = {{ sha256 = "{sha256}" }} }}]\n',
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


def test_apply_locked_dependencies_populates_hash_for_winning_source() -> None:
    """The cascade calls the winning source's own hash extractor and
    stores the result on ``locked_dependency_hashes`` -- see
    lock-hash-preservation.md."""
    sha256 = "a" * 64
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock_with_hash(tmp_path, "requests", "2.31.0", sha256)
        metadata = ProjectMetadata(name="pkg")

        apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependency_hashes == {"requests": sha256}


def test_apply_locked_dependencies_no_hash_data_leaves_hashes_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _write_pylock(tmp_path, "requests", "2.31.0")
        metadata = ProjectMetadata(name="pkg")

        apply_locked_dependencies(metadata, tmp_path)

        assert not metadata.locked_dependency_hashes


def test_apply_locked_dependencies_no_source_present_leaves_metadata_untouched() -> (
    None
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        metadata = ProjectMetadata(name="pkg")

        apply_locked_dependencies(metadata, tmp_path)

        # pylint: disable-next=use-implicit-booleaness-not-comparison
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
        # `_write_pylock()` carries no hash data -- this also verifies the
        # stale `requests` hash left over from the superseded poetry.lock
        # source doesn't survive alongside the new locked_dependencies.
        _write_pylock(tmp_path, "httpx", "0.27.0")
        metadata = ProjectMetadata(
            name="pkg",
            locked_dependencies=["requests==2.31.0"],
            locked_dependency_hashes={"requests": "a" * 64},
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
        assert not metadata.locked_dependency_hashes
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
            'lock-version = "1.0"\ncreated-by = "test"\npackages = []\n',
            encoding="utf-8",
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

        # pylint: disable-next=use-implicit-booleaness-not-comparison
        assert metadata.locked_dependencies == []
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pylock.toml | Method: resolved_lockfile"
        )

        (tmp_path / "pylock.toml").unlink()
        metadata_uv = ProjectMetadata(name="demo")
        apply_locked_dependencies(metadata_uv, tmp_path)
        assert metadata_uv.locked_dependencies == ["requests==2.31.0"]


def test_apply_locked_dependencies_truncated_pylock_falls_back_to_lower_priority(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A truncated pylock.toml (e.g. missing 'packages') is not a valid empty lock;
    it must warn and let the cascade fall back to lower-priority sources."""
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

        with caplog.at_level(logging.WARNING):
            apply_locked_dependencies(metadata, tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: uv.lock | Method: resolved_lockfile"
        )
        assert "missing top-level 'packages' key" in caplog.text


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


def _dynamic_project(root: Path, listed: str, text: str) -> Path:
    """A setuptools project reading its dependencies from *listed*
    (``[tool.setuptools.dynamic]``), with ``requirements.txt`` holding
    *text*, ``other.txt`` a copy and ``linked.txt`` a hard link to it."""
    root.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend = "setuptools.build_meta"\n'
        '[project]\nname = "demo"\nversion = "1"\ndynamic = ["dependencies"]\n'
        f'[tool.setuptools.dynamic]\ndependencies = {{file = "{listed}"}}\n',
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text(text, encoding="utf-8")
    (root / "other.txt").write_text(text, encoding="utf-8")
    os.link(root / "requirements.txt", root / "linked.txt")
    return root


@pytest.mark.parametrize("surface", ["cli", "lib"])
@pytest.mark.parametrize(
    ("listed", "ignored"),
    [
        ("requirements.txt", False),
        ("./requirements.txt", False),
        ("linked.txt", False),
        ("other.txt", True),
    ],
    ids=["named", "dot-slash", "hard-link", "merely-present"],
)
def test_dynamic_dependencies_file_is_not_a_lock(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    listed: str,
    ignored: bool,
) -> None:
    """``requirements.txt`` the project reads its dependencies from is not
    tried as a lock, so nothing is "ignored"; one merely present still is
    (and says so)."""
    project = _dynamic_project(tmp_path / "p", listed, "requests>=2\n")
    out = tmp_path / "sbom.json"

    with caplog.at_level(logging.WARNING):
        if surface == "cli":
            run_cli(["project", str(project), "--offline", "-o", str(out)], monkeypatch)
        else:
            generate_project_sbom(project, output_path=out, offline=True)

    ignoring = [m for m in caplog.messages if "ignoring requirements.txt" in m]
    assert len(ignoring) == ignored
    assert "requests" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("listed", "locked"),
    [("requirements.txt", []), ("other.txt", ["requests==2.0"])],
    ids=["named", "merely-present"],
)
def test_pinned_dynamic_dependencies_file_is_not_a_lock(
    tmp_path: Path, listed: str, locked: list[str]
) -> None:
    """A fully pinned ``requirements.txt`` read as the dependencies is not
    also their lock; one merely present is."""
    project = _dynamic_project(tmp_path, listed, "requests==2.0\n")

    metadata = read_project(project)[0]

    assert metadata.dependencies == ["requests==2.0"]
    assert metadata.dependency_files == [listed]
    assert metadata.locked_dependencies == locked


@pytest.mark.parametrize(
    ("listed", "ignored"),
    [("./requirements.txt", False), ("linked.txt", True)],
    ids=["by-path", "link-unknown"],
)
def test_without_file_identity_the_path_decides(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    listed: str,
    ignored: bool,
) -> None:
    """With no file identity (FAT/exFAT), the listed path alone tells the
    dependencies file: a hard link is then a different file."""
    monkeypatch.setattr(cascade, "file_id", lambda _path: None)
    project = _dynamic_project(tmp_path, listed, "requests>=2\n")

    with caplog.at_level(logging.WARNING):
        read_project(project)

    assert ("ignoring requirements.txt" in caplog.text) == ignored
