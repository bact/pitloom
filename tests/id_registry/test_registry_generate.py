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

import logging
from pathlib import Path
from typing import Any

import pytest

import pitloom.id_registry._registry as ids_mod
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from pitloom.id_registry._types import _iter_files
from tests.id_registry.shared import _sha256
from tests.registry_helpers import make_registry


def _files(registry: IdRegistry) -> dict[str, RegistryEntry]:
    """The registry's ``software_File`` entries, name -> entry."""
    return {name: e for (t, name), e in registry.elements.items() if t == FILE_TYPE}


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
    reloaded.generate([Path(".")], root)
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

    # Also test registry filename ignored
    registry_file = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_file.write_text("a")

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


def _model_project(tmp_path: Path, data: bytes = _GGUF + b"\0" * 16) -> Path:
    (tmp_path / "models").mkdir(exist_ok=True)
    (tmp_path / "models" / "tiny.gguf").write_bytes(data)
    return tmp_path


@pytest.fixture(autouse=True)
def _info_level(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")


def _content_changed(caplog: pytest.LogCaptureFixture, name: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith(f"ID registry: content changed for {name};")
    ]


def test_generate_gates_a_model_entry_on_its_hash(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An ``ai_AIPackage`` entry holding the file's hash is reused; one
    holding another hash, or none, is a retrained or unknown model: one
    INFO and a new id that replaces the entry (D3, D12)."""
    root = _model_project(tmp_path)
    same = ("urn:x#AIPackage-3", _sha256(_GGUF + b"\0" * 16))
    other = ("urn:x#AIPackage-3", "c" * 64)
    no_hash = ("urn:x#AIPackage-3", None)

    for entry, kept in ((same, True), (other, False), (no_hash, False)):
        caplog.clear()
        registry = make_registry({(AI_PACKAGE_TYPE, "tiny"): entry}, namespace="urn:x")
        registry.generate([Path("models")], root)

        got = registry.get(AI_PACKAGE_TYPE, "tiny")
        assert got is not None
        assert (got.spdx_id == entry[0]) is kept
        assert got.sha256 == same[1]
        assert len(_content_changed(caplog, "tiny")) == (0 if kept else 1)
        assert "models/tiny.gguf" in _files(registry)  # non-vacuous: it ran


def test_generate_a_retrained_model_is_a_new_id_and_a_rerun_is_stable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _model_project(tmp_path)
    registry_path = root / "reg.json"
    registry = IdRegistry.new("proj", path=registry_path, project_root=root)
    registry.generate([Path("models")], root)
    registry.save()
    old = registry.get(AI_PACKAGE_TYPE, "tiny")
    assert old is not None

    # Unchanged bytes: the saved file is byte-identical, nothing is logged.
    first = registry_path.read_bytes()
    caplog.clear()
    again = IdRegistry.load(registry_path)
    again.generate([Path("models")], root)
    again.save()
    assert registry_path.read_bytes() == first
    assert not _content_changed(caplog, "tiny")

    # Retrained (other bytes): one INFO, a new id, the old key replaced.
    _model_project(tmp_path, _GGUF + b"\1" * 16)
    again.generate([Path("models")], root)
    new = again.get(AI_PACKAGE_TYPE, "tiny")
    assert new is not None
    assert new.spdx_id != old.spdx_id
    assert new.sha256 != old.sha256
    assert len(_content_changed(caplog, "tiny")) == 1
    assert sum(1 for (t, _n) in again.elements if t == AI_PACKAGE_TYPE) == 1


def test_generate_a_stem_shared_by_model_files_is_name_only_and_stable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No one file stands for a stem two files share, and a hash gate would
    re-mint on every run: name only, one INFO per run."""
    for directory, byte in (("a", b"\0"), ("b", b"\1")):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "m.gguf").write_bytes(_GGUF + byte * 16)

    registry = IdRegistry.new("proj", project_root=tmp_path)
    registry.generate([Path("a"), Path("b")], tmp_path)
    first = registry.get(AI_PACKAGE_TYPE, "m")
    assert first is not None
    assert first.sha256 is None
    caplog.clear()
    registry.generate([Path("a"), Path("b")], tmp_path)

    assert registry.get(AI_PACKAGE_TYPE, "m") == first
    assert [r.getMessage() for r in caplog.records if "share the name" in r.message]
    assert not _content_changed(caplog, "m")


def test_generate_a_stem_becoming_shared_leaves_its_entry_as_is_and_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """1 -> 2 files: the entry keeps its id and its hash (D12: never
    erased), so it differs from a fresh registry's over the same tree; a
    third run saves the same bytes. 2 -> 1: the hash still matches, so the
    entry is reused, with no ``content changed``."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "m.gguf").write_bytes(_GGUF + b"\0" * 16)
    path = tmp_path / "reg.json"
    registry = IdRegistry.new("proj", path=path, project_root=tmp_path)
    registry.generate([Path("a")], tmp_path)
    single = registry.get(AI_PACKAGE_TYPE, "m")
    assert single is not None and single.sha256 is not None  # non-vacuous

    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "m.gguf").write_bytes(_GGUF + b"\1" * 16)
    caplog.clear()
    registry.generate([Path("a"), Path("b")], tmp_path)
    registry.save()
    second = path.read_bytes()
    registry.generate([Path("a"), Path("b")], tmp_path)
    registry.save()
    fresh = IdRegistry.new("proj", project_root=tmp_path)
    fresh.generate([Path("a"), Path("b")], tmp_path)

    assert registry.get(AI_PACKAGE_TYPE, "m") == single
    assert path.read_bytes() == second
    fresh_entry = fresh.get(AI_PACKAGE_TYPE, "m")
    assert fresh_entry is not None and fresh_entry.sha256 is None
    shared = "ID registry: 2 model files share the name m; "
    shares = [r.getMessage() for r in caplog.records if "share the name" in r.message]
    assert shares == [shared + "its entry is left as is"] * 2 + [
        shared + "its new entry is not content-gated"  # the fresh registry
    ]

    (tmp_path / "b" / "m.gguf").unlink()
    registry.generate([Path("a"), Path("b")], tmp_path)

    assert registry.get(AI_PACKAGE_TYPE, "m") == single
    assert not _content_changed(caplog, "m")
