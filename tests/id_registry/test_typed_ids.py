# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Registry drift guards (id-registry-v3 D2, section 7): every surface's
output carries typed ids, every lookup type is a type the registry can
hold, and a registry run twice stops changing.

See also: tests/id_registry/test_typed_ids_round_trip.py (seed, regenerate,
same ids), tests/id_registry/test_lookup_table.py (the type and gate each
surface looks up), tests/id_registry/surfaces_shared.py (the runners).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.assemble import enrich_model, generate_project_sbom, generate_wheel_sbom
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import FILE_TYPE, PACKAGE_TYPE, IdRegistry, type_id_prefix
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.id_registry.surfaces_base import (
    _run_cli,
    demo_project,
    demo_wheel,
    seed_registry,
)
from tests.id_registry.surfaces_shared import (
    MODEL_RUNNERS,
    SURFACES,
    declare_via,
)

_PROJECT = frozenset({"File", "Package"})
_WHEEL = _PROJECT
_MODEL = frozenset({"AIPackage"})

#: Surface -> the element kinds (type prefixes) its run must emit with an
#: id from the registry's namespace; a new surface has to be added here.
_EXPECTED_KINDS: dict[str, frozenset[str]] = {
    "cli-project": _PROJECT,
    "cli-project-sdist": frozenset({"Package"}),  # files sit under demo-1.0.0/
    "cli-generate": _PROJECT,
    "cli-wheel": _WHEEL,
    "cli-wheel-embed": _WHEEL,
    "cli-env": frozenset({"Package"}),
    "cli-model": _MODEL,
    "cli-embed-wheel-project": _WHEEL,
    "cli-embed-wheel-standalone": _WHEEL,
    "lib-generate": _PROJECT,
    "lib-generate_project_sbom": _PROJECT,
    "lib-generate_wheel_sbom": _WHEEL,
    "lib-generate_env_sbom": frozenset({"Package"}),
    "lib-generate_model_sbom": _MODEL,
    "lib-embed_wheel_sbom": _WHEEL,
    "hook": _PROJECT,
    "project-with-model": _PROJECT | _MODEL,
    "wheel-with-model": _WHEEL | _MODEL,
    "loom-with-model": _MODEL | {"File"},
}
#: Enrichment fragments point at the base document's AI package without
#: defining it; see :func:`test_enrich_fragment_points_at_a_typed_id`.
_REFERENCE_ONLY = frozenset(
    {"cli-enrich-standalone", "cli-enrich-project", "lib-enrich_model"}
)
#: Surfaces that write a registry rather than an SBOM, and a loom run
#: that names no model (it emits nothing registry-backed).
_NOT_GENERATING = frozenset({"cli-id-generate", "cli-id-import", "loom-run"})

_Runner = Callable[[Path, pytest.MonkeyPatch, Any], object]


def _runner(name: str) -> _Runner:
    return SURFACES[name] if name in SURFACES else MODEL_RUNNERS[name]


def run_capturing(
    name: str, tmp_path: Path, mp: pytest.MonkeyPatch, registry: Path
) -> list[str]:
    """Run surface *name* against *registry*; return every SBOM it serialised."""
    sboms: list[str] = []
    real = Spdx3JsonExporter.to_json

    def spy(self: Spdx3JsonExporter, *args: Any, **kwargs: Any) -> str:
        out = real(self, *args, **kwargs)
        sboms.append(out)
        return out

    mp.setattr(Spdx3JsonExporter, "to_json", spy)
    result = _runner(name)(tmp_path, mp, declare_via(name, registry))
    assert result in (None, 0)  # a CLI-backed runner returns its exit code
    return sboms


def _graph(sbom: str) -> list[dict[str, Any]]:
    return list(json.loads(sbom)["@graph"])


def _fragment_prefix(spdx_id: str) -> str:
    """``File`` for ``https://x/y#File-12``."""
    return spdx_id.partition("#")[2].rpartition("-")[0]


def test_every_generating_surface_is_covered() -> None:
    covered = set(_EXPECTED_KINDS) | _REFERENCE_ONLY
    assert covered == (set(SURFACES) - _NOT_GENERATING) | set(MODEL_RUNNERS)


