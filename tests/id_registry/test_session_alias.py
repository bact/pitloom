# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The layout alias through :class:`~pitloom.id_registry.IdRegistrySession`
and a document build: a real file at the shorter key is no alias, only a
``src``/``lib`` first part aliases, a tie says so once per key, and a
document counts its alias hits in one ``INFO:``.

See also: test_session_keys.py (the lookup order and direction),
test_keys_alias.py (the candidates).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import FilesOrigin, ProjectFile, ProjectMetadata
from pitloom.id_registry import (
    FILE_TYPE,
    Alias,
    IdRegistry,
    IdRegistrySession,
    LookupKey,
)
from tests.id_registry._alias_shared import NoScanTable
from tests.registry_helpers import make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_EMPTY = hashlib.sha256(b"").hexdigest()
_A = "a" * 64
_HITS = "through the src/lib layout alias"


def _write(root: Path, *names: str) -> Path:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"")
    return root


def _session(root: Path, *held: str, sha: str = _EMPTY) -> IdRegistrySession:
    entries = {(FILE_TYPE, k): (f"{_NS}#File-{n}", sha) for n, k in enumerate(held, 1)}
    return IdRegistrySession(make_registry(entries, project_root=root))


def _find(
    session: IdRegistrySession, alias: Alias, key: str, sha: str = _EMPTY
) -> str | None:
    return session.lookup_key(key, FILE_TYPE, LookupKey(key, alias, True), sha256=sha)


@pytest.mark.parametrize("real", [True, False], ids=["both-real", "alias-only"])
def test_a_real_file_at_the_shorter_key_keeps_its_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, real: bool
) -> None:
    """``zebra/__init__.py`` and ``src/zebra/__init__.py`` both real, both
    empty: the canonical lookup first must not take the held id of the
    other real file (it would then lose it, with a WARNING)."""
    _write(tmp_path, "src/zebra/__init__.py", *(["zebra/__init__.py"] * real))
    session = _session(tmp_path, "zebra/__init__.py")

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        first = _find(session, Alias.CANONICAL, "src/zebra/__init__.py")
        second = _find(session, Alias.CANONICAL, "zebra/__init__.py")

    if real:
        assert (first, second) == (None, f"{_NS}#File-1")
        assert not caplog.records
    else:  # non-vacuous: without the real file it is the alias
        assert (first, second) == (f"{_NS}#File-1", None)


def test_a_flat_member_never_takes_another_top_directory(tmp_path: Path) -> None:
    """A wheel member ``foo/__init__.py`` missing its key does not take the
    id of ``tests/foo/__init__.py`` with the same bytes."""
    session = _session(tmp_path, "tests/foo/__init__.py", "docs/foo/__init__.py")

    assert _find(session, Alias.LAYOUT, "foo/__init__.py") is None
    other = _session(tmp_path, "lib/foo/__init__.py")
    assert _find(other, Alias.LAYOUT, "foo/__init__.py") == f"{_NS}#File-1"


def test_tie_info_once_per_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    held = ("src/a/x.py", "lib/a/x.py", "src/a/y.py", "lib/a/y.py")
    session = _session(tmp_path, *held)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        for key in ("a/x.py", "a/x.py", "a/y.py", "a/x.py"):
            assert _find(session, Alias.LAYOUT, key) is None
        assert _find(_session(tmp_path, *held), Alias.LAYOUT, "a/x.py") is None

    infos = [r.getMessage() for r in caplog.records]
    assert [m.split(" matches")[0] for m in infos] == [
        "ID registry: a/x.py",
        "ID registry: a/y.py",
        "ID registry: a/x.py",  # a new session says it again
    ]


def test_lookups_never_scan_the_table(tmp_path: Path) -> None:
    session = _session(tmp_path, "src/a/x.py", "b/y.py")
    registry = session.registry
    assert registry is not None
    registry.elements = NoScanTable(registry.elements)

    assert _find(session, Alias.LAYOUT, "a/x.py") == f"{_NS}#File-1"
    assert _find(session, Alias.CANONICAL, "src/b/y.py") == f"{_NS}#File-2"
    assert _find(session, Alias.LAYOUT, "c/z.py") is None


@pytest.mark.parametrize(
    ("lookups", "count"),
    [
        ([(Alias.LAYOUT, "a/x.py"), (Alias.CANONICAL, "src/b/y.py")], 2),
        ([(Alias.LAYOUT, "a/x.py"), (Alias.LAYOUT, "a/x.py")], 1),  # rejected
        ([(Alias.NONE, "src/a/x.py"), (Alias.LAYOUT, "c/z.py")], 0),
    ],
    ids=["two", "claim-rejected", "none"],
)
def test_alias_hits_info_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    lookups: list[tuple[Alias, str]],
    count: int,
) -> None:
    session = _session(tmp_path, "src/a/x.py", "b/y.py")
    for alias, key in lookups:
        _find(session, alias, key)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        session.info_layout_alias_hits()

    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    want = [f"ID registry: {count} element(s) matched a registry key {_HITS}"]
    assert infos == (want if count else [])


