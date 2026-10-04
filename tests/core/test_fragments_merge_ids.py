# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment that re-declares the base document's ids merges into them:
its references compare by id with the base's, so a list gains no second
copy of an element or a ``Hash`` and a scalar shows no false conflict. A
real conflict names both values by id, never as a Python object repr.

See also: tests/assemble/test_fragments_surfaces.py (a fragment that is the
document itself) and tests/assemble/test_fragments_unify.py (the helpers).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._license_graph import fragment_graph, write_fragment
from tests.assemble.embed_surfaces_shared import demo_project

_FRAGMENT = '\n[tool.pitloom.fragment]\nfiles = ["frag.spdx3.json"]\n'


def test_redeclared_ids_merge_without_copies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The project's own SBOM, less its ``SpdxDocument``, as a fragment:
    every element is a re-declared id, linked as an object in the fragment
    and held as an id string in the base."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    base = json.loads(generate_project_sbom(demo_project(tmp_path / "a"), offline=True))
    fragment = {
        **base,
        "@graph": [e for e in base["@graph"] if e["type"] != "SpdxDocument"],
    }
    write_fragment(tmp_path / "b" / "proj" / "frag.spdx3.json", fragment)
    with caplog.at_level(logging.WARNING):
        merged = generate_project_sbom(
            demo_project(tmp_path / "b", _FRAGMENT), offline=True
        )
    assert not [r for r in caplog.records if "Merge:" in r.getMessage()]
    graph = json.loads(merged)["@graph"]
    relationships = [e for e in graph if e["type"] == "Relationship"]
    assert relationships
    for rel in relationships:
        assert len(rel["to"]) == len(set(rel["to"])), rel
    hashed = [e for e in graph if "verifiedUsing" in e]
    assert hashed
    for element in hashed:
        hashes = [h["hashValue"] for h in element["verifiedUsing"]]
        assert Counter(hashes).most_common(1)[0][1] == 1, element
    by_id = Counter(e["spdxId"] for e in graph if "spdxId" in e)
    base_ids = {e["spdxId"] for e in base["@graph"] if "spdxId" in e}
    assert {i for i in by_id if i in base_ids} == base_ids
    assert by_id.most_common(1)[0][1] == 1


_BASE_NS = "https://spdx.org/spdxdocs/base"


def _conflict_messages(tmp: Path, caplog: pytest.LogCaptureFixture) -> list[str]:
    """The ``Merge:`` warnings of a fragment re-declaring the base's package
    with another supplier and description."""
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=[f"{_BASE_NS}#A"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(spdx3.SpdxDocument(spdxId=_BASE_NS, creationInfo=ci))
    exporter.add_agent(spdx3.Agent(spdxId=f"{_BASE_NS}#A", name="A", creationInfo=ci))
    package = spdx3.software_Package(
        spdxId=f"{_BASE_NS}#P", name="p", creationInfo=ci, description="base"
    )
    package.suppliedBy = f"{_BASE_NS}#A"
    exporter.add_package(package)
    elements: list[dict[str, Any]] = [
        {"type": "Agent", "spdxId": "https://spdx.org/spdxdocs/frag#B", "name": "B"},
        {
            "type": "software_Package",
            "spdxId": f"{_BASE_NS}#P",
            "name": "p",
            "description": "fragment",
            "suppliedBy": "https://spdx.org/spdxdocs/frag#B",
        },
    ]
    write_fragment(tmp / "f.spdx3.json", fragment_graph(elements))
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        merge_fragments(tmp, [FragmentConfig(path="f.spdx3.json")], exporter)
    return [r.getMessage() for r in caplog.records if "Merge:" in r.getMessage()]


def test_conflict_warning_names_elements_by_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    first = _conflict_messages(tmp_path / "1", caplog)
    assert first == _conflict_messages(tmp_path / "2", caplog)
    assert len(first) == 2
    assert not [m for m in first if "object at 0x" in m]
    supplier = next(m for m in first if "'suppliedBy'" in m)
    assert f"on software_Package {_BASE_NS}#P 'p'" in supplier
    assert "frag#B" in supplier
