# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``embed-wheel --project-dir``: a wheel member is keyed below the
project's prefix, as a built file is, so a registry rooted above the
project (a monorepo) gives the member and its model the ids ``id generate``
wrote for the project's files.

See also: _surfaces_path_keys_shared.py (the project and runners),
test_surfaces_path_keys.py (the other surfaces), test_keys_files.py
(``keys.file_lookup_key``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import FILE_TYPE, IdRegistry
from tests.assemble.conftest import _make_dummy_wheel
from tests.id_registry._surfaces_path_keys_shared import (
    FILES,
    MODEL,
    REGISTRY,
    SURFACES,
    file_ids,
    held_files,
    held_models,
    model_ids,
    src_project,
)

pytestmark = pytest.mark.usefixtures("fixed_epoch")

#: A wheel's ``.data`` member: no layout alias, keyed below the prefix too.
_DATA = "demo-1.0.0.data/scripts/run"
_DATA_BYTES = b"#!run\n"


def _generated(
    tmp_path: Path, where: str, *, flat: bool = False
) -> tuple[Path, Path, str]:
    """A project at *where* below a registry root, ``id generate`` having run
    over it: the project, the registry file and the project's prefix."""
    repo = tmp_path / "repo"
    project = src_project(
        repo / where if where else repo,
        registry=f"{'../' * len(Path(where).parts)}{REGISTRY}",
        flat=flat,
    )
    registry = IdRegistry.new("demo", project_root=repo)
    registry.generate([project / ("demo" if flat else "src")], project)
    registry.save(repo / REGISTRY)
    return project, repo / REGISTRY, where


@pytest.mark.parametrize(
    ("where", "flat"),
    [("pkgs/demo", False), ("pkgs/demo", True), ("", False), ("a/b/c", False)],
    ids=["src", "flat", "root", "deep"],
)
def test_embed_wheel_project_reuses_the_generated_ids(
    where: str, flat: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every file and the model take the id ``id generate`` wrote under the
    project's path from the root, and no key is added."""
    project, registry, prefix = _generated(tmp_path, where, flat=flat)
    top = "" if flat else "src/"
    under = f"{prefix}/" if prefix else ""
    held = held_files(registry)
    assert set(held) == {f"{under}{top}{name}" for name in FILES}  # non-vacuous
    held_model = held_models(registry)
    assert list(held_model) == [f"{under}{top}{MODEL}"]

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sbom = SURFACES["embed-wheel-project"].run(project, registry, scratch, monkeypatch)

    ids = file_ids(sbom)
    assert {f"{under}{top}{name}": ids[name] for name in FILES} == held
    assert model_ids(sbom) == list(held_model.values())
    assert held_files(registry) == held
    assert held_models(registry) == held_model  # lookup only: nothing written


@pytest.mark.parametrize("held_at", ["pkgs/demo/", ""], ids=["prefixed", "bare"])
def test_embed_wheel_project_keys_a_data_member_below_the_prefix(
    held_at: str, tmp_path: Path
) -> None:
    """A ``.data`` member has no layout alias, and its key is joined to the
    prefix: a held key with the prefix is hit, the bare one is not."""
    project = src_project(tmp_path / "repo" / "pkgs" / "demo", f"../../{REGISTRY}")
    registry = IdRegistry.new("demo", project_root=tmp_path / "repo")
    sha = hashlib.sha256(_DATA_BYTES).hexdigest()
    pinned = registry.register(FILE_TYPE, f"{held_at}{_DATA}", sha256=sha)
    path = tmp_path / "repo" / REGISTRY
    registry.save(path)
    wheel = _make_dummy_wheel(
        tmp_path / "dist", "demo", "1.0.0", extra_members={_DATA: _DATA_BYTES}
    )

    embed_wheel_sbom(wheel, project_dir=project, id_registry=path)

    with zipfile.ZipFile(wheel) as zf:
        (name,) = [n for n in zf.namelist() if "/sboms/" in n]
        ids = file_ids(zf.read(name).decode("utf-8"))
    assert (ids[_DATA] == pinned) is bool(held_at)
