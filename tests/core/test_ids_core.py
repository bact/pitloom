# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core tests for pitloom.id_registry."""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

import pitloom.id_registry._harvest as ids_mod
from pitloom.id_registry import (
    DIRECTORY_ENTITY_TYPE,
    EntityEntry,
    FileEntry,
    IdRegistry,
    resolve_registry,
)
from pitloom.id_registry._harvest import _import_sbom_element
from pitloom.id_registry._types import _REGISTRY_VERSION, _sha256_from_verified_using


def test_resolve_registry_error(tmp_path: Path) -> None:
    # Passing an invalid file
    invalid_file = tmp_path / "loom-ids.json"
    invalid_file.write_text("{")  # Malformed JSON

    assert resolve_registry(tmp_path, invalid_file) is None

    missing_file = tmp_path / "missing.json"
    assert resolve_registry(tmp_path, missing_file) is None


def test_register_entity_different_type_gets_its_own_id() -> None:
    """Two different types sharing a name are distinct entries, each with
    its own id -- (type, name) keying means this is no longer a conflict."""
    registry = IdRegistry.new("test")

    id1 = registry.register_entity("my-entity", "Software")
    id2 = registry.register_entity("my-entity", "Dataset")

    assert id1 != id2
    assert registry.lookup_entity("my-entity", "Software") == id1
    assert registry.lookup_entity("my-entity", "Dataset") == id2


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
                "version": _REGISTRY_VERSION,
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
    assert "Registry: ignoring invalid file" in caplog.text


def test_save_without_path_raises() -> None:
    registry = IdRegistry.new("test")

    with pytest.raises(ValueError, match="No path given"):
        registry.save()


def test_entities_keyed_by_type_survive_a_shared_name_round_trip(
    tmp_path: Path,
) -> None:
    """A directory and a package sharing one name are distinct registry
    entries: (type, name) keying means neither is lost, before or after a
    save/load round trip -- regression for the name-only-keyed overwrite
    hazard (a harvested directory and a same-named package silently
    replacing each other)."""
    registry = IdRegistry.new("demo-proj")
    dir_id = registry.register_entity("demo", DIRECTORY_ENTITY_TYPE)
    pkg_id = registry.register_entity("demo", "software_Package")

    assert dir_id != pkg_id
    assert registry.lookup_entity("demo", DIRECTORY_ENTITY_TYPE) == dir_id
    assert registry.lookup_entity("demo", "software_Package") == pkg_id

    registry_path = tmp_path / "loom-ids.json"
    registry.save(registry_path)
    reloaded = IdRegistry.load(registry_path)

    assert reloaded.lookup_entity("demo", DIRECTORY_ENTITY_TYPE) == dir_id
    assert reloaded.lookup_entity("demo", "software_Package") == pkg_id
    assert len(reloaded.entities) == 2


def test_load_rejects_old_registry_version(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An old-version registry file is rejected outright (no migration) --
    surfaced by resolve_registry()/find() as exactly one WARNING, never a
    crash."""
    registry_path = tmp_path / "loom-ids.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": _REGISTRY_VERSION - 1,
                "namespace": "https://spdx.org/spdxdocs/old-1",
                "files": {},
                "entities": {"demo": {"type": "software_Package", "spdxId": "x#1"}},
            }
        )
    )

    with pytest.raises(ValueError, match=f"expected {_REGISTRY_VERSION}"):
        IdRegistry.load(registry_path)

    with caplog.at_level("WARNING"):
        result = resolve_registry(tmp_path, registry_path)

    assert result is None
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].message.startswith("Registry: could not load")


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


def test_harvest_drops_stale_file_key_when_content_differs() -> None:
    """A second file harvested under a *different* path but the exact
    same id, with different content, proves the first key was stale --
    e.g. a fresh-mint coincidentally landing on an old, no-longer-
    looked-up file's registered number. ``_release_stale_keys_for_id``
    must drop the stale key so it can't keep colliding on every later
    harvest (the mint-collision class this whole reservation mechanism
    exists to prevent, but at the registry's own write boundary instead
    of at resolution time -- see
    working-docs/implementation/id-registry-autosync.md's "One key per
    id in the registry" section)."""
    registry = IdRegistry.new("proj")
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    shared_id = "https://spdx.org/spdxdocs/proj-1#File-5"

    file_b = spdx3.software_File(
        spdxId=shared_id,
        name="demo/b.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="b" * 64)
        ],
    )
    _import_sbom_element(registry, file_b)
    assert registry.files["demo/b.py"].spdx_id == shared_id

    file_c = spdx3.software_File(
        spdxId=shared_id,
        name="demo/c.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="c" * 64)
        ],
    )
    _import_sbom_element(registry, file_c)

    assert "demo/b.py" not in registry.files
    assert registry.files["demo/c.py"].spdx_id == shared_id


