# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests verifying that Hatchling build hook metadata extraction strictly
isolates source-stage lock files from build-stage wheel metadata.

See also: :mod:`tests.extract.test_hatch_hook_metadata` for general Hatchling
build hook metadata extraction tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.plugin.manager import PluginManager

from pitloom.extract.hatchling import metadata_from_hatchling
from pitloom.extract.project import read_project

from .conftest import POETRY_GAP_FILL_PYPROJECT, write_pyproject


@pytest.mark.parametrize(
    ("lock_file", "content"),
    [
        (
            "poetry.lock",
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
        ),
        (
            "pylock.toml",
            'lock-version = "1.0"\ncreated-by = "test"\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
        ),
        (
            "uv.lock",
            'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
            '[[package]]\nname = "testpkg"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        ),
        (
            "pdm.lock",
            '[metadata]\nlock_version = "4.5.1"\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'groups = ["default"]\n',
        ),
        (
            "Pipfile.lock",
            '{"_meta": {"pipfile-spec": 6}, '
            '"default": {"requests": {"version": "==2.31.0"}}}',
        ),
        (
            "requirements.txt",
            "requests==2.31.0\n",
        ),
    ],
)
def test_metadata_from_hatchling_does_not_leak_lock_dependencies(
    lock_file: str, content: str
) -> None:
    """Lock files are source-stage-only artifacts -- the real wheel Hatchling
    builds never consults them, so the build hook's gap-fill path must never
    populate locked_dependencies from any lock file sitting next to a
    Hatchling-backed project."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, POETRY_GAP_FILL_PYPROJECT)
        (tmp_path / lock_file).write_text(content, encoding="utf-8")

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance

        # Companion assertion: absent the isolation boundary (via read_project's
        # default path), the same directory DOES resolve the lock file -- guards
        # against a vacuous pass where the lock fixture is broken or not found.
        direct, _, _ = read_project(tmp_path)
        assert direct.locked_dependencies == ["requests==2.31.0"]
