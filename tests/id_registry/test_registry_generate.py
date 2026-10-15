# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.id_registry registry generation.

See also: test_registry.py, test_registry_import.py, shared.py.
"""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

import pitloom.id_registry._generate as ids_mod
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DEFAULT_ID_REGISTRY_FILENAME,
    IdRegistry,
)
from pitloom.id_registry._types import _iter_files
from tests._unreadable import POSIX_NON_ROOT
from tests.id_registry.shared import _files, _sha256


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_bytes(b"hello\n")
    return tmp_path


def test_generate_indexes_files_with_hashes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)

    files = _files(registry)
    assert set(files) == {"src/a.py", "data/x.txt"}
    assert files["src/a.py"].sha256 == _sha256(b"print(1)\n")
    assert files["data/x.txt"].sha256 == _sha256(b"hello\n")
    # Every id lives in the registry namespace with a #File-<n> fragment.
    for entry in files.values():
        assert entry.spdx_id.startswith(f"{registry.namespace}#File-")


def test_generate_is_stable_for_unchanged_files(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)
    before = _files(registry)

    registry.generate([Path("src"), Path("data")], root)
    after = _files(registry)
    assert after == before


def test_generate_mints_new_id_for_changed_content(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("data")], root)
    old_id = _files(registry)["data/x.txt"].spdx_id

    (root / "data" / "x.txt").write_bytes(b"changed\n")
    registry.generate([Path("data")], root)

    new_entry = _files(registry)["data/x.txt"]
    assert new_entry.spdx_id != old_id
    assert new_entry.sha256 == _sha256(b"changed\n")


def test_generate_preserves_namespace_across_regeneration(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_ID_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path("src")], root)
    registry.save()
    namespace = registry.namespace

    reloaded = IdRegistry.load(registry_path)
    (root / "data" / "new.txt").write_bytes(b"more\n")
    reloaded.generate([Path("src"), Path("data")], root)
    assert reloaded.namespace == namespace
    # Old entries kept, new files appended with fresh ids.
    assert _files(reloaded)["src/a.py"] == _files(registry)["src/a.py"]
    assert "data/new.txt" in _files(reloaded)


def test_generate_registers_ai_model_entity(tmp_path: Path) -> None:
    root = tmp_path
    models = root / "models"
    models.mkdir()
    # GGUF magic bytes make this file a detectable AI model.
    (models / "sentimentdemo.bin").write_bytes(b"GGUF" + b"\x00" * 16)

    registry = IdRegistry.new("proj")
    registry.generate([Path("models")], root)

    assert "models/sentimentdemo.bin" in _files(registry)
    entity = registry.get(AI_PACKAGE_TYPE, "sentimentdemo")
    assert entity is not None
    assert entity.spdx_id.startswith(f"{registry.namespace}#AIPackage-")
    assert entity.sha256 == _sha256(b"GGUF" + b"\x00" * 16)  # the model gate (D3)


_LFS = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\n"
_GGUF = AiModelFormat.GGUF.magic or b""
_HDF5 = AiModelFormat.HDF5.magic or b""
_CRF = AiModelFormat.CRFSUITE.magic or b""


@pytest.mark.parametrize(
    ("name", "data", "is_model"),
    [
        ("ok.gguf", _GGUF + b"\0" * 16, True),
        ("ok.bin", _GGUF + b"\0" * 16, True),  # magic, a suffix a scan reads
        ("ok.h5", _HDF5 + b"\0" * 16, True),
        # ``.model`` is shared: a model only with the CRFsuite signature
        ("ok.model", _CRF + b"\0" * 16, True),
        ("sp.model", b"\n\x0f" + b"\0" * 16, False),
        ("lfs.model", _LFS, False),
        ("ok.onnx", b"\x08\x07", True),
        ("empty.onnx", b"", False),
        ("lfs.gguf", _LFS, False),
        ("lfs.safetensors", _LFS, False),
        ("lfs.keras", _LFS, False),
        # a Git LFS pointer is no model under a suffix that trusts any header
        ("lfs.pt", _LFS, False),
        ("lfs.onnx", _LFS, False),
        ("lfs.h5", _LFS, False),
        # a suffix a scan does not read, whatever the magic
        ("data.dat", _GGUF + b"\0" * 16, False),
        ("data.nc", _HDF5 + b"\0" * 16, False),
        ("data.mat", _HDF5 + b"\0" * 16, False),
        ("site.pth", b"import os\n", False),
    ],
)
def test_generate_registers_an_entity_exactly_for_what_a_scan_lists(
    tmp_path: Path, name: str, data: bytes, is_model: bool
) -> None:
    """Drift guard: ``id generate`` and the project scan decide the same
    (the scan's suffix filter, then the header), a file a scan does not list
    gets no entity."""
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / name).write_bytes(data)
    rel = f"models/{name}"

    registry = IdRegistry.new("proj")
    registry.generate([Path("models")], tmp_path)
    listed = scan_project_for_ai_models(
        tmp_path,
        [ProjectFile(physical_path=rel, distribution_path=rel)],
        scan_usage=False,
        usage_hint=lambda: False,
    )

    assert rel in _files(registry)
    assert (registry.get(AI_PACKAGE_TYPE, Path(name).stem) is not None) is is_model
    assert bool(listed) is is_model


def test_generate_skips_registry_file_itself(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_ID_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path(".")], root)
    registry.save()

    reloaded = IdRegistry.load(registry_path)
    reloaded.generate([Path(".")], root, exclude=registry_path)
    assert DEFAULT_ID_REGISTRY_FILENAME not in _files(reloaded)


def test_generate_handles_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path)
    (root / "src").mkdir(exist_ok=True)
    f = root / "src" / "test.txt"
    f.write_text("data")

    def fake_sha256(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Permission denied")

    monkeypatch.setattr(ids_mod, "sha256_file", fake_sha256)

    registry = IdRegistry.new("test")
    registry.generate([root / "src"], root)
    assert "src/test.txt" not in _files(registry)


def test_iter_files_edge_cases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Missing root
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert list(_iter_files([tmp_path / "missing"], tmp_path)) == []
    assert "path not found, skipping" in caplog.text

    # Root is file
    f = tmp_path / "file.txt"
    f.write_text("a")
    assert list(_iter_files([f], tmp_path)) == [f]

    # Ignored directory
    ignored_dir = tmp_path / ".git" / "objects"
    ignored_dir.mkdir(parents=True)
    ignored_file = ignored_dir / "file.txt"
    ignored_file.write_text("a")

    # Duplicate file
    assert list(_iter_files([Path("."), Path(".")], tmp_path)) == [f]


def test_generate_indexes_a_project_below_an_ignored_directory_name(
    tmp_path: Path,
) -> None:
    """Only the project-relative directory names are ignored: a project
    under ``<tmp>/build/`` (or ``dist``, ``venv``) is indexed in full."""
    project = tmp_path / "build" / "dist" / "proj"
    project.mkdir(parents=True)
    root = _make_project(project)
    (root / "src" / "build").mkdir()
    (root / "src" / "build" / "skipped.py").write_bytes(b"x\n")

    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)

    # Still ignored inside the project, below the walk root.
    assert set(_files(registry)) == {"src/a.py", "data/x.txt"}


def test_generate_leaves_out_the_declared_registry(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    declared = root / "src" / "my-ids.json"
    declared.write_text("{}", encoding="utf-8")

    unexcluded = IdRegistry.new("proj")
    unexcluded.generate([Path("src")], root)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src")], root, exclude=declared)

    assert "src/my-ids.json" in _files(unexcluded)  # not vacuous
    assert set(_files(registry)) == {"src/a.py"}


def test_iter_files_exclude_matches_another_spelling(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    declared = root / "src" / "my-ids.json"
    declared.write_text("{}", encoding="utf-8")
    spelled = root / "data" / ".." / "src" / "my-ids.json"

    files = list(_iter_files([root / "src"], root, spelled))
    assert files == [root / "src" / "a.py"]


def test_iter_files_outside_the_project_ignores_names_below_the_walk_root(
    tmp_path: Path,
) -> None:
    project = tmp_path / "build" / "proj"
    project.mkdir(parents=True)
    outside = tmp_path / "build" / "other"
    (outside / "node_modules").mkdir(parents=True)
    (outside / "node_modules" / "skipped.js").write_bytes(b"x\n")
    (outside / "kept.txt").write_bytes(b"x\n")

    assert list(_iter_files([outside], project)) == [outside / "kept.txt"]


def test_generate_outside_the_project_root_is_a_clean_error(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    root = _make_project(tmp_path / "proj")
    outside = tmp_path / "other.txt"
    outside.write_bytes(b"x")
    registry = IdRegistry.new("proj")

    with pytest.raises(ValueError, match="outside the project root") as excinfo:
        registry.generate([outside], root)

    assert "other.txt" in str(excinfo.value)
    assert str(root) in str(excinfo.value)
    assert not registry.elements


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege")
@pytest.mark.parametrize("spelling", ["root-link", "paths-link"])
def test_generate_compares_a_symlinked_project_root_by_realpath(
    tmp_path: Path, spelling: str
) -> None:
    (tmp_path / "real").mkdir()
    real = _make_project(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    root, walked = (link, real) if spelling == "root-link" else (real, link)
    registry = IdRegistry.new("proj")

    registry.generate([walked / "src"], root)

    assert set(_files(registry)) == {"src/a.py"}


def test_generate_skips_a_name_that_is_not_utf8_with_one_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A lone surrogate (a non-UTF-8 file name) never reaches the table,
    and the logged name is escaped, so the log handler cannot crash."""
    root = _make_project(tmp_path)
    bad = root / "\udcff.txt"
    monkeypatch.setattr(
        ids_mod, "_iter_files", lambda *_a, **_k: iter([bad, root / "src" / "a.py"])
    )
    monkeypatch.setattr(ids_mod, "sha256_file", lambda _p: "c" * 64)
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    handler = logging.StreamHandler(stream)
    failures: list[object] = []
    monkeypatch.setattr(handler, "handleError", failures.append)
    logger = logging.getLogger("pitloom.id_registry")
    logger.addHandler(handler)
    registry = IdRegistry.new("proj")

    try:
        with caplog.at_level(logging.WARNING, logger="pitloom"):
            registry.generate([root], root)
    finally:
        logger.removeHandler(handler)

    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("FILE=") and "lone surrogate" in warning
    assert "\\udcff" in warning
    assert not failures
    assert set(_files(registry)) == {"src/a.py"}


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege")
def test_generate_keys_an_in_project_symlink_to_outside_by_project_path(
    tmp_path: Path,
) -> None:
    (tmp_path / "proj").mkdir()
    root = _make_project(tmp_path / "proj")
    outside = tmp_path / "bigdisk" / "models"
    outside.mkdir(parents=True)
    (outside / "w.bin").write_bytes(b"w")
    (root / "models").symlink_to(outside, target_is_directory=True)
    registry = IdRegistry.new("proj")

    registry.generate([root / "models" / "w.bin"], root)

    assert "models/w.bin" in _files(registry)


@pytest.mark.parametrize(
    ("given", "key"),
    [("d/../d/a.txt", "d/a.txt"), ("../out/o.txt", None)],
    ids=["dotdot-inside", "dotdot-outside"],
)
def test_generate_collapses_dotdot_before_keying(
    tmp_path: Path, given: str, key: str | None
) -> None:
    root = tmp_path / "proj"
    (root / "d").mkdir(parents=True)
    (root / "d" / "a.txt").write_bytes(b"a")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "o.txt").write_bytes(b"o")
    registry = IdRegistry.new("proj")

    if key is None:
        with pytest.raises(ValueError, match="outside the project root"):
            registry.generate([Path(given)], root)
    else:
        registry.generate([Path(given)], root)
        assert set(_files(registry)) == {key}


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
def test_generate_unreadable_root_warns_unless_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _make_project(tmp_path)
    (root / "data").chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            registry = IdRegistry.new("proj")
            registry.generate([root / "data", root / "src"], root, explicit=False)
        with pytest.raises(ValueError, match="PATH data: could not be read"):
            IdRegistry.new("proj").generate([root / "data"], root)
    finally:
        (root / "data").chmod(0o755)

    assert set(_files(registry)) == {"src/a.py"}
    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("DIR=data")


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
def test_generate_unreadable_root_file_warns_unless_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _make_project(tmp_path)
    locked = root / "data" / "x.txt"
    locked.chmod(0)
    try:
        with caplog.at_level(logging.WARNING):
            IdRegistry.new("proj").generate([locked], root, explicit=False)
    finally:
        locked.chmod(0o644)

    (warning,) = [r.getMessage() for r in caplog.records]
    assert warning.startswith("FILE=data/x.txt")
