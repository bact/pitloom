# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The PyPI prefetch of :func:`pitloom.assemble.spdx3.document.build` fetches
the versions the dependency groups resolved
(:mod:`pitloom.assemble.spdx3._dep_groups`): one resolution, one identity rule.

See also: tests/assemble/test_deps_enrichment_prefetch.py (the prefetch itself).
"""

# pylint: disable=protected-access

from __future__ import annotations

import json
import logging
import sys
from typing import Any

import pytest
from packaging.utils import canonicalize_name

from pitloom.assemble.spdx3 import _document_locked_deps, deps, deps_installed
from pitloom.assemble.spdx3._dep_groups import project_dependencies
from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.pep508 import is_direct_reference
from pitloom.core.project import ProjectMetadata

_CONFLICT = "conflicts with declared exact pin"
_DIRECT = "vendored @ https://example.invalid/vendored-1.0.tar.gz"


def _project() -> ProjectMetadata:
    """A range, an exact pin, a pin the lock contradicts, a direct reference,
    and a lock-resolved dependency no declared string names."""
    return ProjectMetadata(
        name="main-project",
        version="1.0.0",
        dependencies=["requests>=2.0", "urllib3==2.0.0", "idna==3.0", _DIRECT],
        locked_dependencies=[
            "requests==2.31.0",
            "urllib3==2.0.0",
            "idna==3.4",
            "certifi==2024.1.1",
        ],
    )


def test_prefetch_fetches_the_grouped_keys_and_the_resolution_runs_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The (name, version) pairs prefetched equal the packages built, minus the
    direct reference; each declared string is resolved once and a conflict
    warns once."""
    fetched: list[tuple[str, str]] = []

    def _record(pairs: Any) -> dict[Any, Any]:
        fetched.extend(pairs)
        return {}

    monkeypatch.setattr(_document_locked_deps, "_prefetch_pypi_release_infos", _record)
    monkeypatch.setattr(deps, "_prefetch_pypi_release_infos", _record)
    resolved: list[str] = []
    real = deps_installed._resolve_version

    def _count(name: str, dep: str, **kwargs: Any) -> tuple[str, str | None]:
        resolved.append(dep)
        return real(name, dep, **kwargs)

    for module in list(sys.modules.values()):  # every module that bound the name
        if getattr(module, "_resolve_version", None) is real:
            monkeypatch.setattr(module, "_resolve_version", _count)

    project = _project()
    with caplog.at_level(logging.WARNING):
        exporter = build(
            DocumentModel(project=project, creation_metadata=CreationMetadata())
        )
    # Four declared strings and one lock-only string, each resolved once.
    assert len(resolved) == 5
    assert caplog.text.count(_CONFLICT) == 1

    graph = json.loads(exporter.to_json())["@graph"]
    built = {
        (canonicalize_name(e["name"]), e["software_packageVersion"])
        for e in graph
        if e.get("type") == "software_Package" and e["name"] != project.name
    }
    prefetched = {(canonicalize_name(name), version) for name, version in fetched}
    # The same inputs build() derives, resolved apart from it.
    locked = {"requests": "2.31.0", "urllib3": "2.0.0", "idna": "3.4"}
    grouped = project_dependencies(project, ["certifi==2024.1.1"], locked)
    keys = {
        (group.canonical_name, group.version)
        for lst in (grouped.direct, grouped.transitive)
        for group in lst.groups
    }
    vendored = canonicalize_name("vendored")
    assert any(is_direct_reference(dep) for dep in project.dependencies)
    assert prefetched == {key for key in keys if key[0] != vendored}
    assert prefetched == {key for key in built if key[0] != vendored}
    assert ("idna", "3.0") in prefetched  # the declared pin beats the lock
    assert ("requests", "2.31.0") in prefetched  # a range takes the locked version
    assert ("certifi", "2024.1.1") in prefetched  # lock-only
