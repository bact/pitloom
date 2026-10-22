# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the post-serialisation graph passes of
:class:`pitloom.export.spdx3_json.Spdx3JsonExporter`: relationship
descriptions and CreationInfo deduplication."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export.spdx3_json import Spdx3JsonExporter

_BASE = "https://e.org/a#"


def _creation_info() -> spdx3.CreationInfo:
    info = spdx3.CreationInfo()
    info.specVersion = "3.0.1"
    info.created = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return info


def _graph(exporter: Spdx3JsonExporter, **kwargs: Any) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(exporter.to_json(**kwargs))["@graph"]
    return graph


@pytest.mark.parametrize(
    ("given", "expected"),
    [("KEEP ME", "KEEP ME"), ("", ""), (None, "p1 dependsOn: p2")],
    ids=["existing", "empty-string-counts-as-present", "absent"],
)
def test_describe_relationship_keeps_an_existing_description(
    given: str | None, expected: str
) -> None:
    info = _creation_info()
    agent = spdx3.SoftwareAgent(spdxId=_BASE + "A", name="x", creationInfo=info)
    info.createdBy = [agent]
    p1 = spdx3.software_Package(spdxId=_BASE + "P1", name="p1", creationInfo=info)
    p2 = spdx3.software_Package(spdxId=_BASE + "P2", name="p2", creationInfo=info)
    rel = spdx3.Relationship(
        spdxId=_BASE + "R",
        creationInfo=info,
        from_=p1,
        to=[p2],
        relationshipType=spdx3.RelationshipType.dependsOn,
    )
    if given is not None:
        rel.description = given
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(info)
    for element in (agent, p1, p2):
        exporter.object_set.add(element)
    exporter.add_relationship(rel)
    nodes = _graph(exporter, describe_relationship=True)
    assert [n.get("description") for n in nodes if n["type"] == "Relationship"] == [
        expected
    ]


def _two_infos(
    *, orphan_first: bool, comment: str | None = None, description: str | None = None
) -> list[dict[str, Any]]:
    """An exporter holding a CreationInfo no element refers to (so it has no
    ``@id``) and the one the packages use."""
    used, orphan = _creation_info(), _creation_info()
    agent = spdx3.SoftwareAgent(spdxId=_BASE + "A", name="x", creationInfo=used)
    used.createdBy = [agent]
    orphan.createdBy = [agent]
    package = spdx3.software_Package(spdxId=_BASE + "P1", name="p1", creationInfo=used)
    if comment is not None:
        used.comment = comment
    if description is not None:
        package.description = description
    exporter = Spdx3JsonExporter()
    for info in (orphan, used) if orphan_first else (used, orphan):
        exporter.add_creation_info(info)
    exporter.add_agent(agent)
    exporter.add_package(package)
    return _graph(exporter)


@pytest.mark.parametrize("orphan_first", [True, False], ids=["first", "last"])
def test_a_creation_info_without_an_id_is_dropped(orphan_first: bool) -> None:
    graph = _two_infos(orphan_first=orphan_first)
    infos = [n for n in graph if n["type"] == "CreationInfo"]
    assert [n.get("@id") for n in infos] == ["_:CreationInfo0"]
    refs = [n["creationInfo"] for n in graph if "creationInfo" in n]
    assert refs and set(refs) == {"_:CreationInfo0"}


@pytest.mark.parametrize("orphan_first", [True, False], ids=["first", "last"])
def test_only_references_are_remapped(orphan_first: bool) -> None:
    """A text equal to a dropped node's id (or an empty comment) stays."""
    graph = _two_infos(
        orphan_first=orphan_first, comment="", description="_:CreationInfo9"
    )
    info = next(n for n in graph if n["type"] == "CreationInfo")
    package = next(n for n in graph if n["type"] == "software_Package")
    assert package["description"] == "_:CreationInfo9"
    assert info.get("comment", "") == ""
    assert package["creationInfo"] == info["@id"] == "_:CreationInfo0"
