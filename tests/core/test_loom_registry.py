# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom registry consultation and script-file + generates edges.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and dataset lineage.
- :mod:`tests.core.test_loom_creators` for creators and tools handling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.id_registry import DATASET_PACKAGE_TYPE, FILE_TYPE
from tests.registry_helpers import make_registry

from .conftest import _relationships

# An existing on-disk file, stable across the test run, used as a stand-in
# "dataset" so add_dataset()'s "name is an existing file" branch engages.
_EXISTING_FILE = "pyproject.toml"


def _sha256_of(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_loom_dataset_gets_verified_using_hash_when_file_exists() -> None:
    """A dataset name that is an existing file gets a SHA-256 verifiedUsing hash."""
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
    """A dataset name that is not an existing file gets no verifiedUsing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.set_model("test-model")
            loom.add_dataset("no-such-file-anywhere.txt")

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert "verifiedUsing" not in ds


def test_loom_registry_id_reuse_for_dataset_and_model() -> None:
    """A dataset, its file and the model already registered get the
    registry's spdxIds, each under its own type."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {
            (FILE_TYPE, _EXISTING_FILE): (
                f"{namespace}#File-1",
                _sha256_of(_EXISTING_FILE),
            ),
            (DATASET_PACKAGE_TYPE, _EXISTING_FILE): (
                f"{namespace}#DatasetPackage-1",
                None,
            ),
            ("ai_AIPackage", "registered-model"): (f"{namespace}#AIPackage-1", None),
        },
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file, id_registry=registry):
            loom.set_model("registered-model")
            loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert model["spdxId"] == f"{namespace}#AIPackage-1"
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert ds["spdxId"] == f"{namespace}#DatasetPackage-1"
        (data_file,) = [
            e
            for e in graph
            if e["type"] == "software_File" and e["name"] == _EXISTING_FILE
        ]
        assert data_file["spdxId"] == f"{namespace}#File-1"


def test_loom_registry_hash_mismatch_warns_and_mints_new_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A registry entry with non-matching recorded hash is treated as unregistered."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {(FILE_TYPE, _EXISTING_FILE): (f"{namespace}#File-1", "0" * 64)},  # wrong
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        files = [e for e in graph if e.get("name") == _EXISTING_FILE]
        assert {e["type"] for e in files} == {"software_File", "dataset_DatasetPackage"}
        assert f"{namespace}#File-1" not in {e["spdxId"] for e in files}
        assert any("no longer matches" in r.message for r in caplog.records)


def test_loom_training_run_emits_script_file_and_generates_edge() -> None:
    """A training run gets a software_File for calling script and generates edge."""
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
    """An evaluation-only run gets a hasDataFile edge and a script File."""
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
    """generated=True forces the generates edge even without a training dataset."""
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
    """generated=False suppresses generates edge, emits hasDataFile."""
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
    """use_model is an explicit shortcut for set_model(generated=False)."""
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
    """A preprocessing run gets a generates edge to its output dataset(s)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with loom.run(output_file):
            loom.add_output_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        (ds,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        rels = _relationships(graph)
        (generates,) = [r for r in rels if r.get("relationshipType") == "generates"]
        assert generates["to"] == [ds["spdxId"]]


def test_loom_set_model_called_twice_with_registry_gets_two_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``set_model()`` called twice for the same name (e.g. once before and
    once after training, a common loom pattern) with a registry: the
    first call claims the registered id, the second is unconditionally a
    miss -- not raise, two distinct ``ai_AIPackage`` elements, one
    ``WARNING: ID registry: ... registered for both ...``. Matches
    no-registry behaviour (two elements) except for the warning, which
    is the truthful record of which call got the registered id."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {("ai_AIPackage", "m"): (f"{namespace}#AIPackage-1", None)},
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("m")
                loom.set_model("m")

        graph = json.loads(output_file.read_text())["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 2
        assert models[0]["spdxId"] != models[1]["spdxId"]
        assert f"{namespace}#AIPackage-1" in {m["spdxId"] for m in models}
        warnings = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "registered for both" in r.message
        ]
        assert len(warnings) == 1


def test_loom_set_model_called_twice_with_different_content_gets_two_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``set_model()`` called twice for the same name but with *differing*
    content (e.g. hyperparameters filled in after training) must not
    raise, and must not silently collapse into the first: the second
    call gets its own fresh id plus one ``WARNING: ID registry: ...
    registered for both ...``, matching what happens with no registry
    at all."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {("ai_AIPackage", "m"): (f"{namespace}#AIPackage-1", None)},
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("m")
                loom.set_model("m", model_type="cnn", hyperparameters={"lr": "0.1"})

        graph = json.loads(output_file.read_text())["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 2
        assert models[0]["spdxId"] != models[1]["spdxId"]
        assert f"{namespace}#AIPackage-1" in {m["spdxId"] for m in models}
        warnings = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "registered for both" in r.message
        ]
        assert len(warnings) == 1


def test_loom_input_then_output_dataset_after_file_rewrite_gets_two_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A realistic pipeline: ``add_input_dataset("data.txt")`` before
    training, the script rewrites ``data.txt``, then
    ``add_output_dataset("data.txt")`` after -- same name, same default
    ``dataset_type``, but a DIFFERENT file hash (``verifiedUsing``). This
    is the case a content-*signature* comparison misses, because the
    signature never covered the hash: must not raise, and each dataset
    keeps its own distinct id."""
    monkeypatch.chdir(tmp_path)
    data_file = tmp_path / "data.txt"
    data_file.write_text("before\n")
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {(FILE_TYPE, "data.txt"): (f"{namespace}#File-1", _sha256_of("data.txt"))},
        namespace=namespace,
    )

    output_file = tmp_path / "frag.json"
    with loom.run(output_file, id_registry=registry):
        loom.add_input_dataset("data.txt")
        data_file.write_text("after\n")
        loom.add_output_dataset("data.txt")

    graph = json.loads(output_file.read_text())["@graph"]
    datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert len(datasets) == 2
    assert datasets[0]["spdxId"] != datasets[1]["spdxId"]
    hash_values = {d["verifiedUsing"][0]["hashValue"] for d in datasets}
    assert len(hash_values) == 2


