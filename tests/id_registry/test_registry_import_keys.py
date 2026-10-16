# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``id import`` writes a dataset package and a model under the key a run
looks them up by (:mod:`pitloom.id_registry.import_keys`), so their ids
survive the next run.

See also: test_registry_import.py (``import_sbom`` itself),
tests/core/test_loom_dataset_path_keys.py (the loom dataset lookup).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.core.dataset_hash import hash_dataset
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from pitloom.id_registry.import_keys import IMPORT_NOT_FOUND
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.id_registry._registry_harvest_shared import _SHA_A, _SHA_B, _object_set
from tests.id_registry.surfaces_base import DEMO_INIT_CONTENT, MODEL_FILE, _run_cli
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/imported-1"
_DATA = b"one line\n"
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "{}"\n'
)
_CI = spdx3.CreationInfo(
    specVersion="3.0.1",
    created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    createdBy=[f"{_NS}#SoftwareAgent-1"],
)

Graph = list[dict[str, Any]]


def _graph(path: Path) -> Graph:
    graph: Graph = json.loads(path.read_text(encoding="utf-8"))["@graph"]
    return graph


def _ids(graph: Graph, type_name: str) -> list[str]:
    return [e["spdxId"] for e in graph if e["type"] == type_name]


def _messages(caplog: pytest.LogCaptureFixture, prefix: str) -> list[str]:
    return [m for m in caplog.messages if m.startswith(prefix)]


def _element(cls: Any, name: str, number: int, sha256: str | None = None) -> Any:
    """A *cls* element ``#<prefix>-<number>`` with a valid creation info."""
    prefix = str(cls.__name__).rpartition("_")[2]
    obj = cls(spdxId=f"{_NS}#{prefix}-{number}", name=name, creationInfo=_CI)
    if sha256 is not None:
        obj.verifiedUsing = [
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)
        ]
    if isinstance(obj, spdx3.dataset_DatasetPackage):
        obj.dataset_datasetType = [spdx3.dataset_DatasetType.text]
    return obj


def _write(path: Path, *objects: Any) -> Path:
    """*objects* as the SPDX 3 JSON-LD SBOM at *path*."""
    with open(path, "wb") as f:
        spdx3.JSONLDSerializer().write(_object_set(*objects), f)
    return path


