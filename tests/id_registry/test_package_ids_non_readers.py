# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Packages that never look the registry up do not make a name ambiguous
for run auto-harvest.

A self-referencing dependency, and a phantom dependency named like the
project or a dependency, mint their own id without a lookup (their name
belongs to another package of the document). Run auto-harvest neither
counts nor writes them, so the one package that does look the name up is
written and pinned on the next run. ``id import`` has no such knowledge and
still skips every multi-holder name.

See also: :mod:`tests.id_registry.test_package_ids_ambiguous` (names held by
several packages that all look up).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import PACKAGE_ENTITY_TYPE, IdRegistry
from tests.assemble.conftest import _make_dummy_wheel
from tests.extract.conftest import make_hook
from tests.id_registry.package_ids_base import (
    MAIN,
    build_doc,
    make_doc,
    package_entries,
    packages,
    phantom,
    project_with_dependencies,
    root_element_id,
    sbom_packages,
)
from tests.id_registry.surfaces_base import DEPENDENCY

#: Runs are compared byte for byte.
pytestmark = pytest.mark.usefixtures("fixed_epoch")

_SELF_EXTRA = f"{MAIN}[x]; extra == 'all'"

#: doc kwargs -> the name one reader and one non-reader share.
_SHARED_NAME_DOCS: dict[str, tuple[dict[str, Any], str]] = {
    "self-referencing-dependency": ({"dependencies": [_SELF_EXTRA]}, MAIN),
    "phantom-like-project": ({"phantom": [phantom("Demo", "1")]}, MAIN),
    "phantom-like-dependency": (
        {"dependencies": ["libfoo==1.0"], "phantom": [phantom("libfoo", "1")]},
        "libfoo",
    ),
}


def _root_id(exporter: Spdx3JsonExporter) -> str:
    return root_element_id(exporter.to_json())


def _harvest(exporter: Spdx3JsonExporter, registry: IdRegistry) -> None:
    """Run auto-harvest, as every generator does after building."""
    _sync_registry(exporter, registry, True)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]


# --- which ids are non-readers -------------------------------------------


@pytest.mark.parametrize("pins", [None, [MAIN, "libfoo", "libz"]], ids=["none", "pins"])
def test_non_readers_are_exactly_the_packages_that_never_looked_up(
    pins: list[str] | None,
) -> None:
    registry = None
    if pins is not None:
        registry = IdRegistry.new("pins")
        for name in pins:
            registry.register_entity(name, PACKAGE_ENTITY_TYPE)
    doc = make_doc(
        dependencies=["libfoo==1.0", _SELF_EXTRA],
        phantom=[phantom("Demo", "1"), phantom("libfoo", "1"), phantom("libz", "1")],
    )

    exporter = build_doc(doc, registry)

    root = _root_id(exporter)
    expected = {
        p.spdx_id
        for p in packages(exporter)
        if (p.name == MAIN and p.spdx_id != root)
        or (p.version == "1" and p.name in {"Demo", "libfoo"})
    }
    assert len(expected) == 3  # non-vacuous: self-dependency and two phantoms
    assert exporter.registry_non_readers == expected


def test_two_versions_of_one_dependency_both_look_up(tmp_path: Path) -> None:
    doc = make_doc(dependencies=["foo==1.0", "Foo==2.0"])
    registry = IdRegistry.new("r", tmp_path / "registry.json")

    exporter = build_doc(doc, registry)
    _harvest(exporter, registry)

    assert [p.name.lower() for p in packages(exporter)].count("foo") == 2
    assert not exporter.registry_non_readers
    assert registry.lookup_entity("foo", PACKAGE_ENTITY_TYPE) is None
    assert registry.lookup_entity(MAIN, PACKAGE_ENTITY_TYPE) == _root_id(exporter)


# --- run auto-harvest writes the owner -----------------------------------


@pytest.mark.parametrize(
    ("doc_kwargs", "name"), _SHARED_NAME_DOCS.values(), ids=list(_SHARED_NAME_DOCS)
)
def test_run_harvest_writes_the_owner_and_never_the_non_reader(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    doc_kwargs: dict[str, Any],
    name: str,
) -> None:
    doc = make_doc(**doc_kwargs)
    registry = IdRegistry.new("r", tmp_path / "registry.json")

    with caplog.at_level("WARNING"):
        first = build_doc(doc, registry)
        _harvest(first, registry)
        second = build_doc(doc, registry)
        _harvest(second, registry)
        third = build_doc(doc, registry)

    holders = [p for p in packages(first) if p.name.lower() == name]
    assert len(holders) == 2  # non-vacuous: one reader, one non-reader
    (non_reader,) = first.registry_non_readers
    (owner,) = [p.spdx_id for p in holders if p.spdx_id != non_reader]
    assert registry.lookup_entity(name, PACKAGE_ENTITY_TYPE) == owner
    written = {entry.spdx_id for entry in registry.entities.values()}
    assert non_reader not in written
    assert second.to_json() == first.to_json()
    assert third.to_json() == first.to_json()
    assert not _warnings(caplog)


# --- end to end: run 2 pins what run 1 harvested -------------------------


def _self_referencing_run(surface: str, tmp_path: Path, registry: Path) -> str:
    requires = [f"{DEPENDENCY}==1.0", _SELF_EXTRA]
    if surface == "wheel":
        wheel = _make_dummy_wheel(
            tmp_path / "dist", MAIN, "1.0.0", requires_dist=tuple(requires)
        )
        return generate_wheel_sbom(wheel, id_registry=registry)
    project = project_with_dependencies(tmp_path / "run", requires)
    return generate_project_sbom(project, creation_metadata=None, id_registry=registry)


@pytest.mark.parametrize("surface", ["project", "wheel"])
def test_self_referencing_dependency_main_package_is_pinned_on_run_two(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, surface: str
) -> None:
    registry_path = tmp_path / "registry.json"
    IdRegistry.new("r").save(registry_path)

    with caplog.at_level("WARNING"):
        first = _self_referencing_run(surface, tmp_path, registry_path)
        after_first = package_entries(registry_path)
        second = _self_referencing_run(surface, tmp_path, registry_path)
        registry_bytes = registry_path.read_bytes()
        third = _self_referencing_run(surface, tmp_path, registry_path)

    assert [p.name for p in sbom_packages(first)].count(MAIN) == 2  # non-vacuous
    assert after_first[MAIN] == root_element_id(first)
    assert root_element_id(second) == after_first[MAIN]
    assert second == first
    assert third == second
    assert registry_path.read_bytes() == registry_bytes
    assert not _warnings(caplog)


def test_hook_pins_the_main_package_a_project_run_harvested(tmp_path: Path) -> None:
    """The hook never harvests; it reads what a project run wrote."""
    registry_path = tmp_path / "registry.json"
    IdRegistry.new("r").save(registry_path)
    project = project_with_dependencies(tmp_path / "run", [_SELF_EXTRA])
    with (project / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write(f"\n[tool.pitloom]\nid-registry = {json.dumps(str(registry_path))}\n")
    generate_project_sbom(project, creation_metadata=None)
    pinned = package_entries(registry_path)[MAIN]

    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    staging = hook._sbom_staging_path  # pylint: disable=protected-access
    assert staging is not None
    sbom_json = staging.read_text(encoding="utf-8")
    hook.finalize("standard", build_data, "")

    assert [p.name for p in sbom_packages(sbom_json)].count(MAIN) == 2
    assert root_element_id(sbom_json) == pinned
