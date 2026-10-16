# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard for the one model rule: a model's ``ai_AIPackage`` is keyed
by its own file's path, so every surface that names the model file gives
it the one id that key holds, whatever name the model, its stem or a loom
declaration gives it; other bytes at that path are a new id.

See also: _surfaces_path_keys_shared.py (the project and runners),
test_surfaces_path_keys.py (its files), test_registry_generate_models.py
(``id generate``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from tests._wheel_models import write_model_wheel
from tests.id_registry._surfaces_path_keys_shared import (
    FILES,
    MODEL,
    MODEL_BYTES,
    MODEL_NAME,
    REGISTRY,
    SURFACES,
    id_generate,
    src_project,
)
from tests.id_registry.surfaces_base import _run_cli

pytestmark = pytest.mark.usefixtures("fixed_epoch")

#: The model's key: its file's path from the project (the registry's root).
MODEL_KEY = f"src/{MODEL}"
_README = "---\nlicense: mit\ndatasets:\n  - squad\n---\n# M\n"
_NUMPY = Path(__file__).parents[1] / "fixtures" / "aimodels" / "numpy"
_Route = Callable[[Path, Path, pytest.MonkeyPatch], str]
_FLAT_PYPROJECT = (
    b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    b'[project]\nname = "demo"\nversion = "1.0.0"\n'
)


def _graph(text: str) -> list[dict[str, Any]]:
    return list(json.loads(text)["@graph"])


def _model_id(text: str) -> str:
    """The id of the one model: its package's, or what an enrichment
    fragment's relationships start from (it names the package only)."""
    graph = _graph(text)
    packages = [e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"]
    if not packages:
        packages = sorted({e["from"] for e in graph if e["type"] == "Relationship"})
    (spdx_id,) = packages
    return str(spdx_id)


def held_models(registry: Path) -> dict[str, str]:
    """Each held ``ai_AIPackage`` key -> its id."""
    return {
        name: entry.spdx_id
        for (type_name, name), entry in IdRegistry.load(registry).elements.items()
        if type_name == AI_PACKAGE_TYPE
    }


def _surface(name: str) -> _Route:
    def run(project: Path, registry: Path, mp: pytest.MonkeyPatch) -> str:
        scratch = project.parent / f"run-{name}"
        scratch.mkdir(exist_ok=True)
        return SURFACES[name].run(project, registry, scratch, mp)

    return run


def _cli(project: Path, argv: list[str], mp: pytest.MonkeyPatch) -> str:
    out = project.parent / f"{argv[0]}-{len(list(project.parent.glob('*.out')))}.out"
    assert _run_cli(mp, [*argv, "-o", str(out)]) == 0
    return out.read_text(encoding="utf-8")


def _model_route(project: Path, registry: Path, mp: pytest.MonkeyPatch) -> str:
    argv = ["model", str(project / "src" / MODEL), "--id-registry", str(registry)]
    return _cli(project, argv, mp)


def _enrich(project: Path, registry: Path, mp: pytest.MonkeyPatch) -> str:
    (project / "src" / "demo" / "README.md").write_bytes(_README.encode())
    argv = ["enrich", str(project / "src" / MODEL), "--id-registry", str(registry)]
    return _cli(project, argv, mp)


def _enrich_project(project: Path, _reg: Path, mp: pytest.MonkeyPatch) -> str:
    """The model argument from the current directory, the registry the
    project's own (its root the project)."""
    (project / "src" / "demo" / "README.md").write_bytes(_README.encode())
    mp.chdir(project / "src")
    return _cli(project, ["enrich", MODEL, "--project-dir", str(project)], mp)


def _loom(declare: Callable[..., None], name: str) -> _Route:
    """A loom run declaring the model by *name*, its ``path=`` from the
    project, the current directory."""

    def run(project: Path, registry: Path, mp: pytest.MonkeyPatch) -> str:
        mp.chdir(project)
        mp.setattr("pitloom._loom_active_run._get_caller_script_path", lambda: None)
        out = project.parent / f"loom-{name}.json"
        with loom.run(out, id_registry=IdRegistry.load(registry)):
            declare(name, path=f"src/{MODEL}")
        return out.read_text(encoding="utf-8")

    return run


#: Every route that names the model file (an sdist scans no models).
ROUTES: dict[str, _Route] = {
    **{name: _surface(name) for name in SURFACES if "sdist" not in name},
    "model": _model_route,
    "enrich": _enrich,
    "enrich-project": _enrich_project,
    # Neither the model's own name nor its stem, and each other's rename.
    "loom-set": _loom(loom.set_model, "declared-a"),
    "loom-use": _loom(loom.use_model, "declared-b"),
}
#: The routes that write the registry, and so can come first.
_HARVESTING = ["cli-project", "lib-project", "allow-build", "wheel", "loom-set"]


@pytest.mark.parametrize("route", list(ROUTES))
def test_route_reuses_the_generated_model_id(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    id_generate(monkeypatch, project, registry)
    held = held_models(registry)
    assert list(held) == [MODEL_KEY]  # its file's key, not a stem or a name

    assert _model_id(ROUTES[route](project, registry, monkeypatch)) == held[MODEL_KEY]
    assert held_models(registry) == held  # no key added, none moved


@pytest.mark.parametrize("first", _HARVESTING)
def test_route_first_then_id_generate_keeps_one_id_and_key(
    first: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    spdx_id = _model_id(ROUTES[first](project, registry, monkeypatch))

    id_generate(monkeypatch, project, registry)

    assert held_models(registry) == {MODEL_KEY: spdx_id}
    for route in ("model", "wheel", "loom-use"):
        assert _model_id(ROUTES[route](project, registry, monkeypatch)) == spdx_id


@pytest.mark.parametrize("route", list(ROUTES))
def test_retrained_bytes_at_the_same_path_are_a_new_id(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3: the registry records other bytes at the model's path; every
    route's lookup is gated by the bytes it reads, so it misses."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    model = project / "src" / MODEL
    model.write_bytes(MODEL_BYTES + b"\0")  # trained before
    id_generate(monkeypatch, project, registry)
    held = held_models(registry)[MODEL_KEY]
    model.write_bytes(MODEL_BYTES)  # retrained: the bytes every route reads

    assert _model_id(ROUTES[route](project, registry, monkeypatch)) != held


@pytest.mark.parametrize("data", ["same", "other"], ids=["copies", "k9"])
def test_two_model_files_sharing_a_stem_get_two_ids(
    data: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """K9: ``a/model.npy`` and ``b/model.npy`` (copies, or other bytes) are
    two keys and two ids on ``id generate``, the project, the wheel and
    ``model``, with no shared-name ``INFO:``."""
    root = tmp_path / "proj"
    members = {
        "demo/__init__.py": b"",
        "demo/models/a/model.npy": (_NUMPY / "example-model-v1.npy").read_bytes(),
        "demo/models/b/model.npy": (
            _NUMPY / f"example-model-{'v1' if data == 'same' else 'v2'}.npy"
        ).read_bytes(),
    }
    for name, payload in members.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(payload)
    (root / "pyproject.toml").write_bytes(_FLAT_PYPROJECT)
    registry = root / REGISTRY
    argv = ["id", "generate", str(root / "demo"), "--project-dir", str(root)]
    with caplog.at_level(logging.INFO):
        assert _run_cli(monkeypatch, [*argv, "-o", str(registry)]) == 0
    keys = sorted(n for n in members if n.endswith(".npy"))
    held = held_models(registry)
    assert sorted(held) == keys and len(set(held.values())) == 2

    by_file = _models_by_file(
        generate_project_sbom(root, creation_metadata=None, id_registry=registry)
    )
    wheel = write_model_wheel(tmp_path / "dist", members)
    assert by_file == held
    assert _models_by_file(generate_wheel_sbom(wheel, id_registry=registry)) == held
    for key in keys:
        argv = ["model", str(root / key), "--id-registry", str(registry)]
        assert _model_id(_cli(root, argv, monkeypatch)) == held[key]
    assert not [r for r in caplog.records if "share the name" in r.getMessage()]


def _models_by_file(text: str) -> dict[str, str]:
    """Each model's file name -> its package's id (``contains``)."""
    graph = _graph(text)
    names = {e.get("spdxId"): str(e.get("name")) for e in graph}
    packages = {e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"}
    return {
        names[target]: str(rel["from"])
        for rel in graph
        if rel["type"] == "Relationship"
        and rel["relationshipType"] == "contains"
        and rel["from"] in packages
        for target in rel["to"]
    }


def test_own_name_and_stem_are_no_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K10: entries under the model's own name and its stem are never hit
    by a pathful model: its file's key decides."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    id_generate(monkeypatch, project, registry)
    held = IdRegistry.load(registry)
    decoys = {held.register(AI_PACKAGE_TYPE, name) for name in (MODEL_NAME, "m")}
    held.save()

    for route in ("lib-project", "wheel", "model"):
        spdx_id = _model_id(ROUTES[route](project, registry, monkeypatch))
        assert spdx_id == held_models(registry)[MODEL_KEY]
        assert spdx_id not in decoys


@pytest.mark.parametrize("command", ["model", "enrich"])
def test_a_model_outside_the_root_is_keyed_by_its_stem_once_said(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Outside the registry's root the model keeps its stem as key, looked
    up ungated (a hash-less pin hits), with exactly one ``INFO:`` naming
    why."""
    registry = tmp_path / "reg" / REGISTRY
    registry.parent.mkdir()
    pinned = IdRegistry.new("demo")
    spdx_id = pinned.register(AI_PACKAGE_TYPE, "m")
    pinned.save(registry)
    model = tmp_path / "elsewhere" / "m.gguf"
    model.parent.mkdir()
    model.write_bytes(MODEL_BYTES)
    (model.parent / "README.md").write_bytes(_README.encode())

    argv = [command, str(model), "--id-registry", str(registry)]
    with caplog.at_level(logging.INFO):
        assert _model_id(_cli(model.parent, argv, monkeypatch)) == spdx_id

    infos = [r.getMessage() for r in caplog.records if "keyed by its name" in r.message]
    assert infos == ["ID registry: model m keyed by its name: outside the project root"]


@pytest.mark.parametrize("route", ["cli-project", "lib-project", "hook", "allow-build"])
def test_monorepo_project_keys_the_model_from_the_registry_root(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    project = src_project(repo / "pkgs" / "demo", registry=f"../../{REGISTRY}")
    registry = IdRegistry.new("demo", project_root=repo)
    registry.generate([project / "src"], project)
    registry.save(repo / REGISTRY)
    held = held_models(repo / REGISTRY)
    assert list(held) == [f"pkgs/demo/{MODEL_KEY}"]

    spdx_id = _model_id(ROUTES[route](project, repo / REGISTRY, monkeypatch))

    assert spdx_id == held[f"pkgs/demo/{MODEL_KEY}"]
    assert held_models(repo / REGISTRY) == held


@pytest.mark.parametrize("route", ["loom-set", "loom-use", "model", "enrich"])
def test_typed_src_path_after_a_wheel_reuses_its_model_id(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wheel keys the model by its installed path; a route typed the
    ``src/`` path hits that key through the layout alias and registers
    nothing; the project then promotes it, the id kept."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    spdx_id = _model_id(ROUTES["wheel"](project, registry, monkeypatch))
    assert held_models(registry) == {MODEL: spdx_id}

    assert _model_id(ROUTES[route](project, registry, monkeypatch)) == spdx_id
    assert held_models(registry) == {MODEL: spdx_id}

    assert _model_id(ROUTES["lib-project"](project, registry, monkeypatch)) == spdx_id
    assert held_models(registry) == {MODEL_KEY: spdx_id}


#: The aggregated alias ``INFO:`` (one per run or command), by hit count.
_ALIAS_INFO = (
    "ID registry: {} element(s) matched a registry key through the src/lib layout alias"
)


def _alias_infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "layout alias" in r.message]


@pytest.mark.parametrize(
    "route", ["loom-set", "loom-use", "model", "enrich", "enrich-project"]
)
def test_alias_hit_of_a_model_says_one_info_on_every_route(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A model found through the layout alias (a wheel minted its id) says
    so once at the end of the loom run or command, as ``project`` does; a
    direct hit says nothing."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    spdx_id = _model_id(ROUTES["wheel"](project, registry, monkeypatch))
    with caplog.at_level(logging.INFO):
        assert _model_id(ROUTES[route](project, registry, monkeypatch)) == spdx_id
    assert _alias_infos(caplog) == [_ALIAS_INFO.format(1)]

    id_generate(monkeypatch, project, registry)  # promotes: a direct hit now
    caplog.clear()
    with caplog.at_level(logging.INFO):
        assert _model_id(ROUTES[route](project, registry, monkeypatch)) == spdx_id
    assert not _alias_infos(caplog)


def test_project_after_a_wheel_says_its_alias_hits_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The model's package and each of the project's files count in the
    one line; ``loom``'s own end-of-run call does not add a second."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    IdRegistry.new("demo").save(registry)
    ROUTES["wheel"](project, registry, monkeypatch)
    with caplog.at_level(logging.INFO):
        ROUTES["lib-project"](project, registry, monkeypatch)
    (info,) = _alias_infos(caplog)
    assert info == _ALIAS_INFO.format(len(FILES) + 1)  # files, and the package


@pytest.mark.parametrize("route", ["cli-project", "model", "enrich"])
def test_retrain_info_names_the_model_by_its_own_name_on_every_route(
    route: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Other bytes at a held key give one ``INFO:`` naming the model by its
    own name, not its stem, whichever surface says it."""
    project = src_project(tmp_path / "proj")
    registry = project / REGISTRY
    model = project / "src" / MODEL
    model.write_bytes(MODEL_BYTES + b"\0")
    id_generate(monkeypatch, project, registry)
    model.write_bytes(MODEL_BYTES)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        ROUTES[route](project, registry, monkeypatch)
    infos = [
        r.getMessage() for r in caplog.records if "records its SHA-256" in r.message
    ]
    assert infos == [
        f"ID registry: model {MODEL_NAME}: no registry entry records its SHA-256; "
        "a new id is used"
    ]
