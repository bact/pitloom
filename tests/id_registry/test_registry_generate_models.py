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
from pitloom.id_registry.import_keys import LAYOUT_ALIAS_CHANGED_INFO
from tests.id_registry.shared import _files, _sha256
from tests.registry_helpers import make_registry

_GGUF = AiModelFormat.GGUF.magic or b""


_KEY = "models/tiny.gguf"


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
        registry = make_registry({(AI_PACKAGE_TYPE, _KEY): entry}, namespace="urn:x")
        registry.generate([Path("models")], root)

        got = registry.get(AI_PACKAGE_TYPE, _KEY)
        assert got is not None
        assert (got.spdx_id == entry[0]) is kept
        assert got.sha256 == same[1]
        assert len(_content_changed(caplog, _KEY)) == (0 if kept else 1)
        assert _KEY in _files(registry)  # non-vacuous: it ran


def test_generate_a_retrained_model_is_a_new_id_and_a_rerun_is_stable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _model_project(tmp_path)
    registry_path = root / "reg.json"
    registry = IdRegistry.new("proj", path=registry_path, project_root=root)
    registry.generate([Path("models")], root)
    registry.save()
    old = registry.get(AI_PACKAGE_TYPE, _KEY)
    assert old is not None

    # Unchanged bytes: the saved file is byte-identical, nothing is logged.
    first = registry_path.read_bytes()
    caplog.clear()
    again = IdRegistry.load(registry_path)
    again.generate([Path("models")], root)
    again.save()
    assert registry_path.read_bytes() == first
    assert not _content_changed(caplog, _KEY)

    # Retrained (other bytes): one INFO, a new id, the old key replaced.
    _model_project(tmp_path, _GGUF + b"\1" * 16)
    again.generate([Path("models")], root)
    new = again.get(AI_PACKAGE_TYPE, _KEY)
    assert new is not None
    assert new.spdx_id != old.spdx_id
    assert new.sha256 != old.sha256
    assert len(_content_changed(caplog, _KEY)) == 2  # its file, its package
    assert sum(1 for (t, _n) in again.elements if t == AI_PACKAGE_TYPE) == 1


@pytest.mark.parametrize("byte", [b"\0", b"\1"], ids=["same-bytes", "other-bytes"])
def test_generate_two_model_files_sharing_a_stem_get_two_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, byte: bytes
) -> None:
    """K9: each model file's package is keyed by its own path, with its
    hash, so two files with one stem (equal bytes or not) are two models:
    no stem entry, no shared-name ``INFO:``, and a rerun changes nothing."""
    keys = ["a/m.gguf", "b/m.gguf"]
    for key, data in zip(keys, (b"\0", byte), strict=True):
        (tmp_path / key).parent.mkdir()
        (tmp_path / key).write_bytes(_GGUF + data * 16)

    registry = IdRegistry.new("proj", project_root=tmp_path)
    registry.generate([Path("a"), Path("b")], tmp_path)
    entries = [registry.get(AI_PACKAGE_TYPE, key) for key in keys]
    caplog.clear()
    registry.generate([Path("a"), Path("b")], tmp_path)

    assert entries[0] is not None and entries[1] is not None
    assert entries[0].spdx_id != entries[1].spdx_id
    assert [e.sha256 for e in entries if e is not None] == [
        _sha256((tmp_path / key).read_bytes()) for key in keys
    ]
    assert registry.get(AI_PACKAGE_TYPE, "m") is None
    assert [registry.get(AI_PACKAGE_TYPE, key) for key in keys] == entries
    assert not [r for r in caplog.records if "share the name" in r.getMessage()]


@pytest.mark.parametrize(
    ("retrained", "said"),
    [
        (False, "ID registry: 2 key(s) promoted from a layout alias"),
        (True, LAYOUT_ALIAS_CHANGED_INFO % 2),
    ],
    ids=["new-key", "retrained"],
)
def test_generate_promotes_a_models_layout_alias_with_its_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, retrained: bool, said: str
) -> None:
    """A model a wheel run keyed by its installed path (``demo/m.gguf``)
    keeps its id when ``id generate`` keys it by ``src/demo/m.gguf``: its
    package moves with its file, never minting; also over the entries
    ``src/demo/m.gguf`` held for its bytes before a retrain the wheel run
    saw first."""
    data = _GGUF + b"\0" * 16
    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "m.gguf").write_bytes(data)
    types = ((AI_PACKAGE_TYPE, "AIPackage"), ("software_File", "File"))
    held = {
        (type_name, "demo/m.gguf"): (f"urn:x#{prefix}-1", _sha256(data))
        for type_name, prefix in types
    }
    if retrained:
        held.update(
            ((type_name, "src/demo/m.gguf"), (f"urn:x#{prefix}-2", "c" * 64))
            for type_name, prefix in types
        )
    registry = make_registry(held, namespace="urn:x", project_root=tmp_path)
    registry.id_counters.update({"AIPackage": 2, "File": 2})

    registry.generate([Path("src")], tmp_path)

    moved = registry.get(AI_PACKAGE_TYPE, "src/demo/m.gguf")
    assert moved is not None and moved.spdx_id == "urn:x#AIPackage-1"
    assert registry.get(AI_PACKAGE_TYPE, "demo/m.gguf") is None
    assert registry.id_counters == {"AIPackage": 2, "File": 2}
    assert not _content_changed(caplog, "src/demo/m.gguf")
    assert [m for m in caplog.messages if "layout alias" in m] == [said]
