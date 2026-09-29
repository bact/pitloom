# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One package name held by several elements of one document.

A name-keyed registry cannot pin a name several looking-up elements hold:
ids swapped between runs whenever harvest kept one element (the last in
``spdxId`` order) and lookup handed the id to another (the first
claimant). Harvest leaves such a name alone; a pinned id goes to the first
claimant, with the claim ``WARNING:``. A self-referencing extra, or a
phantom named like another package, never looks up, so run auto-harvest
writes the name for the package that does.

See also: :mod:`tests.id_registry.test_package_ids` (the single-owner
cases), :mod:`tests.id_registry.test_package_ids_non_readers` (packages
that never look up).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.id_registry import PACKAGE_ENTITY_TYPE, IdRegistry
from pitloom.id_registry._ambiguous import _ambiguous_entity_keys
from tests.assemble.conftest import _make_dummy_wheel
from tests.id_registry.package_ids_base import (
    MAIN,
    build_doc,
    claim_warnings,
    make_doc,
    new_registry,
    package_entries,
    packages,
    phantom,
    project_with_dependencies,
    root_element_id,
    sbom_packages,
    wheel_with_libs,
)
from tests.id_registry.surfaces_base import DEPENDENCY

#: Runs are compared byte for byte.
pytestmark = pytest.mark.usefixtures("fixed_epoch")

_SELF_EXTRA = f"{MAIN}[x]; extra == 'all'"
_TWO_VERSIONS = ['foo==1.0; python_version<"3.10"', 'foo==2.0; python_version>="3.10"']


@pytest.fixture(name="pin_namespace", params=["a", "zz"])
def _pin_namespace(request: pytest.FixtureRequest) -> str:
    """Project name of a pin registry: its ids sort before ("a") or after
    ("zz") the document's own ids in spdxId order. "a" is the case a
    last-one-wins harvest got wrong."""
    return str(request.param)


def _wheel(tmp_path: Path, requires: list[str]) -> Path:
    return _make_dummy_wheel(
        tmp_path / "dist", MAIN, "1.0.0", requires_dist=tuple(requires)
    )


def _names(sbom_json: str) -> list[str]:
    return [p.name for p in sbom_packages(sbom_json)]


# --- (A) self-referencing extra ---------------------------------------


def test_wheel_self_referencing_extra_keeps_root_id_stable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry_path, _ = new_registry(tmp_path)
    wheel = _wheel(tmp_path, [f"{DEPENDENCY}==1.0", _SELF_EXTRA])

    with caplog.at_level("WARNING"):
        runs = [generate_wheel_sbom(wheel, id_registry=registry_path) for _ in range(3)]

    assert _names(runs[0]).count(MAIN) == 2  # non-vacuous: main + self-dependency
    assert len({root_element_id(run) for run in runs}) == 1
    assert runs[1] == runs[0]
    assert runs[2] == runs[0]
    entries = package_entries(registry_path)
    assert set(entries) == {DEPENDENCY, MAIN}
    assert entries[MAIN] == root_element_id(runs[0])  # the main package, pinned
    assert not claim_warnings(caplog)


def test_wheel_self_referencing_extra_uses_pinned_main_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pin_namespace: str
) -> None:
    registry_path, (pinned,) = new_registry(tmp_path, [MAIN], pin_namespace)
    wheel = _wheel(tmp_path, [_SELF_EXTRA])

    with caplog.at_level("WARNING"):
        runs = [generate_wheel_sbom(wheel, id_registry=registry_path) for _ in range(2)]

    for run in runs:
        assert root_element_id(run) == pinned
        assert [p.spdx_id for p in sbom_packages(run)].count(pinned) == 1
    assert package_entries(registry_path) == {MAIN: pinned}
    assert not claim_warnings(caplog)


