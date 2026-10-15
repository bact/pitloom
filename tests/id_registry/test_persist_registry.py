# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.id_registry.persist_registry`: a run's changes
are re-applied onto the registry file as it is at save time, so two runs
sharing one file keep both their entries; an id another run saved first
for another key is not recorded; a failed save is one ``WARNING:``.

See also: tests/id_registry/test_registry_sync_log.py (the log lines through
run auto-harvest), tests/core/test_loom_model.py (loom, the other writer),
tests/test_sbom_io.py (the atomic replace).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import errno
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom._sbom_io import open_text_lf
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    IdRegistrySession,
    RegistryEntry,
    persist_registry,
    save_registry,
)
from pitloom.id_registry._persist import replay_changes
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_DOC = "https://spdx.org/spdxdocs/demo-run"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)


def _entry(n: int, sha: str | None = None) -> RegistryEntry:
    return RegistryEntry(spdx_id=f"{_NS}#AIPackage-{n}", sha256=sha)


def _messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


def _table(spec: str) -> dict[tuple[str, str], RegistryEntry]:
    """``"a1 b2:f"``: model ``a`` as ``#AIPackage-1``, model ``b`` as
    ``#AIPackage-2`` with SHA-256 ``f``; ``"-"``: empty."""
    table: dict[tuple[str, str], RegistryEntry] = {}
    for item in spec.split():
        head, _, sha = item.partition(":")
        if head != "-":
            table[(AI_PACKAGE_TYPE, head[0])] = _entry(int(head[1:]), sha or None)
    return table


