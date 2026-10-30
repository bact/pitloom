# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``software_Package`` ids -- the project's own main package, its declared
and lock-resolved dependencies, and its phantom dependencies -- come from
the declared ID registry, the same way ``env``'s do: a pinned id survives a
project or wheel run, alternating runs do not churn the package entries,
and the direct ``build()`` claim rules (first claimant wins, registry ids
are reserved before anything is minted).

See also: :mod:`tests.id_registry.test_package_ids_ambiguous` (one name held
by several elements of one document),
:mod:`tests.id_registry.test_surfaces_same_ids` (one snapshot, every
surface), :mod:`tests.id_registry.test_session` (claim mechanics).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.id_registry import PACKAGE_TYPE, IdRegistry, RegistryEntry
from tests.assemble.conftest import _make_sdist
from tests.id_registry.package_ids_base import (
    MAIN,
    build_doc,
    claim_warnings,
    make_doc,
    new_registry,
    package_entries,
    packages,
    phantom,
    root_element_id,
    sbom_package_ids,
    sbom_packages,
)
from tests.id_registry.surfaces_base import (
    DEPENDENCY,
    DEPENDENCY_KEY,
    MAIN_KEY,
    _run_cli,
    demo_project,
    demo_wheel,
)

# --- pinned ids survive, project and wheel ---------------------------


def test_pinned_ids_survive_project_run_via_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = demo_project(tmp_path / "run")
    registry_path = tmp_path / "registry.json"
    monkeypatch.chdir(project)
    assert (
        _run_cli(
            monkeypatch,
            [
                "id",
                "generate",
                "demo",
                "--project-dir",
                str(project),
                "--id-registry",
                str(registry_path),
                "-e",
                f"{DEPENDENCY}@1.0:software_Package",
                "-e",
                f"{MAIN}@1.0.0:software_Package",
            ],
        )
        == 0
    )
    pinned = package_entries(registry_path)
    assert set(pinned) == {DEPENDENCY_KEY, MAIN_KEY}

    out = tmp_path / "out.spdx3.json"
    assert (
        _run_cli(
            monkeypatch,
            ["project", str(project), "--id-registry", str(registry_path)]
            + ["-o", str(out)],
        )
        == 0
    )

    assert package_entries(registry_path) == pinned
    emitted = sbom_package_ids(out.read_text(encoding="utf-8"))
    assert emitted[DEPENDENCY] == pinned[DEPENDENCY_KEY]
    assert emitted[MAIN] == pinned[MAIN_KEY]
    # Non-vacuous: a registry-free run mints different ids.
    free = sbom_package_ids(generate_project_sbom(project, creation_metadata=None))
    assert free[DEPENDENCY] != pinned[DEPENDENCY_KEY]
    assert free[MAIN] != pinned[MAIN_KEY]


def test_pinned_ids_survive_wheel_run(tmp_path: Path) -> None:
    registry_path, _ = new_registry(tmp_path, [DEPENDENCY_KEY, MAIN_KEY])
    pinned = package_entries(registry_path)
    wheel = demo_wheel(tmp_path / "run")

    sbom_json = generate_wheel_sbom(wheel, id_registry=registry_path)

    assert package_entries(registry_path) == pinned
    emitted = sbom_package_ids(sbom_json)
    assert emitted[DEPENDENCY] == pinned[DEPENDENCY_KEY]
    assert emitted[MAIN] == pinned[MAIN_KEY]
    free = sbom_package_ids(generate_wheel_sbom(wheel))
    assert free[DEPENDENCY] != pinned[DEPENDENCY_KEY]
    assert free[MAIN] != pinned[MAIN_KEY]


@pytest.mark.parametrize("surface", ["project", "wheel"])
def test_main_package_id_comes_from_registry(tmp_path: Path, surface: str) -> None:
    registry_path, (main_id,) = new_registry(tmp_path, [MAIN_KEY])

    if surface == "project":
        sbom_json = generate_project_sbom(
            demo_project(tmp_path / "run"),
            creation_metadata=None,
            id_registry=registry_path,
        )
    else:
        sbom_json = generate_wheel_sbom(
            demo_wheel(tmp_path / "run"), id_registry=registry_path
        )

    assert sbom_package_ids(sbom_json)[MAIN] == main_id
    # The main package is the SBOM's root element, so the id is wired in.
    assert root_element_id(sbom_json) == main_id


# --- sdist --------------------------------------------------------------


