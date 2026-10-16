# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.id_registry.keys`: path keys, the on-disk
spelling step, project prefixes and artifact keys.

See also: test_keys_alias.py (layout aliases),
tests/id_registry/test_registry_key_for_path.py (the lexical,
identity and realpath steps, shared through ``registry_key_for_path``),
tests/core/test_walk_rules.py (``shortened_by``).
"""

from __future__ import annotations

import ntpath
import os
import posixpath
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from pitloom.core.file_identity import FileId
from pitloom.id_registry import (
    Alias,
    LookupKey,
    artifact_key,
    join_key,
    keys,
    path_key,
    project_prefix,
)
from pitloom.id_registry.keys import on_disk_path
from tests._symlink import CAN_SYMLINK
from tests.registry_helpers import make_registry

_NFD = "cafe\u0301"
_NFC = "caf\u00e9"


@pytest.fixture(name="project")
def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / "data" / "t.txt").write_bytes(b"x")
    return root


@pytest.mark.parametrize("on_disk", [False, True], ids=["as-spelt", "on-disk"])
@pytest.mark.parametrize(
    ("cwd", "given", "key"),
    [
        (".", "data/t.txt", "data/t.txt"),
        ("sub", "../data/t.txt", "data/t.txt"),
        ("sub", "./../data/./t.txt", "data/t.txt"),
        ("sub", "<root>/data/t.txt", "data/t.txt"),
        ("sub", "..", "."),
        (".", f"data/{_NFD}.txt", f"data/{_NFC}.txt"),
        ("..", "../elsewhere.txt", None),
        (".", "<root>-other/x", None),
    ],
    ids=["relative", "dotdot", "dots", "absolute", "root", "nfd", "outside", "sibling"],
)
def test_path_key(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    on_disk: bool,
    cwd: str,
    given: str,
    key: str | None,
) -> None:
    """Root-relative, ``/``-separated, NFC; ``"."`` for the root; ``None``
    outside it, a sibling sharing the root's name as a prefix included."""
    monkeypatch.chdir(project / cwd)
    registry = make_registry(project_root=project)
    path = given.replace("<root>", str(project))
    assert path_key(registry, path, on_disk=on_disk) == key


@pytest.mark.skipif(not CAN_SYMLINK, reason="needs symlinks")
def test_path_key_through_a_symlinked_ancestor(tmp_path: Path) -> None:
    """The root reached through a symlinked ancestor is the root by
    identity; the on-disk step lists below that spelling."""
    project = tmp_path / "real" / "proj"
    (project / "data").mkdir(parents=True)
    (project / "data" / "t.txt").write_bytes(b"x")
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    registry = make_registry(project_root=project)
    given = tmp_path / "alias" / "proj" / "data" / "t.txt"
    assert path_key(registry, given, on_disk=True) == "data/t.txt"


@pytest.mark.parametrize(
    ("path", "root", "parts"),
    [
        (r"C:\proj\data\t.txt", r"C:\proj", ("data", "t.txt")),
        (r"C:\PROJ\Data\t.txt", r"C:\proj", ("Data", "t.txt")),
        (r"C:\proj", r"C:\proj", ()),
        (r"D:\proj\x", r"C:\proj", None),
        (r"\\srv\share\proj\x", r"C:\proj", None),
        (r"\\srv\share\proj\x", r"\\srv\share\proj", ("x",)),
        (r"C:\proj-other\x", r"C:\proj", None),
    ],
    ids=["inside", "other-case", "root", "other-drive", "unc", "unc-root", "sibling"],
)
def test_windows_paths_below_the_root(
    path: str, root: str, parts: tuple[str, ...] | None
) -> None:
    """As Windows spells paths: case-insensitive root, kept tail spelling;
    another drive or UNC share is outside. The parts join with ``/``."""
    # pylint: disable-next=protected-access
    found = keys._below(PureWindowsPath(path), PureWindowsPath(root))
    assert (None if found is None else found[1]) == parts


