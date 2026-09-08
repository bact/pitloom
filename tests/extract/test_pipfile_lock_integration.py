# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``Pipfile.lock``'s overlay onto
``ProjectMetadata.locked_dependencies`` via ``read_project()``'s lock
cascade (:mod:`pitloom.extract._locked_dependencies`), and real-world
fixture coverage.

See also: test_pipfile_lock.py (core extraction and validation unit
tests this module's integration tests were split from).
"""

import json
import tempfile
from pathlib import Path

from pitloom.extract._pipfile_lock import extract_pipfile_lock_dependencies
from pitloom.extract.project import read_project

REAL_WORLD_LOCKS = (
    Path(__file__).parent.parent / "fixtures" / "real-world-locks" / "pipfile"
)

_META = {"pipfile-spec": 6}


def _write_lock(
    tmp_dir: Path, data: dict[str, object], include_meta: bool = True
) -> None:
    full_data = {"_meta": _META, **data} if include_meta else data
    (tmp_dir / "Pipfile.lock").write_text(json.dumps(full_data), encoding="utf-8")


# --- read_project() cascade integration -------------------------------


def test_read_project_populates_locked_dependencies_from_setup_py_only() -> None:
    """Regression: Pipfile.lock predates PEP 621 almost entirely --
    every real project pairs it with a bare setup.py, never
    pyproject.toml. The cascade must reach it via read_project()'s
    setup.py-only dispatch path, not only the pyproject.toml one."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(name='demo', version='1.0.0')\n",
            encoding="utf-8",
        )
        _write_lock(tmp_path, {"default": {"requests": {"version": "==2.31.0"}}})

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["requests==2.31.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: Pipfile.lock | Method: resolved_lockfile"
        )


def test_read_project_pdm_lock_takes_priority_over_pipfile_lock() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / "pdm.lock").write_text(
            '[[package]]\nname = "httpx"\nversion = "0.27.0"\ngroups = ["default"]\n'
            '[metadata]\nlock_version = "4.5.1"\n',
            encoding="utf-8",
        )
        _write_lock(tmp_path, {"default": {"requests": {"version": "==2.31.0"}}})

        metadata, _config, _path = read_project(tmp_path)

        assert metadata.locked_dependencies == ["httpx==0.27.0"]
        assert metadata.provenance["locked_dependencies"] == (
            "Source: pdm.lock | Method: resolved_lockfile"
        )


# --- real-world fixtures -------------------------------------------------


def test_real_world_requests_html() -> None:
    """`psf/requests-html` -- real, unmodified `Pipfile.lock` from the
    matching GitHub tag, read directly via the extractor rather than
    `read_project()`: `requests-html`'s `setup.py` declares `name`/
    `version` via module-level constants (`NAME = 'requests-html'`,
    `setup(name=NAME, ...)`), which `_setuptools_py.py`'s literal-only
    AST resolution can't follow -- a known, separate, pre-existing gap
    (see the `pyyaml` entry in `real-world-projects/README.md`) that
    makes `read_setup_py()` raise `ValueError` and, with no `setup.cfg`
    fallback either, `read_project()` raise `FileNotFoundError` entirely
    for this fixture. That's this fixture's own known limitation, not
    something for the lock-cascade extractor to work around -- so this
    test exercises `extract_pipfile_lock_dependencies()` directly
    against the real fixture data instead."""
    dependencies = extract_pipfile_lock_dependencies(
        REAL_WORLD_LOCKS / "requests-html-0.10.0"
    )

    assert dependencies is not None
    names = {dep.split("==", maxsplit=1)[0] for dep in dependencies}
    assert "requests" in names
    assert "beautifulsoup4" in names


def test_real_world_responder() -> None:
    """`kennethreitz/responder` -- also has a self-referential editable
    `path`-sourced entry (`responder` itself) in its own `default`
    section, exercising the non-registry-source skip against real data.
    Same `setup.py`-constant limitation as `requests-html` above applies
    here too, so this also calls the extractor directly."""
    dependencies = extract_pipfile_lock_dependencies(
        REAL_WORLD_LOCKS / "responder-2.0.0"
    )

    assert dependencies is not None
    names = {dep.split("==", maxsplit=1)[0] for dep in dependencies}
    assert "requests" in names
    assert "responder" not in names  # self-referential, editable/path-sourced
