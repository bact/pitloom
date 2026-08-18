# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for _loom_caller stack frame inspection and loom SDK helper functions.

See also:
- :mod:`tests.core.test_loom` for loom context manager and decorator basics.
- :mod:`tests.core.test_loom_registry` for ID registry integration.
"""

from __future__ import annotations

import collections
import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import _loom_caller, loom
from pitloom.ids import EntityEntry, FileEntry, IdRegistry


def test_loom_functions_raise_runtime_error_without_active_run() -> None:
    """All module-level loom functions raise RuntimeError when no active run exists."""
    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.set_model("model-a")

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.use_model("model-b")

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.set_model_hyperparameters({"lr": "0.01"})

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.add_dataset("data.txt")

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.add_validation_dataset("valid.txt")

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.add_input_dataset("input.txt")

    with pytest.raises(RuntimeError, match="No active loom.run"):
        loom.add_output_dataset("output.txt")


def test_loom_module_level_helpers_inside_active_run() -> None:
    """Module-level loom functions work correctly inside an active run context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "module_helpers_frag.spdx3.json"

        with loom.run(output_file):
            loom.use_model("pretrained-bert", model_type="Transformer")
            loom.set_model_hyperparameters({"epochs": "3", "batch_size": "32"})
            loom.add_input_dataset("raw_corpus.txt", dataset_type="text")
            loom.add_output_dataset(
                "tokenized.bin",
                dataset_type="binary",
                data_preprocessing=["tokenization", "subword"],
                input_datasets=["raw_corpus.txt"],
            )

        assert output_file.exists()
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        assert any(e.get("name") == "pretrained-bert" for e in graph)
        assert any(e.get("name") == "raw_corpus.txt" for e in graph)
        assert any(e.get("name") == "tokenized.bin" for e in graph)


