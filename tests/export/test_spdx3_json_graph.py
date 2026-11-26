# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the post-serialisation graph passes of
:class:`pitloom.export.spdx3_json.Spdx3JsonExporter`: relationship
descriptions, CreationInfo deduplication and the lone-surrogate escape."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.export import spdx3_json
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import CODE_ATTR

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


@pytest.mark.parametrize(
    ("names", "warned"),
    [(("b\udc80", "a\udcff"), [f"ELEMENT={_BASE}P1"]), (("b", "a"), [])],
    ids=["lone-surrogates", "clean"],
)
def test_a_lone_surrogate_is_written_as_text_with_one_warning(
    names: tuple[str, str], warned: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Every element's text is escaped before the passes that read it (the
    relationship description); one warning names the least element
    changed, a package by its spdxId."""
    info = _creation_info()
    agent = spdx3.SoftwareAgent(spdxId=_BASE + "A", name="x", creationInfo=info)
    info.createdBy = [agent]
    p1, p2 = (
        spdx3.software_Package(spdxId=_BASE + f"P{n}", name=name, creationInfo=info)
        for n, name in enumerate(names, 1)
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(info)
    for element in (agent, p1, p2):
        exporter.object_set.add(element)
    exporter.add_relationship(
        spdx3.Relationship(
            spdxId=_BASE + "R",
            creationInfo=info,
            from_=p1,
            to=[p2],
            relationshipType=spdx3.RelationshipType.dependsOn,
        )
    )
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        nodes = _graph(exporter, describe_relationship=True)
    shown = [name.encode("ascii", "backslashreplace").decode() for name in names]
    assert [n["name"] for n in nodes if n["type"] == "software_Package"] == shown
    (rel,) = [n for n in nodes if n["type"] == "Relationship"]
    assert rel["description"] == f"{shown[0]} dependsOn: {shown[1]}"
    said = [r.getMessage().rpartition(": lone surrogates")[0] for r in caplog.records]
    assert said == warned


@pytest.mark.parametrize(
    ("graph", "warned"),
    [
        (
            [
                {"type": "software_Package", "spdxId": "a#P", "name": "p\udcff"},
                {"type": "software_File", "spdxId": "a#F", "name": "z\udcff.py"},
            ],
            "FILE='z\\udcff.py'",
        ),
        (
            [
                {"type": "software_Package", "spdxId": "a#Q", "name": "q\udcff"},
                {"type": "software_Package", "spdxId": "a#P", "name": "z\udcff"},
            ],
            "ELEMENT=a#P",
        ),
        ([{"type": "software_File", "spdxId": "a#F", "x": "\udcff"}], "ELEMENT=a#F"),
        ([{"@id": "_:c", "comment": "\udcff"}], "ELEMENT=_:c"),
        # A non-ASCII name escaped once, by the field writer.
        (
            [{"type": "software_File", "spdxId": "a#F", "name": "é\udcff.py"}],
            "FILE='\\xe9\\udcff.py'",
        ),
        # No spdxId and no @id: named by its type.
        ([{"type": "CreationInfo", "comment": "c\udcff"}], "ELEMENT=CreationInfo"),
    ],
    ids=[
        "file-first",
        "least-id",
        "file-with-no-name",
        "blank-node",
        "non-ascii-file",
        "type-only",
    ],
)
def test_the_surrogate_warning_names_a_file_by_name_else_an_element_by_id(
    graph: list[dict[str, Any]], warned: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A file is named by its path (``FILE=``), any other element by its
    spdxId (``ELEMENT=``): a package's name is no file."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        spdx3_json.escape_lone_surrogates_in_graph(graph)
    (record,) = caplog.records
    assert record.getMessage() == f"{warned}: lone surrogates written as \\uXXXX"
    assert getattr(record, CODE_ATTR) == "text-malformed"