def test_harvest_keeps_both_file_keys_when_content_matches() -> None:
    """Two paths sharing an id with *identical* content -- the intentional
    physical-path/distribution-path dual-keying for one src/-layout file
    (see ``_add_package_files()``'s two-path lookup) -- are not a stale
    duplicate, and both must survive."""
    registry = IdRegistry.new("proj")
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    shared_id = "https://spdx.org/spdxdocs/proj-1#File-1"
    same_hash = "a" * 64

    physical = spdx3.software_File(
        spdxId=shared_id,
        name="src/pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=same_hash)
        ],
    )
    _import_sbom_element(registry, physical)

    distribution = spdx3.software_File(
        spdxId=shared_id,
        name="pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=same_hash)
        ],
    )
    _import_sbom_element(registry, distribution)

    assert registry.files["src/pkg/train.py"].spdx_id == shared_id
    assert registry.files["pkg/train.py"].spdx_id == shared_id


def test_harvest_drops_stale_file_key_when_alias_shaped_but_content_differs() -> None:
    """Two paths shaped exactly like the physical/distribution-path alias
    (one a suffix of the other) but with *different* content are not the
    same file -- e.g. the stale entry is genuinely superseded content, or
    the two paths are otherwise unrelated. Path-suffix shape alone is not
    sufficient: both ``sha256`` match AND the path-suffix shape are
    required (:func:`pitloom.id_registry._harvest._is_files_path_alias`)
    for the entry to survive; a differing hash must still drop the stale
    key."""
    registry = IdRegistry.new("proj")
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    shared_id = "https://spdx.org/spdxdocs/proj-1#File-1"

    physical = spdx3.software_File(
        spdxId=shared_id,
        name="src/pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="a" * 64)
        ],
    )
    _import_sbom_element(registry, physical)

    distribution = spdx3.software_File(
        spdxId=shared_id,
        name="pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue="b" * 64)
        ],
    )
    _import_sbom_element(registry, distribution)

    assert "src/pkg/train.py" not in registry.files
    assert registry.files["pkg/train.py"].spdx_id == shared_id


def test_harvest_drops_stale_entity_key_sharing_id() -> None:
    """Same as the file-table case above, for ``entities``: no alias case
    exists there (unlike files' physical/distribution dual-keying), so
    any other entities key sharing the id is always dropped."""
    registry = IdRegistry.new("proj")
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    shared_id = "https://spdx.org/spdxdocs/proj-1#Package-1"

    pkg_a = spdx3.software_Package(spdxId=shared_id, name="aaa", creationInfo=ci)
    _import_sbom_element(registry, pkg_a)
    assert ("software_Package", "aaa") in registry.entities

    pkg_b = spdx3.software_Package(spdxId=shared_id, name="bbb", creationInfo=ci)
    _import_sbom_element(registry, pkg_b)

    assert ("software_Package", "aaa") not in registry.entities
    assert registry.entities[("software_Package", "bbb")].spdx_id == shared_id


def _build_sample_object_set(
    namespace: str = "https://spdx.org/spdxdocs/h-1",
) -> tuple[spdx3.SHACLObjectSet, str, str, str]:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    pkg_id = f"{namespace}#Package-1"
    pkg = spdx3.software_Package(spdxId=pkg_id, name="requests", creationInfo=ci)
    file_hash = "aa" * 32
    file_id = f"{namespace}#File-1"
    file_elem = spdx3.software_File(
        spdxId=file_id,
        name="src/pkg/train.py",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=file_hash)
        ],
    )
    object_set = spdx3.SHACLObjectSet()
    object_set.add(ci)
    object_set.add(pkg)
    object_set.add(file_elem)
    return object_set, pkg_id, file_id, file_hash


