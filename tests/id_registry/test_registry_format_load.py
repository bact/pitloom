# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry file, version 3: every ``load()`` failure.

See also: test_registry_format.py (round trip and determinism),
test_registry_counters.py (the id counters, I8).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.quote_source import quote_source
from pitloom.id_registry import (
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)
from tests.id_registry.shared import REGISTRY_NS as _NS
from tests.id_registry.shared import valid_registry_data

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
    "version-float": (_set("version", 3.0), "version 3.0, expected 3"),
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
    "surrogate-name": (
        _set("elements", {FILE_TYPE: {"\udcff.txt": {"spdxId": "x#1"}}}),
        "lone surrogate",
    ),
    "surrogate-type": (
        _set("elements", {"\ud800": {"a": {"spdxId": "x#1"}}}),
        "lone surrogate",
    ),
    "surrogate-spdx-id": (_entry(spdxId="x#\udcff"), "lone surrogate"),
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
    data = valid_registry_data()
    mutate(data)
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        IdRegistry.load(path)

    message = str(excinfo.value)
    assert message.startswith(f"ID registry file {quote_source(path)}: ")
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
        f"ID registry file {quote_source(path)}: version 2, expected 3 "
        "(no migration support "
        "-- delete it and re-run `pitloom id generate` or `pitloom id import`)"
    )


_DUP = "duplicate key "
_TWO_A = (
    f'{{"software_File": {{"a": {{"spdxId": "{_NS}#File-9"}}, '
    f'"a": {{"spdxId": "{_NS}#File-1"}}}}}}'
)


def _registry_text(override: str) -> bytes:
    """A valid registry's JSON text with *override* (``"key": value``
    pairs) written last, as text: ``json.dumps`` writes no duplicate key."""
    fields = {
        "elements": "{}",
        "id_counters": "{}",
        "namespace": f'"{_NS}"',
        "project_root": '"."',
        "version": "3",
    }
    for key in fields.copy():
        if f'"{key}":' in override:
            del fields[key]
    pairs = [f'"{key}": {value}' for key, value in fields.items()] + [override]
    return ("{" + ", ".join(pairs) + "}").encode("utf-8")


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"{not valid json", "not valid JSON"),
        (b"\xff\xfe\x00\x01not json at all", "not valid JSON"),
        (b"[" * 200_000 + b"]" * 200_000, "not valid JSON"),
        (b"[1, 2, 3]", "not a JSON object"),
        (_registry_text('"id_counters": {"File": 9, "File": 1}'), _DUP + "'File'"),
        (_registry_text(f'"elements": {_TWO_A}'), _DUP + "'a'"),
        (
            _registry_text('"id_counters": {}, "id_counters": {}'),
            _DUP + "'id_counters'",
        ),
        (b"\xef\xbb\xbf" + _registry_text('"id_counters": {"F": 1, "F": 1}'), _DUP),
    ],
    ids=["bad-json", "non-utf8", "deep", "array", "dup-counter", "dup-name"]
    + ["dup-top", "bom-dup"],
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


@pytest.mark.parametrize("bad", [None, 5, b"r.json", ["r.json"]], ids=repr)
def test_load_refuses_an_argument_that_is_not_a_path(bad: Any) -> None:
    with pytest.raises(TypeError, match="str or os.PathLike"):
        IdRegistry.load(bad)


def test_load_takes_a_str_and_names_a_directory_or_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text(json.dumps(valid_registry_data()), encoding="utf-8")

    assert IdRegistry.load(str(path)).path == path
    for bad in (tmp_path, tmp_path / "nope.json"):
        with pytest.raises(ValueError, match="not found or not a file"):
            IdRegistry.load(bad)