@pytest.mark.parametrize("flavour", ["posix", "nt"])
@pytest.mark.parametrize(
    ("prefix", "rel", "posix", "nt"),
    [
        ("", "a/b.py", "a/b.py", "a/b.py"),
        ("pkg", "a/b.py", "pkg/a/b.py", "pkg/a/b.py"),
        ("pkg", ".", "pkg", "pkg"),
        ("", ".", ".", "."),
        ("pkg", "../shared/x.py", "shared/x.py", "shared/x.py"),
        ("", "../x.py", None, None),
        ("pkg", "../../x", None, None),
        ("pkg", "..", ".", "."),
        ("", "..", None, None),
        ("", "/abs/x", None, None),
        ("pkg", "C:/tmp/x", "pkg/C:/tmp/x", None),
        ("pkg", "C:x", "pkg/C:x", None),
        ("", f"{_NFD}/x", f"{_NFC}/x", f"{_NFC}/x"),
    ],
    ids=[
        "plain",
        "prefix",
        "dot",
        "root",
        "up-in",
        "up-out",
        "up-out-2",
        "up-to-root",
        "up-from-root",
        "absolute",
        "drive",
        "drive-relative",
        "nfd",
    ],
)
def test_join_key(
    monkeypatch: pytest.MonkeyPatch,
    flavour: str,
    prefix: str,
    rel: str,
    posix: str | None,
    nt: str | None,
) -> None:
    """``..`` collapsed lexically, NFC; ``None`` leaving the root or for
    an absolute path, a Windows drive included (each ``os.path`` flavour
    emulated on every platform)."""
    flavour_path = ntpath if flavour == "nt" else posixpath
    monkeypatch.setattr(keys, "os", SimpleNamespace(path=flavour_path))
    assert join_key(prefix, rel) == (posix if flavour == "posix" else nt)


def _fake_fs(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    listing: dict[str, list[str]],
    ids: dict[str, int],
) -> None:
    """Patch the listing and file identity below *root*: *listing* maps a
    root-relative directory (``""`` the root) to its names, a missing one
    is unlistable; *ids* maps a root-relative path to its identity."""

    def rel(path: str) -> str:
        found = os.path.relpath(path, root).replace(os.sep, "/")
        return "" if found == "." else found

    def listdir(directory: str) -> list[str]:
        if rel(directory) not in listing:
            raise PermissionError(directory)
        return listing[rel(directory)]

    def identity(path: str) -> FileId | None:
        number = ids.get(rel(path))
        return None if number is None else (1, number)

    monkeypatch.setattr(keys, "_listdir", listdir)
    monkeypatch.setattr(keys, "file_id", identity)


@pytest.mark.parametrize(
    ("given", "listing", "ids", "key"),
    [
        ("Data/t.txt", {"": ["DATA", "Data"]}, {"DATA": 1, "Data": 1}, "Data/t.txt"),
        (
            "DATA/T.TXT",
            {"": ["other", "data"], "data": ["t.txt"]},
            {"DATA": 1, "data": 1, "other": 1, "data/T.TXT": 2, "data/t.txt": 2},
            "data/t.txt",
        ),
        (
            "Data/x",
            {"": ["data", "DATA", "AAA"]},
            {"Data": 1, "data": 1, "DATA": 1, "AAA": 1},
            "DATA/x",
        ),
        ("DATA/t.txt", {}, {"DATA": 1, "data": 1}, "DATA/t.txt"),
        ("DATA/t.txt", {"": ["data"]}, {"data": 1}, "DATA/t.txt"),
        ("DATA/t.txt", {"": ["data"]}, {"DATA": 1, "data": 2}, "DATA/t.txt"),
        (f"{_NFC}/x", {"": [_NFD]}, {_NFC: 1, _NFD: 1}, f"{_NFC}/x"),
    ],
    ids=["exact", "case", "tie-sorted", "unlistable", "missing", "other-file", "nfd"],
)
def test_on_disk_spelling(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    given: str,
    listing: dict[str, list[str]],
    ids: dict[str, int],
    key: str,
) -> None:
    """Each part as its parent lists it: an exact listing wins; else the
    first sorted name folding alike that is the same file (a same-file
    name folding otherwise never); else the spelling as given. NFC out."""
    _fake_fs(monkeypatch, project, listing, ids)
    registry = make_registry(project_root=project)
    assert path_key(registry, project / given, on_disk=True) == key