def _doc(project: Path, *files: tuple[str, str]) -> DocumentModel:
    return DocumentModel(
        project=ProjectMetadata(
            name="zebra",
            version="1.0.0",
            files=[ProjectFile(p, d, digest_sha256=_EMPTY) for p, d in files],
        ),
        files_origin=FilesOrigin(project_dir=project),
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )


def _file_ids(exporter: object) -> dict[str, str]:
    objects = exporter.object_set.objects  # type: ignore[attr-defined]
    return {
        o.name: o.spdxId for o in objects if o.get_compact_type() == "software_File"
    }


def test_build_keeps_each_real_files_id_and_counts_alias_hits(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Both ``zebra`` files real (one force-included elsewhere): each keeps
    its own id, no claim collision; one alias hit, one ``INFO:``."""
    project = _write(
        tmp_path, "src/zebra/__init__.py", "zebra/__init__.py", "src/zebra/a.py"
    )
    registry = make_registry(
        {
            (FILE_TYPE, "zebra/__init__.py"): (f"{_NS}#File-1", _EMPTY),
            (FILE_TYPE, "zebra/a.py"): (f"{_NS}#File-2", _EMPTY),
        },
        namespace=_NS,
        project_root=project,
    )
    doc = _doc(
        project,
        ("src/zebra/__init__.py", "zebra/__init__.py"),
        ("zebra/__init__.py", "vendored/zebra/__init__.py"),
        ("src/zebra/a.py", "zebra/a.py"),
    )

    with caplog.at_level(logging.INFO, logger="pitloom.id_registry"):
        ids = _file_ids(build(doc, registry=registry))

    assert ids["vendored/zebra/__init__.py"] == f"{_NS}#File-1"
    assert ids["zebra/a.py"] == f"{_NS}#File-2"  # the one alias hit
    assert ids["zebra/__init__.py"] not in (f"{_NS}#File-1", f"{_NS}#File-2")
    messages = [r.getMessage() for r in caplog.records]
    assert not [m for m in messages if "registered for both" in m]
    assert [m for m in messages if _HITS in m] == [
        f"ID registry: 1 element(s) matched a registry key {_HITS}"
    ]


def test_build_deployed_says_nothing_of_aliases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    doc = _doc(tmp_path)
    registry = IdRegistry.new("zebra", project_root=tmp_path)

    with caplog.at_level(logging.INFO, logger="pitloom.id_registry"):
        build_deployed(doc, [], registry=registry)
        build(doc, registry=registry)

    assert not [r for r in caplog.records if _HITS in r.getMessage()]


@pytest.mark.parametrize(
    ("alias", "key", "base", "found", "recorded"),
    [
        (Alias.LAYOUT, "p/d/a/x.py", "p/d", 1, "p/d/src/a/x.py"),
        (Alias.LAYOUT, "p/d/a/x.py", "", None, None),
        (Alias.CANONICAL, "p/d/src/b/y.py", "p/d", 2, "p/d/src/b/y.py"),
        (Alias.CANONICAL, "p/d/src/b/y.py", "", None, None),
        (Alias.CANONICAL, "p/d/a/x.py", "p/d", None, None),
        (Alias.LAYOUT, "p/d/src/b/y.py", "p/d", None, None),
    ],
    ids=[
        "layout",
        "layout-no-base",
        "canonical",
        "canonical-no-base",
        "canonical-wrong-way",
        "layout-wrong-way",
    ],
)
def test_alias_below_the_lookups_base(
    tmp_path: Path,
    alias: Alias,
    key: str,
    base: str,
    found: int | None,
    recorded: str | None,
) -> None:
    """A key joined to a project prefix takes its alias below it, in the
    lookup's direction only; a hit records the held key (``LAYOUT``) or
    the lookup key (``CANONICAL``)."""
    session = _session(tmp_path, "p/d/src/a/x.py", "p/d/b/y.py")
    lookup = LookupKey(key, alias, True, base)

    spdx_id = session.lookup_key(key, FILE_TYPE, lookup, sha256=_EMPTY)

    assert spdx_id == (None if found is None else f"{_NS}#File-{found}")
    keys = dict(session.recorded_keys())
    assert keys == ({} if spdx_id is None else {spdx_id: (FILE_TYPE, recorded)})