def test_project_then_wheel_self_referencing_extra_keeps_project_root_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Alternating surfaces: the project run (its extra is not a dependency
    of the main package) pins ``demo``; the wheel run reuses that id for
    its root."""
    registry_path, _ = new_registry(tmp_path)
    project = project_with_dependencies(tmp_path / "run", [DEPENDENCY + "==1.0"])
    wheel = _wheel(tmp_path, [f"{DEPENDENCY}==1.0", _SELF_EXTRA])

    with caplog.at_level("WARNING"):
        generate_project_sbom(
            project, creation_metadata=None, id_registry=registry_path
        )
        pinned = package_entries(registry_path)[MAIN]
        for _ in range(2):
            run = generate_wheel_sbom(wheel, id_registry=registry_path)
            assert root_element_id(run) == pinned
    assert package_entries(registry_path)[MAIN] == pinned
    assert not claim_warnings(caplog)


# --- (B) same name, different versions --------------------------------


def _alternate(tmp_path: Path, registry_path: Path) -> list[tuple[str, str]]:
    project = project_with_dependencies(tmp_path / "run", _TWO_VERSIONS)
    wheel = _wheel(tmp_path, _TWO_VERSIONS)
    outputs = []
    for surface in ["project", "wheel"] * 3:
        if surface == "project":
            sbom = generate_project_sbom(
                project, creation_metadata=None, id_registry=registry_path
            )
        else:
            sbom = generate_wheel_sbom(wheel, id_registry=registry_path)
        outputs.append((surface, sbom))
    return outputs


def test_same_name_two_versions_is_stable_across_runs_and_surfaces(
    tmp_path: Path,
) -> None:
    registry_path, _ = new_registry(tmp_path)

    outputs = _alternate(tmp_path, registry_path)

    by_surface: dict[str, set[str]] = {}
    for surface, sbom in outputs:
        assert _names(sbom).count("foo") == 2  # non-vacuous
        by_surface.setdefault(surface, set()).add(sbom)
    # Same surface, same bytes: run 1 of the two is the one that harvests.
    assert all(len(runs) == 1 for runs in by_surface.values())
    entries = package_entries(registry_path)
    assert "foo" not in entries
    assert MAIN in entries


def test_same_name_two_versions_pinned_id_goes_to_first_claimant(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, pin_namespace: str
) -> None:
    registry_path, (pinned,) = new_registry(tmp_path, ["foo"], pin_namespace)

    with caplog.at_level("WARNING"):
        outputs = _alternate(tmp_path, registry_path)

    holders = set()
    for _surface, sbom in outputs:
        foo = [p for p in sbom_packages(sbom) if p.name == "foo"]
        holders.add(tuple(p.version for p in foo if p.spdx_id == pinned))
    assert holders == {("1.0",)}  # one holder, the same version, every run
    assert package_entries(registry_path)["foo"] == pinned
    assert len(claim_warnings(caplog)) == len(outputs)


# --- (C) a phantom dependency sharing a name --------------------------


@pytest.mark.parametrize(
    "doc_kwargs",
    [
        {"dependencies": ["libfoo==1.0"], "phantom": [phantom("libfoo", "1")]},
        {"name": "libfoo", "phantom": [phantom("Libfoo", "1")]},
    ],
    ids=["dependency", "main"],
)
def test_phantom_sharing_a_name_with_a_pin_never_looks_up(
    doc_kwargs: dict[str, Any], pin_namespace: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The dependency or main package owns the name and takes the pin; the
    phantom mints its own id, silently."""
    registry = IdRegistry.new(pin_namespace)
    pinned = registry.register_entity("libfoo", PACKAGE_ENTITY_TYPE)
    doc = make_doc(**doc_kwargs)

    with caplog.at_level("WARNING"):
        first = build_doc(doc, registry)
        registry.harvest(first.object_set)
        second = build_doc(doc, registry)

    assert second.to_json() == first.to_json()
    holders = [p for p in packages(first) if p.spdx_id == pinned]
    assert len(holders) == 1
    assert holders[0].version != "1"  # not the phantom
    assert registry.lookup_entity("libfoo", PACKAGE_ENTITY_TYPE) == pinned
    assert not claim_warnings(caplog)


def test_wheel_with_phantom_dependencies_is_stable_with_a_registry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """End to end: ``libz`` is a plain phantom package (pinned), ``fakedep``
    is both declared and bundled: the declared package is pinned, the
    phantom never looks up and is never written."""
    registry_path, _ = new_registry(tmp_path)
    wheel = wheel_with_libs(
        tmp_path / "dist", [f"{DEPENDENCY}==1.0"], ["libz", DEPENDENCY]
    )

    with caplog.at_level("WARNING"):
        runs = [generate_wheel_sbom(wheel, id_registry=registry_path) for _ in range(3)]

    names = _names(runs[0])
    assert "libz" in names  # non-vacuous: phantom dependencies were found
    assert names.count(DEPENDENCY) == 2
    assert runs[1] == runs[0]
    assert runs[2] == runs[0]
    entries = package_entries(registry_path)
    assert "libz" in entries
    (declared,) = [
        p for p in sbom_packages(runs[0]) if p.name == DEPENDENCY and p.version == "1.0"
    ]
    assert entries[DEPENDENCY] == declared.spdx_id
    assert not claim_warnings(caplog)


