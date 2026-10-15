# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for loom models resolved at run exit (:mod:`pitloom._loom_model`):
``path=`` is hashed when the run ends, the hash gates the registry lookup of
the model's name, a miss is registered and saved after the fragment, and a
raising block touches nothing.

See also: tests/core/test_loom_registry.py (registry reuse at large),
tests/id_registry/test_persist_registry.py (the save),
tests/id_registry/test_loom_miss_warnings.py (the miss wording).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import _loom_model, loom
from pitloom._loom_active_run import _ActiveRun
from pitloom.core.config import PitloomConfig
from pitloom.core.file_hash import sha256_digest
from pitloom.core.models import _clear_doc_counters
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from tests._network import assert_spdx3_validate_ok
from tests._unreadable import POSIX_NON_ROOT, deny
from tests.registry_helpers import Entries, entries_of, make_registry


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_NS = "https://spdx.org/spdxdocs/test-1"
_BYTES = b"weights v1"
_SHA = _sha256(_BYTES)
_OTHER = "0" * 64


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project holding the model file ``m.bin`` and ``sub/``;
    the calling script is not captured."""
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    (root / "m.bin").write_bytes(_BYTES)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _registry(root: Path, entries: Entries | None = None) -> Path:
    path = root / "reg.json"
    make_registry(entries, path=path)
    return path


def _models(output: Path) -> list[dict[str, Any]]:
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return [e for e in graph if e["type"] == "ai_AIPackage"]


def _sha_of(model: dict[str, Any]) -> str | None:
    hashes = model.get("verifiedUsing") or [{}]
    value: str | None = hashes[0].get("hashValue")
    return value


def _logged(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


@pytest.mark.parametrize(
    ("entries", "model_id", "infos"),
    [
        ({(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-7", _SHA)}, 7, []),
        ({}, 1, ["added 1"]),
        ({(FILE_TYPE, "m"): (f"{_NS}#File-1", _SHA)}, 1, ["added 1"]),
        (
            {(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-7", _OTHER)},
            8,
            ["content changed", "added 1"],
        ),
        (
            {(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-7", None)},
            8,
            ["content changed", "added 1"],
        ),
    ],
    ids=["hit", "miss", "other-type", "retrained", "name-only-pin"],
)
def test_model_with_a_file_is_gated_and_recorded(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    entries: Entries,
    model_id: int,
    infos: list[str],
) -> None:
    """A hit reuses the id; any miss (a retrained file, or a pin with no
    hash, D12) registers a new id under the model's name, never its path."""
    path = _registry(project, entries)
    before = path.read_bytes()

    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json", id_registry=path) as run:
            loom.set_model("m", path="m.bin")
            resolved = [run.model]
        resolved.append(run.model)

    assert resolved[0] is None and resolved[1] is not None

    (model,) = _models(project / "out.json")
    assert model["spdxId"] == f"{_NS}#AIPackage-{model_id}"
    assert _sha_of(model) == _SHA
    assert not _logged(caplog, logging.WARNING)
    logged = _logged(caplog, logging.INFO)
    assert len(logged) == len(infos)
    assert all(needle in line for needle, line in zip(infos, logged, strict=True))
    saved = IdRegistry.load(path)
    entry = saved.get(AI_PACKAGE_TYPE, "m")
    assert entry is not None and (entry.spdx_id, entry.sha256) == (
        model["spdxId"],
        _SHA,
    )
    assert saved.get(AI_PACKAGE_TYPE, "m.bin") is None
    assert (path.read_bytes() == before) is (not infos)


