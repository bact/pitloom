# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A registry made by ``id generate`` on a checkout (a pointer recorded by its
``oid``) is hit by the routes that keep the pointer text's digest: the
hook, a wheel and an sdist.

See also: tests/id_registry/test_registry_lfs_pointer.py (the checkout
route), tests/extract/project/test_hatch_hook_lfs_pointer.py.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.id_registry import FILE_TYPE, IdRegistry, RegistryEntry
from tests._lfs import lfs_pointer_bytes, write_project
from tests._raw_archive import write_raw_tar
from tests._wheel_models import write_model_wheel
from tests.extract.conftest import make_hook, staged_sbom

_CONTENT = b"real content\n"
_POINTER = lfs_pointer_bytes(_CONTENT)
_OID = hashlib.sha256(_CONTENT).hexdigest()
_TEXT_SHA = hashlib.sha256(_POINTER).hexdigest()
_OTHER_SHA = hashlib.sha256(b"other").hexdigest()
_INIT = b"x = 1\n"
_LOOK_ALIKE = b"version https://git-lfs.github.com/spec/v1\n" + b"x" * 1024
_TREES = {
    "pointer": {"demo/__init__.py": _INIT, "demo/data.bin": _POINTER},
    "look-alike": {"demo/__init__.py": _INIT, "demo/data.bin": _LOOK_ALIKE},
}
_NAMES = ("demo/__init__.py", "demo/data.bin")


def _ids(sbom: str, names: tuple[str, ...] = _NAMES) -> dict[str, str]:
    """The ``spdxId`` of the SBOM's files *names*, by name (an sdist's
    top directory dropped)."""
    return {
        name: n["spdxId"]
        for n in json.loads(sbom)["@graph"]
        if n.get("type") == "software_File"
        and (name := n.get("name", "").removeprefix("demo-1.0/")) in names
    }


def _hook_sbom(root: Path, _: Path, __: dict[str, bytes]) -> str:
    hook = make_hook(str(root), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        staged = staged_sbom(build_data)
        assert staged is not None
        return staged.read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def _wheel_sbom(root: Path, tmp_path: Path, tree: dict[str, bytes]) -> str:
    wheel = write_model_wheel(tmp_path / "dist", tree)
    return generate_wheel_sbom(wheel, id_registry=root / "ids.json")


def _sdist_sbom(root: Path, tmp_path: Path, tree: dict[str, bytes]) -> str:
    members = {
        "demo-1.0/PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        **{f"demo-1.0/{n}": d for n, d in tree.items()},
    }
    sdist = write_raw_tar(tmp_path / "demo-1.0.tar.gz", members)
    return generate_project_sbom(sdist, id_registry=root / "ids.json")


_ROUTES: dict[str, Callable[[Path, Path, dict[str, bytes]], str]] = {
    "hook": _hook_sbom,
    "wheel": _wheel_sbom,
    "sdist": _sdist_sbom,
}


def _checkout_registry(
    tmp_path: Path, tree: dict[str, bytes]
) -> tuple[Path, dict[str, RegistryEntry]]:
    """A project of *tree* whose registry ``id generate`` made (a pointer
    keyed by its ``oid``), declared in its ``pyproject.toml``; the entries
    of its files."""
    root = write_project(tmp_path / "p", tree)
    with (root / "pyproject.toml").open("ab") as handle:
        handle.write(b'[tool.pitloom]\nid-registry = "ids.json"\n')
    registry = IdRegistry.new("proj", root / "ids.json", project_root=root)
    registry.generate([Path("demo")], root)
    registry.save(root / "ids.json")
    entries = {n: registry.get(FILE_TYPE, n) for n in _NAMES}
    return root, {n: e for n, e in entries.items() if e is not None}


def _rekey(root: Path, name: str, sha256: str) -> None:
    """Make the registry at *root* record *sha256* for file *name*."""
    registry = IdRegistry.load(root / "ids.json")
    entry = registry.get(FILE_TYPE, name)
    assert entry is not None
    entry.sha256 = sha256
    registry.save(root / "ids.json")


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("kind", _TREES)
def test_a_checkout_registry_is_hit_by_the_routes_keeping_the_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str, kind: str
) -> None:
    """Both files reuse the id ``id generate`` gave them, a pointer through
    its ``oid`` though the SBOM states the text's digest; a look-alike (a
    long file opening like a pointer) is an ordinary file."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    tree = _TREES[kind]
    root, held = _checkout_registry(tmp_path, tree)
    assert sorted(held) == list(_NAMES)
    assert (held["demo/data.bin"].sha256 == _OID) is (kind == "pointer")
    ids = _ids(_ROUTES[route](root, tmp_path, tree))
    assert ids == {n: e.spdx_id for n, e in held.items()}


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize(
    ("kind", "recorded", "hits"),
    [
        ("pointer", _TEXT_SHA, True),  # an earlier run's own hash
        ("pointer", _OTHER_SHA, False),  # the gate stays
        ("look-alike", _OTHER_SHA, False),
    ],
    ids=["text-digest", "pointer-other-hash", "look-alike-other-hash"],
)
def test_the_hash_gate_accepts_the_text_or_the_oid_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    kind: str,
    recorded: str,
    hits: bool,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    tree = _TREES[kind]
    root, held = _checkout_registry(tmp_path, tree)
    _rekey(root, "demo/data.bin", recorded)
    ids = _ids(_ROUTES[route](root, tmp_path, tree))
    assert ids["demo/__init__.py"] == held["demo/__init__.py"].spdx_id
    assert (ids["demo/data.bin"] == held["demo/data.bin"].spdx_id) is hits


def test_pointers_of_one_oid_at_two_paths_keep_two_ids(
    tmp_path: Path,
) -> None:
    """A checkout under ``src/`` with two pointers of one ``oid``: a wheel
    of the same files, laid out without ``src/``, joins each member to its
    own entry through the layout alias, never both to one."""
    tree = {
        "src/demo/__init__.py": _INIT,
        "src/demo/x.bin": _POINTER,
        "src/demo/y.bin": _POINTER,
    }
    root = write_project(tmp_path / "p", tree)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src")], root)
    registry.save(root / "ids.json")
    held = {n: registry.get(FILE_TYPE, f"src/demo/{n}.bin") for n in "xy"}
    assert held["x"] and held["y"] and held["x"].spdx_id != held["y"].spdx_id
    assert held["x"].sha256 == held["y"].sha256 == _OID
    wheel = write_model_wheel(
        tmp_path / "dist",
        {"demo/__init__.py": _INIT, "demo/x.bin": _POINTER, "demo/y.bin": _POINTER},
    )
    sbom = generate_wheel_sbom(wheel, id_registry=root / "ids.json")
    ids = _ids(sbom, ("demo/x.bin", "demo/y.bin"))
    assert ids == {"demo/x.bin": held["x"].spdx_id, "demo/y.bin": held["y"].spdx_id}
