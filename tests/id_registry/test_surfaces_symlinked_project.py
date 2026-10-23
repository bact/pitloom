# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project reached through a symlink has the ids of the project it links to.

See also: test_surfaces_path_keys.py (the surfaces and their project),
test_keys.py (``keys.project_prefix``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry
from tests.id_registry._surfaces_path_keys_shared import (
    KEYS,
    REGISTRY,
    SURFACES,
    file_ids,
    held_files,
    src_project,
)

pytestmark = pytest.mark.usefixtures("fixed_epoch")

#: The surfaces that take the project directory as given.
_TAKING_A_PROJECT = [
    "cli-project",
    "lib-project",
    "allow-build",
    "cli-sdist-project",
    "lib-sdist-project",
    "cli-generate-sdist-project",
    "cli-wheel-project",
    "lib-wheel-project",
    "lib-generate-wheel-project",
]


@pytest.mark.parametrize("surface", _TAKING_A_PROJECT)
def test_a_symlinked_project_dir_gives_the_ids_of_the_real_one(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    project = src_project(repo / "pkgs" / "demo", registry=f"../../{REGISTRY}")
    link = repo / "link"
    try:
        os.symlink(project, link, target_is_directory=True)
    except (OSError, NotImplementedError):  # Windows without the privilege
        pytest.skip("cannot create a symlink")
    registry = IdRegistry.new("demo", project_root=repo)
    registry.generate([project / "src"], project)
    registry.save(repo / REGISTRY)
    held = held_files(repo / REGISTRY)
    assert set(held) == {f"pkgs/demo/{key}" for key in KEYS}

    run = SURFACES[surface]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    ids = file_ids(run.run(link, repo / REGISTRY, scratch, monkeypatch))

    assert {f"pkgs/demo/{key}": ids[run.name(key)] for key in KEYS} == held
    assert held_files(repo / REGISTRY) == held