def test_generate_on_an_sdist_takes_package_ids_from_the_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_path, (main_id, dep_id) = new_registry(
        tmp_path, [MAIN_KEY, DEPENDENCY_KEY]
    )
    pkg_info = (
        f"Metadata-Version: 2.1\nName: {MAIN}\nVersion: 1.0.0\n"
        f"Requires-Dist: {DEPENDENCY}==1.0\n"
    )
    sdist = _make_sdist(
        tmp_path,
        members={
            "PKG-INFO": pkg_info.encode(),
            "demo/__init__.py": b"__version__ = '1.0.0'\n",
        },
    )
    out = tmp_path / "out.spdx3.json"
    monkeypatch.chdir(tmp_path)

    code = _run_cli(
        monkeypatch,
        ["generate", str(sdist), "--id-registry", str(registry_path), "-o", str(out)],
    )

    assert code == 0
    emitted = {p.name: p.spdx_id for p in sbom_packages(out.read_text("utf-8"))}
    assert emitted[MAIN] == main_id
    assert emitted[DEPENDENCY] == dep_id
    assert package_entries(registry_path) == {MAIN_KEY: main_id, DEPENDENCY_KEY: dep_id}
    # Non-vacuous: without the registry the ids differ.
    free = {p.name: p.spdx_id for p in sbom_packages(generate_project_sbom(sdist))}
    assert free[MAIN] != main_id


# --- no churn ----------------------------------------------------------


def test_no_package_churn_across_alternating_project_and_wheel_runs(
    tmp_path: Path,
) -> None:
    """A registry with no package entries is filled by the first run's
    harvest; the later runs of the *other* surface (a different document,
    so different freshly minted ids) leave the package entries alone and
    emit the very same ids."""
    registry_path, _ = new_registry(tmp_path)
    initial_bytes = registry_path.read_bytes()
    project = demo_project(tmp_path / "run")
    wheel = demo_wheel(tmp_path / "run")

    def run(surface: str) -> str:
        if surface == "project":
            return generate_project_sbom(
                project, creation_metadata=None, id_registry=registry_path
            )
        return generate_wheel_sbom(wheel, id_registry=registry_path)

    first = run("project")
    harvested = package_entries(registry_path)
    # Non-vacuous: the first harvest changed the registry and stored both,
    # each under its name and version.
    assert registry_path.read_bytes() != initial_bytes
    assert set(harvested) == {DEPENDENCY_KEY, MAIN_KEY}
    by_name = {DEPENDENCY: harvested[DEPENDENCY_KEY], MAIN: harvested[MAIN_KEY]}
    assert sbom_package_ids(first) == by_name

    for surface in ("wheel", "project", "wheel"):
        emitted = sbom_package_ids(run(surface))
        assert emitted == by_name, surface
        assert package_entries(registry_path) == harvested, surface


# --- direct build(): overlap and reservation ---------------------------


def test_registry_without_package_entries_changes_nothing() -> None:
    """A registry that knows no package is the same as no registry."""
    doc = make_doc(
        dependencies=["Fake_Dep==1.0", "other>=2"],
        locked=["locked-lib==3.0"],
        phantom=[phantom("libz", "1.2")],
    )

    without = build_doc(doc, None).to_json()
    with_empty = build_doc(doc, IdRegistry.new("empty")).to_json()

    assert with_empty == without


def test_non_canonical_dependency_name_hits_canonical_key() -> None:
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, "fake-dep@1.0")
    other = registry.register(PACKAGE_TYPE, "OTHER")

    exporter = build_doc(make_doc(dependencies=["Fake_Dep==1.0", "other>=2"]), registry)

    ids = {p.name: p.spdx_id for p in packages(exporter)}
    assert ids["fake-dep"] == pinned
    assert ids["other"] == other


def test_locked_transitive_dependency_id_comes_from_registry() -> None:
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, "locked-lib@3")

    exporter = build_doc(make_doc(locked=["Locked_Lib==3.0"]), registry)

    ids = {p.name: p.spdx_id for p in packages(exporter)}
    assert ids["locked-lib"] == pinned


def test_phantom_dependency_id_comes_from_registry() -> None:
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, "libz@1.2")

    exporter = build_doc(make_doc(phantom=[phantom("libz", "1.2")]), registry)

    assert {p.name: p.spdx_id for p in packages(exporter)}["libz"] == pinned


