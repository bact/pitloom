# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Loom ID registry file, version 3: read and write.

The file is one JSON object with exactly four keys::

    {
      "elements": {"<compact type>": {"<name>": {"sha256": "...", "spdxId": "..."}}},
      "namespace": "<IRI>",
      "project_root": "<POSIX path relative to this file's directory>",
      "version": 3
    }

``sha256`` is omitted when an element has no hash, never written as
``null``. Keys are sorted at every level, and the text ends in one LF.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.load`` and
``IdRegistry.save`` call this module), :mod:`pitloom.id_registry._types`
(``RegistryEntry`` and the key rule).
"""

from __future__ import annotations

import json
import os
from os.path import relpath
from pathlib import Path, PureWindowsPath
from typing import Any, NamedTuple

from pitloom._sbom_io import replace_text_lf
from pitloom.core.canonical_json import canonical_json_indented
from pitloom.core.iri import require_namespace_iri
from pitloom.id_registry._types import (
    _REGISTRY_VERSION,
    RegistryEntry,
    _element_key,
    registry_file_error,
)

__all__ = [
    "RegistryFileContents",
    "read_registry_file",
    "registry_dir",
    "write_registry_file",
]

_TOP_LEVEL_KEYS = frozenset({"elements", "namespace", "project_root", "version"})
_ENTRY_KEYS = frozenset({"sha256", "spdxId"})


class RegistryFileContents(NamedTuple):
    """What a registry file holds, validated."""

    namespace: str
    elements: dict[tuple[str, str], RegistryEntry]
    project_root: Path


def registry_dir(path: Path) -> Path:
    """The realpath of the directory holding the registry file *path*: the
    base its ``project_root`` is stored relative to."""
    return Path(os.path.realpath(path.parent))


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


def read_registry_file(path: Path) -> RegistryFileContents:
    """Read and validate the registry file at *path*.

    Every failure raises one ``ValueError`` built by
    :func:`~pitloom.id_registry._types.registry_file_error`. The version is
    checked before the key set, so a version 2 file gets the version
    message, not an "unknown key" one.
    """
    if not os.path.isfile(path):
        raise registry_file_error(path, "not found or not a file")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise registry_file_error(path, f"cannot be read: {exc}") from exc

    try:
        # Bytes, not str: json.loads() strips a leading UTF-8 BOM from bytes.
        data: Any = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise registry_file_error(path, f"not valid JSON: {exc}") from exc

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
    if version != _REGISTRY_VERSION:
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
    for required in ("elements", "project_root"):
        if required not in data:
            raise registry_file_error(path, f"missing {required!r}")

    return RegistryFileContents(
        namespace=namespace,
        elements=_parse_elements(path, data["elements"]),
        project_root=_parse_project_root(path, data["project_root"]),
    )


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
            target, f"project root {root} has no path relative to {base}: {exc}"
        ) from exc
    if not _is_relative_posix(text):
        raise registry_file_error(
            target, f"project root {root} cannot be stored as {text!r}"
        )
    return text


def write_registry_file(
    target: Path,
    namespace: str,
    elements: dict[tuple[str, str], RegistryEntry],
    project_root: Path,
) -> None:
    """Write a version 3 registry file to *target*: canonical JSON,
    indented, LF line endings and one trailing newline. Replaced atomically
    (:func:`~pitloom._sbom_io.replace_text_lf`): a run reading it meanwhile
    sees the old file or the new one, never part."""
    target.parent.mkdir(parents=True, exist_ok=True)
    by_type: dict[str, dict[str, dict[str, str]]] = {}
    for (type_name, name), entry in sorted(elements.items()):
        record = {"spdxId": entry.spdx_id}
        if entry.sha256 is not None:
            record["sha256"] = entry.sha256
        by_type.setdefault(type_name, {})[name] = record
    data = {
        "elements": by_type,
        "namespace": namespace,
        "project_root": _stored_project_root(target, project_root),
        "version": _REGISTRY_VERSION,
    }
    replace_text_lf(target, canonical_json_indented(data) + "\n")