def test_loom_nested_runs_restore_previous_run() -> None:
    """Exiting an inner loom.run restores the outer active run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outer_file = Path(tmpdir) / "outer.spdx3.json"
        inner_file = Path(tmpdir) / "inner.spdx3.json"

        with loom.run(outer_file) as outer_run:
            # pylint: disable=protected-access
            loom.set_model("outer-model")

            with loom.run(inner_file) as inner_run:
                assert loom._active_run is inner_run
                loom.set_model("inner-model")

            assert loom._active_run is outer_run
            loom.add_dataset("outer_data.txt")

        assert outer_file.exists()
        assert inner_file.exists()


def test_caller_info_module_level_and_external_path() -> None:
    """_get_caller_info formats '<module>' and paths outside cwd properly."""
    fake_frame = collections.namedtuple(
        "fake_frame", ["filename", "function", "lineno"]
    )

    # Frame with function == '<module>' and path outside cwd
    frame = fake_frame(
        filename="/opt/custom/scripts/train_script.py",
        function="<module>",
        lineno=10,
    )
    with patch("pitloom._loom_caller.inspect.stack", return_value=[frame]):
        # pylint: disable=protected-access
        info = _loom_caller._get_caller_info()
        assert "train_script.py" in info
        assert "function: <module>" in info

    # Frame with a named function outside cwd
    frame2 = fake_frame(
        filename="/opt/custom/scripts/eval_script.py",
        function="evaluate",
        lineno=25,
    )
    with patch("pitloom._loom_caller.inspect.stack", return_value=[frame2]):
        # pylint: disable=protected-access
        info2 = _loom_caller._get_caller_info()
        assert "eval_script.py" in info2
        assert "function: evaluate" in info2


def test_caller_script_path_edge_cases() -> None:
    """_get_caller_script_path handles repl frames, missing files, and outside cwd."""
    fake_frame = collections.namedtuple("fake_frame", ["filename"])

    # 1. Filename starts with '<' (REPL / stdin)
    repl_frame = fake_frame(filename="<stdin>")
    with patch("pitloom._loom_caller.inspect.stack", return_value=[repl_frame]):
        # pylint: disable=protected-access
        assert _loom_caller._get_caller_script_path() is None

    # 2. Filename does not exist on disk
    nonexistent = fake_frame(filename="/tmp/nonexistent_dummy_file_12345.py")
    with patch("pitloom._loom_caller.inspect.stack", return_value=[nonexistent]):
        # pylint: disable=protected-access
        assert _loom_caller._get_caller_script_path() is None

    # 3. Existing file outside cwd
    with tempfile.NamedTemporaryFile(suffix=".py") as f:
        ext_frame = fake_frame(filename=f.name)
        with patch("pitloom._loom_caller.inspect.stack", return_value=[ext_frame]):
            # pylint: disable=protected-access
            result = _loom_caller._get_caller_script_path()
            assert result is not None
            assert Path(result).name == Path(f.name).name

    # 4. Exception in inspect.stack
    with patch("pitloom._loom_caller.inspect.stack", side_effect=RuntimeError("fail")):
        # pylint: disable=protected-access
        assert _loom_caller._get_caller_script_path() is None


def test_hash_and_registry_lookup_content_changed_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_hash_and_registry_lookup logs a warning when a file's hash changed."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"modified content")
        file_path = f.name

    try:
        registry = IdRegistry(
            namespace="https://spdx.org/spdxdocs/test",
            files={
                file_path: FileEntry(
                    spdx_id="https://spdx.org/spdxdocs/doc/test-File-1",
                    sha256="0" * 64,
                )
            },
            entities={},
        )
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            # pylint: disable=protected-access
            hash_elem, registered_id = _loom_caller._hash_and_registry_lookup(
                file_path, registry
            )
            assert hash_elem is not None
            assert registered_id is None
            assert any("content changed" in r.message for r in caplog.records)
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_active_run_set_model_registry_type_mismatch_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ActiveRun.set_model logs warning when an entity has a different type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "type_mismatch.spdx3.json"
        registry = IdRegistry(
            namespace="https://spdx.org/spdxdocs/test",
            files={},
            entities={
                "my_model": EntityEntry(
                    type="software_Package",  # Different from ai_AIPackage
                    spdx_id="https://spdx.org/spdxdocs/doc/test-Package-1",
                )
            },
        )
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file, registry=registry) as run:
                run.set_model("my_model")

            assert any("different type" in r.message for r in caplog.records)


def test_active_run_resolve_input_ids_missing_dataset_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ActiveRun logs warning when output references undeclared input dataset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "missing_input_ds.spdx3.json"
        with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
            with loom.run(output_file) as run:
                run.add_input_dataset("input_a.txt")
                run.add_output_dataset(
                    "output_b.txt",
                    input_datasets=["nonexistent_input.txt"],
                )

            assert any(
                "no add_input_dataset('nonexistent_input.txt') was declared"
                in r.message
                for r in caplog.records
            )


def test_active_run_use_model_has_data_file_relationship() -> None:
    """ActiveRun.use_model marks model consumed and emits hasDataFile edge."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "use_model.spdx3.json"
        with loom.run(output_file) as run:
            run.use_model(
                "inference-bert",
                model_type="Transformer",
                hyperparameters={"temp": "0.7"},
            )

        assert output_file.exists()
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        assert any(e.get("name") == "inference-bert" for e in graph)
        rels = [e for e in graph if "relationshipType" in e]
        assert any(r.get("relationshipType") == "hasDataFile" for r in rels)


def test_active_run_preprocessing_only_without_model() -> None:
    """ActiveRun without a model generates a valid preprocessing fragment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "preprocessing_only.spdx3.json"
        with loom.run(output_file) as run:
            run.add_input_dataset("raw_data.csv")
            run.add_output_dataset(
                "cleaned_data.parquet",
                data_preprocessing=["outlier_removal"],
            )

        assert output_file.exists()
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        assert not any(e.get("type") == "ai_AIPackage" for e in graph)
        assert any(e.get("name") == "raw_data.csv" for e in graph)
        assert any(e.get("name") == "cleaned_data.parquet" for e in graph)


def test_active_run_set_model_hyperparameters_without_model_raises() -> None:
    """ActiveRun.set_model_hyperparameters raises when no model is set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "no_model.spdx3.json"
        with pytest.raises(RuntimeError, match="No model set"):
            with loom.run(output_file) as run:
                run.set_model_hyperparameters({"lr": "0.01"})


def test_active_run_input_only_returns_early_without_script() -> None:
    """ActiveRun with only input dataset (no model/output) generates no script edges."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "input_only.spdx3.json"
        with loom.run(output_file) as run:
            run.add_input_dataset("input_only.csv")

        assert output_file.exists()
        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)

        graph = data["@graph"]
        assert not any(e.get("type") == "ai_AIPackage" for e in graph)
        assert any(e.get("name") == "input_only.csv" for e in graph)