@pytest.mark.parametrize(
    ("base", "mine", "theirs", "merged", "refused"),
    [
        # Theirs added b meanwhile; mine added c: both kept.
        ("a1", "a1 c3", "a1 b2", "a1 b2 c3", 0),
        # Mine replaced a (content changed): mine wins over theirs.
        ("a1:1", "a2:2", "a1:1", "a2:2", 0),
        # Mine dropped a (a stale key released): dropped from theirs too.
        ("a1 b2", "b2", "a1 b2", "b2", 0),
        # Mine left a alone; theirs changed it: theirs kept.
        ("a1:1", "a1:1", "a4:4", "a4:4", 0),
        # Both minted #2 from one table, theirs for b, mine for c: refused.
        ("a1", "a1 c2", "a1 b2", "a1 b2", 1),
        # Mine moved a known id to a new key (a harvest's release): replayed.
        ("a1", "c1", "a1", "c1", 0),
        # Mine gave a known id a second key (a src-layout alias): replayed.
        ("a1", "a1 c1", "a1", "a1 c1", 0),
        # Both moved a's known id, mine to c, theirs to b: refused (I4).
        ("a1", "c1", "b1", "b1", 1),
        # No table read (a registry made in memory): mine onto theirs.
        ("-", "c2", "a1", "a1 c2", 0),
        # ... unless theirs holds mine's id already, for another key.
        ("-", "c1", "a1", "a1", 1),
        # A refused key keeps theirs' entry, so its id is held too (I4).
        ("-", "b2 m1", "b1 c2", "b1 c2", 2),
    ],
    ids=[
        "both-added",
        "replaced",
        "dropped",
        "untouched",
        "refused",
        "moved",
        "alias",
        "both-moved",
        "no-base",
        "no-base-held",
        "refused-holds",
    ],
)
def test_replay_changes(
    caplog: pytest.LogCaptureFixture,
    base: str,
    mine: str,
    theirs: str,
    merged: str,
    refused: int,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        replayed = replay_changes(_table(base), _table(mine), _table(theirs))
    assert replayed == (_table(merged), refused)
    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == refused
    if refused:
        assert "another run saved" in warnings[0]
        assert repr("c") in warnings[0]


def _files(*pairs: tuple[str, int]) -> spdx3.SHACLObjectSet:
    """``software_File`` elements ``(name, n)``, each ``#File-<n>`` of a
    document namespace."""
    object_set = spdx3.SHACLObjectSet()
    for name, number in pairs:
        object_set.add(
            spdx3.software_File(
                spdxId=f"{_DOC}#File-{number}", name=name, creationInfo=_CI
            )
        )
    return object_set


def _registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "reg.json"
    make_registry({(FILE_TYPE, "x.py"): (f"{_NS}#File-1", "f" * 64)}, path=path)
    return path


def test_two_runs_sharing_one_file_keep_both_entries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Two runs load the file; each re-reads it before minting and before
    saving: both entries survive, with two ids."""
    path = _registry_file(tmp_path)
    first, second = IdRegistry.load(path), IdRegistry.load(path)

    first.register(AI_PACKAGE_TYPE, "m1", sha256="1" * 64)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(first, 1, True)
        second.rebase()  # loom re-reads before minting
        second.register(AI_PACKAGE_TYPE, "m2", sha256="2" * 64)
        persist_registry(second, 1, True)

    saved = IdRegistry.load(path)
    m1, m2 = saved.get(AI_PACKAGE_TYPE, "m1"), saved.get(AI_PACKAGE_TYPE, "m2")
    assert m1 is not None and m2 is not None
    assert m1.spdx_id != m2.spdx_id
    assert saved.get(FILE_TYPE, "x.py") is not None
    assert (
        _messages(caplog, logging.INFO)
        == [f"ID registry: added 1 new id(s) to {path}"] * 2
    )


def test_an_id_saved_first_by_another_run_is_not_recorded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Both runs minted ``#AIPackage-1`` from one table (no re-read in
    between): the second's entry is not saved, so no two keys share it."""
    path = _registry_file(tmp_path)
    first, second = IdRegistry.load(path), IdRegistry.load(path)
    assert first.register(AI_PACKAGE_TYPE, "m1", sha256="1" * 64) == (
        second.register(AI_PACKAGE_TYPE, "m2", sha256="2" * 64)
    )
    persist_registry(first, 1, True)
    before = path.read_bytes()

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(second, 1, True)

    assert path.read_bytes() == before
    assert IdRegistry.load(path).get(AI_PACKAGE_TYPE, "m2") is None
    (warning,) = _messages(caplog, logging.WARNING)
    assert "another run saved" in warning
    assert not _messages(caplog, logging.INFO)


@pytest.mark.parametrize(
    ("unread", "new_ids", "message"),
    [(False, 0, "updated stale entries in"), (True, 1, "added 1 new id(s) to")],
    ids=["update", "unread"],
)
def test_the_added_count_is_at_most_the_caller_s(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    unread: bool,
    new_ids: int,
    message: str,
) -> None:
    """A re-mint for a key the file holds, counted as an update (a
    harvest's count), adds no id; a registry made in memory adds to a new
    file only the ids the caller says it added."""
    path = tmp_path / "reg.json"
    entries = {(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-1", None)}
    if unread:
        registry = make_registry(entries)
        registry.path = path
    else:
        make_registry(entries, path=path)
        registry = IdRegistry.load(path)
    registry.register(AI_PACKAGE_TYPE, "n" if unread else "m", sha256="1" * 64)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(registry, new_ids, True)

    assert _messages(caplog, logging.INFO) == [f"ID registry: {message} {path}"]


@pytest.mark.parametrize("refused", ["b", "m"], ids=["update", "addition"])
def test_the_added_count_leaves_out_a_refused_change(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, refused: str
) -> None:
    """The run added ``a`` and gave ``b`` (an update) or ``m`` (an
    addition) an id another run saved first for ``c``: that change is
    refused, ``a``'s addition counts, ``c``'s (theirs) never does."""
    path = tmp_path / "reg.json"
    make_registry({(FILE_TYPE, "b"): (f"{_NS}#File-9", None)}, path=path)
    mine, theirs = IdRegistry.load(path), IdRegistry.load(path)
    persist_registry(theirs, *theirs.harvest(_files(("b", 9), ("c", 2))))
    new_ids, changed = mine.harvest(_files(("a", 1), (refused, 2)))

    with caplog.at_level(logging.INFO, logger="pitloom"):
        persist_registry(mine, new_ids, changed)

    assert _messages(caplog, logging.INFO) == [
        f"ID registry: added 1 new id(s) to {path}"
    ]
    assert len(_messages(caplog, logging.WARNING)) == 1


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
        f"ID registry: added 1 new id(s) to {path}"
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
    model = saved.get(AI_PACKAGE_TYPE, "m")
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
