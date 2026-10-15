# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry file, version 3: round trip, determinism and every
``load()`` failure.

See also: test_registry.py (the in-memory API), test_surfaces_failures.py
(a version 2 file on every surface), test_registry_counters.py (the id
counters, I8), tests/registry_helpers.py.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.canonical_json import canonical_json
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from tests._symlink import CAN_SYMLINK
from tests.json_text_helpers import without_token_whitespace
from tests.registry_helpers import entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_SHA = "a" * 64


def _valid() -> dict[str, Any]:
    return {
        "elements": {
            FILE_TYPE: {"src/a.py": {"sha256": _SHA, "spdxId": f"{_NS}#File-1"}},
            PACKAGE_TYPE: {"requests": {"spdxId": f"{_NS}#Package-2"}},
        },
        "id_counters": {"File": 1, "Package": 2},
        "namespace": _NS,
        "project_root": ".",
        "version": 3,
    }


def _sample(tmp_path: Path) -> IdRegistry:
    return make_registry(
        {
            (AI_PACKAGE_TYPE, "tiny"): (f"{_NS}#AIPackage-4", _SHA.upper()),
            (DATASET_PACKAGE_TYPE, "data/train"): (f"{_NS}#DatasetPackage-5", None),
            (FILE_TYPE, "src/demo"): (f"{_NS}#File-1", None),
            (FILE_TYPE, "src/demo/x.py"): (f"{_NS}#File-2", _SHA),
            (PACKAGE_TYPE, "Requests"): (f"{_NS}#Package-3", None),
        },
        project_root=tmp_path,
    )


def _state(registry: IdRegistry) -> tuple[object, ...]:
    return (
        registry.namespace,
        entries_of(registry),
        registry.project_root,
        registry.id_counters,
    )


# --- round trip and determinism (I7) -----------------------------------


@pytest.mark.parametrize("where", ["here", "build", "outside"])
def test_round_trip_and_two_saves_are_byte_identical(
    tmp_path: Path, where: str
) -> None:
    registry = _sample(tmp_path / "proj")
    (tmp_path / "proj").mkdir()
    path = {
        "here": tmp_path / "proj" / "reg.json",
        "build": tmp_path / "proj" / "build" / "reg.json",
        "outside": tmp_path / "elsewhere" / "deep" / "reg.json",
    }[where]

    registry.save(path)
    first = path.read_bytes()
    reloaded = IdRegistry.load(path)
    reloaded.save(path)

    assert path.read_bytes() == first
    assert _state(reloaded) == _state(registry)
    stored = json.loads(first)["project_root"]
    assert stored == {"here": ".", "build": "..", "outside": "../../proj"}[where]


def test_saved_file_shape(tmp_path: Path) -> None:
    """Nested by type, sha256 omitted (never null) when absent, a package
    name stored canonical, LF only and one trailing newline."""
    path = tmp_path / "reg.json"
    _sample(tmp_path).save(path)
    raw = path.read_bytes()
    data = json.loads(raw)

    assert sorted(data) == [
        "elements",
        "id_counters",
        "namespace",
        "project_root",
        "version",
    ]
    assert data["version"] == 3
    assert data["id_counters"] == {
        "AIPackage": 4,
        "DatasetPackage": 5,
        "File": 2,
        "Package": 3,
    }
    assert data["elements"][DATASET_PACKAGE_TYPE] == {
        "data/train": {"spdxId": f"{_NS}#DatasetPackage-5"}
    }
    assert data["elements"][AI_PACKAGE_TYPE]["tiny"]["sha256"] == _SHA
    assert list(data["elements"][PACKAGE_TYPE]) == ["requests"]
    assert b"null" not in raw
    assert b"\r" not in raw
    assert raw.endswith(b"}\n")
    assert not raw.endswith(b"\n\n")


def test_saved_registry_is_canonical_text_with_indentation(tmp_path: Path) -> None:
    """RFC 8785 key order (U+10000 before U+E000), indentation only added."""
    registry = IdRegistry(namespace="urn:x")
    registry.register(FILE_TYPE, "\ue000.py", sha256="0" * 64)
    registry.register(FILE_TYPE, "\U00010000.py", sha256="1" * 64)
    path = tmp_path / "reg.json"
    registry.save(path)
    text = path.read_text(encoding="utf-8")
    assert text.index("\U00010000.py") < text.index("\ue000.py")
    compact = without_token_whitespace(text).rstrip("\n")
    assert compact == canonical_json(json.loads(text))
    assert text != compact  # indented, so the check above is not vacuous


