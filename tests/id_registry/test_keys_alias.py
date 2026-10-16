# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the layout alias of :mod:`pitloom.id_registry.keys`:
``alias_tail``, ``is_layout_alias`` and ``alias_candidates``.

See also: test_keys.py (path keys), test_session_keys.py (the lookup's
direction filter), test_registry_generate_promote.py (``id generate``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

import pytest

from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    alias_candidates,
    alias_tail,
    is_layout_alias,
)
from pitloom.id_registry.keys import LAYOUT_ROOTS
from tests.id_registry._alias_shared import SCANNED, NoScanTable
from tests.registry_helpers import make_registry

_NFD = "café"
_NFC = "café"
_A, _B, _C, _D = "a" * 64, "b" * 64, "c" * 64, "d" * 64


def test_layout_roots() -> None:
    assert LAYOUT_ROOTS == ("src", "lib")


@pytest.mark.parametrize(
    ("key", "tail"),
    [
        ("src/demo/x.py", "demo/x.py"),
        ("lib/demo/x.py", "demo/x.py"),
        ("src/a/b/c", "a/b/c"),
        # only a src/lib layout: another first part is another file
        ("a/b/c/d", None),
        ("tests/foo/__init__.py", None),
        ("python/demo/x.py", None),
        ("Src/demo/x.py", None),
        ("demo/x.py", None),
        ("src/x.py", None),
        ("demo-1.0.data/data/x", None),
        ("src/demo-1.0.data/x", None),
        ("", None),
        ("./demo/x.py", None),
        ("src//demo/x.py", None),
        ("/src/demo/x.py", None),
        ("src/../demo/x.py", None),
    ],
    ids=[
        "src",
        "lib",
        "deeper",
        "other-root",
        "tests",
        "python",
        "case",
        "one-remains",
        "one-part",
        "data-first",
        "data-second",
        "empty",
        "dot",
        "empty-part",
        "absolute",
        "dotdot",
    ],
)
def test_alias_tail(key: str, tail: str | None) -> None:
    """A ``src``/``lib`` first part dropped, a directory and a file left,
    no ``*.data`` part either side, only for a clean relative key."""
    assert alias_tail(key) == tail


@pytest.mark.parametrize(
    ("first", "second", "alias"),
    [
        ("src/demo/x.py", "demo/x.py", True),
        ("demo/x.py", "lib/demo/x.py", True),
        ("tests/demo/x.py", "demo/x.py", False),
        ("a/src/demo/x.py", "demo/x.py", False),
        ("demo/x.py", "demo/x.py", False),
        ("src/x.py", "x.py", False),
        ("d-1.data/data/x", "data/x", False),
        ("src/d-1.data/x", "d-1.data/x", False),
        ("src/demo/x.py", "other/x.py", False),
    ],
    ids=[
        "shorter-second",
        "shorter-first",
        "other-root",
        "two-parts",
        "equal",
        "one-remains",
        "data-longer",
        "data-shorter",
        "other-dir",
    ],
)
def test_is_layout_alias(first: str, second: str, alias: bool) -> None:
    assert is_layout_alias(first, second) is alias


def test_alias_candidates(tmp_path: Path) -> None:
    """Held keys of the type that are layout aliases of the key in either
    direction, with the same hash (any case), sorted: a tie returns both;
    none ungated, none for another first part."""
    registry = make_registry(
        {
            (FILE_TYPE, "src/demo/x.py"): ("ns#File-1", _A),
            (FILE_TYPE, "lib/demo/x.py"): ("ns#File-2", _A),
            (FILE_TYPE, "pkg/demo/x.py"): ("ns#File-3", _B),
            (FILE_TYPE, "src/demo/y.py"): ("ns#File-4", _A),
            (FILE_TYPE, "demo/z.py"): ("ns#File-5", _C),
            (FILE_TYPE, f"src/demo/{_NFC}.py"): ("ns#File-6", _D),
            (FILE_TYPE, "lib/demo/w.py"): ("ns#File-7", None),
            (AI_PACKAGE_TYPE, "src/demo/x.py"): ("ns#AIPackage-1", _B),
        },
        project_root=tmp_path,
    )

    def found(key: str, sha: str | None, type_name: str = FILE_TYPE) -> Any:
        return alias_candidates(registry, type_name, key, sha)

    assert found("demo/x.py", _A.upper()) == ("lib/demo/x.py", "src/demo/x.py")
    assert not found("demo/x.py", _B)  # pkg/ is no layout root
    assert not found("demo/x.py", None)
    assert not found("demo/w.py", _A)
    assert found("src/demo/z.py", _C) == ("demo/z.py",)
    assert found(f"demo/{_NFD}.py", _D) == (f"src/demo/{_NFC}.py",)
    assert found("demo/x.py", _B, AI_PACKAGE_TYPE) == ("src/demo/x.py",)