def test_harvest_adds_new_entities_and_files_from_object_set() -> None:
    registry = IdRegistry.new("proj")
    object_set, pkg_id, file_id, file_hash = _build_sample_object_set()

    new_files, new_entities, changed = registry.harvest(object_set)

    assert (new_files, new_entities, changed) == (1, 1, True)
    assert registry.entities[("software_Package", "requests")] == EntityEntry(
        spdx_id=pkg_id
    )
    assert registry.files["src/pkg/train.py"] == FileEntry(
        spdx_id=file_id, sha256=file_hash
    )


def test_harvest_is_idempotent_for_already_registered_ids() -> None:
    registry = IdRegistry.new("proj")
    object_set, _, _, _ = _build_sample_object_set()

    registry.harvest(object_set)
    new_files, new_entities, changed = registry.harvest(object_set)

    assert (new_files, new_entities, changed) == (0, 0, False)


def _write_registry_entities(
    registry_path: Path, entities: dict[str, dict[str, dict[str, str]]]
) -> None:
    registry_path.write_text(
        json.dumps(
            {
                "version": _REGISTRY_VERSION,
                "namespace": "https://spdx.org/spdxdocs/test-1",
                "files": {},
                "entities": entities,
            }
        )
    )


def test_load_canonicalizes_package_entity_names(tmp_path: Path) -> None:
    """A non-canonical ``software_Package`` key on disk is found by the
    canonical lookup every other reader uses."""
    registry_path = tmp_path / "loom-ids.json"
    _write_registry_entities(
        registry_path,
        {"software_Package": {"PyYAML": {"spdxId": "x#Package-2"}}},
    )

    registry = IdRegistry.load(registry_path)

    assert registry.lookup_entity("pyyaml", "software_Package") == "x#Package-2"
    assert registry.lookup_entity("PyYAML", "software_Package") == "x#Package-2"


def test_load_rejects_package_names_equal_after_canonicalization(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "loom-ids.json"
    _write_registry_entities(
        registry_path,
        {
            "software_Package": {
                "PyYAML": {"spdxId": "x#Package-2"},
                "pyyaml": {"spdxId": "x#Package-3"},
            }
        },
    )

    with pytest.raises(ValueError, match="two software_Package entries"):
        IdRegistry.load(registry_path)


def test_has_entity_named_matches_a_canonicalized_package_name() -> None:
    registry = IdRegistry.new("test")
    registry.register_entity("My_Model", "software_Package")

    assert registry.has_entity_named("My_Model")
    assert registry.has_entity_named("my-model")
    assert not registry.has_entity_named("other")


def test_release_stale_keys_checks_id_before_computing_path_alias() -> None:
    """A harvest against a large registry must only compute
    ``_is_files_path_alias`` for candidates that already share the
    harvested element's ``spdxId`` -- never scan/alias-check the whole
    ``files`` table per harvested element (the quadratic regression the
    ``_SpdxIdIndex`` reverse index exists to prevent).

    2,000 unrelated files share one content hash but each has its own
    distinct, non-colliding id (so a naive per-element full-table scan
    would still compute the sha256-matching alias check against all
    2,000 of them); two more files, ``colliding_a``/``colliding_b``,
    additionally share one id with EACH OTHER. Harvesting a new element
    that hits that shared id must call ``_is_files_path_alias`` exactly
    twice (once per real candidate), not 2,000+ times.
    """
    registry = IdRegistry.new("proj")
    same_hash = "a" * 64
    collided_id = f"{registry.namespace}#File-1"
    for i in range(2000):
        registry.files[f"pkg{i}/mod.py"] = FileEntry(
            spdx_id=f"{registry.namespace}#File-unique-{i}", sha256=same_hash
        )
    registry.files["colliding_a"] = FileEntry(spdx_id=collided_id, sha256=same_hash)
    registry.files["colliding_b"] = FileEntry(spdx_id=collided_id, sha256=same_hash)

    ci = spdx3.CreationInfo(
        specVersion="3.0.1", created=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    new_file = spdx3.software_File(
        spdxId=collided_id,
        name="colliding_c",
        creationInfo=ci,
        verifiedUsing=[
            spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=same_hash)
        ],
    )

    with patch.object(
        ids_mod, "_is_files_path_alias", wraps=ids_mod._is_files_path_alias
    ) as spy:
        _import_sbom_element(registry, new_file)

    assert spy.call_count == 2
    assert "colliding_a" not in registry.files
    assert "colliding_b" not in registry.files
    assert registry.files["colliding_c"].spdx_id == collided_id