def test_save_without_path_raises() -> None:
    with pytest.raises(ValueError, match="No path given"):
        IdRegistry.new("test").save()


def test_save_defaults_project_root_to_the_registry_directory(tmp_path: Path) -> None:
    registry = IdRegistry.new("x")
    path = tmp_path / "sub" / "reg.json"

    registry.save(path)

    assert registry.project_root == Path(os.path.realpath(tmp_path / "sub"))
    assert json.loads(path.read_bytes())["project_root"] == "."


@pytest.mark.parametrize(
    ("raises", "returns", "reason"),
    [
        (ValueError("drives"), None, "no path relative"),
        (None, "C:x", "cannot be stored as 'C:x'"),
    ],
    ids=["two-drives", "would-not-load"],
)
def test_save_reports_a_project_root_it_cannot_store(
    tmp_path: Path, raises: Exception | None, returns: str | None, reason: str
) -> None:
    """``os.path.relpath`` raises across Windows drives, and a stored root
    must load back: either is one registry file error, never a traceback,
    and nothing is written."""
    registry = IdRegistry.new("x", project_root=tmp_path)
    path = tmp_path / "reg.json"

    with patch("pitloom.id_registry._format.relpath", autospec=True) as fake:
        fake.side_effect = raises
        fake.return_value = returns
        with pytest.raises(ValueError, match=f"^ID registry file .*{reason}"):
            registry.save(path)

    assert not path.exists()


@pytest.mark.skipif(not CAN_SYMLINK, reason="cannot create a symlink here")
def test_save_stores_the_project_root_realpath(tmp_path: Path) -> None:
    """The root is realpath'd when stored, even when set after creation
    through a symlink."""
    (tmp_path / "proj").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "proj", target_is_directory=True)
    registry = IdRegistry.new("x")
    registry.project_root = tmp_path / "link"

    registry.save(tmp_path / "proj" / "reg.json")

    assert (
        json.loads((tmp_path / "proj" / "reg.json").read_bytes())["project_root"] == "."
    )


def test_load_resolves_project_root_against_the_registry_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "proj" / "build").mkdir(parents=True)
    path = tmp_path / "proj" / "build" / "reg.json"
    data = _valid()
    data["project_root"] = ".."
    path.write_text(json.dumps(data), encoding="utf-8")

    registry = IdRegistry.load(path)

    assert registry.project_root == Path(os.path.realpath(tmp_path / "proj"))
    assert registry.root_dir() == registry.project_root


def test_load_tolerates_a_leading_bom(tmp_path: Path) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_valid()).encode("utf-8"))

    registry = IdRegistry.load(path)

    assert registry.namespace == _NS
    assert registry.get(FILE_TYPE, "src/a.py") == RegistryEntry(f"{_NS}#File-1", _SHA)
    assert registry.get(PACKAGE_TYPE, "Requests") == RegistryEntry(f"{_NS}#Package-2")


def test_load_canonicalises_a_package_name(tmp_path: Path) -> None:
    data = _valid()
    data["elements"][PACKAGE_TYPE] = {"PyYAML": {"spdxId": "x#Package-2"}}
    path = tmp_path / "reg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    registry = IdRegistry.load(path)

    assert registry.lookup(PACKAGE_TYPE, ["pyyaml"]) == "x#Package-2"


@pytest.mark.parametrize("namespace", ["urn:x", "https://example.org/a%20b/ns"])
def test_load_accepts_a_str_path_and_any_namespace_iri(
    tmp_path: Path, namespace: str
) -> None:
    path = tmp_path / "reg.json"
    make_registry(
        {(FILE_TYPE, "a"): (f"{namespace}#File-1", None)},
        namespace=namespace,
        path=path,
    )

    loaded = IdRegistry.load(str(path))

    assert (loaded.namespace, loaded.path) == (namespace, path)


def test_load_accepts_an_empty_elements_table(tmp_path: Path) -> None:
    data = _valid()
    data["elements"] = {}
    path = tmp_path / "reg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert not IdRegistry.load(path).elements


