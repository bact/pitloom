# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core tests for pitloom.ids."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import json
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.ids import IdRegistry, _sha256_from_verified_using


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


def test_register_entity_matching_type_reuses_id_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Re-registering an entity with the *same* type is a silent no-op."""
    registry = IdRegistry.new("test")

    id1 = registry.register_entity("my-entity", "Software")
    id2 = registry.register_entity("my-entity", "Software")

    assert id1 == id2
    assert "already registered as type" not in caplog.text


def test_load_missing_namespace_raises(tmp_path: Path) -> None:
    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text(json.dumps({"files": {}, "entities": {}}))

    with pytest.raises(ValueError, match="missing a valid 'namespace'"):
        IdRegistry.load(registry_path)


def test_load_malformed_entry_raises(tmp_path: Path) -> None:
    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text(
        json.dumps(
            {
                "namespace": "https://spdx.org/spdxdocs/test-1",
                "files": {"a.py": {"spdxId": "x#File-1"}},  # missing sha256
                "entities": {},
            }
        )
    )

    with pytest.raises(ValueError, match="has a malformed entry"):
        IdRegistry.load(registry_path)


def test_find_ignores_invalid_registry_and_returns_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """find() logs and returns None when the nearest registry is invalid."""
    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text("{not valid json")

    with caplog.at_level("WARNING"):
        result = IdRegistry.find(start=tmp_path)

    assert result is None
    assert "Ignoring invalid registry" in caplog.text


def test_save_without_path_raises() -> None:
    registry = IdRegistry.new("test")

    with pytest.raises(ValueError, match="No path given"):
        registry.save()


class _FakeHash:
    def __init__(self, algorithm: object, hash_value: str | None) -> None:
        self.algorithm = algorithm
        self.hashValue = hash_value


class _FakeVerified:
    def __init__(self, verified_using: list[_FakeHash]) -> None:
        self.verifiedUsing = verified_using


def test_sha256_from_verified_using_skips_non_sha256_algorithm() -> None:
    """A non-sha256 hash entry is skipped in favor of a later sha256 one."""
    obj = _FakeVerified(
        [
            _FakeHash(spdx3.HashAlgorithm.sha1, "deadbeef"),
            _FakeHash(spdx3.HashAlgorithm.sha256, "cafebabe"),
        ]
    )
    assert _sha256_from_verified_using(obj) == "cafebabe"


def test_sha256_from_verified_using_skips_empty_hash_value() -> None:
    """A sha256 entry with a falsy hashValue is skipped in favor of the next."""
    obj = _FakeVerified(
        [
            _FakeHash(spdx3.HashAlgorithm.sha256, ""),
            _FakeHash(spdx3.HashAlgorithm.sha256, "cafebabe"),
        ]
    )
    assert _sha256_from_verified_using(obj) == "cafebabe"
