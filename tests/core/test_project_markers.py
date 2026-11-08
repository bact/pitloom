# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: :func:`pitloom.core.project_markers.has_project_config`
says a folder has no project exactly when
:func:`pitloom.extract.project.read_project` says so, for each marker alone,
a directory named like one, an empty marker and none.

See also: tests/extract/test_model_target.py (its user).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.project_markers import PROJECT_MARKERS, has_project_config
from pitloom.extract.project import read_project
from pitloom.extract.remote import _git_folder

#: Each case: the entries of the folder, a name ending in ``/`` a directory.
_CASES = {
    "none": ("README.md",),
    "pyproject": ("pyproject.toml",),
    "setup-cfg": ("setup.cfg",),
    "setup-py": ("setup.py",),
    "dir-pyproject": ("pyproject.toml/",),
    "dir-setup-cfg": ("setup.cfg/",),
    "near-miss": ("pyproject.tom", "Setup.py.bak", "setup.cfg~"),
}


def _says_no_project(folder: Path) -> bool:
    """Whether ``read_project`` refuses *folder* for having no project."""
    try:
        read_project(folder, include_installed_metadata=False, quiet=True)
    except FileNotFoundError as exc:
        return str(exc).startswith("No pyproject.toml, setup.cfg, or setup.py ")
    # pylint: disable-next=broad-exception-caught
    except Exception:  # another failure: it found something to read
        return False
    return False


@pytest.mark.parametrize("entries", _CASES.values(), ids=list(_CASES))
def test_the_markers_agree_with_read_project(
    entries: tuple[str, ...], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.CRITICAL + 1)  # read_project's own lines
    for entry in entries:
        if entry.endswith("/"):
            (tmp_path / entry).mkdir()
        else:
            (tmp_path / entry).write_bytes(b"")
    assert has_project_config(tmp_path) is not _says_no_project(tmp_path)
    assert has_project_config(str(tmp_path)) is has_project_config(tmp_path)


def test_a_missing_folder_has_no_project(tmp_path: Path) -> None:
    assert not has_project_config(tmp_path / "gone")


def test_the_git_folder_uses_the_one_list() -> None:
    assert _git_folder.PROJECT_MARKERS is PROJECT_MARKERS
    assert PROJECT_MARKERS == ("pyproject.toml", "setup.cfg", "setup.py")
