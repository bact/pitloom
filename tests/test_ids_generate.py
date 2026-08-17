# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.ids registry generation."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import pitloom.ids as ids_mod
from pitloom.ids import (
    DEFAULT_REGISTRY_FILENAME,
    IdRegistry,
)
from tests.ids_shared import _sha256


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
    registry_path = root / DEFAULT_REGISTRY_FILENAME
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
    assert "sentimentdemo" in registry.entities
    entity = registry.entities["sentimentdemo"]
    assert entity.type == "ai_AIPackage"
    assert entity.spdx_id.startswith(f"{registry.namespace}#AIPackage-")


def test_generate_skips_registry_file_itself(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    registry_path = root / DEFAULT_REGISTRY_FILENAME
    registry = IdRegistry.new("proj", path=registry_path)
    registry.generate([Path(".")], root)
    registry.save()

    reloaded = IdRegistry.load(registry_path)
    reloaded.generate([Path(".")], root)
    assert DEFAULT_REGISTRY_FILENAME not in reloaded.files


def test_generate_handles_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path)
    (root / "src").mkdir(exist_ok=True)
    f = root / "src" / "test.txt"
    f.write_text("data")

    def fake_sha256(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Permission denied")

    monkeypatch.setattr(ids_mod, "_sha256_file", fake_sha256)

    registry = IdRegistry.new("test")
    registry.generate([root / "src"], root)
    assert "src/test.txt" not in registry.files
