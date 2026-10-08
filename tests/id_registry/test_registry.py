# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Core tests for pitloom.id_registry.

See also: test_registry_harvest.py (harvest-specific tests, split out of
this file -- see AGENTS.md's file-size rule), test_registry_generate.py,
test_registry_import.py, shared.py (fixtures shared by this group).
"""

# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-few-public-methods

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.core.canonical_json import canonical_json
from pitloom.id_registry import (
    DEFAULT_ID_REGISTRY_FILENAME,
    DIRECTORY_ENTITY_TYPE,
    IdRegistry,
    resolve_registry,
)
from pitloom.id_registry._types import _REGISTRY_VERSION
from tests.json_text_helpers import without_token_whitespace


def test_resolve_registry_error(tmp_path: Path) -> None:
    # A declared-but-broken registry raises, it is never silently ignored.
    invalid_file = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    invalid_file.write_text("{")  # Malformed JSON

    with pytest.raises(ValueError, match="ID registry file"):
        resolve_registry(invalid_file, None, tmp_path)

    missing_file = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="ID registry file"):
        resolve_registry(missing_file, None, tmp_path)


def test_register_entity_different_type_gets_its_own_id() -> None:
    """Two different types sharing a name are distinct entries, each with
    its own id -- (type, name) keying means this is no longer a conflict."""
    registry = IdRegistry.new("test")

    id1 = registry.register_entity("my-entity", "Software")
    id2 = registry.register_entity("my-entity", "Dataset")

    assert id1 != id2
    assert registry.lookup_entity("my-entity", "Software") == id1
    assert registry.lookup_entity("my-entity", "Dataset") == id2


def test_register_entity_encodes_a_user_given_type_prefix() -> None:
    """``loom id generate -e NAME:TYPE`` takes any TYPE; its id prefix is
    encoded, and the next mint for that type still finds the previous one."""
    registry = IdRegistry.new("test")

    first = registry.register_entity("a", "My Type#1")
    second = registry.register_entity("b", "My Type#1")

    assert first == f"{registry.namespace}#My%20Type%231-1"
    assert second == f"{registry.namespace}#My%20Type%231-2"


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
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text(json.dumps({"files": {}, "entities": {}}))

    with pytest.raises(ValueError, match="missing a valid 'namespace'"):
        IdRegistry.load(registry_path)


def test_load_missing_file_raises_not_found(tmp_path: Path) -> None:
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME

    with pytest.raises(ValueError, match="not found or not a file"):
        IdRegistry.load(registry_path)


def test_load_directory_raises_not_found(tmp_path: Path) -> None:
    """A directory (``lexists`` but ``os.path.isfile`` is false) is the
    same 'not found or not a file' reason as a missing path."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.mkdir()

    with pytest.raises(ValueError, match="not found or not a file"):
        IdRegistry.load(registry_path)


def test_load_not_a_json_object_raises(tmp_path: Path) -> None:
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text(json.dumps([1, 2, 3]))

    with pytest.raises(ValueError, match="not a JSON object"):
        IdRegistry.load(registry_path)


def test_load_malformed_json_raises_not_valid_json(tmp_path: Path) -> None:
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text("{not valid json")

    with pytest.raises(ValueError, match="not valid JSON"):
        IdRegistry.load(registry_path)


def test_load_tolerates_a_leading_bom(tmp_path: Path) -> None:
    """A UTF-8 BOM-prefixed but otherwise valid registry still loads --
    reading raw bytes with ``json.loads(bytes)`` strips a leading BOM,
    unlike ``json.loads(str)`` after a plain ``.decode("utf-8")``."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    payload = json.dumps(
        {
            "version": _REGISTRY_VERSION,
            "namespace": "https://spdx.org/spdxdocs/bom-1",
            "files": {},
            "entities": {},
        }
    ).encode("utf-8")
    registry_path.write_bytes(b"\xef\xbb\xbf" + payload)

    registry = IdRegistry.load(registry_path)

    assert registry.namespace == "https://spdx.org/spdxdocs/bom-1"


def test_load_os_error_on_read_raises_cannot_be_read(tmp_path: Path) -> None:
    """A genuine read failure (e.g. permission denied) is surfaced as the
    'cannot be read' reason, not left to propagate as a bare OSError --
    mocked rather than a real chmod, since NTFS has no matching bit
    (see AGENTS.md's Windows/macOS permission-test guidance)."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text("{}")

    with patch(
        "pitloom.id_registry._registry.open",
        side_effect=OSError("Permission denied"),
    ):
        with pytest.raises(ValueError, match="cannot be read"):
            IdRegistry.load(registry_path)


def test_load_non_utf8_bytes_raises_not_valid_json(tmp_path: Path) -> None:
    """A ``UnicodeDecodeError`` from non-UTF-8 bytes must not escape
    uncaught -- it's surfaced as the same 'not valid JSON' reason."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_bytes(b"\xff\xfe\x00\x01not json at all")

    with pytest.raises(ValueError, match="not valid JSON"):
        IdRegistry.load(registry_path)


def test_load_malformed_entry_raises(tmp_path: Path) -> None:
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
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

    with pytest.raises(ValueError, match=r"ID registry file .*: malformed entry"):
        IdRegistry.load(registry_path)


def test_load_null_spdx_id_raises(tmp_path: Path) -> None:
    """A ``null`` ``spdxId`` must not silently stringify to the literal
    text ``"None"`` -- it's a malformed entry, not a valid id."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text(
        json.dumps(
            {
                "version": _REGISTRY_VERSION,
                "namespace": "https://spdx.org/spdxdocs/test-1",
                "files": {"a.py": {"spdxId": None, "sha256": "a" * 64}},
                "entities": {},
            }
        )
    )

    with pytest.raises(ValueError, match=r"ID registry file .*: malformed entry"):
        IdRegistry.load(registry_path)


def test_load_list_spdx_id_raises(tmp_path: Path) -> None:
    """A list-valued ``spdxId`` (wrong JSON type) is a malformed entry,
    not silently stringified to its Python repr."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry_path.write_text(
        json.dumps(
            {
                "version": _REGISTRY_VERSION,
                "namespace": "https://spdx.org/spdxdocs/test-1",
                "files": {"a.py": {"spdxId": ["a", "b"], "sha256": "a" * 64}},
                "entities": {},
            }
        )
    )

    with pytest.raises(ValueError, match=r"ID registry file .*: malformed entry"):
        IdRegistry.load(registry_path)


def test_load_deeply_nested_json_raises_not_valid_json(tmp_path: Path) -> None:
    """A ``RecursionError`` from a pathologically deep JSON structure must
    be caught alongside ``ValueError`` around ``json.loads`` -- surfaced
    as the same 'not valid JSON' reason, never left to propagate
    uncaught."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    depth = 200_000
    payload = "[" * depth + "]" * depth
    registry_path.write_text(payload)

    with pytest.raises(ValueError, match="not valid JSON"):
        IdRegistry.load(registry_path)


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

    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    registry.save(registry_path)
    reloaded = IdRegistry.load(registry_path)

    assert reloaded.lookup_entity("demo", DIRECTORY_ENTITY_TYPE) == dir_id
    assert reloaded.lookup_entity("demo", "software_Package") == pkg_id
    assert len(reloaded.entities) == 2


def test_load_rejects_old_registry_version(tmp_path: Path) -> None:
    """An old-version registry file is rejected outright (no migration) --
    surfaced by resolve_registry() as the same ValueError load() raises,
    never a silent None."""
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
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

    with pytest.raises(ValueError, match="ID registry file"):
        resolve_registry(registry_path, None, tmp_path)


def test_saved_registry_is_canonical_text_with_indentation(tmp_path: Path) -> None:
    """RFC 8785 key order (U+10000 before U+E000), indentation only added."""
    registry = IdRegistry(namespace="urn:x")
    registry.register_file(".py", "0" * 64)
    registry.register_file("\U00010000.py", "1" * 64)
    path = tmp_path / "reg.json"
    registry.save(path)
    text = path.read_text(encoding="utf-8")
    assert text.index("\U00010000.py") < text.index(".py")
    assert text.endswith("}\n")
    compact = without_token_whitespace(text).rstrip("\n")
    assert compact == canonical_json(json.loads(text))
    assert text != compact  # indented, so the check above is not vacuous
    assert IdRegistry.load(path).files.keys() == registry.files.keys()