@pytest.mark.parametrize(
    ("registry_kind", "needle"),
    [("no-update", "not found in registry"), ("in-memory", "no file path resolved")],
    ids=["update-false", "in-memory"],
)
def test_a_miss_not_recorded_mints_with_one_warning(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    registry_kind: str,
    needle: str,
) -> None:
    """``update-id-registry = false`` (from ``pitloom_config``) or a
    registry with no file: no write, one WARNING, a minted id, still the
    hash."""
    path = _registry(project)
    before = path.read_bytes()
    registry: IdRegistry | Path = (
        path if registry_kind == "no-update" else (make_registry())
    )
    config = PitloomConfig(update_id_registry=registry_kind != "no-update")

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(
            project / "out.json", id_registry=registry, pitloom_config=config
        ):
            loom.set_model("m", path="m.bin")

    (model,) = _models(project / "out.json")
    assert not model["spdxId"].startswith(_NS)
    assert _sha_of(model) == _SHA
    (warning,) = _logged(caplog, logging.WARNING)
    assert needle in warning
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("second", "warns", "infos"),
    [("m.bin", True, ["added 1"]), ("m2.bin", False, ["content changed", "added 1"])],
    ids=["same-file", "other-file"],
)
def test_a_model_declared_twice(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    second: str,
    warns: bool,
    infos: list[str],
) -> None:
    """The same file twice: the second hits the id the first registered,
    its claim is rejected (one collision WARNING, a fresh id, not
    recorded). Another file: the second replaces the entry; one id added."""
    (project / "m2.bin").write_bytes(b"weights v2")
    path = _registry(project)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json", id_registry=path):
            loom.set_model("m", path="m.bin")
            loom.set_model("m", path=second)

    first, other = _models(project / "out.json")
    assert first["spdxId"] != other["spdxId"]
    warnings = _logged(caplog, logging.WARNING)
    assert [("registered for both" in w) for w in warnings] == ([True] * warns)
    logged = _logged(caplog, logging.INFO)
    assert len(logged) == len(infos)
    assert all(needle in line for needle, line in zip(infos, logged, strict=True))
    registered = IdRegistry.load(path).get(AI_PACKAGE_TYPE, "m")
    assert registered is not None
    assert registered.spdx_id in {first["spdxId"], other["spdxId"]}