@pytest.mark.parametrize("libs", [[DEPENDENCY], [MAIN]], ids=["dependency", "main"])
def test_alternating_project_and_wheel_with_a_phantom_named_like_another_package(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    pin_namespace: str,
    libs: list[str],
) -> None:
    """A bundled library named like a dependency or the project never
    looks up: pinned ids stay with the declared and main packages and no
    surface warns."""
    registry_path, pinned = new_registry(tmp_path, [MAIN, DEPENDENCY], pin_namespace)
    project = project_with_dependencies(tmp_path / "run", [f"{DEPENDENCY}==1.0"])
    wheel = wheel_with_libs(tmp_path / "dist", [f"{DEPENDENCY}==1.0"], libs)

    with caplog.at_level("WARNING"):
        wheels = []
        for _ in range(3):
            generate_project_sbom(
                project, creation_metadata=None, id_registry=registry_path
            )
            wheels.append(generate_wheel_sbom(wheel, id_registry=registry_path))

    assert _names(wheels[0]).count(libs[0]) == 2  # non-vacuous: phantom present
    assert wheels[1] == wheels[0]
    assert wheels[2] == wheels[0]
    assert root_element_id(wheels[0]) == pinned[0]
    assert package_entries(registry_path) == {MAIN: pinned[0], DEPENDENCY: pinned[1]}
    assert not claim_warnings(caplog)


# --- harvest itself ----------------------------------------------------


def _write_sbom(tmp_path: Path, doc_kwargs: dict[str, Any]) -> Path:
    sbom_path = tmp_path / "two-foo.spdx3.json"
    sbom_path.write_text(build_doc(make_doc(**doc_kwargs), None).to_json(), "utf-8")
    return sbom_path


def test_import_sbom_does_not_write_an_ambiguous_name(tmp_path: Path) -> None:
    sbom_path = _write_sbom(tmp_path, {"dependencies": ["foo==1.0", "Foo==2.0", "bar"]})
    registry = IdRegistry.new("r")

    skipped = registry.import_sbom(sbom_path)

    assert skipped == {(PACKAGE_ENTITY_TYPE, "foo")}
    assert registry.lookup_entity("foo", PACKAGE_ENTITY_TYPE) is None
    assert registry.lookup_entity("bar", PACKAGE_ENTITY_TYPE) is not None
    assert registry.lookup_entity(MAIN, PACKAGE_ENTITY_TYPE) is not None


def test_import_sbom_leaves_an_existing_ambiguous_entry_untouched(
    tmp_path: Path,
) -> None:
    sbom_path = _write_sbom(tmp_path, {"dependencies": ["foo==1.0", "Foo==2.0"]})
    registry = IdRegistry.new("r")
    pinned = registry.register_entity("foo", PACKAGE_ENTITY_TYPE)
    before = dict(registry.entities)

    registry.import_sbom(sbom_path)

    assert registry.lookup_entity("foo", PACKAGE_ENTITY_TYPE) == pinned
    assert {k: v for k, v in registry.entities.items() if k in before} == before


def test_ambiguous_entity_keys_counts_only_named_typed_non_file_elements() -> None:
    class Named:
        def __init__(self, name: str | None, spdx_id: str | None = "urn:x") -> None:
            self.name = name
            self.spdxId = spdx_id

        def get_compact_type(self) -> str:
            return "software_Package"

    class Untyped(Named):
        def get_compact_type(self) -> str:
            return "object"

    objects = [
        Named("Foo_Bar"),
        Named("foo-bar"),
        Named("solo"),
        Named(None),
        Named("no-id", None),
        Untyped("foo-bar"),
        Untyped("foo-bar"),
    ]

    assert _ambiguous_entity_keys(objects) == {(PACKAGE_ENTITY_TYPE, "foo-bar")}
