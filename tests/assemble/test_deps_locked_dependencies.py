# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``ProjectMetadata.locked_dependencies`` (e.g. ``poetry.lock``-
resolved transitive dependencies) flowing into the assembled SPDX 3 graph.

See also: tests/assemble/test_deps_relationship_edges.py for the
``add_dependencies``/``add_phantom_dependencies`` defensive-guard tests
this module's low-level test mirrors; tests/extract/test_poetry_lock.py
for the ``poetry.lock`` parsing tests this assemble-layer wiring builds on.
"""

# pylint: disable=protected-access

from __future__ import annotations

import json

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _make_ci


def test_add_dependencies_completeness_kwarg_sets_relationship_field() -> None:
    """Passing ``completeness`` sets it on every ``dependsOn`` relationship
    this call creates."""
    doc_uuid = compute_doc_uuid("completeness-set", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    add_dependencies(
        ["somepkg==1.0.0"],
        "Source: poetry.lock | Method: resolved_lockfile",
        "http://spdx.org/spdxdocs/main-pkg",
        ci,
        "completeness-set",
        doc_uuid,
        exporter,
        offline=True,
        completeness=spdx3.RelationshipCompleteness.complete,
    )

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    dep_rel = next(
        r
        for r in relationships
        if r.relationshipType == spdx3.RelationshipType.dependsOn
    )
    assert dep_rel.completeness == spdx3.RelationshipCompleteness.complete


def test_add_dependencies_omitted_completeness_leaves_field_unset() -> None:
    """Omitting ``completeness`` (the default, and every pre-existing call
    site's behavior) leaves the relationship's ``completeness`` unset --
    regression guard against changing direct-dependency output."""
    doc_uuid = compute_doc_uuid("completeness-unset", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    add_dependencies(
        ["somepkg==1.0.0"],
        "Source: pyproject.toml | Field: project.dependencies",
        "http://spdx.org/spdxdocs/main-pkg",
        ci,
        "completeness-unset",
        doc_uuid,
        exporter,
        offline=True,
    )

    relationships = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.Relationship)
    ]
    dep_rel = next(
        r
        for r in relationships
        if r.relationshipType == spdx3.RelationshipType.dependsOn
    )
    assert dep_rel.completeness is None


def test_locked_dependencies_add_transitive_only_edges() -> None:
    """A locked (poetry.lock-resolved) package not already a direct
    dependency gets an additive ``dependsOn`` edge tagged ``complete``;
    the direct dependency's own edge is untouched (no ``completeness``)."""
    project = ProjectMetadata(
        name="main-project",
        version="1.0.0",
        dependencies=["requests>=2.0"],
        locked_dependencies=["requests==2.31.0", "urllib3==2.2.0", "idna==3.7"],
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = {e["name"]: e for e in graph if e.get("type") == "software_Package"}
    assert set(packages) == {"main-project", "requests", "urllib3", "idna"}

    relationships = [
        e
        for e in graph
        if e.get("type") == "Relationship" and e["relationshipType"] == "dependsOn"
    ]
    main_id = packages["main-project"]["spdxId"]
    depends_on = {r["to"][0]: r for r in relationships if r["from"] == main_id}

    assert len(depends_on) == 3  # one edge per package, no duplicate for requests
    assert "completeness" not in depends_on[packages["requests"]["spdxId"]]
    assert depends_on[packages["urllib3"]["spdxId"]]["completeness"] == "complete"
    assert depends_on[packages["idna"]["spdxId"]]["completeness"] == "complete"


def test_locked_dependencies_dedup_is_case_and_separator_insensitive() -> None:
    """A direct dependency declared with the author's own casing (e.g.
    ``Django``) must still dedup against a lock-resolved entry that PEP
    503-normalizes it (``django``) -- and dash/underscore variants must
    dedup the same way. Regression test: comparing raw, unnormalized names
    let a package declared both directly and in the lock double-emit as
    two separate nodes/edges."""
    project = ProjectMetadata(
        name="main-project",
        version="1.0.0",
        dependencies=["Django>=4.0", "my_package>=1.0"],
        locked_dependencies=["django==4.2.1", "my-package==1.0.0", "idna==3.7"],
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    package_names = [e["name"] for e in graph if e.get("type") == "software_Package"]
    assert sorted(package_names) == ["Django", "idna", "main-project", "my_package"]

    relationships = [
        e
        for e in graph
        if e.get("type") == "Relationship" and e["relationshipType"] == "dependsOn"
    ]
    main_id = next(e["spdxId"] for e in graph if e.get("name") == "main-project")
    depends_on = [r for r in relationships if r["from"] == main_id]
    assert len(depends_on) == 3  # Django, my_package, idna -- no duplicate edges


def test_locked_dependencies_empty_adds_no_extra_edges() -> None:
    """No ``locked_dependencies`` (the default -- every non-Poetry project,
    and a Poetry project with no ``poetry.lock``) adds nothing beyond the
    direct-dependency edges, unchanged from before this field existed."""
    project = ProjectMetadata(
        name="main-project", version="1.0.0", dependencies=["requests>=2.0"]
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]

    packages = {e["name"] for e in graph if e.get("type") == "software_Package"}
    assert packages == {"main-project", "requests"}


def test_locked_dependencies_change_doc_uuid() -> None:
    """Two documents with identical name/version/direct-dependencies but
    different locked_dependencies must not collide on the same doc UUID --
    otherwise their differing dependency graphs would be indistinguishable
    by the one identifier meant to key them."""
    base = compute_doc_uuid("pkg", "1.0.0", ["requests>=2.0"])
    with_lock_a = compute_doc_uuid(
        "pkg", "1.0.0", ["requests>=2.0"], locked_dependencies=["idna==3.7"]
    )
    with_lock_b = compute_doc_uuid(
        "pkg", "1.0.0", ["requests>=2.0"], locked_dependencies=["idna==3.8"]
    )

    assert len({base, with_lock_a, with_lock_b}) == 3


def test_locked_dependencies_same_content_different_provenance_changes_doc_uuid() -> (
    None
):
    """Two documents with an *identical* resolved dependency set but from
    different lock sources (e.g. a ``poetry.lock``-only run and a
    ``pylock.toml``-only run of the same project happening to resolve to
    the same pins) must not collide on the same doc UUID either -- their
    ``provenance["locked_dependencies"]`` strings (and any override note)
    differ, which is a real content difference in the generated document
    that seeding on dependency content alone would miss."""
    same_content = ["idna==3.7"]
    from_poetry = compute_doc_uuid(
        "pkg",
        "1.0.0",
        ["requests>=2.0"],
        locked_dependencies=same_content,
        locked_dependencies_provenance=(
            "Source: poetry.lock | Method: resolved_lockfile"
        ),
    )
    from_pylock = compute_doc_uuid(
        "pkg",
        "1.0.0",
        ["requests>=2.0"],
        locked_dependencies=same_content,
        locked_dependencies_provenance=(
            "Source: pylock.toml | Method: resolved_lockfile"
        ),
    )
    unattributed = compute_doc_uuid(
        "pkg", "1.0.0", ["requests>=2.0"], locked_dependencies=same_content
    )

    assert len({from_poetry, from_pylock, unattributed}) == 3


def test_locked_dependencies_provenance_omitted_matches_empty_string() -> None:
    """Omitting ``locked_dependencies_provenance`` (every pre-existing
    call site) must produce the same UUID as every caller that predates
    this parameter -- purely additive, no behavior change for callers
    that don't know about it."""
    omitted = compute_doc_uuid(
        "pkg", "1.0.0", ["requests>=2.0"], locked_dependencies=["idna==3.7"]
    )
    explicit_none = compute_doc_uuid(
        "pkg",
        "1.0.0",
        ["requests>=2.0"],
        locked_dependencies=["idna==3.7"],
        locked_dependencies_provenance=None,
    )

    assert omitted == explicit_none


def test_locked_dependencies_omitted_matches_empty_list() -> None:
    """Omitting ``locked_dependencies`` entirely (every pre-existing call
    site) must produce the same UUID as passing an empty list -- the new
    parameter is purely additive, never a behavior change for callers that
    don't know about it."""
    omitted = compute_doc_uuid("pkg", "1.0.0", ["requests>=2.0"])
    empty = compute_doc_uuid("pkg", "1.0.0", ["requests>=2.0"], locked_dependencies=[])

    assert omitted == empty
