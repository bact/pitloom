# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hatchling build hook's staging directory: one that cannot be fully
removed in ``finalize()``, after the wheel is written (a file still held open
on Windows), is one ``WARNING:``, never a failed build; one whose SBOM cannot
be written is removed before the error rises.

See also: tests/extract/project/test_hatch_hook_hook_basic.py (the hook's
lifecycle) and tests/core/test_temp_dirs.py (the removal).
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from pitloom.plugins import hatch
from tests._held_open import hold_open
from tests.build_and_read_shared import use_sys_tmp

from ..conftest import make_hook, staged_sbom, write_pyproject


@pytest.fixture(name="sys_tmp")
def _sys_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return use_sys_tmp(tmp_path, monkeypatch)


@pytest.fixture(name="project")
def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    write_pyproject(project)
    (project / "testpkg").mkdir()
    (project / "testpkg" / "__init__.py").write_bytes(b"")
    return project


def test_finalize_warns_when_the_staging_dir_stays(
    sys_tmp: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    staged = staged_sbom(build_data)
    assert staged is not None and staged.parent.parent == sys_tmp
    # From here on, no directory can be removed: the wheel is written, the
    # staged SBOM is still held open.
    refused = hold_open(monkeypatch, "")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        hook.finalize("standard", build_data, "dist/testpkg-0.1.0-py3-none-any.whl")
    assert set(refused) == {staged.parent.name} and staged.is_file()
    assert [r.getMessage() for r in caplog.records] == [
        f"Pitloom: could not fully remove temporary directory "
        f"'{staged.parent.name}' (in the system temp directory)"
    ]
    assert hook._staging_dir is None


def test_a_staged_sbom_that_cannot_be_written_leaves_no_directory(
    sys_tmp: Path, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full_disk(*_args: object, **_kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(hatch, "write_text_lf", full_disk)
    hook = make_hook(str(project), {})
    with pytest.raises(OSError, match="No space left"):
        hook.initialize("standard", {})
    assert not list(sys_tmp.iterdir())
    assert hook._staging_dir is None
