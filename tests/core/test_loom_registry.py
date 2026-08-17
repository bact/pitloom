# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom registry consultation (id reuse/hash-mismatch),
creation-comment/creator handling, and script-file + generates edges.

See also: tests/core/test_loom.py for the loom.run() context-manager/
decorator basics, hyperparameters, model type, and dataset-lineage tests.
"""

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.__about__ import __version__
from pitloom.core.creation import CreationMetadata, Creator
from pitloom.ids import EntityEntry, FileEntry, IdRegistry

from .conftest import _relationships


def test_loom_output_dataset_unknown_input_name_warns_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ``input_datasets=`` name with no matching ``add_input_dataset()``
    call is dropped with a warning, not a crash -- likely a typo the
    developer should see."""
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
    """An explicit creation_comment overrides the default loom-SDK provenance note."""
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
    """A fragment's createdBy is the SoftwareAgent "Pitloom" (not a Person) and
    createdUsing is the Tool "Pitloom" with a versioned summary."""
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


def _run_creation_info(
    output_file: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (createdBy agents, CreationInfo) from a written fragment."""
    with open(output_file, encoding="utf-8") as f:
        graph = json.load(f)["@graph"]
    by_id = {e["spdxId"]: e for e in graph if "spdxId" in e}
    ci = next(e for e in graph if e["type"] == "CreationInfo")
    return [by_id[ref] for ref in ci["createdBy"]], ci


def test_loom_run_named_person_creator() -> None:
    """loom.run(creation_metadata=CreationMetadata(creators=[Creator(...)])) records
    a Person in createdBy, on par with the CLI."""
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
    """A creator's type also allows a named SoftwareAgent or the generic Agent,
    not just Person/Organization."""
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
    """An unrecognised creator type raises ValueError rather than silently
    falling back to Person.

    Validation now happens eagerly in ``Creator.__post_init__`` (construction
    time) rather than later at fragment assembly, so the invalid type is
    rejected before ``loom.run`` is ever reached."""
    with pytest.raises(ValueError, match="Invalid creator type"):
        Creator(name="Bot", type="robot")


def test_loom_run_suppress_tool_and_fixed_datetime() -> None:
    """tools=[] omits createdUsing; creation_datetime is
    normalised into created."""
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


# ---------------------------------------------------------------------------
# Registry consultation: verifiedUsing hashes, registered id reuse, hash
# mismatch warn+mint (see pitloom.ids.IdRegistry)
# ---------------------------------------------------------------------------

# An existing on-disk file, stable across the test run, used as a stand-in
# "dataset" so add_dataset()'s "name is an existing file" branch engages.
_EXISTING_FILE = "pyproject.toml"


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_loom_dataset_gets_verified_using_hash_when_file_exists() -> None:
    """A dataset name that is an existing file gets a SHA-256 verifiedUsing
    hash, even with no registry -- this is what lets merge's hash-fallback
    unification work without one."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        (ds,) = [d for d in datasets if d["name"] == _EXISTING_FILE]
        (hash_obj,) = ds["verifiedUsing"]
        assert hash_obj["algorithm"] == "sha256"
        assert hash_obj["hashValue"] == _sha256_of(_EXISTING_FILE)


def test_loom_dataset_without_existing_file_has_no_hash() -> None:
    """A dataset name that is not an existing file gets no verifiedUsing --
    unchanged legacy behaviour."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset("no-such-file-anywhere.txt")

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert "verifiedUsing" not in ds


def test_loom_registry_id_reuse_for_dataset_and_model() -> None:
    """A dataset/model already registered gets the registry's spdxId, not a
    freshly minted one."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = IdRegistry(
        namespace=namespace,
        files={
            _EXISTING_FILE: FileEntry(
                spdx_id=f"{namespace}#File-1", sha256=_sha256_of(_EXISTING_FILE)
            )
        },
        entities={
            "registered-model": EntityEntry(
                type="ai_AIPackage", spdx_id=f"{namespace}#AIPackage-1"
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file, registry=registry):
            loom.set_model("registered-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert model["spdxId"] == f"{namespace}#AIPackage-1"
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] == f"{namespace}#File-1"


def test_loom_registry_hash_mismatch_warns_and_mints_new_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry entry whose recorded hash no longer matches the file's
    current content is treated as unregistered: warn, then mint a fresh id
    rather than reusing the stale one."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = IdRegistry(
        namespace=namespace,
        files={
            _EXISTING_FILE: FileEntry(
                spdx_id=f"{namespace}#File-1",
                sha256="0" * 64,  # deliberately wrong
            )
        },
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, registry=registry):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] != f"{namespace}#File-1"
        assert any("no longer matches" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Script File + generates relationships
# ---------------------------------------------------------------------------


def test_loom_training_run_emits_script_file_and_generates_edge() -> None:
    """A run that declares a model and a training dataset (add_dataset) gets
    a software_File for the calling script plus a generates edge to the
    model -- the heuristic default (generated=None)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        script_files = [
            e
            for e in graph
            if e["type"] == "software_File"
            and e.get("name") == "tests/core/test_loom_registry.py"
        ]
        assert len(script_files) == 1

        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        rels = _relationships(graph)
        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["from"] == script_files[0]["spdxId"]
        assert generates[0]["to"] == [model["spdxId"]]


def test_loom_testedon_only_run_emits_hasdatafile_edge() -> None:
    """An evaluation-only run (model + validation dataset, no training
    dataset) gets no generates edge, but DOES get a hasDataFile edge and
    a script File."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_validation_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        assert [e for e in graph if e["type"] == "software_File"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]


def test_loom_generated_true_override_forces_edge() -> None:
    """generated=True forces the generates edge even without a training
    dataset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model", generated=True)
            loom.add_validation_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert [r for r in rels if r.get("relationshipType") == "generates"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_generated_false_override_emits_hasdatafile_edge() -> None:
    """generated=False suppresses the generates edge even with a training
    dataset declared, but emits hasDataFile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model", generated=False)
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_use_model_emits_hasdatafile_edge() -> None:
    """use_model is an explicit shortcut for set_model(generated=False),
    emitting hasDataFile even if a training dataset is accidentally declared."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.use_model("test-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
        assert [r for r in rels if r.get("relationshipType") == "hasDataFile"]
        assert [e for e in graph if e["type"] == "software_File"]


def test_loom_output_dataset_only_run_gets_generates_edge_to_outputs() -> None:
    """A preprocessing-style run (no model, only output datasets) gets a
    generates edge from the script to its output dataset(s)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.add_output_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        rels = _relationships(graph)
        (generates,) = [r for r in rels if r.get("relationshipType") == "generates"]
        assert generates["to"] == [ds["spdxId"]]


def test_loom_repl_caller_gets_no_script_file() -> None:
    """When the caller cannot be resolved to an on-disk script (e.g. a REPL
    frame), no script File is emitted even for an otherwise-generates-worthy
    run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with patch("pitloom.loom._get_caller_script_path", return_value=None):
            with loom.run(output_file):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        assert not [e for e in graph if e["type"] == "software_File"]
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
