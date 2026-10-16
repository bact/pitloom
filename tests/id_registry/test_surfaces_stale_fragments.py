# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom fragment configured in ``[tool.pitloom.fragment]`` and older than
its data or model: ``loom project`` merges it every run, yet its old ids
never roll back the registry, so ``id generate`` and ``project`` settle;
nor does a model card's dataset take the id its dataset pin holds.

See also: test_registry_harvest_stale.py (the harvest rules),
surfaces_base.py (``_run_cli``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pitloom import loom
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
)
from tests.id_registry.surfaces_base import _run_cli

_PYPROJECT = b"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]

[tool.pitloom]
id-registry = "reg.json"

[tool.pitloom.fragment]
files = ["frag.json"]
"""
_MODEL = "src/demo/m.npy"
_DATA = "data/t.txt"
_DS = DATASET_PACKAGE_TYPE
_NPY = Path(__file__).parents[1] / "fixtures" / "aimodels" / "numpy"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    (root / "src" / "demo").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "src" / "demo" / "__init__.py").write_bytes(b"")
    (root / "data" / "t.txt").write_bytes(b"rows\n")
    (root / _MODEL).write_bytes((_NPY / "example-model-v1.npy").read_bytes())
    (root / "pyproject.toml").write_bytes(_PYPROJECT)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    assert _run_cli(monkeypatch, ["id", "generate", "data", "src"]) == 0
    return root


def _settle(monkeypatch: pytest.MonkeyPatch, project: Path) -> tuple[bytes, bytes]:
    """``id generate`` then ``project``, twice: the registry after each."""
    states = []
    for n in range(2):
        assert _run_cli(monkeypatch, ["id", "generate", "data", "src"]) == 0
        assert _run_cli(monkeypatch, ["project", ".", "-o", f"out{n}.json"]) == 0
        states.append((project / "reg.json").read_bytes())
    return states[0], states[1]


def test_stale_fragment_file_never_rolls_back_a_newer_entry(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The R4 repro: data appended after the run; ``id generate`` mints its
    new content an id, and the merged fragment's old file (no recorded
    key) no longer writes its old id and SHA-256 back over it."""
    with loom.run(project / "frag.json", id_registry=IdRegistry.load("reg.json")):
        loom.add_dataset("data/t.txt")
    with open(project / "data" / "t.txt", "ab") as f:
        f.write(b"more\n")

    first, second = _settle(monkeypatch, project)

    assert first == second
    entry = IdRegistry.load(project / "reg.json").get(FILE_TYPE, "data/t.txt")
    assert entry is not None
    assert entry.sha256 == hashlib.sha256(b"rows\nmore\n").hexdigest()


def test_retrained_model_old_id_is_never_harvested_by_name(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The R4 repro: ``set_model`` with ``path=``, the model retrained, then
    ``project`` twice: the fragment's old model is written under no key
    (no file of its bytes in the document), so no name entry keeps the
    pre-retrain id and the registry stops changing."""
    with loom.run(project / "frag.json", id_registry=IdRegistry.load("reg.json")):
        loom.set_model("demo-model", path=_MODEL)
    (project / _MODEL).write_bytes((_NPY / "example-model-v2.npy").read_bytes())

    first, second = _settle(monkeypatch, project)

    assert first == second
    held = IdRegistry.load(project / "reg.json")
    models = sorted(k[1] for k in held.elements if k[0] == AI_PACKAGE_TYPE)
    assert models == [_MODEL]
    entry = held.get(AI_PACKAGE_TYPE, _MODEL)
    assert entry is not None
    assert entry.sha256 == hashlib.sha256((project / _MODEL).read_bytes()).hexdigest()


def test_model_card_dataset_never_takes_a_loom_dataset_pin(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fuzz repro: the registry takes the document's namespace (``id
    import``), ``-e`` pins ``data/t.txt`` there, a loom fragment uses the
    pin, then ``project --enrich`` mints the model card's dataset: never
    the pinned id, so the merge keeps both datasets."""
    (project / "src" / "demo" / "README.md").write_bytes(
        b"---\ndatasets: [imdb]\n---\n"
    )
    assert _run_cli(monkeypatch, ["project", ".", "-o", "p0.json"]) == 0
    (project / "reg.json").unlink()
    for argv in (["import", "p0.json"], ["generate", "-e", f"{_DATA}:{_DS}"]):
        assert _run_cli(monkeypatch, ["id", *argv, "-o", "reg.json"]) == 0
    with loom.run(project / "frag.json", id_registry=IdRegistry.load("reg.json")):
        loom.add_dataset(_DATA)

    assert _run_cli(monkeypatch, ["project", ".", "--enrich", "-o", "out.json"]) == 0

    graph = json.loads((project / "out.json").read_bytes())["@graph"]
    datasets = {e["name"]: e["spdxId"] for e in graph if e["type"] == _DS}
    assert sorted(datasets) == [_DATA, "imdb"]
    pin = IdRegistry.load(project / "reg.json").get(_DS, _DATA)
    assert pin is not None
    assert datasets[_DATA] == pin.spdx_id != datasets["imdb"]
