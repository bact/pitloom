# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry file, version 4: every ``load()`` failure.

See also: test_registry_format.py (round trip and determinism),
test_registry_counters.py (the id counters, I8).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import errno
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.id_registry import (
    DEFAULT_ID_REGISTRY_FILENAME,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)
from pitloom.messages import code_of
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
    "v2": (_v2, "version 2, expected 4"),
    "v3": (_set("version", 3), "version 3, expected 4"),
    "version-str": (_set("version", "4"), "version '4', expected 4"),
    "version-float": (_set("version", 4.0), "version 4.0, expected 4"),
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
        "malformed entry: 'software_File' 'a' is not an object",
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
        "two 'software_Package' entries for 'pyyaml'",
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


def _code(case: str) -> str:
    """The code a case of :data:`_FAILURES` says."""
    if case.startswith(("v2", "v3", "version")):
        return "registry-wrong-format"
    if case.startswith("unknown"):
        return "registry-unknown-key"
    return "registry-malformed"


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
    # One prefix, once: a lone surrogate's line no longer stacks a second.
    assert message.startswith(f"ID registry: FILE={path}: ")
    assert message.count("ID registry") == 1
    assert reason in message
    assert code_of(excinfo.value) == _code(case)


@pytest.mark.parametrize(
    "old",
    [
        {"version": 2, "namespace": _NS, "files": {}, "entities": {}},
        {**valid_registry_data(), "version": 3},
    ],
    ids=["v2", "v3"],
)
def test_load_old_version_message_is_exact_and_file_untouched(
    tmp_path: Path, old: dict[str, Any]
) -> None:
    """A version 2 or 3 file (a v3 package key has no version) is refused
    whole, never migrated: nothing is dropped or rewritten."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text(json.dumps(old), encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(ValueError) as excinfo:
        IdRegistry.load(path)

    assert str(excinfo.value) == (
        f"ID registry: FILE={path}: version {old['version']}, "
        "expected 4 (no migration support "
        "-- delete it and re-run `loom id generate` or `loom id import`)"
    )
    assert path.read_bytes() == before


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


_JSON = ("FILE=", ": not valid JSON for the ID registry; ", "json-malformed")
_MALFORMED = ("ID registry: FILE=", ": " + _DUP, "registry-malformed")
_NOT_UTF8 = (
    "FILE=",
    ": could not read for the ID registry; not UTF-8: ",
    "file-unreadable/not-utf8",
)


@pytest.mark.parametrize(
    ("raw", "said"),
    [
        (b"{not valid json", _JSON),
        (b"\xff\xfe\x00\x01not json at all", _JSON),
        (b"\x80{}", _NOT_UTF8),
        (b"[" * 200_000 + b"]" * 200_000, _JSON),
        (
            b"[1, 2, 3]",
            ("FILE=", ": not a JSON object for the ID registry", "json-malformed"),
        ),
        (_registry_text('"id_counters": {"File": 9, "File": 1}'), _MALFORMED),
        (_registry_text(f'"elements": {_TWO_A}'), _MALFORMED),
        (_registry_text('"id_counters": {}, "id_counters": {}'), _MALFORMED),
        (
            b"\xef\xbb\xbf" + _registry_text('"id_counters": {"F": 1, "F": 1}'),
            _MALFORMED,
        ),
    ],
    ids=["bad-json", "bad-utf16", "bad-byte", "deep", "array", "dup-counter"]
    + ["dup-name", "dup-top", "bom-dup"],
)
def test_load_rejects_raw_bytes(
    tmp_path: Path, raw: bytes, said: tuple[str, str, str]
) -> None:
    """Not JSON, not UTF-8 or not an object: the shared codes, read for the
    ID registry; a key named twice: the registry's own."""
    prefix, condition, code = said
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_bytes(raw)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    message = str(caught.value)
    assert message.startswith(f"{prefix}{path}{condition}"), message
    assert code_of(caught.value) == code


@pytest.mark.parametrize(
    ("raw", "encoding"),
    [
        (b"\xff\xfe{\x00}\x00\x00", "utf-16-le"),
        (b"\x00\x00\x00{\x00", "utf-32-be"),
    ],
    ids=["utf16", "utf32"],
)
def test_a_utf16_or_utf32_registry_that_does_not_decode_is_not_called_utf8(
    tmp_path: Path, raw: bytes, encoding: str
) -> None:
    """The reader takes UTF-16 and UTF-32 too: a file read as one that does
    not decode is not JSON, in the decoder's words, never "not UTF-8"."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_bytes(raw)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    message = str(caught.value)
    assert message.startswith(f"FILE={path}: not valid JSON for the ID registry; ")
    assert f"'{encoding}' codec can't decode" in message
    assert "UTF-8" not in message
    assert code_of(caught.value) == "json-malformed"


def test_load_still_reads_utf16_with_its_bom(tmp_path: Path) -> None:
    """JSON read as bytes: a UTF-16 file with a byte order mark loads."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_bytes(json.dumps(valid_registry_data()).encode("utf-16"))
    assert IdRegistry.load(path).namespace == _NS


@pytest.mark.parametrize("kind", ["missing", "directory"])
def test_load_not_found_or_not_a_file(tmp_path: Path, kind: str) -> None:
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    if kind == "directory":
        path.mkdir()

    with pytest.raises(FileNotFoundError, match="ID registry file not found") as caught:
        IdRegistry.load(path)

    assert not isinstance(caught.value, ValueError)


def test_load_os_error_on_read_raises_cannot_be_read(tmp_path: Path) -> None:
    """Mocked rather than a real chmod, since NTFS has no matching bit."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text("{}")

    with patch(
        "pitloom.core.given_file.open",
        side_effect=PermissionError(errno.EACCES, "Permission denied"),
    ):
        with pytest.raises(ValueError) as caught:
            IdRegistry.load(path)
    assert str(caught.value) == (
        f"FILE={path}: could not read for the ID registry; Permission denied"
    )
    assert code_of(caught.value) == "file-unreadable"


def test_load_of_a_file_gone_since_it_was_found_is_not_found(
    tmp_path: Path,
) -> None:
    """Gone between the check and the read: not found, never an internal
    error (an absent file is not unreadable)."""
    path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    path.write_text("{}")

    with patch(
        "pitloom.core.given_file.open",
        side_effect=FileNotFoundError(errno.ENOENT, "No such file or directory"),
    ):
        with pytest.raises(FileNotFoundError) as caught:
            IdRegistry.load(path)
    assert code_of(caught.value) == "input-not-found"


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
        with pytest.raises(FileNotFoundError, match="ID registry file not found"):
            IdRegistry.load(bad)
