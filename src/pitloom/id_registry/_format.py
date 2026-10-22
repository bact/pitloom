# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Loom ID registry file, version 3: read and write.

The file is one JSON object with exactly five keys::

    {
      "elements": {"<compact type>": {"<name>": {"sha256": "...", "spdxId": "..."}}},
      "id_counters": {"<id prefix>": <highest number minted or seen>},
      "namespace": "<IRI>",
      "project_root": "<POSIX path relative to this file's directory>",
      "version": 3
    }

``sha256`` is omitted when an element has no hash, never written as
``null``. Keys are sorted at every level, and the text ends in one LF.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.load`` and
``IdRegistry.save`` call this module), :mod:`pitloom.id_registry._types`
(``RegistryEntry`` and the key rule), :mod:`pitloom.id_registry._counters`
(``id_counters``).
"""

from __future__ import annotations

import json
import os
from os.path import relpath
from pathlib import Path, PureWindowsPath
from typing import Any, NamedTuple

from pitloom._sbom_io import replace_text_lf
from pitloom.core.canonical_json import canonical_json_indented
from pitloom.core.iri import is_iri_segment, require_namespace_iri
from pitloom.core.quote_source import quote_source
from pitloom.id_registry._counters import MAX_ID_NUMBER, Counters
from pitloom.id_registry._types import (
    _REGISTRY_VERSION,
    RegistryEntry,
    _element_key,
    is_utf8_text,
    registry_file_error,
    unencodable_message,
)

__all__ = [
    "RegistryFileContents",
    "read_registry_file",
    "registry_dir",
    "write_registry_file",
]

_TOP_LEVEL_KEYS = frozenset(
    {"elements", "id_counters", "namespace", "project_root", "version"}
)
_ENTRY_KEYS = frozenset({"sha256", "spdxId"})


class RegistryFileContents(NamedTuple):
    """What a registry file holds, validated."""

    namespace: str
    elements: dict[tuple[str, str], RegistryEntry]
    project_root: Path
    id_counters: Counters


def registry_dir(path: Path) -> Path:
    """The directory of the registry file *path*, a symlink resolved first
    (the file a save replaces): the base its ``project_root`` is stored
    relative to, so reading it through the link or its target gives one
    root."""
    return Path(os.path.realpath(path)).parent


def _is_relative_posix(value: str) -> bool:
    """Whether *value* is a non-empty relative POSIX path that means the
    same on every platform (no backslash, no drive, no UNC, no NUL)."""
    return (
        bool(value)
        and "\\" not in value
        and "\x00" not in value
        and not value.startswith("/")
        and not PureWindowsPath(value).drive
    )


def _read_json(path: Path) -> Any:
    """The JSON value in the file *path*; a duplicate object key, as every
    other failure, is the registry file error."""
    if not os.path.isfile(path):
        raise registry_file_error(path, "not found or not a file")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise registry_file_error(path, f"cannot be read: {exc}") from exc
    try:
        # Bytes, not str: json.loads() strips a leading UTF-8 BOM from bytes.
        return json.loads(raw, object_pairs_hook=_unique_keys)
    except _DuplicateKeyError as exc:
        raise registry_file_error(path, str(exc)) from exc
    except (ValueError, RecursionError) as exc:
        raise registry_file_error(path, f"not valid JSON: {exc}") from exc


def read_registry_file(path: Path) -> RegistryFileContents:
    """Read and validate the registry file at *path*.

    Every failure raises one ``ValueError`` built by
    :func:`~pitloom.id_registry._types.registry_file_error`. The version is
    checked before the key set, so a version 2 file gets the version
    message, not an "unknown key" one.
    """
    data = _read_json(path)
    if not isinstance(data, dict):
        raise registry_file_error(path, "not a JSON object")

    namespace = data.get("namespace")
    if not isinstance(namespace, str) or not namespace:
        raise registry_file_error(path, "missing a valid 'namespace'")
    try:
        require_namespace_iri(namespace)
    except ValueError as exc:
        raise registry_file_error(path, f"'namespace': {exc}") from exc

    version = data.get("version")
    if not isinstance(version, int) or version != _REGISTRY_VERSION:
        raise registry_file_error(
            path,
            f"version {version!r}, expected {_REGISTRY_VERSION} (no "
            "migration support -- delete it and re-run `pitloom id "
            "generate` or `pitloom id import`)",
        )

    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        raise registry_file_error(
            path, f"unknown top-level key(s): {', '.join(map(repr, unknown))}"
        )
    for required in ("elements", "id_counters", "project_root"):
        if required not in data:
            raise registry_file_error(path, f"missing {required!r}")

    return RegistryFileContents(
        namespace=namespace,
        elements=_parse_elements(path, data["elements"]),
        project_root=_parse_project_root(path, data["project_root"]),
        id_counters=_parse_counters(path, data["id_counters"]),
    )


class _DuplicateKeyError(ValueError):
    """A JSON object of the registry file names one key twice."""


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``object_pairs_hook``: the object, unless a key appears twice (plain
    ``json`` keeps the last silently, so a hand edit could lower a counter
    or drop an entry unseen)."""
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise _DuplicateKeyError(f"duplicate key {key!r}")
        data[key] = value
    return data