def test_on_disk_spelling_of_a_real_file(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``data/T.TXT`` keys as the listed ``data/t.txt``: by the file
    system on a case-insensitive one; on a case-sensitive one, through a
    hard link the listing hides. Listed as spelt, it keeps its spelling."""
    target, other = project / "data" / "t.txt", project / "data" / "T.TXT"
    try:
        os.link(target, other)
        linked = True
    except FileExistsError:  # case-insensitive: already the same name
        linked = False
    except OSError:
        pytest.skip("hard links unavailable on this file system")
    registry = make_registry(project_root=project)
    if linked:
        assert path_key(registry, other, on_disk=True) == "data/T.TXT"
    real = os.listdir
    monkeypatch.setattr(
        keys, "_listdir", lambda d: [n for n in real(d) if n != "T.TXT"]
    )
    assert path_key(registry, other, on_disk=True) == "data/t.txt"
    assert path_key(registry, other) == "data/T.TXT"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("data/t.txt", LookupKey("data/t.txt", Alias.NONE, path=True)),
        (None, LookupKey("t")),
        ("data/missing.txt", LookupKey("t")),
        ("../outside.txt", LookupKey("t")),
    ],
    ids=["path", "no-path", "missing", "outside"],
)
def test_artifact_key(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    given: str | None,
    expected: LookupKey,
) -> None:
    """A path key (tier 1) when the path exists below the root, with the
    alias asked for; else the name (tier 2), never with an alias."""
    (project.parent / "outside.txt").write_bytes(b"y")
    monkeypatch.chdir(project)
    registry = make_registry(project_root=project)
    assert artifact_key(registry, path=given, name="t") == expected
    aliased = expected._replace(alias=Alias.CANONICAL) if expected.path else expected
    found = artifact_key(registry, path=given, name="t", alias=Alias.CANONICAL)
    assert found == aliased


@pytest.mark.parametrize(
    ("given", "prefix"),
    [(".", ""), ("sub", "sub"), ("..", None)],
    ids=["root", "below", "outside"],
)
def test_project_prefix(
    project: Path, monkeypatch: pytest.MonkeyPatch, given: str, prefix: str | None
) -> None:
    """The project directory's key: ``""`` at the root, ``None`` outside."""
    monkeypatch.chdir(project)
    registry = make_registry(project_root=project)
    assert project_prefix(registry, given) == prefix


@pytest.mark.parametrize(
    ("given", "spelt"),
    [
        ("DATA/T.TXT", "data/t.txt"),
        ("sub/../DATA", "data"),
        ("<root>-other/DATA", None),
    ],
    ids=["case", "dotdot", "outside"],
)
def test_on_disk_path(
    project: Path, monkeypatch: pytest.MonkeyPatch, given: str, spelt: str | None
) -> None:
    """Each part below the root as its directory lists it, ``..``
    collapsed; a path not below the root as given."""
    listing = {"": ["data", "sub"], "data": ["t.txt"]}
    ids = {"DATA": 1, "data": 1, "data/T.TXT": 2, "data/t.txt": 2}
    _fake_fs(monkeypatch, project, listing, ids)
    path = Path(given.replace("<root>", str(project)))
    path = path if path.is_absolute() else project / path
    found = on_disk_path(project, path)
    assert found == (path if spelt is None else project / spelt)
