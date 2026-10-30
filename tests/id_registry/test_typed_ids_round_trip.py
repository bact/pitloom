# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One round trip per row of the id-registry-v3 lookup table (design
section 7): seed a registry with ``id generate`` or ``id import``, build
the SBOM again, and every element of the row keeps the id the registry
holds -- under the name the row's lookup uses (physical or distribution
path, directory, package, a model file's path).

An ``id import`` row builds its source SBOM from another version of the
project, so a build with no registry gets other ids and a match cannot be
an accident of a deterministic document namespace.

See also: tests/id_registry/test_typed_ids.py (typed ids, lookup types,
settling), tests/id_registry/test_lookup_table.py (the names and gates).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.id_registry.surfaces_base import (
    DEMO_INIT_CONTENT,
    MODEL_FILE,
    _run_cli,
    demo_project,
)

_INIT = "demo/__init__.py"
_MODEL_STEM = MODEL_FILE.partition(".")[0]
_MODEL_KEY = f"demo/{MODEL_FILE}"  # a model's key: its file's
_FIXTURE_KEY = f"models/{SAFETENSORS_FIXTURE.name}"
_SRC_TOML = '\n[tool.hatch.build.targets.wheel]\npackages = ["src/demo"]\n'

_Key = tuple[str, str, str]  # (type, name in the SBOM, key in the registry)


@dataclass(frozen=True)
class Row:
    """One lookup-table row: how the registry is seeded, what is rebuilt."""

    seed: str  # "generate" or "import"
    layout: str  # flat, src, model (project); wheel, model-file
    keys: tuple[_Key, ...]


_ROWS: dict[str, Row] = {
    "file-physical-path": Row("generate", "src", ((FILE_TYPE, _INIT, "src/" + _INIT),)),
    "file-flat-path": Row("generate", "flat", ((FILE_TYPE, _INIT, _INIT),)),
    "file-distribution-path": Row("import", "src", ((FILE_TYPE, _INIT, _INIT),)),
    "directory": Row("import", "flat", ((FILE_TYPE, "demo", "demo"),)),
    # The seed SBOM is demo 0.9.0: another release than the rebuilt 1.0.0,
    # so only the dependency, one release in both, keeps its id
    # (test_an_imported_release_does_not_pin_another_one).
    "own-and-dependency-package": Row(
        "import", "flat", ((PACKAGE_TYPE, "fakedep", "fakedep@1"),)
    ),
    "ai-model-in-project-generate": Row(
        "generate", "model", ((AI_PACKAGE_TYPE, _MODEL_STEM, _MODEL_KEY),)
    ),
    "model-file-path": Row(
        "generate",
        "model-file",
        ((AI_PACKAGE_TYPE, SAFETENSORS_FIXTURE.stem, _FIXTURE_KEY),),
    ),
    "wheel-import": Row("import", "wheel", ((FILE_TYPE, _INIT, _INIT),)),
    "wheel-model-generate": Row(
        "generate", "wheel", ((AI_PACKAGE_TYPE, _MODEL_STEM, _MODEL_KEY),)
    ),
}


def _model_file(tmp_path: Path) -> Path:
    """The model fixture copied to ``tmp_path/models`` (once)."""
    path = tmp_path / _FIXTURE_KEY
    if not path.exists():
        path.parent.mkdir()
        shutil.copyfile(SAFETENSORS_FIXTURE, path)
    return path


def _project(tmp_path: Path, tag: str, layout: str, version: str) -> Path:
    root = demo_project(tmp_path / tag, _SRC_TOML if layout == "src" else "")
    if layout == "src":
        (root / "src").mkdir()
        (root / "demo").rename(root / "src" / "demo")
    if layout == "model":
        (root / "demo" / MODEL_FILE).write_bytes(safetensors_bytes())
    manifest = root / "pyproject.toml"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace('"1.0.0"', f'"{version}"', 1), encoding="utf-8")
    return root