@pytest.mark.parametrize(
    ("held", "key", "on_disk"),
    [
        ("zebra/__init__.py", "src/zebra/__init__.py", "zebra/__init__.py"),
        ("zebra/__init__.py", "src/zebra/__init__.py", "zebra/__init__.py/"),
        ("src/demo/x.py", "demo/x.py", "demo/x.py"),
    ],
    ids=["canonical-file", "canonical-dir", "layout"],
)
def test_alias_candidates_none_when_the_shorter_key_exists(
    tmp_path: Path, held: str, key: str, on_disk: str
) -> None:
    """A file or directory at the shorter key's path makes the two keys two
    real files, not one file and its alias."""
    registry = make_registry(
        {(FILE_TYPE, held): ("ns#File-1", _A)}, project_root=tmp_path
    )
    assert alias_candidates(registry, FILE_TYPE, key, _A) == (held,)

    target = tmp_path / on_disk
    if on_disk.endswith("/"):
        target.mkdir(parents=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")

    assert not alias_candidates(registry, FILE_TYPE, key, _A)


def test_alias_candidates_take_a_root(tmp_path: Path) -> None:
    """*root* replaces the registry's own root for the shorter key."""
    (tmp_path / "proj" / "demo").mkdir(parents=True)
    (tmp_path / "proj" / "demo" / "x.py").write_bytes(b"")
    registry = make_registry(
        {(FILE_TYPE, "demo/x.py"): ("ns#File-1", _A)}, project_root=tmp_path
    )

    assert alias_candidates(registry, FILE_TYPE, "src/demo/x.py", _A) == ("demo/x.py",)
    assert not alias_candidates(
        registry, FILE_TYPE, "src/demo/x.py", _A, root=tmp_path / "proj"
    )


def test_alias_candidates_none_without_a_root(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(_self: IdRegistry) -> NoReturn:
        raise FileNotFoundError("the current directory was deleted")

    registry = make_registry({(FILE_TYPE, "demo/x.py"): ("ns#File-1", _A)})
    monkeypatch.setattr(IdRegistry, "root_dir", gone)

    assert not alias_candidates(registry, FILE_TYPE, "src/demo/x.py", _A)
    assert not alias_candidates(registry, FILE_TYPE, "src/demo/y.py", _A)  # no hit


def test_alias_candidates_never_scan_the_table(tmp_path: Path) -> None:
    """Each candidate is one dictionary lookup: a run's lookups stay linear
    in its files, not their product with the registry's size."""
    registry = make_registry(
        {
            (FILE_TYPE, "demo/x.py"): ("ns#File-1", _A),
            (FILE_TYPE, "src/demo/y.py"): ("ns#File-2", _A),
            **{(FILE_TYPE, f"f{n}/x.py"): (f"ns#File-{n + 3}", _A) for n in range(50)},
        },
        project_root=tmp_path,
    )
    registry.elements = NoScanTable(registry.elements)

    assert alias_candidates(registry, FILE_TYPE, "src/demo/x.py", _A) == ("demo/x.py",)
    assert alias_candidates(registry, FILE_TYPE, "demo/y.py", _A) == ("src/demo/y.py",)
    with pytest.raises(AssertionError, match=SCANNED):
        list(registry.elements)  # non-vacuous: a walk would fail


@pytest.mark.parametrize(
    ("key", "tail"),
    [
        ("pkgs/demo/src/demo/x.py", "pkgs/demo/demo/x.py"),
        ("pkgs/demo/lib/demo/x.py", "pkgs/demo/demo/x.py"),
        ("pkgs/demo/demo/x.py", None),
        ("pkgs/demo/src/x.py", None),
        ("pkgs/demo/src/d-1.data/x", None),
        ("pkgs/other/src/demo/x.py", None),
        ("pkgs/demox/src/demo/x.py", None),
        ("src/demo/x.py", None),
    ],
    ids=["src", "lib", "flat", "one-remains", "data", "other", "sibling", "root"],
)
def test_alias_tail_below_a_base(key: str, tail: str | None) -> None:
    """The first part below the project prefix is cut; a key not below it
    has no alias."""
    assert alias_tail(key, "pkgs/demo") == tail


def test_alias_candidates_below_a_base(tmp_path: Path) -> None:
    """Both directions below *base*; the shorter full key on disk is two
    files; without *base* a monorepo key has no alias."""
    registry = make_registry(
        {
            (FILE_TYPE, "pkgs/demo/src/demo/x.py"): ("ns#File-1", _A),
            (FILE_TYPE, "pkgs/demo/demo/y.py"): ("ns#File-2", _A),
            (FILE_TYPE, "pkgs/demo/d-1.data/z.py"): ("ns#File-3", _A),
        },
        project_root=tmp_path,
    )

    def found(key: str, base: str = "pkgs/demo") -> Any:
        return alias_candidates(registry, FILE_TYPE, key, _A, base=base)

    assert found("pkgs/demo/demo/x.py") == ("pkgs/demo/src/demo/x.py",)
    assert found("pkgs/demo/src/demo/y.py") == ("pkgs/demo/demo/y.py",)
    assert not found("pkgs/demo/demo/x.py", "")
    assert not found("pkgs/demo/src/demo/y.py", "")
    assert not found("pkgs/demo/src/d-1.data/z.py")
    assert not found("other/demo/x.py")
    (tmp_path / "pkgs" / "demo" / "demo").mkdir(parents=True)
    (tmp_path / "pkgs" / "demo" / "demo" / "y.py").write_bytes(b"")
    assert not found("pkgs/demo/src/demo/y.py")