@pytest.mark.parametrize("name", list(_EXPECTED_KINDS))
def test_registry_namespace_ids_carry_their_type_prefix(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2 on the output: inside the registry's namespace the fragment prefix
    is the element type's own prefix; foreign ids are not looked at."""
    registry = seed_registry(tmp_path)
    namespace = IdRegistry.load(registry).namespace

    sboms = run_capturing(name, tmp_path, monkeypatch, registry)

    checked = [
        (node["type"], node["spdxId"])
        for sbom in sboms
        for node in _graph(sbom)
        if str(node.get("spdxId", "")).startswith(f"{namespace}#")
    ]
    wrong = [
        (type_name, spdx_id)
        for type_name, spdx_id in checked
        if _fragment_prefix(spdx_id) != type_id_prefix(type_name)
    ]
    assert wrong == []
    # Non-vacuous: the kinds this surface emits did come from the registry.
    assert {type_id_prefix(type_name) for type_name, _ in checked} >= (
        _EXPECTED_KINDS[name]
    )


@pytest.mark.parametrize("name", ["project-with-model", "wheel-with-model"])
def test_ids_the_registry_stores_keep_their_type_prefix(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-harvest never files an id under another type: each stored id's
    fragment starts with its key's own type prefix."""
    registry = tmp_path / "ids.json"
    IdRegistry.new("demo").save(registry)

    run_capturing(name, tmp_path, monkeypatch, registry)

    stored = IdRegistry.load(registry).elements
    assert {type_name for type_name, _ in stored} >= {
        "software_File",
        "software_Package",
    }
    for (type_name, _), entry in stored.items():
        fragment = entry.spdx_id.partition("#")[2]
        assert fragment.startswith(f"{type_id_prefix(type_name)}-"), entry.spdx_id


def _enrich(
    variant: str, tmp_path: Path, mp: pytest.MonkeyPatch, registry: Path
) -> str:
    """Enrich a model that has a README naming a dataset, so the fragment has
    something to say about the registry-backed AI package."""
    model_dir = tmp_path / "hub"
    model_dir.mkdir()
    model = model_dir / SAFETENSORS_FIXTURE.name
    shutil.copyfile(SAFETENSORS_FIXTURE, model)
    (model_dir / "README.md").write_text(
        "---\nlicense: mit\ndatasets:\n  - squad\n---\n# M\n", encoding="utf-8"
    )
    if variant == "api":
        return enrich_model(model, id_registry=registry)
    out = tmp_path / "enriched.spdx3.json"
    argv = ["enrich", str(model), "-o", str(out), "--id-registry", str(registry)]
    if variant == "cli-project":
        argv += ["--project-dir", str(demo_project(tmp_path))]
    assert _run_cli(mp, argv) == 0
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("variant", ["api", "cli", "cli-project"])
def test_enrich_fragment_points_at_a_typed_id(
    variant: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = seed_registry(tmp_path)
    namespace = IdRegistry.load(registry).namespace

    graph = _graph(_enrich(variant, tmp_path, monkeypatch, registry))

    # What a relationship starts from is the base document's AI package.
    origins = [n["from"] for n in graph if n.get("type") == "Relationship"]
    in_registry = [i for i in origins if i.startswith(f"{namespace}#")]
    assert in_registry  # non-vacuous
    assert {_fragment_prefix(i) for i in in_registry} == {"AIPackage"}


# --- Lookup types are types the registry can hold -------------------------

_LOOKUP_RUNS = ["project-with-model", "wheel-with-model", "lib-generate_model_sbom"]


@pytest.mark.parametrize("name", [*_LOOKUP_RUNS, "loom-with-model"])
def test_lookup_types_are_types_a_run_writes_back(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A type looked up but never written (by auto-harvest or by importing
    the run's own SBOM) could only ever miss."""
    registry = tmp_path / "ids.json"
    IdRegistry.new("demo").save(registry)
    real = IdRegistry.lookup

    with patch.object(IdRegistry, "lookup", autospec=True, side_effect=real) as spy:
        sboms = run_capturing(name, tmp_path, monkeypatch, registry)
    looked_up = {call.args[1] for call in spy.call_args_list}

    written = {type_name for type_name, _ in IdRegistry.load(registry).elements}
    for index, sbom in enumerate(sboms):
        path = tmp_path / f"run-{index}.spdx3.json"
        path.write_text(sbom, encoding="utf-8")
        imported = IdRegistry.new("imported")
        imported.import_sbom(path)
        written |= {type_name for type_name, _ in imported.elements}
    assert looked_up  # non-vacuous
    assert looked_up <= written


# --- A registry settles: further runs leave it as it is --------------------


def _runs(tmp_path: Path) -> dict[str, Callable[[Path], object]]:
    project, wheel = demo_project(tmp_path), demo_wheel(tmp_path)
    return {
        "project": lambda reg: generate_project_sbom(
            project, creation_metadata=None, id_registry=reg
        ),
        "wheel": lambda reg: generate_wheel_sbom(wheel, id_registry=reg),
    }


def _seed_by_id_generate(
    tmp_path: Path, mp: pytest.MonkeyPatch, registry: Path
) -> None:
    project = tmp_path / "proj"
    argv = ["id", "generate", str(project / "demo"), "--project-dir", str(project)]
    assert _run_cli(mp, [*argv, "-o", str(registry)]) == 0


@pytest.mark.parametrize("surface", ["project", "wheel"])
def test_the_third_run_leaves_the_registry_as_the_second_did(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _runs(tmp_path)[surface]
    registry = tmp_path / "ids.json"
    _seed_by_id_generate(tmp_path, monkeypatch, registry)
    seeded = registry.read_bytes()

    run(registry)
    first = registry.read_bytes()
    run(registry)
    second = registry.read_bytes()
    run(registry)

    assert first != seeded  # non-vacuous: the first run did add to it
    assert registry.read_bytes() == second


def test_alternating_surfaces_never_rewrite_a_settled_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once each surface has recorded what it knows, running them in turn
    saves nothing: a run that erased what the other recorded (a hash, say)
    would have it restored, and the file rewritten, every time."""
    runs = _runs(tmp_path)
    registry = tmp_path / "ids.json"
    _seed_by_id_generate(tmp_path, monkeypatch, registry)
    seeded = registry.read_bytes()
    for _ in range(2):  # settle: each surface gets to add what it knows
        runs["project"](registry)
        runs["wheel"](registry)
    settled = registry.read_bytes()

    with patch.object(IdRegistry, "save", autospec=True) as save:
        for _ in range(2):
            runs["project"](registry)
            runs["wheel"](registry)

    assert settled != seeded
    assert save.call_count == 0
    assert registry.read_bytes() == settled


_SRC_LAYOUT_TOML = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "demo"
version = "1.0.0"
[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
"""


def test_project_and_wheel_package_hashes_never_flip_the_registry(
    tmp_path: Path,
) -> None:
    """A src-layout project with a file its wheel lacks: the two main
    packages' Merkle roots differ. No lookup gates a package, so neither
    root is recorded, and alternating runs leave the package and file
    entries as they are."""
    project = tmp_path / "src-proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "pyproject.toml").write_text(_SRC_LAYOUT_TOML, encoding="utf-8")
    (project / "src" / "demo" / "__init__.py").write_bytes(_WHEEL_INIT)
    (project / "src" / "demo" / "extra.py").write_bytes(b"y = 2\n")
    wheel = demo_wheel(tmp_path)
    registry = tmp_path / "ids.json"
    IdRegistry.new("demo").save(registry)

    def gated_and_packages() -> dict[tuple[str, str], Any]:
        elements = IdRegistry.load(registry).elements
        return {k: e for k, e in elements.items() if k[0] in _SETTLED_TYPES}

    tables = []
    for _ in range(3):  # the first round settles: each run adds its files
        generate_project_sbom(project, creation_metadata=None, id_registry=registry)
        tables.append(gated_and_packages())
        generate_wheel_sbom(wheel, id_registry=registry)
        tables.append(gated_and_packages())

    assert tables[2:] == tables[1:2] * 4
    package = tables[-1].get((PACKAGE_TYPE, "demo"))
    assert package is not None and package.sha256 is None


#: The types whose entries a project and a wheel run of one package share.
_SETTLED_TYPES = frozenset({FILE_TYPE, PACKAGE_TYPE})
#: ``demo/__init__.py`` as ``demo_wheel`` writes it.
_WHEEL_INIT = b"__version__ = '1.0.0'\n"
