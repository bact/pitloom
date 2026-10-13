# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency edges in an assembled SBOM: ``LifecycleScopedRelationship``
with scope ``runtime`` for a required dependency, a plain
``hasOptionalDependency`` ``Relationship`` (no scope) for an extra, and
self-references resolved, on the document and wheel routes.

See also: :mod:`tests.assemble.test_dep_scope` (the classifier's rules).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_wheel_sbom
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.document import build_deployed
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.requirements import flatten_optional_dependencies
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.project.pyproject import read_pyproject
from tests.assemble.conftest import _make_ci, _make_dummy_wheel
from tests.id_registry.package_ids_base import MAIN, build_doc, make_doc
from tests.id_registry.package_ids_base import phantom as phantom_dep

_SCOPED = "LifecycleScopedRelationship"
_PLAIN = "Relationship"

#: Hatchling's wheel of a project whose ``full`` extra lists ``demo[dev]``:
#: the self-reference expanded into dev's requirements.
_EXPANDED = ['eps==1.0; extra == "dev"', 'eps==1.0; extra == "full"']
_SELF_REFERENCING = ['eps==1.0; extra == "dev"', f'{MAIN}[dev]; extra == "full"']


def _edges(sbom_json: str) -> dict[str, tuple[str, str, str | None, str | None]]:
    """Dependency name -> (type, relationshipType, scope, comment) of each
    dependency edge from the root package."""
    graph = json.loads(sbom_json)["@graph"]
    names = {node["spdxId"]: node.get("name") for node in graph if "spdxId" in node}
    (root,) = next(n for n in graph if n["type"] == "software_Sbom")["rootElement"]
    return {
        names[node["to"][0]]: (
            node["type"],
            node["relationshipType"],
            node.get("scope"),
            node.get("comment"),
        )
        for node in graph
        if node.get("from") == root
        and node.get("relationshipType") in {"dependsOn", "hasOptionalDependency"}
    }


def test_edge_kind_per_dependency_and_no_self_package() -> None:
    doc = make_doc(
        dependencies=[
            "alpha==1.0",
            'beta==2.0; extra == "x"',
            'gamma==1.0; extra == "b"',
            'gamma==1.0; extra == "a"',
            'delta==1.0; extra == "x"',
            "delta==1.0",
            *_SELF_REFERENCING,
        ],
        locked=["alpha==1.0", "trans==3.0"],
    )

    sbom_json = build_doc(doc, None).to_json()

    optional = (_PLAIN, "hasOptionalDependency", None)
    required = (_SCOPED, "dependsOn", "runtime", None)
    assert _edges(sbom_json) == {
        "alpha": required,
        "beta": (*optional, "extras: x"),
        "gamma": (*optional, "extras: a, b"),
        "delta": required,
        "eps": (*optional, "extras: dev, full"),
        # Pins an open design choice: see extras-parity.md open questions
        "trans": required,  # lock-resolved transitive
    }
    names = [n.get("name") for n in json.loads(sbom_json)["@graph"]]
    assert names.count(MAIN) == 1  # the self-reference adds no package


# Pins an open design choice: see extras-parity.md open questions
@pytest.mark.parametrize(
    "locked",
    [["requests==2.0", "urllib3==2.0"], ["requests==2.0"]],
    ids=["locked", "unlocked"],
)
def test_extra_only_direct_dependency_stays_optional(locked: list[str]) -> None:
    """``urllib3`` is direct only through an extra: optional, listed once,
    locked or not -- a flat lock list shows no runtime path to it."""
    doc = make_doc(
        dependencies=["requests==2.0", 'urllib3==2.0; extra == "socks"'],
        locked=locked,
    )

    sbom_json = build_doc(doc, None).to_json()

    assert _edges(sbom_json)["urllib3"] == (
        _PLAIN,
        "hasOptionalDependency",
        None,
        "extras: socks",
    )
    names = [n.get("name") for n in json.loads(sbom_json)["@graph"]]
    assert names.count("urllib3") == 1


def test_lock_main_group_does_not_make_extra_required() -> None:
    """pendulum's ``poetry.lock`` puts ``time-machine`` (its ``test`` extra
    and ``test`` group) in ``main``, not optional; it is still optional."""
    pyproject = (
        Path(__file__).parents[1]
        / "fixtures/real-world-locks/poetry/pendulum-3.2.0/pyproject.toml"
    )
    metadata, _ = read_pyproject(pyproject)
    assert "time-machine==2.16.0" in metadata.locked_dependencies

    doc = make_doc(
        dependencies=metadata.dependencies, locked=metadata.locked_dependencies
    )
    edges = _edges(build_doc(doc, None).to_json())

    assert edges["time-machine"][1:] == (
        "hasOptionalDependency",
        None,
        "extras: test",
    )


def test_self_reference_matches_expanded_wheel_on_every_route(
    tmp_path: Path,
) -> None:
    def wheel(directory: str, requires: list[str]) -> str:
        path = _make_dummy_wheel(
            tmp_path / directory, MAIN, "1.0.0", requires_dist=tuple(requires)
        )
        return generate_wheel_sbom(path, offline=True)

    runs = {
        "document": build_doc(make_doc(dependencies=_SELF_REFERENCING), None).to_json(),
        "wheel": wheel("self", _SELF_REFERENCING),
        "expanded-wheel": wheel("expanded", _EXPANDED),
    }

    expected: dict[str, tuple[str, str, str | None, str | None]] = {
        "eps": (_PLAIN, "hasOptionalDependency", None, "extras: dev, full")
    }
    assert {route: _edges(run) for route, run in runs.items()} == dict.fromkeys(
        runs, expected
    )


def test_directory_and_wheel_routes_agree_on_self_reference() -> None:
    """Drift guard: the directory route flattens ``full = ["demo[dev]", ...]``
    into dev's requirements; a wheel keeps ``demo[dev]; extra == "full"`` and
    assembly expands it. Both give the same (package, type, comment)."""
    optional = {"dev": ["eps==1.0", "zed==2.0"], "full": [f"{MAIN}[dev]", "own==3.0"]}
    directory = flatten_optional_dependencies(
        ["base==1.0"], optional, MAIN, source="optional-dependencies"
    )
    wheel = [
        "base==1.0",
        'eps==1.0; extra == "dev"',
        'zed==2.0; extra == "dev"',
        f'{MAIN}[dev]; extra == "full"',
        'own==3.0; extra == "full"',
    ]
    assert not any(dep.startswith(f"{MAIN}[") for dep in directory)
    assert any(dep.startswith(f"{MAIN}[") for dep in wheel)

    def edges(dependencies: list[str]) -> set[tuple[str, str, str | None]]:
        sbom_json = build_doc(make_doc(dependencies=dependencies), None).to_json()
        return {(n, e[1], e[3]) for n, e in _edges(sbom_json).items()}

    assert edges(directory) == edges(wheel)
    assert ("eps", "hasOptionalDependency", "extras: dev, full") in edges(wheel)


@pytest.mark.parametrize(
    ("dep", "reason"),
    [
        ('odd==1.0; extra != "q"', "can't be isolated"),
        ('odd >= ; extra == "q"', "not a valid PEP 508 requirement"),
    ],
    ids=["unisolatable", "unparsable"],
)
def test_unreadable_extra_gate_warns_once_per_build(
    caplog: pytest.LogCaptureFixture, dep: str, reason: str
) -> None:
    with caplog.at_level("WARNING"):
        sbom_json = build_doc(make_doc(dependencies=[dep, dep]), None).to_json()

    assert list(_edges(sbom_json).values()) == [(_SCOPED, "dependsOn", "runtime", None)]
    warned = [r.getMessage() for r in caplog.records if dep in r.getMessage()]
    assert len(warned) == 1
    assert reason in warned[0]


@pytest.mark.parametrize(
    ("dep", "scoped"),
    [("foo==1.0", True), ('foo==1.0; extra == "x"', False)],
    ids=["required", "optional"],
)
def test_only_required_edge_carries_scope(dep: str, scoped: bool) -> None:
    sbom_json = build_doc(make_doc(dependencies=[dep]), None).to_json()

    edge_type, _rel, scope, _comment = _edges(sbom_json)["foo"]
    assert (edge_type, scope) == ((_SCOPED, "runtime") if scoped else (_PLAIN, None))
    raw = [n for n in json.loads(sbom_json)["@graph"] if n.get("type") == edge_type]
    assert any("scope" in n for n in raw) == scoped


def test_completeness_kwarg_kept_on_optional_edge() -> None:
    doc_uuid = compute_doc_uuid("scoped-complete", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()

    add_dependencies(
        ['foo==1.0; extra == "x"'],
        "Source: test",
        "https://example.org/main",
        _make_ci(),
        "scoped-complete",
        doc_uuid,
        exporter,
        offline=True,
        completeness=spdx3.RelationshipCompleteness.complete,
    )

    (edge,) = [
        o
        for o in exporter.object_set.objects
        if isinstance(o, spdx3.Relationship)
        and o.relationshipType == spdx3.RelationshipType.hasOptionalDependency
    ]
    assert not isinstance(edge, spdx3.LifecycleScopedRelationship)
    assert (edge.relationshipType, edge.completeness, edge.comment) == (
        spdx3.RelationshipType.hasOptionalDependency,
        spdx3.RelationshipCompleteness.complete,
        "extras: x",
    )


def test_dependency_ids_and_bytes_are_stable() -> None:
    """Relationship and package ids match the ``dependsOn``-only output of
    the tree before scoped edges (no renumbering), and two builds are
    byte-identical."""
    doc = make_doc(
        dependencies=["alpha==1.0", "beta==2.0", "Gamma==3.0"],
        locked=["alpha==1.0", "delta==4.0"],
    )

    first, second = (build_doc(doc, None).to_json() for _ in range(2))

    graph = json.loads(first)["@graph"]
    names = {n["spdxId"]: n.get("name") for n in graph if "spdxId" in n}
    assert sorted(
        (n["spdxId"].split("#")[1], names[n["to"][0]])
        for n in graph
        if "relationshipType" in n
    ) == [
        ("Relationship-1", "alpha"),
        ("Relationship-2", "beta"),
        ("Relationship-3", "Gamma"),
        ("Relationship-4", "delta"),
    ]
    assert sorted(
        (n["spdxId"].split("#")[1], n["name"])
        for n in graph
        if n["type"] == "software_Package"
    ) == [
        ("Package-1", MAIN),
        ("Package-2", "alpha"),
        ("Package-3", "beta"),
        ("Package-4", "Gamma"),
        ("Package-5", "delta"),
    ]
    assert second == first


def test_every_depends_on_edge_is_runtime_scoped_except_in_loom_env() -> None:
    """Required, locked and phantom edges from the main package are all
    ``runtime``-scoped; ``loom env`` edges are plain: installed is not
    evidence of runtime use."""
    doc = make_doc(
        dependencies=["alpha==1.0"],
        locked=["alpha==1.0", "trans==3.0"],
        phantom=[phantom_dep("libfoo", "1.0")],
    )
    graph = json.loads(build_doc(doc, None).to_json())["@graph"]
    edges = [e for e in graph if e.get("relationshipType") == "dependsOn"]
    assert len(edges) == 3  # alpha, trans, libfoo
    assert {(e["type"], e["scope"]) for e in edges} == {(_SCOPED, "runtime")}

    tree: list[dict[str, Any]] = [
        {
            "package": {"key": "a", "package_name": "a", "installed_version": "1"},
            "dependencies": [
                {"key": "b", "package_name": "b", "installed_version": "1"}
            ],
        },
        {"package": {"key": "b", "package_name": "b", "installed_version": "1"}},
    ]
    env = build_deployed(make_doc(name="env"), tree, offline=True)
    env_edges = [
        e
        for e in json.loads(env.to_json())["@graph"]
        if e.get("relationshipType") == "dependsOn"
    ]
    assert len(env_edges) == 2  # root -> a, a -> b
    assert {(e["type"], e.get("scope")) for e in env_edges} == {(_PLAIN, None)}
