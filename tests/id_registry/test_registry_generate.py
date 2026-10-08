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

from pathlib import Path
from typing import Any

import pytest

import pitloom.id_registry._registry as ids_mod
from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner_project import scan_project_for_ai_models
from pitloom.id_registry import (
    DEFAULT_ID_REGISTRY_FILENAME,
    IdRegistry,
)
from pitloom.id_registry._types import _iter_files
from tests.id_registry.shared import _sha256


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

    assert set(registry.files) == {"src/a.py", "data/x.txt"}
    assert registry.files["src/a.py"].sha256 == _sha256(b"print(1)\n")
    assert registry.files["data/x.txt"].sha256 == _sha256(b"hello\n")
    # Every id lives in the registry namespace with a #File-<n> fragment.
    for entry in registry.files.values():
        assert entry.spdx_id.startswith(f"{registry.namespace}#File-")


def test_generate_is_stable_for_unchanged_files(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("src"), Path("data")], root)
    before = {p: e.spdx_id for p, e in registry.files.items()}

    registry.generate([Path("src"), Path("data")], root)
    after = {p: e.spdx_id for p, e in registry.files.items()}
    assert after == before


def test_generate_mints_new_id_for_changed_content(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry = IdRegistry.new("proj")
    registry.generate([Path("data")], root)
    old_id = registry.files["data/x.txt"].spdx_id

    (root / "data" / "x.txt").write_bytes(b"changed\n")
    registry.generate([Path("data")], root)

    new_entry = registry.files["data/x.txt"]
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
    assert reloaded.files["src/a.py"].spdx_id == registry.files["src/a.py"].spdx_id
    assert "data/new.txt" in reloaded.files


def test_generate_registers_ai_model_entity(tmp_path: Path) -> None:
    root = tmp_path
    models = root / "models"
    models.mkdir()
    # GGUF magic bytes make this file a detectable AI model.
    (models / "sentimentdemo.bin").write_bytes(b"GGUF" + b"\x00" * 16)

    registry = IdRegistry.new("proj")
    registry.generate([Path("models")], root)

    assert "models/sentimentdemo.bin" in registry.files
    assert ("ai_AIPackage", "sentimentdemo") in registry.entities
    entity = registry.entities[("ai_AIPackage", "sentimentdemo")]
    assert entity.spdx_id.startswith(f"{registry.namespace}#AIPackage-")


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

    assert rel in registry.files
    assert bool(registry.entities) is is_model
    assert bool(listed) is is_model


def test_generate_skips_registry_file_itself(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_ID_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path(".")], root)
    registry.save()

    reloaded = IdRegistry.load(registry_path)
    reloaded.generate([Path(".")], root)
    assert DEFAULT_ID_REGISTRY_FILENAME not in reloaded.files


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
    assert "src/test.txt" not in registry.files


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
