# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One registry snapshot, consulted by several surfaces: each surface
that emits a given shared element (the demo package's ``__init__.py``
file, its ``demo`` directory, the ``demo`` main package, the ``fakedep``
dependency, the AI model) must use the snapshot's id for it.

Never a whole-SBOM byte comparison across surfaces -- two surfaces
legitimately produce different documents (different namespaces, extra
elements a project scan sees that a wheel doesn't, and vice versa); the
registry is an *input* the generator consults per element, not a
guarantee of identical output. See :mod:`tests.id_registry.surfaces_shared`.

See also: :mod:`tests.id_registry.test_surfaces` (declaration/failure/
completeness, not id reuse), :mod:`tests.id_registry.test_session`
(the claim mechanics behind "first hit wins" that this module exercises
end to end).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, PACKAGE_TYPE, IdRegistry
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.extract.conftest import make_hook
from tests.id_registry.surfaces_shared import (
    DEPENDENCY,
    demo_project,
    demo_wheel,
)

#: The demo package's directory name, registered under
#: :data:`~pitloom.id_registry.FILE_TYPE` with no hash -- see
#: ``_document_files.py``'s directory-hit resolution.
_DIRECTORY_NAME = "demo"

#: The demo project's own name: its main ``software_Package``, registered
#: under :data:`~pitloom.id_registry.PACKAGE_TYPE`.
_MAIN_PACKAGE_NAME = "demo"

_MODEL_STEM = SAFETENSORS_FIXTURE.stem


@pytest.fixture(name="snapshot_path")
def _snapshot_path(tmp_path: Path) -> Path:
    """Build one populated registry and return the path it was saved to.
    Every test below copies its *bytes* fresh -- never reuses this
    :class:`IdRegistry` object or this file across surfaces, since
    generation may harvest (and rewrite) the registry it was given."""
    project = demo_project(tmp_path / "snapshot-source")
    registry = IdRegistry.new("snapshot")
    registry.generate([project / "demo"], project)
    registry.register(FILE_TYPE, _DIRECTORY_NAME)
    registry.register(PACKAGE_TYPE, _MAIN_PACKAGE_NAME)
    registry.register(PACKAGE_TYPE, DEPENDENCY)
    # With its bytes' SHA-256: a model lookup is gated by its file's hash.
    model_sha = hashlib.sha256(SAFETENSORS_FIXTURE.read_bytes()).hexdigest()
    registry.register(AI_PACKAGE_TYPE, _MODEL_STEM, sha256=model_sha)

    path = tmp_path / "snapshot.json"
    registry.save(path)
    return path


def _fresh_copy(snapshot_path: Path, destination: Path) -> Path:
    """A byte-for-byte copy of *snapshot_path* at *destination* -- so one
    surface's harvest-and-rewrite can never affect another's read."""
    shutil.copyfile(snapshot_path, destination)
    return destination


def _snapshot_ids(snapshot_path: Path) -> dict[str, str | None]:
    registry = IdRegistry.load(snapshot_path)
    return {
        "file": registry.lookup(
            FILE_TYPE, ["demo/__init__.py"], sha256=_init_sha(snapshot_path)
        ),
        "directory": registry.lookup(FILE_TYPE, [_DIRECTORY_NAME]),
        "main": registry.lookup(PACKAGE_TYPE, [_MAIN_PACKAGE_NAME]),
        "dependency": registry.lookup(PACKAGE_TYPE, [DEPENDENCY]),
        "model": registry.lookup(AI_PACKAGE_TYPE, [_MODEL_STEM]),
    }


def _init_sha(snapshot_path: Path) -> str:
    entry = IdRegistry.load(snapshot_path).get(FILE_TYPE, "demo/__init__.py")
    assert entry is not None and entry.sha256 is not None
    return entry.sha256


def _elements(sbom_json: str) -> list[dict[str, Any]]:
    return list(json.loads(sbom_json)["@graph"])


def _spdx_id(elements: list[dict[str, Any]], type_name: str, name: str) -> str | None:
    for node in elements:
        if node.get("type") == type_name and node.get("name") == name:
            return node.get("spdxId")
    return None


def _project_like_ids(elements: list[dict[str, Any]]) -> dict[str, str | None]:
    """The ids a project-shaped surface (project, wheel, hook) emits for the
    elements the snapshot registers."""
    return {
        "file": _spdx_id(elements, "software_File", "demo/__init__.py"),
        "directory": _spdx_id(elements, "software_File", _DIRECTORY_NAME),
        "main": _spdx_id(elements, "software_Package", _MAIN_PACKAGE_NAME),
        "dependency": _spdx_id(elements, "software_Package", DEPENDENCY),
    }


def _assert_project_like_reuse(
    elements: list[dict[str, Any]], expected: dict[str, str | None]
) -> None:
    reused = _project_like_ids(elements)
    for kind, spdx_id in reused.items():
        assert spdx_id is not None, kind  # non-vacuous: the element exists
        assert spdx_id == expected[kind], kind


def _only_ai_package_id(elements: list[dict[str, Any]]) -> str | None:
    ai_packages = [n for n in elements if n.get("type") == "ai_AIPackage"]
    assert len(ai_packages) == 1, ai_packages
    return ai_packages[0].get("spdxId")


def test_project_surface_reuses_snapshot_ids(
    tmp_path: Path, snapshot_path: Path
) -> None:
    expected = _snapshot_ids(snapshot_path)
    project = demo_project(tmp_path / "run")
    # In the project: a saved registry's root is its own directory.
    registry_copy = _fresh_copy(snapshot_path, project / "project-copy.json")

    sbom_json = generate_project_sbom(
        project, creation_metadata=None, id_registry=registry_copy
    )

    _assert_project_like_reuse(_elements(sbom_json), expected)


def test_wheel_surface_reuses_snapshot_ids(tmp_path: Path, snapshot_path: Path) -> None:
    expected = _snapshot_ids(snapshot_path)
    registry_copy = _fresh_copy(snapshot_path, tmp_path / "wheel-copy.json")
    wheel = demo_wheel(tmp_path / "run")

    sbom_json = generate_wheel_sbom(wheel, id_registry=registry_copy)

    _assert_project_like_reuse(_elements(sbom_json), expected)


def test_hook_surface_reuses_snapshot_ids(tmp_path: Path, snapshot_path: Path) -> None:
    """The Hatchling build hook resolves only the project's own
    ``[tool.pitloom] id-registry`` (see
    :mod:`tests.id_registry.surfaces_shared`'s ``run_hook``)."""
    expected = _snapshot_ids(snapshot_path)
    toml = '\n[tool.pitloom]\nid-registry = "hook-copy.json"\n'
    project = demo_project(tmp_path / "run", toml)
    _fresh_copy(snapshot_path, project / "hook-copy.json")

    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    assert hook._sbom_staging_path is not None  # pylint: disable=protected-access
    sbom_json = hook._sbom_staging_path.read_text(  # pylint: disable=protected-access
        encoding="utf-8"
    )
    hook.finalize("standard", build_data, "")

    _assert_project_like_reuse(_elements(sbom_json), expected)


def test_env_surface_reuses_dependency_id(
    tmp_path: Path, snapshot_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _snapshot_ids(snapshot_path)
    registry_copy = _fresh_copy(snapshot_path, tmp_path / "env-copy.json")

    tree = [
        {
            "package": {
                "key": DEPENDENCY,
                "package_name": DEPENDENCY,
                "installed_version": "1.0",
            }
        }
    ]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(
            args=["pipdeptree"], returncode=0, stdout=json.dumps(tree), stderr=""
        ),
    )

    sbom_json = generate_env_sbom(id_registry=registry_copy)
    elements = _elements(sbom_json)

    dependency_id = _spdx_id(elements, "software_Package", DEPENDENCY)
    assert dependency_id == expected["dependency"]
    assert dependency_id is not None  # non-vacuous


def test_model_surface_reuses_model_stem_id(
    tmp_path: Path, snapshot_path: Path
) -> None:
    expected = _snapshot_ids(snapshot_path)
    registry_copy = _fresh_copy(snapshot_path, tmp_path / "model-copy.json")

    sbom_json = generate_model_sbom(SAFETENSORS_FIXTURE, id_registry=registry_copy)
    elements = _elements(sbom_json)

    model_id = _only_ai_package_id(elements)
    assert model_id == expected["model"]
    assert model_id is not None  # non-vacuous


def test_snapshot_ids_are_all_distinct_guard(snapshot_path: Path) -> None:
    """Vacuous-pass guard: if the snapshot's five ids collided, the
    assertions above could pass by accident (e.g. every surface just
    reusing whichever id happens to be first)."""
    ids = _snapshot_ids(snapshot_path)
    assert all(ids.values()), ids
    assert len(set(ids.values())) == len(ids), ids