def _build(
    tmp_path: Path, tag: str, row: Row, version: str, registry: Path | None
) -> str:
    """The SBOM of *row*'s subject at *version*, with *registry* (if any)."""
    if row.layout == "wheel":
        wheel = write_model_wheel(
            tmp_path / tag / "dist",
            {_INIT: DEMO_INIT_CONTENT, _MODEL_KEY: safetensors_bytes()},
            version=version,
        )
        return generate_wheel_sbom(wheel, id_registry=registry)
    if row.layout == "model-file":
        return generate_model_sbom(_model_file(tmp_path), id_registry=registry)
    root = _project(tmp_path, tag, row.layout, version)
    return generate_project_sbom(root, creation_metadata=None, id_registry=registry)


def _id(sbom: str, type_name: str, name: str) -> str:
    found = [
        node["spdxId"]
        for node in json.loads(sbom)["@graph"]
        if node.get("type") == type_name and node.get("name") == name
    ]
    assert len(found) == 1, (type_name, name, found)
    return str(found[0])


def _seed(
    row: Row, tmp_path: Path, mp: pytest.MonkeyPatch, registry: Path
) -> Callable[[_Key], str]:
    """Seed *registry* the way *row* says; return, per key, the id it holds."""
    if row.seed == "import":
        source = tmp_path / "source.spdx3.json"
        source.write_text(_build(tmp_path, "a", row, "0.9.0", None), encoding="utf-8")
        mp.chdir(registry.parent)  # the root `id import` stores
        assert _run_cli(mp, ["id", "import", str(source), "-o", str(registry)]) == 0
        return lambda key: _id(source.read_text(encoding="utf-8"), key[0], key[1])
    if row.layout == "model-file":  # the model's own directory, from tmp_path
        argv = ["id", "generate", str(_model_file(tmp_path).parent)]
        argv += ["--project-dir", str(tmp_path), "-o", str(registry)]
    else:  # a wheel's files and model: the flat project's
        layout = row.layout if row.layout in ("flat", "src") else "model"
        root = _project(tmp_path, "seed", layout, "1.0.0")
        argv = ["id", "generate", str(root / ("src" if layout == "src" else "demo"))]
        argv += ["--project-dir", str(root), "-o", str(registry)]
    assert _run_cli(mp, argv) == 0
    held = IdRegistry.load(registry)

    def held_id(key: _Key) -> str:
        entry = held.get(key[0], key[2])
        assert entry is not None, key
        return entry.spdx_id

    return held_id


@pytest.mark.parametrize("name", list(_ROWS))
def test_seeded_registry_gives_the_rebuilt_sbom_its_ids(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _ROWS[name]
    # In the rebuilt project, its root: no key prefix.
    registry = tmp_path / "b" / "proj" / "ids.json"
    registry.parent.mkdir(parents=True)
    held_id = _seed(row, tmp_path, monkeypatch, registry)
    expected = {key: held_id(key) for key in row.keys}

    rebuilt = _build(tmp_path, "b", row, "1.0.0", registry)
    unseeded = _build(tmp_path, "c", row, "1.0.0", None)

    for key, spdx_id in expected.items():
        assert _id(rebuilt, key[0], key[1]) == spdx_id, key
        # Non-vacuous: without the registry the element has another id.
        assert _id(unseeded, key[0], key[1]) != spdx_id, key


@pytest.mark.parametrize("name", ["own-and-dependency-package", "wheel-import"])
def test_an_imported_release_does_not_pin_another_one(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``id import`` of the demo 0.9.0 SBOM keys its package ``demo@0.9``:
    the rebuilt 1.0.0 is another release, with an id of its own (Q-D)."""
    row = _ROWS[name]
    registry = tmp_path / "b" / "proj" / "ids.json"
    registry.parent.mkdir(parents=True)
    _seed(row, tmp_path, monkeypatch, registry)
    source = (tmp_path / "source.spdx3.json").read_text(encoding="utf-8")

    rebuilt = _build(tmp_path, "b", row, "1.0.0", registry)

    held = IdRegistry.load(registry).get(PACKAGE_TYPE, "demo@0.9.0")
    assert held is not None and held.spdx_id == _id(source, PACKAGE_TYPE, "demo")
    assert _id(rebuilt, PACKAGE_TYPE, "demo") != held.spdx_id
