# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the version a locked dependency resolves to
(``_extract_locked_version_map``) and the lock entries kept
(``_deduplicated_locked_dependencies``,
``_locked_transitive_only_dependencies``) in the assembled SPDX 3 graph.

See also: tests/assemble/test_deps_locked_dependencies.py (the edges and ``doc_uuid``).
"""

# pylint: disable=protected-access

from __future__ import annotations

import json

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.document import (
    _deduplicated_locked_dependencies,
    _extract_locked_version_map,
    _locked_transitive_only_dependencies,
    build,
)
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _make_ci


def test_direct_dependency_range_resolves_to_locked_version_over_host_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per GEMINI.md ("Explicit pin beats local environment"): when
    metadata.dependencies declares a range (requests>=2.0) and
    metadata.locked_dependencies has an exact pin (requests==2.31.0),
    the assembled Package node must use the locked version (2.31.0),
    never introspecting Pitloom's host environment."""
    monkeypatch.setattr(
        deps_installed,
        "get_package_version",
        lambda _name: pytest.fail("host environment should not be consulted"),
    )

    project = ProjectMetadata(
        name="main-project",
        version="1.0.0",
        dependencies=["requests>=2.0"],
        locked_dependencies=["requests==2.31.0", "urllib3==2.2.0"],
        provenance={
            "locked_dependencies": "Source: pylock.toml | Method: resolved_lockfile"
        },
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    exporter = build(doc, offline=True)
    graph = json.loads(exporter.to_json())["@graph"]
    packages = {e["name"]: e for e in graph if e.get("type") == "software_Package"}

    assert packages["requests"]["software_packageVersion"] == "2.31.0"
    assert packages["urllib3"]["software_packageVersion"] == "2.2.0"


def test_extract_locked_version_map_unpinned_does_not_leak_host_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_extract_locked_version_map must only extract exact pins from lock
    entries, never falling back to host environment importlib.metadata."""
    monkeypatch.setattr(deps_installed, "get_package_version", lambda _name: "9.9.9")

    locked_map = _extract_locked_version_map(["unpinned-pkg", "range-dep>=1.0"])
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert locked_map == {}

    pinned_map = _extract_locked_version_map(
        [
            "pinned-pkg==2.0.0",
            "custom-pkg===legacy.1",
            "unparseable-pkg===legacy.2; invalid @ marker",
        ]
    )
    assert pinned_map == {
        "pinned-pkg": "2.0.0",
        "custom-pkg": "legacy.1",
        "unparseable-pkg": "legacy.2",
    }


def test_add_dependencies_groups_pep440_equivalent_versions() -> None:
    """Declared dependencies with PEP 440 equivalent versions (e.g. 2.31 and 2.31.0)
    must group under the same Package node rather than creating duplicate nodes."""
    doc_uuid = compute_doc_uuid("equiv-versions", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()

    add_dependencies(
        ["requests==2.31", "requests==2.31.0"],
        "Source: pyproject.toml",
        "http://spdx.org/spdxdocs/main-pkg",
        ci,
        "equiv-versions",
        doc_uuid,
        exporter,
        offline=True,
    )

    pkg_nodes = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.software_Package)
    ]
    assert len(pkg_nodes) == 1
    assert pkg_nodes[0].name == "requests"


def test_extract_locked_version_map_warns_on_conflicting_duplicates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Conflicting duplicate package entries in locked_dependencies must warn
    and be excluded entirely -- neither conflicting version is guessed at."""
    caplog.set_level("WARNING")
    locked_map = _extract_locked_version_map(["requests==2.31.0", "requests==2.28.0"])
    assert "requests" not in locked_map
    assert "pinned to conflicting versions" in caplog.text


def test_locked_transitive_only_dependencies_excludes_conflicting_duplicates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A conflicting duplicate name in locked_dependencies must not reach the
    assembled SBOM as two separate dependsOn edges for the same package."""
    caplog.set_level("WARNING")
    meta = ProjectMetadata(
        name="testpkg",
        dependencies=["requests>=2.0"],
        locked_dependencies=["bar==1.0", "bar==2.0", "requests==2.31.0"],
    )
    assert _locked_transitive_only_dependencies(meta) == []
    assert "pinned to conflicting versions" in caplog.text


def test_locked_transitive_only_dependencies_keeps_unpinned_entries() -> None:
    """An unpinned/ranged locked_dependencies entry has no version to
    compare or conflict on, so it must pass through unfiltered rather
    than being silently dropped by the pin-only conflict-dedup step --
    only _extract_locked_version_map needs a pin, not this function."""
    meta = ProjectMetadata(
        name="testpkg",
        dependencies=[],
        locked_dependencies=["unpinned-pkg", "range-dep>=1.0", "pinned==1.0"],
    )

    assert set(_locked_transitive_only_dependencies(meta)) == {
        "unpinned-pkg",
        "range-dep>=1.0",
        "pinned==1.0",
    }


def test_deduplicated_locked_dependencies_preserves_original_order() -> None:
    """The docstring promises 'preserving order' -- a deduplicated pinned
    entry must land at its first occurrence's original position, not be
    moved to the end (or the front) relative to unrelated entries."""
    assert _deduplicated_locked_dependencies(["foo==1.0", "bar", "baz==2.0"]) == [
        "foo==1.0",
        "bar",
        "baz==2.0",
    ]
    # A name repeated later (agreeing pin) still resolves at its FIRST
    # occurrence's position, not its last.
    assert _deduplicated_locked_dependencies(["foo==1.0", "bar", "foo==1.0.0"]) == [
        "foo==1.0",
        "bar",
    ]


def test_build_warns_conflicting_locked_duplicates_only_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """build() shares one _dedup_and_locked_versions() result between
    _locked_transitive_only_dependencies() and its own locked-version-map
    unpacking instead of each recomputing it -- a genuine conflict must log
    'pinned to conflicting versions' exactly once per document, not once
    per caller."""
    project = ProjectMetadata(
        name="main-project",
        version="1.0.0",
        dependencies=["requests>=2.0"],
        locked_dependencies=["bar==1.0", "bar==2.0", "requests==2.31.0"],
        provenance={
            "locked_dependencies": "Source: poetry.lock | Method: resolved_lockfile"
        },
    )
    doc = DocumentModel(project=project, creation_metadata=CreationMetadata())

    caplog.set_level("WARNING")
    build(doc, offline=True)

    assert caplog.text.count("pinned to conflicting versions") == 1


def test_locked_transitive_only_dependencies_handles_none_locked() -> None:
    """None locked_dependencies must safely return empty list without TypeError."""
    meta = ProjectMetadata(name="testpkg", dependencies=["requests>=2.0"])
    meta.locked_dependencies = None  # type: ignore[assignment]
    assert _locked_transitive_only_dependencies(meta) == []