def _check_counter(path: Path, prefix: object, number: object) -> None:
    """Raise the registry file error unless *prefix* is an id prefix a mint
    can write (:func:`~pitloom.core.iri.is_iri_segment`) and *number* a
    whole number from 1 to
    :data:`~pitloom.id_registry._counters.MAX_ID_NUMBER` (a boolean is not
    one). Checked on read and on write, so no save writes a counter the
    loader rejects."""
    if not isinstance(prefix, str) or not is_iri_segment(prefix):
        raise registry_file_error(
            path, f"'id_counters' key {prefix!r} is not an id prefix"
        )
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 1 <= number <= MAX_ID_NUMBER
    ):
        raise registry_file_error(
            path,
            f"'id_counters' {prefix!r}: {number!r} is not a whole number "
            f"from 1 to {MAX_ID_NUMBER}",
        )


def _parse_counters(path: Path, raw: object) -> Counters:
    """The ``id_counters`` table, each pair checked by
    :func:`_check_counter`."""
    if not isinstance(raw, dict):
        raise registry_file_error(path, "'id_counters' is not an object")
    counters: Counters = {}
    for prefix, number in sorted(raw.items()):
        _check_counter(path, prefix, number)
        counters[prefix] = number
    return counters


def _parse_project_root(path: Path, value: object) -> Path:
    """The absolute, realpath'd project root *value* names, relative to
    the directory of the registry file *path*."""
    if not isinstance(value, str) or not _is_relative_posix(value):
        raise registry_file_error(
            path,
            f"'project_root' {value!r} is not a relative POSIX path "
            "(relative to the registry file's directory)",
        )
    return Path(os.path.realpath(registry_dir(path) / value))


def _parse_elements(path: Path, raw: object) -> dict[tuple[str, str], RegistryEntry]:
    """The ``elements`` table, keyed by
    :func:`~pitloom.id_registry._types._element_key`."""
    if not isinstance(raw, dict):
        raise registry_file_error(path, "malformed entry: 'elements' is not an object")
    elements: dict[tuple[str, str], RegistryEntry] = {}
    for type_name, names in sorted(raw.items()):
        if not isinstance(names, dict):
            raise registry_file_error(
                path, f"malformed entry: elements {type_name!r} is not an object"
            )
        for name, record in sorted(names.items()):
            for text in (type_name, name):
                if not is_utf8_text(text):
                    raise registry_file_error(path, unencodable_message("key", text))
            key = _element_key(type_name=type_name, name=name)
            if key in elements:
                raise registry_file_error(path, f"two {key[0]} entries for {key[1]!r}")
            elements[key] = _parse_entry(path, key, record)
    return elements


def _parse_entry(path: Path, key: tuple[str, str], record: object) -> RegistryEntry:
    """One entry: ``spdxId`` (a non-empty string) and an optional ``sha256``
    (a non-empty string when present; ``null`` and ``""`` are rejected)."""
    where = f"malformed entry: {key[0]} {key[1]!r}"
    if not isinstance(record, dict):
        raise registry_file_error(path, f"{where} is not an object")
    unknown = sorted(set(record) - _ENTRY_KEYS)
    if unknown:
        raise registry_file_error(
            path, f"{where} has unknown key(s): {', '.join(map(repr, unknown))}"
        )
    spdx_id = record.get("spdxId")
    if not isinstance(spdx_id, str) or not spdx_id:
        raise registry_file_error(path, f"{where}: 'spdxId' must be a non-empty string")
    if not is_utf8_text(spdx_id):
        raise registry_file_error(path, unencodable_message("spdxId", spdx_id))
    if "sha256" not in record:
        return RegistryEntry(spdx_id=spdx_id)
    sha256 = record["sha256"]
    if not isinstance(sha256, str) or not sha256:
        raise registry_file_error(
            path, f"{where}: 'sha256' must be a non-empty string, or left out"
        )
    return RegistryEntry(spdx_id=spdx_id, sha256=sha256)


def _stored_project_root(target: Path, project_root: Path) -> str:
    """*project_root* relative to the directory of *target*, realpath on
    both sides, as POSIX text. Raises the registry file ``ValueError`` when
    there is no such path (two Windows drives) or the result would not
    load back."""
    base = registry_dir(target)
    root = Path(os.path.realpath(project_root))
    try:
        text = Path(relpath(root, base)).as_posix()
    except ValueError as exc:
        raise registry_file_error(
            target,
            f"project root {quote_source(root)} has no path relative to "
            f"{quote_source(base)}: {exc}",
        ) from exc
    if not _is_relative_posix(text):
        raise registry_file_error(
            target,
            f"project root {quote_source(root)} cannot be stored as {text!r}",
        )
    return text


def write_registry_file(
    target: Path,
    namespace: str,
    elements: dict[tuple[str, str], RegistryEntry],
    project_root: Path,
    id_counters: Counters,
) -> None:
    """Write a version 3 registry file to *target*: canonical JSON,
    indented, LF line endings and one trailing newline. Replaced atomically
    (:func:`~pitloom._sbom_io.replace_text_lf`): a run reading it meanwhile
    sees the old file or the new one, never part. A counter the loader
    would reject raises the registry file error, and nothing is written."""
    for prefix, number in id_counters.items():
        _check_counter(target, prefix, number)
    target.parent.mkdir(parents=True, exist_ok=True)
    by_type: dict[str, dict[str, dict[str, str]]] = {}
    for (type_name, name), entry in sorted(elements.items()):
        record = {"spdxId": entry.spdx_id}
        if entry.sha256 is not None:
            record["sha256"] = entry.sha256
        by_type.setdefault(type_name, {})[name] = record
    data = {
        "elements": by_type,
        "id_counters": dict(sorted(id_counters.items())),
        "namespace": namespace,
        "project_root": _stored_project_root(target, project_root),
        "version": _REGISTRY_VERSION,
    }
    replace_text_lf(target, canonical_json_indented(data) + "\n")
