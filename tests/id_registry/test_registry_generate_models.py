# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.id_registry generation of AI model entries.

See also: test_registry_generate.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from tests.id_registry.shared import _files, _sha256
from tests.registry_helpers import make_registry

_GGUF = AiModelFormat.GGUF.magic or b""


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
