# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.id_registry.persist_registry`: a run's changes
are re-applied onto the registry file as it is at save time, so two runs
sharing one file keep both their entries; an id another run saved first
for another key is not recorded.

See also: tests/id_registry/test_registry_sync_log.py (the log lines
through run auto-harvest), tests/core/test_loom_model.py (loom, the other
writer), tests/test_sbom_io.py (the atomic replace),
test_persist_registry_save.py (skipped, failed and unread saves),
_persist_registry_shared.py (shared helpers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    RegistryEntry,
    persist_registry,
)
from pitloom.id_registry._persist import replay_changes
from tests.id_registry._persist_registry_shared import (
    _NS,
    _messages,
    _registry_file,
)
from tests.registry_helpers import make_registry

_DOC = "https://spdx.org/spdxdocs/demo-run"
_CI = spdx3.CreationInfo(
    specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
)


def _entry(n: int, sha: str | None = None) -> RegistryEntry:
    return RegistryEntry(spdx_id=f"{_NS}#AIPackage-{n}", sha256=sha)


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
        # Mine gave a known id a second key: replayed.
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


@pytest.mark.parametrize(
    ("theirs_key", "merged_key", "refused"),
    [("demo/x.py", "src/demo/x.py", 0), ("other/x.py", "other/x.py", 1)],
    ids=["promoted", "theirs-moved"],
)
def test_replay_changes_a_promotion(
    caplog: pytest.LogCaptureFixture,
    theirs_key: str,
    merged_key: str,
    refused: int,
) -> None:
    """Mine promoted a known id from ``demo/x.py`` to ``src/demo/x.py``:
    replayed; theirs moved it to another key meanwhile: refused, once."""
    entry = RegistryEntry(f"{_NS}#File-1", "ab" * 32)
    held, promoted = (FILE_TYPE, "demo/x.py"), (FILE_TYPE, "src/demo/x.py")

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        replayed = replay_changes(
            {held: entry}, {promoted: entry}, {(FILE_TYPE, theirs_key): entry}
        )

    assert replayed == ({(FILE_TYPE, merged_key): entry}, refused)
    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == refused
    assert all("another run saved" in w for w in warnings)


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