# --- every load() failure ----------------------------------------------


def _v2(data: dict[str, Any]) -> None:
    data.clear()
    data.update(
        {"version": 2, "namespace": _NS, "files": {}, "entities": {}},
    )


def _set(key: str, value: object) -> Any:
    def apply(data: dict[str, Any]) -> None:
        data[key] = value

    return apply


def _drop(key: str) -> Any:
    def apply(data: dict[str, Any]) -> None:
        del data[key]

    return apply


def _entry(**changes: object) -> Any:
    def apply(data: dict[str, Any]) -> None:
        record = data["elements"][FILE_TYPE]["src/a.py"]
        for key, value in changes.items():
            if value is _DELETE:
                del record[key]
            else:
                record[key] = value

    return apply


_DELETE = object()

_FAILURES: dict[str, tuple[Any, str]] = {
    "v2": (_v2, "version 2, expected 3"),
    "version-str": (_set("version", "3"), "version '3', expected 3"),
    "no-namespace": (_drop("namespace"), "missing a valid 'namespace'"),
    "empty-namespace": (_set("namespace", ""), "missing a valid 'namespace'"),
    "fragment-namespace": (
        _set("namespace", f"{_NS}#SPDXRef-DOCUMENT"),
        "'namespace': namespace 'https://spdx.org/spdxdocs/test-1#SPDXRef-DOCUMENT'",
    ),
    "relative-namespace": (_set("namespace", "demo"), "'namespace': namespace 'demo'"),
    "unknown-top-key": (_set("files", {}), "unknown top-level key(s): 'files'"),
    "no-elements": (_drop("elements"), "missing 'elements'"),
    "no-project-root": (_drop("project_root"), "missing 'project_root'"),
    "no-id-counters": (_drop("id_counters"), "missing 'id_counters'"),
    "id-counters-list": (_set("id_counters", []), "'id_counters' is not an object"),
    "elements-list": (_set("elements", []), "malformed entry: 'elements'"),
    "type-table-list": (
        _set("elements", {FILE_TYPE: []}),
        "malformed entry: elements 'software_File'",
    ),
    "entry-list": (
        _set("elements", {FILE_TYPE: {"a": []}}),
        "malformed entry: software_File 'a' is not an object",
    ),
    "unknown-entry-key": (_entry(type="x"), "unknown key(s): 'type'"),
    "no-spdx-id": (_entry(spdxId=_DELETE), "'spdxId' must be a non-empty string"),
    "null-spdx-id": (_entry(spdxId=None), "'spdxId' must be a non-empty string"),
    "list-spdx-id": (_entry(spdxId=["a"]), "'spdxId' must be a non-empty string"),
    "empty-spdx-id": (_entry(spdxId=""), "'spdxId' must be a non-empty string"),
    "null-sha256": (_entry(sha256=None), "'sha256' must be a non-empty string"),
    "empty-sha256": (_entry(sha256=""), "'sha256' must be a non-empty string"),
    "int-sha256": (_entry(sha256=1), "'sha256' must be a non-empty string"),
    "duplicate-canonical": (
        _set(
            "elements",
            {PACKAGE_TYPE: {"PyYAML": {"spdxId": "x#1"}, "pyyaml": {"spdxId": "x#2"}}},
        ),
        "two software_Package entries for 'pyyaml'",
    ),
}

_BAD_ROOTS: dict[str, object] = {
    "int": 1,
    "null": None,
    "list": ["."],
    "empty": "",
    "backslash": "a\\b",
    "absolute": "/x",
    "drive": "C:/x",
    "drive-relative": "C:x",
    "unc": "//server/share",
    "unc-backslash": "\\\\server\\share",
    "nul": "a\x00b",
}
for _name, _root in _BAD_ROOTS.items():
    _FAILURES[f"root-{_name}"] = (_set("project_root", _root), "'project_root'")

# 2**53: one above MAX_ID_NUMBER, a number RFC 8785 would write as a string.
_BAD_COUNTERS: dict[str, tuple[str, object]] = {
    "bool": ("File", True),
    "zero": ("File", 0),
    "negative": ("File", -1),
    "float": ("File", 1.0),
    "str": ("File", "1"),
    "null": ("File", None),
    "huge": ("File", 2**53),
    "empty-prefix": ("", 1),
    "space-prefix": ("Fi le", 1),
    "hash-prefix": ("File#x", 1),
    "lower-escape-prefix": ("a%2fb", 1),
}
for _name, (_prefix, _number) in _BAD_COUNTERS.items():
    _FAILURES[f"counter-{_name}"] = (
        _set("id_counters", {_prefix: _number}),
        "'id_counters' ",
    )


