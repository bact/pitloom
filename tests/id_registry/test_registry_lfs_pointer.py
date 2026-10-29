# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Git LFS pointer in the ID registry: the registry hash of a pointer is
its ``oid`` on every route, so a file keeps its id through ``git lfs
pull``, ``id generate``, a run and ``id import`` alike, though an archive's
SBOM states the pointer text's own digest.

See also: tests/test_lfs_pointer_surfaces.py (the routes' digests),
tests/core/test_file_hash.py (the stated-digest reader).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.file_hash import HexDigests
from pitloom.export.hashes import file_digests_of
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from pitloom.id_registry._sbom_read import read_sbom_objects
from tests._lfs import lfs_pointer_bytes, write_project
from tests._wheel_models import write_model_wheel

_CONTENT = b"real content\n"
_OID = hashlib.sha256(_CONTENT).hexdigest()
_POINTER = lfs_pointer_bytes(_CONTENT)
_INIT = b"x = 1\n"
_KEY = "demo/data.bin"


def _sbom_file(sbom: str, name: str) -> dict[str, Any]:
    (found,) = [
        n
        for n in json.loads(sbom)["@graph"]
        if n.get("type") == "software_File" and n.get("name") == name
    ]
    return dict(found)


def _digests(path: Path, name: str) -> HexDigests | None:
    """The digests the SBOM at *path* states for its file *name*."""
    (found,) = [o for o in read_sbom_objects(path) if getattr(o, "name", None) == name]
    return file_digests_of(found)


def _held(registry: IdRegistry, key: str = _KEY) -> tuple[str, str | None]:
    entry = registry.get(FILE_TYPE, key)
    assert entry is not None, key
    return entry.spdx_id, entry.sha256


def _generated(root: Path, path: Path | None = None) -> IdRegistry:
    registry = IdRegistry.load(path) if path else IdRegistry.new("proj")
    registry.generate([Path("demo")], root)
    return registry


def test_a_pointer_keeps_its_id_through_generate_run_import_and_a_pull(
    tmp_path: Path,
) -> None:
    root = write_project(tmp_path / "p", {"demo/__init__.py": _INIT, _KEY: _POINTER})
    path = root / "ids.json"
    _generated(root).save(path)
    seeded = _held(IdRegistry.load(path))
    assert seeded[1] == _OID  # the oid, not the digest of the pointer text

    # A run reuses the id, and states the same SHA-256 and no SHA-512.
    sbom = generate_project_sbom(root, creation_metadata=None, id_registry=path)
    assert _sbom_file(sbom, _KEY)["spdxId"] == seeded[0]
    sbom_path = tmp_path / "sbom.spdx3.json"
    sbom_path.write_text(sbom, encoding="utf-8")
    assert _digests(sbom_path, _KEY) == HexDigests(_OID, None)

    # An import of that SBOM makes the entry `id generate` made.
    imported = IdRegistry.new("other")
    imported.import_sbom(sbom_path)
    assert _held(imported) == seeded

    # After `git lfs pull`: other bytes, one hash, one id, now with a SHA-512.
    (root / _KEY).write_bytes(_CONTENT)
    assert (root / _KEY).read_bytes() != _POINTER
    assert _held(_generated(root, path)) == seeded
    assert _held(_generated(root))[1] == _OID  # a fresh registry: the same hash
    sbom_path.write_text(
        generate_project_sbom(root, creation_metadata=None, id_registry=path),
        encoding="utf-8",
    )
    pulled = _digests(sbom_path, _KEY)
    assert pulled is not None
    assert pulled.sha256 == _OID
    assert pulled.sha512 == hashlib.sha512(_CONTENT).hexdigest()
    assert (
        _sbom_file(sbom_path.read_text(encoding="utf-8"), _KEY)["spdxId"] == seeded[0]
    )


@pytest.mark.parametrize(
    "pair",
    [
        (_POINTER, _POINTER),
        (_POINTER, lfs_pointer_bytes(_CONTENT, eol="\r\n")),
        (b"same bytes\n", b"same bytes\n"),
    ],
    ids=["equal-pointers", "lf-and-crlf-pointers", "equal-plain-files"],
)
def test_equal_hashes_at_two_paths_stay_two_entries(
    tmp_path: Path, pair: tuple[bytes, bytes]
) -> None:
    """Pointers of one ``oid`` act as files of equal bytes do: each path has
    its entry and id (the layout alias, ``src/demo/x`` for ``demo/x``,
    names a real file here, so it joins nothing)."""
    tree = {"demo/x.bin": pair[0], "src/demo/x.bin": pair[1]}
    registry = IdRegistry.new("proj")
    registry.generate([Path("demo"), Path("src")], write_project(tmp_path, tree))
    first, second = _held(registry, "demo/x.bin"), _held(registry, "src/demo/x.bin")
    assert first[0] != second[0]
    assert first[1] == second[1]


@pytest.mark.parametrize("suffix", [".gguf", ".safetensors", ".onnx", ".pt", ".h5"])
def test_a_model_suffixed_pointer_is_a_file_entry_only(
    tmp_path: Path, suffix: str
) -> None:
    root = write_project(tmp_path, {f"demo/m{suffix}": _POINTER})
    registry = IdRegistry.new("proj")
    registry.generate([Path("demo")], root)
    assert _held(registry, f"demo/m{suffix}")[1] == _OID
    assert registry.get(AI_PACKAGE_TYPE, f"demo/m{suffix}") is None


def test_an_archive_pointer_is_keyed_by_its_oid_and_reuses_its_id(
    tmp_path: Path,
) -> None:
    """An archive's SBOM states the pointer text's digest (it matches the
    wheel's RECORD), but the registry holds the ``oid``, and a second run
    hits it."""
    wheel = write_model_wheel(
        tmp_path / "dist", {"demo/__init__.py": _INIT, _KEY: _POINTER}
    )
    path = tmp_path / "ids.json"
    IdRegistry.new("w").save(path)
    runs = [generate_wheel_sbom(wheel, id_registry=path) for _ in range(2)]
    ids = [_sbom_file(sbom, _KEY)["spdxId"] for sbom in runs]
    assert ids[0] == ids[1] == _held(IdRegistry.load(path))[0]
    assert _held(IdRegistry.load(path))[1] == _OID
    stated = hashlib.sha256(_POINTER).hexdigest()
    assert all(f'"{stated}"' in sbom and _OID not in sbom for sbom in runs)
