# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core tests for pitloom.ids."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.ids import IdRegistry


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_bytes(b"print(1)\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.txt").write_bytes(b"hello\n")
    return tmp_path


def test_resolve_registry_error(tmp_path: Path) -> None:
    from pitloom.ids import resolve_registry

    # Passing an invalid file
    invalid_file = tmp_path / "loom-ids.json"
    invalid_file.write_text("{")  # Malformed JSON

    assert resolve_registry(tmp_path, invalid_file) is None

    missing_file = tmp_path / "missing.json"
    assert resolve_registry(tmp_path, missing_file) is None


def test_register_entity_mismatched_type(caplog: pytest.LogCaptureFixture) -> None:
    registry = IdRegistry.new("test")

    # First registration
    id1 = registry.register_entity("my-entity", "Software")

    # Second registration with mismatched type
    id2 = registry.register_entity("my-entity", "Dataset")

    # ID should be reused, but warning logged
    assert id1 == id2
    assert "entity 'my-entity' already registered as type 'Software'" in caplog.text