def test_loom_script_file_hit_shares_id_with_dataset_gets_two_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The generating script's own registry hit is a loom registry hit like
    any other, and goes through the run's claims the same way a dataset's
    file does. A registry where a dataset file's key and the script's key
    share one id (two independently-registered files never meant to
    collide) must not raise at ``Run.__exit__``: the dataset's file claims
    the id first, the script's own hit is a miss and gets its own fresh id
    plus one collision warning."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.txt").write_text("data\n")
    (tmp_path / "script.py").write_text("print('hi')\n")
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    shared_id = f"{namespace}#File-1"
    registry = make_registry(
        {
            (FILE_TYPE, "data.txt"): (shared_id, _sha256_of("data.txt")),
            (FILE_TYPE, "script.py"): (shared_id, _sha256_of("script.py")),
        },
        namespace=namespace,
    )

    output_file = tmp_path / "frag.json"
    with patch(
        "pitloom._loom_active_run._get_caller_script_path", return_value="script.py"
    ):
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("m")
                loom.add_input_dataset("data.txt")

    graph = json.loads(output_file.read_text())["@graph"]
    files = {e["name"]: e for e in graph if e["type"] == "software_File"}
    data_id, script_id = files["data.txt"]["spdxId"], files["script.py"]["spdxId"]
    assert data_id == shared_id != script_id  # the dataset's file claimed it first
    warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "registered for both" in r.message
    ]
    assert len(warnings) == 1


def test_loom_set_model_hyperparameters_then_set_model_again_gets_two_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``set_model("m")`` -> ``set_model_hyperparameters({...})`` (mutating
    the first ``ai_AIPackage`` element in place) -> ``set_model("m")``
    again: the first and second elements now differ (hyperparameters
    present vs. absent). This is the case a content-*signature* recorded
    only at the first call's own time misses, since the mutation happens
    after that. Must not raise, two distinct ids, one warning."""
    namespace = "https://spdx.org/spdxdocs/test-proj-fixed"
    registry = make_registry(
        {("ai_AIPackage", "m"): (f"{namespace}#AIPackage-1", None)},
        namespace=namespace,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, id_registry=registry):
                loom.set_model("m")
                loom.set_model_hyperparameters({"lr": "0.1"})
                loom.set_model("m")

        graph = json.loads(output_file.read_text())["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 2
        assert models[0]["spdxId"] != models[1]["spdxId"]
        has_hyperparameters = [bool(m.get("ai_hyperparameter")) for m in models]
        assert sorted(has_hyperparameters) == [False, True]
        warnings = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "registered for both" in r.message
        ]
        assert len(warnings) == 1


def test_loom_repl_caller_gets_no_script_file() -> None:
    """When caller cannot be resolved to a script file, no script File is emitted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "frag.json"
        with patch(
            "pitloom._loom_active_run._get_caller_script_path", return_value=None
        ):
            with loom.run(output_file):
                loom.set_model("test-model")
                loom.add_dataset(_EXISTING_FILE)

        graph = json.loads(output_file.read_text())["@graph"]
        files = [e["name"] for e in graph if e["type"] == "software_File"]
        assert files == [_EXISTING_FILE]  # the dataset's file, no script
        rels = _relationships(graph)
        assert not [r for r in rels if r.get("relationshipType") == "generates"]