@pytest.mark.parametrize("case", sorted(_FAILURES))
def test_load_rejects(tmp_path: Path, case: str) -> None:
    mutate, reason = _FAILURES[case]
    data = _valid()
    mutate(data)
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        IdRegistry.load(path)

    message = str(excinfo.value)
    assert message.startswith(f"ID registry file {path}: ")
    assert reason in message


def test_load_v2_message_is_exact(tmp_path: Path) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text(
        json.dumps({"version": 2, "namespace": _NS, "files": {}, "entities": {}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        IdRegistry.load(path)

    assert str(excinfo.value) == (
        f"ID registry file {path}: version 2, expected 3 (no migration support "
        "-- delete it and re-run `pitloom id generate` or `pitloom id import`)"
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"{not valid json", "not valid JSON"),
        (b"\xff\xfe\x00\x01not json at all", "not valid JSON"),
        (b"[" * 200_000 + b"]" * 200_000, "not valid JSON"),
        (b"[1, 2, 3]", "not a JSON object"),
    ],
    ids=["bad-json", "non-utf8", "deep", "array"],
)
def test_load_rejects_raw_bytes(tmp_path: Path, raw: bytes, reason: str) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_bytes(raw)

    with pytest.raises(ValueError, match=f"^ID registry file .*: {reason}"):
        IdRegistry.load(path)


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_load_not_found_or_not_a_file(tmp_path: Path, kind: str) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    if kind == "directory":
        path.mkdir()

    with pytest.raises(ValueError, match="not found or not a file"):
        IdRegistry.load(path)


def test_load_os_error_on_read_raises_cannot_be_read(tmp_path: Path) -> None:
    """Mocked rather than a real chmod, since NTFS has no matching bit."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text("{}")

    with patch(
        "pitloom.id_registry._format.open", side_effect=OSError("Permission denied")
    ):
        with pytest.raises(ValueError, match="cannot be read"):
            IdRegistry.load(path)


def test_load_accepts_a_parent_project_root(tmp_path: Path) -> None:
    """``..`` is allowed (a registry in ``build/``)."""
    path = tmp_path / "build" / "reg.json"
    path.parent.mkdir()
    data = _valid()
    data["project_root"] = "../."
    path.write_text(json.dumps(data), encoding="utf-8")

    assert IdRegistry.load(path).project_root == Path(os.path.realpath(tmp_path))


def _saved_registry(tmp_path: Path) -> IdRegistry:
    (tmp_path / "proj").mkdir()
    path = tmp_path / "build" / "reg.json"
    IdRegistry.new("x", path=path, project_root=tmp_path / "proj").save()
    return IdRegistry.load(path)


@pytest.mark.parametrize("spelling", ["same", "dotdot", "symlink"])
def test_require_project_root_accepts_another_spelling_of_the_root(
    tmp_path: Path, spelling: str
) -> None:
    """Realpath on both sides: the same directory is the same root."""
    registry = _saved_registry(tmp_path)
    given = {
        "same": tmp_path / "proj",
        "dotdot": tmp_path / "build" / ".." / "proj",
        "symlink": tmp_path / "link",
    }[spelling]
    if spelling == "symlink":
        if not CAN_SYMLINK:
            pytest.skip("cannot create a symlink here")
        given.symlink_to(tmp_path / "proj", target_is_directory=True)

    registry.require_project_root(given)


def test_require_project_root_rejects_another_root(tmp_path: Path) -> None:
    registry = _saved_registry(tmp_path)

    with pytest.raises(ValueError, match="^ID registry file .*project root .* is not"):
        registry.require_project_root(tmp_path / "build")


def test_require_namespace_names_both_namespaces(tmp_path: Path) -> None:
    registry = _saved_registry(tmp_path)

    registry.require_namespace(registry.namespace)  # the same one: no-op
    with pytest.raises(ValueError, match="is not --namespace urn:other; delete it"):
        registry.require_namespace("urn:other")