# --- dataset packages of a loom fragment ---------------------------------


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project holding ``data/t.txt``; ``ext.txt`` beside it."""
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "data" / "t.txt").write_bytes(_DATA)
    (tmp_path / "ext.txt").write_bytes(_DATA)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _loom_dataset(output: Path, name: str, registry: IdRegistry | None) -> str:
    """Declare *name* in one loom run; the id of its dataset package."""
    with loom.run(output, id_registry=registry):
        loom.add_dataset(name)
    (spdx_id,) = _ids(_graph(output), DATASET_PACKAGE_TYPE)
    return spdx_id


@pytest.mark.parametrize(
    ("declared", "key", "info"),
    [
        ("data/t.txt", "data/t.txt", None),
        ("./data/t.txt", "data/t.txt", "./data/t.txt keyed by its path: data/t.txt"),
        ("data", "data", None),
        ("imdb", "imdb", "imdb keyed by its name: not found"),
        ("../ext.txt", "../ext.txt", "../ext.txt keyed by its name: outside the"),
    ],
    ids=["same", "dot", "dir", "name", "outside"],
)
def test_import_keys_a_loom_dataset_as_loom_looks_it_up(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    declared: str,
    key: str,
    info: str | None,
) -> None:
    """A fragment's dataset package is written under its path key (or its
    name, one INFO saying why) with its own digest, so the next loom run
    of any spelling reuses its id."""
    imported = _loom_dataset(project / "a.json", declared, None)
    registry = IdRegistry.new("r", project_root=project)
    caplog.set_level(logging.INFO, logger="pitloom")

    registry.import_sbom(project / "a.json")

    said = _messages(caplog, "ID registry: dataset ")
    assert len(said) == int(info is not None)
    assert all(m.startswith(f"ID registry: dataset {info}") for m in said)
    digest = hash_dataset(Path(declared), max_bytes=1 << 20).hex_digest
    entry = registry.get(DATASET_PACKAGE_TYPE, key)
    assert entry == RegistryEntry(imported, digest)
    rerun = key if key != "imdb" and not key.startswith("..") else declared
    assert _loom_dataset(project / "b.json", rerun, registry) == imported


@pytest.mark.parametrize("declared", ["data/t.txt", "./data/t.txt"], ids=str)
def test_import_of_a_dataset_gates_its_content(project: Path, declared: str) -> None:
    """Data changed after the import: a new package id, as for its file."""
    imported = _loom_dataset(project / "a.json", declared, None)
    registry = IdRegistry.new("r", project_root=project)
    registry.import_sbom(project / "a.json")
    (project / "data" / "t.txt").write_bytes(b"other\n")

    assert _loom_dataset(project / "b.json", "data/t.txt", registry) != imported


@pytest.mark.parametrize("imported", [True, False], ids=["import", "harvest"])
def test_only_import_records_a_dataset_digest(tmp_path: Path, imported: bool) -> None:
    """A run's auto-harvest never records a dataset package's digest."""
    dataset = _element(spdx3.dataset_DatasetPackage, "imdb", 1, _SHA_A)
    registry = make_registry(project_root=tmp_path)
    if imported:
        registry.import_sbom(_write(tmp_path / "s.json", dataset))
    else:
        registry.harvest(_object_set(dataset))

    expected = _SHA_A if imported else None
    assert registry.get(DATASET_PACKAGE_TYPE, "imdb") == RegistryEntry(
        str(dataset.spdxId), expected
    )


def test_import_keys_a_dataset_by_name_with_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """No root (the current directory deleted): the name, one INFO."""
    monkeypatch.chdir(tmp_path)
    registry = IdRegistry.new("r")
    dataset = _element(spdx3.dataset_DatasetPackage, "imdb", 1, _SHA_A)
    sbom = _write(tmp_path / "s.json", dataset)

    def _gone() -> Path:
        raise FileNotFoundError("cwd deleted")

    monkeypatch.setattr(registry, "root_dir", _gone)
    caplog.set_level(logging.INFO, logger="pitloom")
    registry.import_sbom(sbom)

    assert registry.get(DATASET_PACKAGE_TYPE, "imdb") is not None
    assert _messages(caplog, "ID registry: dataset ") == [
        f"ID registry: dataset imdb keyed by its name: {IMPORT_NOT_FOUND}"
    ]


# --- models of a project or wheel SBOM ------------------------------------


def _demo(tmp_path: Path, layout: str) -> Path:
    """The demo project, flat or ``src/`` layout, with a model file."""
    project = tmp_path / "proj"
    package = project / ("src/demo" if layout == "src" else "demo")
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(DEMO_INIT_CONTENT)
    (package / MODEL_FILE).write_bytes(safetensors_bytes())
    (project / "pyproject.toml").write_text(_PYPROJECT.format("1.0.0"), "utf-8")
    return project


@pytest.mark.parametrize(
    ("source", "layout"),
    [("project", "flat"), ("project", "src"), ("wheel", "flat"), ("wheel", "src")],
    ids=["project", "project-src", "wheel", "wheel-src"],
)
def test_import_then_project_reuses_the_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, layout: str
) -> None:
    """``id import`` keys a model by its file's key, as every surface looks
    it up: the next project run (another version, another namespace)
    reuses its id and leaves no name entry behind."""
    project = _demo(tmp_path, layout)
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    target = str(project)
    if source == "wheel":
        members = {"demo/__init__.py": DEMO_INIT_CONTENT}
        members[f"demo/{MODEL_FILE}"] = safetensors_bytes()
        target = str(write_model_wheel(tmp_path / "dist", members))
    assert _run_cli(monkeypatch, [source, target, "-o", str(first)]) == 0
    monkeypatch.chdir(project)
    registry = project / "ids.json"
    assert _run_cli(monkeypatch, ["id", "import", str(first), "-o", str(registry)]) == 0
    (project / "pyproject.toml").write_text(_PYPROJECT.format("2.0.0"), "utf-8")

    argv = ["project", str(project), "-o", str(second), "--id-registry", str(registry)]
    assert _run_cli(monkeypatch, argv) == 0

    before, after = _graph(first), _graph(second)
    assert _ids(before, "SpdxDocument") != _ids(after, "SpdxDocument")
    assert _ids(after, AI_PACKAGE_TYPE) == _ids(before, AI_PACKAGE_TYPE)
    models = [k for k in IdRegistry.load(registry).elements if k[0] == AI_PACKAGE_TYPE]
    root = "src/demo" if layout == "src" else "demo"
    assert models == [(AI_PACKAGE_TYPE, f"{root}/{MODEL_FILE}")]


@pytest.mark.parametrize(
    ("files", "models", "keys", "named"),
    [
        ((("a", _SHA_A), ("c", _SHA_B)), (("a", _SHA_A),), ["m/a"], []),
        ((("a", _SHA_A), ("b", _SHA_A)), (("a", _SHA_A),), ["a"], ["a"]),
        ((("c", _SHA_B),), (("a", _SHA_A),), ["a"], ["a"]),
        ((("a", _SHA_A),), (("a", None),), ["a"], ["a"]),
        ((("a", _SHA_A),), (("a", _SHA_A), ("b", _SHA_A)), [], []),
    ],
    ids=["unique", "twin-files", "no-file", "unhashed", "twin-models"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_import_keys_a_model_by_its_unique_file(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    files: tuple[tuple[str, str], ...],
    models: tuple[tuple[str, str | None], ...],
    keys: list[str],
    named: list[str],
) -> None:
    """A model takes the key of the one file holding its SHA-256; with
    none, several, or no SHA-256, its name and one INFO each. Two models
    of one file make that key ambiguous: neither is imported."""
    objects = [
        _element(spdx3.software_File, f"m/{name}", n, sha)
        for n, (name, sha) in enumerate(files, 1)
    ] + [
        _element(spdx3.ai_AIPackage, name, n, sha)
        for n, (name, sha) in enumerate(models, 1)
    ]
    registry = make_registry(project_root=tmp_path)
    caplog.set_level(logging.INFO, logger="pitloom")

    skipped = registry.import_sbom(_write(tmp_path / "s.json", *objects))

    held = [k[1] for k in registry.elements if k[0] == AI_PACKAGE_TYPE]
    assert held == keys
    assert skipped == ({(AI_PACKAGE_TYPE, "m/a")} if not keys else set())
    assert _messages(caplog, "ID registry: model ") == [
        f"ID registry: model {n} imported under its name: "
        "no unique file with its SHA-256"
        for n in named
    ]


def test_import_never_moves_a_model_id_off_its_path_key(tmp_path: Path) -> None:
    """R-keep: a model id a run harvested under ``src/demo/m.bin`` stays
    there when an SBOM keying it ``demo/m.bin`` is imported."""
    model = _element(spdx3.ai_AIPackage, "m", 1, _SHA_A)
    held = {(AI_PACKAGE_TYPE, "src/demo/m.bin"): (str(model.spdxId), _SHA_A)}
    registry = make_registry(held, project_root=tmp_path)
    file = _element(spdx3.software_File, "demo/m.bin", 1, _SHA_A)

    registry.import_sbom(_write(tmp_path / "s.json", file, model))

    assert entries_of(registry) == {
        **held,
        (FILE_TYPE, "demo/m.bin"): (str(file.spdxId), _SHA_A),
    }
