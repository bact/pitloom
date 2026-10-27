# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Datasets declared in one ``loom.run`` that share a creator share one
generic ``Agent`` (the assembler's route is tested in
``test_ai_originators.py``).

See also: :mod:`pitloom.assemble.spdx3._agents`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom._loom_dataset_meta import DatasetDoc, write_metadata
from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter

_CROISSANT = Path(__file__).resolve().parents[1] / "fixtures" / "croissant"


def test_two_datasets_of_one_creator_are_published_by_one_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Croissant creator of both datasets is "Test Author": one Agent,
    two ``publishedBy`` relationships to it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "train.py").write_bytes(b"run()\n")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    output = tmp_path / "loom.spdx3.json"
    full = _CROISSANT / "full.json"
    with loom.run(output):
        loom.add_dataset("first", croissant=full)
        loom.add_dataset("second", croissant=full)
    graph: list[dict[str, Any]] = json.loads(output.read_text(encoding="utf-8"))[
        "@graph"
    ]
    agents = [e for e in graph if e["type"] == "Agent" and e["name"] == "Test Author"]
    published = [
        e
        for e in graph
        if e["type"] == "Relationship" and e["relationshipType"] == "publishedBy"
    ]
    assert len(agents) == 1 and len(published) == 2
    assert {t for r in published for t in r["to"]} == {agents[0]["spdxId"]}


def test_a_creator_name_with_a_bidi_control_is_escaped_and_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The Agent a ``loom.run`` dataset adds reaches the display-text escape
    like every other element: no raw control in the SBOM, one notice."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "train.py").write_bytes(b"run()\n")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    card = json.loads((_CROISSANT / "full.json").read_text(encoding="utf-8"))
    card["creator"]["name"] = "Eve\u202eAdmin"
    source = tmp_path / "card.json"
    source.write_text(json.dumps(card), encoding="utf-8")
    output = tmp_path / "loom.spdx3.json"
    with caplog.at_level(logging.INFO), loom.run(output):
        loom.add_dataset("first", croissant=source)
    text = output.read_text(encoding="utf-8")
    assert "\u202e" not in text
    (agent,) = [
        e
        for e in json.loads(text)["@graph"]
        if e["type"] == "Agent" and e["name"].startswith("Eve")
    ]
    assert agent["name"] == "Eve\\u202eAdmin"
    assert "dataset creator" in caplog.text


def test_a_padded_creator_name_is_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The creator " Eve " is the Agent "Eve" with an id that carries no space
    (as for a model originator)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "train.py").write_bytes(b"run()\n")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    card = json.loads((_CROISSANT / "full.json").read_text(encoding="utf-8"))
    card["creator"]["name"] = "  Eve  "
    source = tmp_path / "card.json"
    source.write_text(json.dumps(card), encoding="utf-8")
    output = tmp_path / "loom.spdx3.json"
    with loom.run(output):
        loom.add_dataset("first", croissant=source)
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    agents = [e for e in graph if e["type"] == "Agent" and "Eve" in e["name"]]
    assert [(a["name"], a["spdxId"].rsplit("#", 1)[1]) for a in agents] == [
        ("Eve", "Agent-Eve-1")
    ]


@pytest.mark.parametrize(
    ("creator", "agents"),
    [("  Eve  ", ["Eve"]), ("   ", []), ("\t", [])],
    ids=["padded", "spaces", "tab"],
)
def test_write_metadata_strips_a_creator_and_skips_a_blank_one(
    creator: str, agents: list[str]
) -> None:
    """A source that did not strip its creator (a card, a declaration): the
    Agent is the stripped name; a blank creator names no one."""
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=["https://example.org/doc#A"],
    )
    exporter = Spdx3JsonExporter()
    package = spdx3.dataset_DatasetPackage(
        spdxId="https://example.org/doc#D", name="d", creationInfo=ci
    )
    doc = DatasetDoc(exporter, ci, "uuid", ProvenanceConfig())
    write_metadata(package, DatasetMetadata(name="d", creator=creator), doc)
    names = [o.name for o in exporter.object_set.objects if isinstance(o, spdx3.Agent)]
    assert names == agents
