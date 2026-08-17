# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom creation-comment, creators, and tool handling.

See also:
- :mod:`tests.core.test_loom` for context manager, hyperparameters, and datasets.
- :mod:`tests.core.test_loom_registry` for registry and script file / generates tests.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.__about__ import __version__
from pitloom.core.creation import CreationMetadata, Creator


def _run_creation_info(
    output_file: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (createdBy agents, CreationInfo) from a written fragment."""
    with open(output_file, encoding="utf-8") as f:
        graph = json.load(f)["@graph"]
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    ci = next(e for e in graph if e["type"] == "CreationInfo")
    return [by_id[ref] for ref in ci["createdBy"]], ci


def test_loom_output_dataset_unknown_input_name_warns_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An input_datasets= name with no matching add_input_dataset() is dropped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_bad_lineage.json"

        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file):
                loom.add_input_dataset("rawdata/pos.txt")
                loom.add_output_dataset(
                    "data/train.txt",
                    input_datasets=["rawdata/pos.txt", "rawdata/typo.txt"],
                )

        assert any("rawdata/typo.txt" in r.message for r in caplog.records)

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        graph = data["@graph"]
        has_input = [e for e in graph if e.get("relationshipType") == "hasInput"]
        assert len(has_input) == 1
        assert len(has_input[0]["to"]) == 1


def test_loom_run_default_comment() -> None:
    """A fragment's CreationInfo.comment defaults to a loom-SDK provenance note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_comment.json"

        with loom.run(output_file):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        creation_infos = [e for e in data["@graph"] if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == (
            f"Generated via Pitloom loom SDK v{__version__} (script/notebook capture)"
        )


def test_loom_run_custom_comment() -> None:
    """An explicit creation_comment overrides the default provenance note."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_custom_comment.json"

        creation = CreationMetadata(
            creation_comment="Generated during nightly training job"
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        creation_infos = [e for e in data["@graph"] if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        assert creation_infos[0]["comment"] == "Generated during nightly training job"


def test_loom_run_creator_is_software_agent_and_tool() -> None:
    """A fragment's createdBy is SoftwareAgent and createdUsing is Tool."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_agent.json"

        with loom.run(output_file):
            loom.set_model("test-model")

        with open(output_file, encoding="utf-8") as f:
            graph = json.load(f)["@graph"]

        by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
        creation_infos = [e for e in graph if e["type"] == "CreationInfo"]
        assert len(creation_infos) == 1
        ci = creation_infos[0]

        agents = [by_id[ref] for ref in ci["createdBy"]]
        assert [a["type"] for a in agents] == ["SoftwareAgent"]
        assert agents[0]["name"] == "Pitloom"
        assert not [e for e in graph if e["type"] == "Person"]

        tools = [by_id[ref] for ref in ci["createdUsing"]]
        assert [t["type"] for t in tools] == ["Tool"]
        assert tools[0]["name"] == "Pitloom"
        assert tools[0]["summary"] == f"Pitloom {__version__}"


def test_loom_run_named_person_creator() -> None:
    """Named Person in createdBy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(creators=[Creator(name="Alice", email="a@ex.com")])
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == ["Person"]
        assert agents[0]["name"] == "Alice"


def test_loom_run_organization_creator() -> None:
    """type='organization' on a Creator records an Organization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creators=[Creator(name="Acme Corp", type="organization")]
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == ["Organization"]
        assert agents[0]["name"] == "Acme Corp"


@pytest.mark.parametrize(
    ("creator_type", "expected_element_type"),
    [
        ("software-agent", "SoftwareAgent"),
        ("agent", "Agent"),
    ],
)
def test_loom_run_software_agent_and_generic_agent_creator(
    creator_type: str, expected_element_type: str
) -> None:
    """A creator's type also allows a named SoftwareAgent or the generic Agent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            creators=[Creator(name="CI Bot", type=creator_type)]
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        agents, _ = _run_creation_info(output_file)
        assert [a["type"] for a in agents] == [expected_element_type]
        assert agents[0]["name"] == "CI Bot"


def test_loom_run_invalid_creator_type_raises() -> None:
    """An unrecognised creator type raises ValueError."""
    with pytest.raises(ValueError, match="Invalid creator type"):
        Creator(name="Bot", type="robot")


def test_loom_run_suppress_tool_and_fixed_datetime() -> None:
    """tools=[] omits createdUsing; creation_datetime is normalised into created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        creation = CreationMetadata(
            tools=[],
            creation_datetime="2026-01-15T10:00:00Z",
        )
        with loom.run(output_file, creation_metadata=creation):
            loom.set_model("test-model")

        _, ci = _run_creation_info(output_file)
        assert "createdUsing" not in ci
        assert ci["created"] == "2026-01-15T10:00:00Z"