def test_same_package_declared_twice_is_one_element_one_hit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two spellings of one name and one version collapse into one package
    that takes the hit -- no claim collision."""
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, "foo@1")

    with caplog.at_level("WARNING"):
        exporter = build_doc(
            make_doc(dependencies=["Foo==1.0", "foo==1.0.0"]), registry
        )

    foo_pkgs = [p for p in packages(exporter) if p.name.lower() == "foo"]
    assert [p.spdx_id for p in foo_pkgs] == [pinned]
    assert not claim_warnings(caplog)


@pytest.mark.parametrize("pinned", [True, False], ids=["pinned", "harvested"])
@pytest.mark.parametrize(
    "order",
    [["foo==1.0", "Foo==2.0"], ["Foo==2.0", "foo==1.0"]],
    ids=["one-first", "two-first"],
)
def test_two_versions_of_one_dependency_are_two_keys(
    caplog: pytest.LogCaptureFixture, order: list[str], pinned: bool
) -> None:
    """Two releases of one dependency in one document (behind markers) are
    two packages under two keys, in either order: each takes its own pin,
    or a harvest writes both, so the next build gives the same ids, with
    no claim WARNING."""
    registry = IdRegistry.new("pins")
    pins = {
        version: registry.register(PACKAGE_TYPE, f"foo@{version}")
        for version in (("1.0", "2.0") if pinned else ())
    }
    doc = make_doc(dependencies=order)

    with caplog.at_level("WARNING"):
        first = build_doc(doc, registry)
        registry.harvest(first.object_set)
        second = build_doc(doc, registry)

    ids = [
        {p.version: p.spdx_id for p in packages(e) if p.name.lower() == "foo"}
        for e in (first, second)
    ]
    assert ids[0] == ids[1] and len(set(ids[0].values())) == 2
    if pinned:
        assert ids[0] == pins
    assert second.to_json() == first.to_json()
    assert registry.lookup(PACKAGE_TYPE, ["foo@1"]) == ids[0]["1.0"]
    assert registry.lookup(PACKAGE_TYPE, ["foo@2"]) == ids[0]["2.0"]
    assert not claim_warnings(caplog)


def test_dependency_and_phantom_dependency_of_one_name_are_two_elements(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A declared package and a bundled binary of the same name are two
    elements: the declared one takes the hit; the phantom one never looks
    up, so it gets a fresh id with no claim WARNING."""
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, "lib-foo@1.0")

    with caplog.at_level("WARNING"):
        exporter = build_doc(
            make_doc(dependencies=["lib_foo==1.0"], phantom=[phantom("Lib.Foo", "9")]),
            registry,
        )

    by_name = {p.name: p.spdx_id for p in packages(exporter)}
    assert by_name["lib-foo"] == pinned
    assert by_name["Lib.Foo"] != pinned
    assert not claim_warnings(caplog)


@pytest.mark.parametrize(
    ("second", "warnings"), [("1", 1), ("2", 0)], ids=["same-version", "two"]
)
def test_two_phantom_dependencies_of_one_name(
    caplog: pytest.LogCaptureFixture, second: str, warnings: int
) -> None:
    """Two phantoms of one name and version share one key: the first takes
    its pin, the second gets the claim WARNING. Two versions are two keys,
    each with its own pin."""
    registry = IdRegistry.new("pins")
    pins = [registry.register(PACKAGE_TYPE, f"libz@{v}") for v in ("1", "2")]

    with caplog.at_level("WARNING"):
        exporter = build_doc(
            make_doc(phantom=[phantom("libz", "1"), phantom("libz", second)]),
            registry,
        )

    libz = [p.spdx_id for p in packages(exporter) if p.name == "libz"]
    assert libz.count(pins[0]) == 1
    assert libz.count(pins[1]) == 1 - warnings
    assert len(claim_warnings(caplog)) == warnings


def test_dependency_named_like_the_project_never_looks_up(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A self-referencing extra (``demo[x]``) names the project itself: the
    main package owns the registry id and the self-reference adds no
    package, silently -- no claim WARNING."""
    registry = IdRegistry.new("pins")
    pinned = registry.register(PACKAGE_TYPE, MAIN_KEY)

    with caplog.at_level("WARNING"):
        exporter = build_doc(
            make_doc(dependencies=[f"{MAIN.upper()}[x]; extra == 'all'"]), registry
        )

    assert [(p.version, p.spdx_id) for p in packages(exporter)] == [("1.0.0", pinned)]
    assert not claim_warnings(caplog)


def test_registry_ids_are_reserved_before_anything_is_minted() -> None:
    """A registry id may equal a counter id this same document would mint
    for another package (a stale entry from an earlier run of the same
    document): resolving after the counters started would emit it twice."""
    doc = make_doc(dependencies=["alpha==1.0", "beta==1.0"])
    fresh = build_doc(doc, None)
    alpha_minted = {p.name: p.spdx_id for p in packages(fresh)}["alpha"]
    registry = IdRegistry.new("stale")
    registry.elements[(PACKAGE_TYPE, "beta@1")] = RegistryEntry(alpha_minted)

    exporter = build_doc(doc, registry)  # asserts no duplicate spdxId

    ids = {p.name: p.spdx_id for p in packages(exporter)}
    assert ids["beta"] == alpha_minted
    assert ids["alpha"] != alpha_minted
    assert len({*ids.values()}) == len(ids)
