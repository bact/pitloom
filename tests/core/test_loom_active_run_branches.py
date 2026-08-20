# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Branch-coverage tests for pitloom._loom_active_run's relationship-emission
and finalize() guard clauses -- the "build_relationship returned None",
"mkdir skipped", and "no hash for the script file" edge paths that the
behavioural tests in test_loom.py / test_loom_registry.py don't exercise.

See also:
- :mod:`tests.core.test_loom` for loom.run() basics and dataset lineage.
- :mod:`tests.core.test_loom_registry` for registry and script file /
  generates edge behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pitloom import _loom_active_run, loom

from .conftest import _relationships


def test_finalize_skips_relationships_when_build_relationship_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When build_relationship() returns None (from_id is None), each of the
    trainedOn/testedOn/hasInput/generates loops must skip add_relationship
    and simply continue, rather than crash."""
    monkeypatch.setattr(
        "pitloom._loom_active_run.build_relationship", lambda **_kw: None
    )

    output_file = tmp_path / "frag_none_rels.json"
    with loom.run(output_file):
        loom.set_model("test-model")
        loom.add_dataset("train.txt")
        loom.add_validation_dataset("valid.txt")
        loom.add_input_dataset("raw.txt")
        loom.add_output_dataset("out.txt", input_datasets=["raw.txt"])

    assert output_file.exists()
    graph = json.loads(output_file.read_text())["@graph"]
    # Every relationship was suppressed by the stubbed build_relationship.
    assert not _relationships(graph)
    # The packages themselves are still emitted.
    assert [e for e in graph if e["type"] == "ai_AIPackage"]
    assert [e for e in graph if e["type"] == "dataset_DatasetPackage"]


def test_finalize_skips_has_data_file_relationship_when_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The hasDataFile branch (generated=False) also tolerates
    build_relationship() returning None."""
    monkeypatch.setattr(
        "pitloom._loom_active_run.build_relationship", lambda **_kw: None
    )

    output_file = tmp_path / "frag_none_hasdatafile.json"
    with loom.run(output_file):
        loom.set_model("test-model", generated=False)
        loom.add_dataset("train.txt")

    assert output_file.exists()
    graph = json.loads(output_file.read_text())["@graph"]
    assert not _relationships(graph)


def test_finalize_skips_mkdir_when_output_parent_is_falsy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """finalize() only calls output_path.parent.mkdir() when the parent is
    truthy; simulate a falsy parent (Path.parent can't itself be falsy) via
    a stand-in Path-like object."""

    class _FalsyParentPath:
        """A minimal os.PathLike whose .parent is falsy (None)."""

        def __init__(self, path: str) -> None:
            self._path = Path(path)

        def __fspath__(self) -> str:
            return str(self._path)

        @property
        def parent(self) -> None:
            return None

    monkeypatch.setattr(
        "pitloom._loom_active_run.Path",
        lambda p: _FalsyParentPath(p),
    )

    output_file = tmp_path / "frag_falsy_parent.json"
    with loom.run(output_file):
        loom.set_model("test-model")
        loom.add_dataset("train.txt")

    assert output_file.exists()


def test_script_file_has_no_verified_using_when_hash_lookup_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_build_script_file leaves verifiedUsing unset when
    _hash_and_registry_lookup can't compute a hash for the script (e.g. it
    isn't a real on-disk file from the lookup's point of view)."""
    real_lookup = _loom_active_run._hash_and_registry_lookup

    def fake_lookup(name: str, registry: Any) -> tuple[None, None] | Any:
        if name.endswith(".py"):
            return None, None
        return real_lookup(name, registry)

    monkeypatch.setattr(
        "pitloom._loom_active_run._hash_and_registry_lookup", fake_lookup
    )

    output_file = tmp_path / "frag_no_script_hash.json"
    with loom.run(output_file):
        loom.set_model("test-model")
        loom.add_dataset("train.txt")

    graph = json.loads(output_file.read_text())["@graph"]
    (script,) = [e for e in graph if e["type"] == "software_File"]
    assert "verifiedUsing" not in script
