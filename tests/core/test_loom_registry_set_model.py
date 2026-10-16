# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.loom registry ids when set_model() or a dataset is
repeated: each distinct content gets its own id, and a repl caller gets no
script file.

See also: test_loom_registry.py (dataset and edge ids),
_loom_registry_shared.py (shared hash helper).
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import loom
from pitloom.id_registry import FILE_TYPE
from tests.core._loom_registry_shared import (
    _EXISTING_FILE,
    _sha256_of,
)
from tests.registry_helpers import make_registry

from .conftest import _relationships


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
