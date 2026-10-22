# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.id_registry.persist_registry` when a save is
skipped, fails or reads no file: a failed write is one ``WARNING:``, an
unread registry never replaces a file, and a namespace change is replayed.

See also: test_persist_registry.py (two runs sharing one file),
_persist_registry_shared.py (helpers shared by both halves).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import errno
import logging
import os
from pathlib import Path
from typing import TextIO

import pytest

from pitloom import loom
from pitloom._sbom_io import open_text_lf
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    IdRegistry,
    IdRegistrySession,
    persist_registry,
    save_registry,
)
from tests.id_registry._persist_registry_shared import (
    _NS,
    _messages,
    _registry_file,
)
from tests.registry_helpers import entries_of, make_registry


@pytest.mark.parametrize("damage", ["deleted", "corrupted"])
def test_a_file_that_no_longer_loads_is_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, damage: str
) -> None:
    """Re-reading fails after the run's output was written: one
    ``failed to save`` WARNING, nothing raised, nothing recreated."""
    path = _registry_file(tmp_path)
    registry = IdRegistry.load(path)
    registry.register(AI_PACKAGE_TYPE, "m", sha256="1" * 64)
    if damage == "deleted":
        path.unlink()
    else:
        path.write_bytes(b"{")

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(registry, 1, True)

    (warning,) = _messages(caplog, logging.WARNING)
    assert warning.startswith(f"ID registry: failed to save {path}")
    assert not _messages(caplog, logging.INFO)
    assert path.exists() is (damage == "corrupted")


def test_a_failed_write_leaves_the_old_file_and_no_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A write that fails half-way (a full disk) leaves the old file whole,
    never partial JSON, and no temporary file."""
    path = _registry_file(tmp_path)
    before = path.read_bytes()
    registry = IdRegistry.load(path)
    registry.register(AI_PACKAGE_TYPE, "m", sha256="1" * 64)

    real_open = open_text_lf

    def _partial(descriptor: int) -> TextIO:
        stream = real_open(descriptor)
        stream.write("{")
        stream.flush()
        stream.close()
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr("pitloom._sbom_io.open_text_lf", _partial)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        persist_registry(registry, 1, True)

    assert path.read_bytes() == before
    assert sorted(os.listdir(tmp_path)) == ["reg.json"]
    (warning,) = _messages(caplog, logging.WARNING)
    assert "failed to save" in warning


@pytest.mark.parametrize(
    ("registry_path", "changed", "warns"),
    [(False, True, True), (False, False, True), (True, False, False)],
    ids=["no-path", "no-path-unchanged", "unchanged"],
)
def test_nothing_is_saved(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    registry_path: bool,
    changed: bool,
    warns: bool,
) -> None:
    """No file path: the no-path WARNING, whatever changed. Unchanged: no
    write and no line."""
    path = _registry_file(tmp_path)
    before = path.read_bytes()
    registry = IdRegistry.load(path) if registry_path else make_registry()

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(registry, 0, changed)

    assert path.read_bytes() == before
    expected = ["ID registry: no file path resolved; skipping auto-update."]
    assert [r.getMessage() for r in caplog.records] == (expected if warns else [])


def test_a_registry_that_read_no_file_is_saved_as_it_is(tmp_path: Path) -> None:
    """A registry made in memory with a path has no table to tell its own
    changes by: it is saved whole, creating the file."""
    path = tmp_path / "new" / "reg.json"
    registry = IdRegistry.new("demo", path=path)
    registry.register(AI_PACKAGE_TYPE, "m", sha256="1" * 64)

    persist_registry(registry, 1, True)

    assert entries_of(IdRegistry.load(path)) == entries_of(registry)


def test_an_unread_registry_keeps_the_file_it_would_replace(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A registry made in memory for an existing file adds to it: the
    file's entries and namespace stay."""
    path = _registry_file(tmp_path)
    before = entries_of(IdRegistry.load(path))
    registry = IdRegistry.new("demo", path=path)
    registry.register(AI_PACKAGE_TYPE, "m", sha256="1" * 64)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(registry, 1, True)

    saved = IdRegistry.load(path)
    assert saved.namespace == _NS
    assert entries_of(saved) == {**before, **entries_of(registry)}
    assert _messages(caplog, logging.INFO) == [
        f"ID registry: added 1 new id(s) to '{path}'"
    ]


def test_an_unread_registry_never_replaces_a_file_that_does_not_load(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "reg.json"
    path.write_bytes(b"{")
    registry = IdRegistry.new("demo", path=path)
    registry.register(AI_PACKAGE_TYPE, "m", sha256="1" * 64)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(registry, 1, True)

    assert path.read_bytes() == b"{"
    (warning,) = _messages(caplog, logging.WARNING)
    assert warning.startswith(f"ID registry: failed to save {path}")


def test_a_loom_run_with_an_unread_registry_keeps_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Loom re-reads the file before it mints: the run's model joins the
    file's entries in the file's namespace."""
    path = _registry_file(tmp_path)
    before = entries_of(IdRegistry.load(path))
    (tmp_path / "m.bin").write_bytes(b"weights")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )

    with loom.Run(
        tmp_path / "frag.json", id_registry=IdRegistry.new("demo", path=path)
    ):
        loom.set_model("m", path="m.bin")

    saved = IdRegistry.load(path)
    model = saved.get(AI_PACKAGE_TYPE, "m.bin")
    assert model is not None and model.spdx_id.startswith(f"{_NS}#")
    assert {k: v for k, v in entries_of(saved).items() if k in before} == before


def test_register_id_needs_a_registry() -> None:
    with pytest.raises(ValueError, match="no ID registry"):
        IdRegistrySession(None).register_id("m", AI_PACKAGE_TYPE, "m", sha256="1")


@pytest.mark.parametrize(
    ("mine", "theirs", "saved"),
    [
        ("urn:mine", None, "urn:mine"),
        ("urn:mine", "urn:x", "urn:x"),
        (None, "urn:x", "urn:x"),
    ],
    ids=["mine", "both", "theirs"],
)
def test_a_namespace_change_is_replayed_unless_the_file_changed_it(
    tmp_path: Path, mine: str | None, theirs: str | None, saved: str
) -> None:
    """``id import`` adopting an SBOM's namespace is this run's change: it
    is saved, unless another run changed the file's namespace meanwhile."""
    path = _registry_file(tmp_path)
    registry, other = IdRegistry.load(path), IdRegistry.load(path)
    if theirs is not None:
        other.namespace = theirs
        other.save()
    if mine is not None:
        registry.namespace = mine

    save_registry(registry)

    assert IdRegistry.load(path).namespace == saved
