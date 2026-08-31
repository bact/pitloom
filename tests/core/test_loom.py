# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration and unit tests for the pitloom.loom module.

See also:
- :mod:`tests.core.test_loom_hyperparameters` for hyperparameters, lineage, and scopes.
- :mod:`tests.core.test_loom_creators` for comments, creators, and tools.
- :mod:`tests.core.test_loom_registry` for registry and script file / generates tests.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import _loom_active_run, loom
from pitloom.core.models import _ID_COUNTERS

from .conftest import _relationships


def test_get_caller_info_exception_logs_and_returns_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When inspect.stack() itself raises, _get_caller_info() catches it,
    logs at debug level, and returns the same fallback."""
    with patch(
        "pitloom._loom_caller.inspect.stack", side_effect=RuntimeError("no frames")
    ):
        with caplog.at_level(logging.DEBUG, logger="pitloom.loom"):
            # pylint: disable=protected-access
            result = _loom_active_run._get_caller_info()

    assert result == "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"
    assert any("caller info" in r.message for r in caplog.records)


def test_run_exit_without_active_run_is_a_noop() -> None:
    """Run.__exit__ is a no-op (no finalize, no crash) when there is no
    active run at all -- e.g. __exit__ invoked without a matching __enter__."""
    run_ctx = loom.Run("unused.json")
    run_ctx.previous_run = None

    original_active_run = loom._active_run
    loom._active_run = None
    try:
        run_ctx.__exit__(None, None, None)
        # previous_run was None, and __exit__ found no active run to
        # finalize -- _active_run stays None rather than raising.
        assert loom._active_run is None
    finally:
        loom._active_run = original_active_run


def test_loom_run_as_context_manager() -> None:
    """Test using loom.run as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_ctx.json"

        with loom.run(output_file):
            loom.set_model("test-model-1")
            loom.add_dataset("test-dataset-1", dataset_type="text")
            loom.add_dataset("test-dataset-2", dataset_type="image")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "@context" in data
        graph = data["@graph"]

        # Verify model
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert models[0]["name"] == "test-model-1"
        assert "test_loom_run_as_context_manager" in models[0].get("comment", "")
        assert "test_loom.py" in models[0].get("comment", "")
        model_id = models[0].get("@id", models[0].get("spdxId"))

        # Verify datasets
        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 2
        dataset_names = {d["name"] for d in datasets}
        assert "test-dataset-1" in dataset_names
        assert "test-dataset-2" in dataset_names
        assert all("test_loom.py" in d.get("comment", "") for d in datasets)
        assert all(
            "test_loom_run_as_context_manager" in d.get("comment", "") for d in datasets
        )

        # Verify relationships
        rels = _relationships(graph)
        trained_on = [r for r in rels if r.get("relationshipType") == "trainedOn"]
        assert len(trained_on) == 2
        for rel in trained_on:
            assert rel["from"] == model_id
            assert len(rel["to"]) == 1
            assert any(d.get("@id", d.get("spdxId")) == rel["to"][0] for d in datasets)

        generates = [r for r in rels if r.get("relationshipType") == "generates"]
        assert len(generates) == 1
        assert generates[0]["to"] == [model_id]
        assert len(rels) == 3


def test_loom_run_as_decorator() -> None:
    """Test using loom.run as a function decorator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_dec.json"

        @loom.run(output_file)
        def dummy_train_function() -> None:
            loom.set_model("test-model-2")
            loom.add_dataset("test-dataset-3", dataset_type="audio")

        dummy_train_function()

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]

        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert models[0]["name"] == "test-model-2"
        assert "dummy_train_function" in models[0].get("comment", "")
        assert "test_loom.py" in models[0].get("comment", "")

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 1
        assert datasets[0]["name"] == "test-dataset-3"
        assert "dummy_train_function" in datasets[0].get("comment", "")
        assert "test_loom.py" in datasets[0].get("comment", "")


def test_loom_run_with_exception() -> None:
    """Test that a fragment is NOT generated if an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_error.json"

        class DummyError(Exception):
            """Simulates a training failure."""

        try:
            with loom.run(output_file):
                loom.set_model("error-model")
                loom.add_dataset("error-dataset")
                raise DummyError("Something went wrong during training")
        except DummyError:
            pass

        assert not output_file.exists()


def test_loom_validation_dataset() -> None:
    """Test add_validation_dataset creates testedOn relationship."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_valid.json"

        with loom.run(output_file):
            loom.set_model("test-model-valid")
            loom.add_dataset("train.txt", dataset_type="text")
            loom.add_validation_dataset("valid.txt", dataset_type="text")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]

        datasets = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
        assert len(datasets) == 2
        dataset_names = {d["name"] for d in datasets}
        assert "train.txt" in dataset_names
        assert "valid.txt" in dataset_names

        rels = _relationships(graph)
        rel_types = {r.get("relationshipType") for r in rels}
        assert "trainedOn" in rel_types
        assert "testedOn" in rel_types


def test_loom_run_clears_id_counters_on_success() -> None:
    """A ``loom.Run``'s ``doc_uuid`` is a fresh ``uuid4`` per run (unlike
    the deterministic doc_uuids other document builders use), so nothing
    will ever revisit it to clear stale ``_ID_COUNTERS`` entries the way
    those builders' "clear right before reuse" pattern does. Regression
    test: ``Run.__exit__`` must explicitly clear its run's counters, or
    every run leaks its ``_ID_COUNTERS`` entries for the rest of the
    process."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_counters.json"

        with loom.run(output_file) as run:
            doc_uuid = run.doc_uuid
            loom.set_model("test-model-counters")
            loom.add_dataset("test-dataset-counters")

        assert not any(key[0] == doc_uuid for key in _ID_COUNTERS)


def test_loom_run_clears_id_counters_on_exception() -> None:
    """Same guarantee as above, but on the exception path -- where
    ``finalize()`` is never called (the fragment is only written on
    success) -- so counter cleanup can't just live inside ``finalize()``,
    it has to happen in ``Run.__exit__`` itself regardless of outcome."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_counters_exc.json"
        doc_uuid = None

        with pytest.raises(RuntimeError):
            with loom.run(output_file) as run:
                doc_uuid = run.doc_uuid
                loom.set_model("test-model-counters-exc")
                raise RuntimeError("boom")

        assert doc_uuid is not None
        assert not any(key[0] == doc_uuid for key in _ID_COUNTERS)


def test_loom_model_type() -> None:
    """Test set_model with model_type sets ai_typeOfModel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test_fragment_modeltype.json"

        with loom.run(output_file):
            loom.set_model("test-model-type", model_type="supervised")
            loom.add_dataset("train.txt")

        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        models = [e for e in graph if e["type"] == "ai_AIPackage"]
        assert len(models) == 1
        assert "supervised" in models[0].get("ai_typeOfModel", [])