def test_path_is_absolute_at_the_call_and_hashed_at_exit(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative ``path=`` names the file from the directory of the call,
    whatever the directory at exit; the file may be written after it."""
    path = _registry(project)
    with loom.run(project / "out.json", id_registry=path):
        loom.set_model("m", path="late.bin")
        monkeypatch.chdir(project / "sub")
        (project / "late.bin").write_bytes(_BYTES)

    (model,) = _models(project / "out.json")
    assert _sha_of(model) == _SHA
    entry = IdRegistry.load(path).get(AI_PACKAGE_TYPE, "m")
    assert entry is not None and entry.sha256 == _SHA


_CHMOD_FILE = pytest.param(
    "chmod-file",
    "could not read for the model hash",
    marks=pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root"),
    id="chmod-file",
)


@pytest.mark.parametrize(
    ("case", "needle"),
    [
        ("none", "has no path="),
        ("missing", "gone.bin is not a file at exit"),
        ("directory", "sub is not a file at exit"),
        ("raced", "m.bin is not a file at exit"),
        ("stat", "could not read for the model hash"),
        _CHMOD_FILE,
    ],
    ids=["none", "missing", "directory", "raced", "stat", "chmod-file"],
)
def test_without_a_usable_file_the_name_is_looked_up_ungated(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
    needle: str,
) -> None:
    """No ``path=``, or one that is not a regular file at exit (gone between
    its check and its read included), or cannot be read: one WARNING, then
    the name lookup ignoring the recorded hash (a sharded model directory
    included); no hash, no write."""
    path = _registry(project, {(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-7", _OTHER)})
    before = path.read_bytes()
    given = {"none": None, "missing": "gone.bin", "directory": "sub"}.get(case, "m.bin")
    if case == "raced":

        def _gone(file: str) -> bytes:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file)

        monkeypatch.setattr(_loom_model, "sha256_digest", _gone)

    denied = case in ("stat", "chmod-file")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with (
            deny(project / "m.bin", case, monkeypatch)
            if denied
            else contextlib.nullcontext()
        ):
            with loom.run(project / "out.json", id_registry=path):
                loom.set_model("m", path=given)

    (model,) = _models(project / "out.json")
    assert model["spdxId"] == f"{_NS}#AIPackage-7"
    assert "verifiedUsing" not in model
    (warning,) = _logged(caplog, logging.WARNING)
    assert needle in warning
    assert path.read_bytes() == before


@pytest.mark.parametrize("given", [None, "m.bin"], ids=["no-path", "path"])
def test_no_registry_is_silent(
    project: Path, caplog: pytest.LogCaptureFixture, given: str | None
) -> None:
    """Without a registry a missing hash is normal absence: no warning."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "out.json"):
            loom.use_model("m", path=given)

    (model,) = _models(project / "out.json")
    assert _sha_of(model) == (None if given is None else _SHA)
    assert not caplog.records


def test_a_raising_block_hashes_and_writes_nothing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is hashed, looked up, recorded or written; the same block
    not raising does all of it (so the run had something to record)."""
    path = _registry(project)
    before = path.read_bytes()
    reads: list[str] = []
    real = sha256_digest

    def _spy(file: str) -> bytes:
        reads.append(file)
        return real(file)

    monkeypatch.setattr(_loom_model, "sha256_digest", _spy)

    with pytest.raises(RuntimeError, match="training failed"):
        with loom.run(project / "out.json", id_registry=path):
            loom.set_model("m", path="m.bin")
            raise RuntimeError("training failed")

    assert not reads
    assert not (project / "out.json").exists()
    assert path.read_bytes() == before

    with loom.run(project / "out.json", id_registry=path):
        loom.set_model("m", path="m.bin")
    assert reads
    assert path.read_bytes() != before


def test_the_fragment_is_written_before_the_registry(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The registry is saved after the fragment; a failed save is one
    WARNING and the run still ends cleanly."""
    path = _registry(project)
    output = project / "out.json"
    seen: list[bool] = []

    def _save(_registry_obj: IdRegistry, _path: Path | None = None) -> None:
        seen.append(output.exists())
        raise OSError("disk full")

    monkeypatch.setattr(IdRegistry, "save", _save)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(output, id_registry=path):
            loom.set_model("m", path="m.bin")

    assert seen == [True]
    (model,) = _models(output)
    assert _sha_of(model) == _SHA
    (warning,) = _logged(caplog, logging.WARNING)
    assert warning.startswith(f"ID registry: failed to save {path}")


def test_training_and_evaluation_share_one_id_and_a_retrain_mints_one(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Train (``set_model``) then evaluate (``use_model``): one id, with no
    ``id generate --entity``. Retrain (new bytes): a new id and exactly one
    ``content changed`` INFO."""
    path = _registry(project)
    with loom.run(project / "train.json", id_registry=path):
        loom.set_model("m", path="m.bin")
    recorded = path.read_bytes()
    with loom.run(project / "eval.json", id_registry=path):
        loom.use_model("m", path="m.bin")
    assert path.read_bytes() == recorded

    (project / "m.bin").write_bytes(b"weights v2")
    with caplog.at_level(logging.INFO, logger="pitloom"):
        with loom.run(project / "retrain.json", id_registry=path):
            loom.set_model("m", path="m.bin")

    (trained,), (evaluated,) = (
        _models(project / "train.json"),
        _models(project / "eval.json"),
    )
    (retrained,) = _models(project / "retrain.json")
    assert trained["spdxId"] == evaluated["spdxId"] != retrained["spdxId"]
    changed = [m for m in _logged(caplog, logging.INFO) if "content changed" in m]
    assert len(changed) == 1
    entry = IdRegistry.load(path).get(AI_PACKAGE_TYPE, "m")
    assert entry is not None and entry.spdx_id == retrained["spdxId"]


def test_interleaved_runs_sharing_one_registry_keep_both(project: Path) -> None:
    """Two runs open before either ends: each re-reads the file before
    minting and before saving, so both models are recorded, with two ids."""
    (project / "m2.bin").write_bytes(b"weights v2")
    path = _registry(project)
    first = _ActiveRun(str(project / "a.json"), id_registry=path)
    second = _ActiveRun(str(project / "b.json"), id_registry=path)
    try:
        first.set_model("m1", path="m.bin")
        second.set_model("m2", path="m2.bin")
        first.finalize()
        second.finalize()
    finally:
        _clear_doc_counters(first.doc_uuid)
        _clear_doc_counters(second.doc_uuid)

    saved = entries_of(IdRegistry.load(path))
    (m1,), (m2,) = _models(project / "a.json"), _models(project / "b.json")
    assert saved == {
        (AI_PACKAGE_TYPE, "m1"): (m1["spdxId"], _SHA),
        (AI_PACKAGE_TYPE, "m2"): (m2["spdxId"], _sha256(b"weights v2")),
    }
    assert m1["spdxId"] != m2["spdxId"]


def test_each_model_has_its_own_hash_object(project: Path) -> None:
    """Two models of one file: equal digests, two ``Hash`` objects."""
    with loom.run(project / "out.json") as run:
        loom.set_model("a", path="m.bin")
        loom.set_model("b", path=os.path.join(str(project), "m.bin"))

    hashes = [
        held
        for obj in run.exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage)
        for held in obj.verifiedUsing
        if isinstance(held, spdx3.Hash)
    ]
    assert len(hashes) == 2
    assert hashes[0] is not hashes[1]
    assert {h.hashValue for h in hashes} == {_SHA}


def test_annotations_name_the_resolved_model(project: Path) -> None:
    """Every annotation written at a call names the model's id once it is
    resolved; an empty hyperparameter update writes none."""
    with loom.run(project / "out.json"):
        loom.set_model("m", path="m.bin", hyperparameters={"lr": "0.1"})
        loom.set_model_hyperparameters({})
        loom.set_model_hyperparameters({"epoch": "3"})

    graph = json.loads((project / "out.json").read_text(encoding="utf-8"))["@graph"]
    (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    subjects = [e["subject"] for e in graph if e["type"] == "Annotation"]
    assert subjects == [model["spdxId"]] * 2
    assert "urn:pitloom:loom:pending" not in json.dumps(graph)


def test_a_registry_gone_before_exit_is_one_warning(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The registry file removed during the run: the model is still minted
    and hashed and the fragment written; the save is one ``failed to save``
    WARNING, not an exception."""
    path = _registry(project)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(project / "out.json", id_registry=path):
            loom.set_model("m", path="m.bin")
            path.unlink()

    (model,) = _models(project / "out.json")
    assert _sha_of(model) == _SHA
    (warning,) = _logged(caplog, logging.WARNING)
    assert warning.startswith(f"ID registry: failed to save {path}")
    assert not path.exists()


@pytest.mark.network
def test_a_hashed_model_validates(project: Path) -> None:
    path = _registry(project)
    with loom.run(project / "out.json", id_registry=path):
        loom.set_model("m", path="m.bin", hyperparameters={"lr": "0.1"})
        loom.add_dataset("m.bin")
    assert_spdx3_validate_ok(project / "out.json")


def test_model_path_with_nul_warns_unreadable_and_run_ends(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A NUL in ``path=`` is not a path: the model is not hashed, with the
    unreadable-file ``WARNING:``, and the fragment is still written."""
    out = tmp_path / "frag.json"
    with caplog.at_level(logging.WARNING, logger="pitloom.loom"):
        with loom.run(out):
            loom.set_model("m", path="a\x00b")
    assert out.exists()
    assert any("for the model hash" in r.message for r in caplog.records)
    # pylint: disable-next=protected-access
    assert loom._active_run is None
