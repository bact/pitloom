# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Loom ID registry file, version 4: read and write.

The file is one JSON object with exactly five keys::

    {
      "elements": {"<compact type>": {"<name>": {"sha256": "...", "spdxId": "..."}}},
      "id_counters": {"<id prefix>": <highest number minted or seen>},
      "namespace": "<IRI>",
      "project_root": "<POSIX path relative to this file's directory>",
      "version": 4
    }

``sha256`` is omitted when an element has no hash, never written as
``null``. Keys are sorted at every level, and the text ends in one LF.
Version 4 differs from 3 only in a ``software_Package`` key, which holds
the package's version (:func:`~pitloom.id_registry._types.package_key`);
an older file is refused, never migrated.

See also: :mod:`pitloom.id_registry._registry` (``IdRegistry.load`` and
``IdRegistry.save`` call this module), :mod:`pitloom.id_registry._types`
(``RegistryEntry`` and the key rule), :mod:`pitloom.id_registry._counters`
(``id_counters``).
"""

from __future__ import annotations

import codecs
import json
import os
from os.path import relpath
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, NamedTuple

from pitloom._sbom_io import replace_text_lf
from pitloom.core.canonical_json import canonical_json_indented
from pitloom.core.given_file import read_given_bytes
from pitloom.core.iri import is_iri_segment, require_namespace_iri
from pitloom.core.quote_source import quote_source
from pitloom.id_registry._counters import MAX_ID_NUMBER, Counters
from pitloom.id_registry._types import (
    _REGISTRY_VERSION,
    RegistryEntry,
    _element_key,
    is_utf8_text,
)
from pitloom.messages import CodedValueError
from pitloom.messages.files import (
    JSON_MALFORMED,
    NOT_OBJECT_LINE,
    REGISTRY_USE,
    file_unreadable_error,
)
from pitloom.messages.id_registry import (
    COUNTER_NUMBER_LINE,
    COUNTER_PREFIX_LINE,
    COUNTERS_LINE,
    DUPLICATE_ENTRY_LINE,
    DUPLICATE_KEY_LINE,
    ELEMENTS_LINE,
    ENTRY_LINE,
    MISSING_KEY_LINE,
    NAMESPACE_LINE,
    NO_NAMESPACE_LINE,
    NO_RELATIVE_ROOT_LINE,
    PROJECT_ROOT_LINE,
    REGISTRY_MALFORMED,
    REGISTRY_UNKNOWN_KEY,
    REGISTRY_UNUSABLE,
    REGISTRY_WRONG_FORMAT,
    ROOT_NOT_STORABLE_LINE,
    SHA256_LINE,
    SPDX_ID_LINE,
    TYPE_TABLE_LINE,
    UNENCODABLE_LINE,
    UNKNOWN_ENTRY_KEY_LINE,
    UNKNOWN_TOP_KEY_LINE,
)

if TYPE_CHECKING:
    from pitloom.messages import Line

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


def _malformed(path: Path, line: Line, **values: object) -> CodedValueError:
    """The ``registry-malformed`` error for the registry file *path*: its
    *line*, naming *values*."""
    return CodedValueError(REGISTRY_MALFORMED, line=line, file=path, **values)


def _read_json(path: Path) -> Any:
    """The JSON value in the file *path*, read whole up to the shared cap
    (:func:`~pitloom.core.given_file.read_given_bytes`): ``input-not-found``
    when it is not there or not a regular file, ``over-cap`` when larger,
    ``file-unreadable`` (``/not-utf8``) when it cannot be read,
    ``json-malformed`` when it is not JSON (a UTF-16 or UTF-32 text that does
    not decode included), ``registry-malformed`` for a duplicate object
    key."""
    raw = read_given_bytes(path, kind="ID registry file", use=REGISTRY_USE)
    try:
        # Bytes, not str: json.loads() strips a leading UTF-8 BOM and, more
        # lenient than RFC 8259 (UTF-8 only), detects UTF-16 and UTF-32.
        return json.loads(raw, object_pairs_hook=_unique_keys)
    except _DuplicateKeyError as exc:
        raise _malformed(path, DUPLICATE_KEY_LINE, name=exc.shown) from exc
    except UnicodeDecodeError as exc:
        if codecs.lookup(exc.encoding).name == "utf-8":
            raise file_unreadable_error(exc, file=path, use=REGISTRY_USE) from exc
        # Read as UTF-16 or UTF-32: "not UTF-8" would be untrue; the decoder's
        # own text names the encoding.
        raise CodedValueError(
            JSON_MALFORMED, file=path, use=REGISTRY_USE, failure=exc
        ) from exc
    except (ValueError, RecursionError) as exc:
        raise CodedValueError(
            JSON_MALFORMED, file=path, use=REGISTRY_USE, failure=exc
        ) from exc


def read_registry_file(path: Path) -> RegistryFileContents:
    """Read and validate the registry file at *path*.

    A file that is not there or not a file raises
    :class:`~pitloom.messages.CodedFileNotFoundError` (``input-not-found``);
    every other failure raises a coded ``ValueError`` (:func:`_read_json`,
    then ``json-malformed``, ``registry-malformed``,
    ``registry-wrong-format`` or ``registry-unknown-key``), naming *path* as
    given (:func:`~pitloom.core.given_path.given_spelling`). The version is
    checked first, before the namespace and the key set, so a file of
    another version (older, newer or none) gets the version message, never
    a namespace or "unknown key" one, and is left as it is.
    """
    data = _read_json(path)
    if not isinstance(data, dict):
        raise CodedValueError(
            JSON_MALFORMED, line=NOT_OBJECT_LINE, file=path, use=REGISTRY_USE
        )

    version = data.get("version")
    if not isinstance(version, int) or version != _REGISTRY_VERSION:
        raise CodedValueError(REGISTRY_WRONG_FORMAT, file=path, value=repr(version))

    namespace = data.get("namespace")
    if not isinstance(namespace, str) or not namespace:
        raise _malformed(path, NO_NAMESPACE_LINE)
    try:
        require_namespace_iri(namespace)
    except ValueError as exc:
        raise _malformed(path, NAMESPACE_LINE, failure=exc) from exc

    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        raise CodedValueError(
            REGISTRY_UNKNOWN_KEY,
            line=UNKNOWN_TOP_KEY_LINE,
            file=path,
            name=_listed(unknown),
        )
    for required in ("elements", "id_counters", "project_root"):
        if required not in data:
            raise _malformed(path, MISSING_KEY_LINE, name=repr(required))

    return RegistryFileContents(
        namespace=namespace,
        elements=_parse_elements(path, data["elements"]),
        project_root=_parse_project_root(path, data["project_root"]),
        id_counters=_parse_counters(path, data["id_counters"]),
    )


def _listed(keys: list[str]) -> str:
    """*keys*, each as its ``repr``, comma-separated."""
    return ", ".join(map(repr, keys))


class _DuplicateKeyError(ValueError):
    """A JSON object of the registry file names one key twice: *shown*, in
    quotes."""

    def __init__(self, key: str) -> None:
        #: The key, in quotes, escaped.
        self.shown: str = quote_source(key)
        super().__init__(f"duplicate key {self.shown}")


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """``object_pairs_hook``: the object, unless a key appears twice (plain
    ``json`` keeps the last silently, so a hand edit could lower a counter
    or drop an entry unseen)."""
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise _DuplicateKeyError(key)
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
        raise _malformed(path, COUNTER_PREFIX_LINE, name=repr(prefix))
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 1 <= number <= MAX_ID_NUMBER
    ):
        raise _malformed(
            path, COUNTER_NUMBER_LINE, name=repr(prefix), value=repr(number)
        )


def _parse_counters(path: Path, raw: object) -> Counters:
    """The ``id_counters`` table, each pair checked by
    :func:`_check_counter`."""
    if not isinstance(raw, dict):
        raise _malformed(path, COUNTERS_LINE)
    counters: Counters = {}
    for prefix, number in sorted(raw.items()):
        _check_counter(path, prefix, number)
        counters[prefix] = number
    return counters


def _parse_project_root(path: Path, value: object) -> Path:
    """The absolute, realpath'd project root *value* names, relative to
    the directory of the registry file *path*."""
    if not isinstance(value, str) or not _is_relative_posix(value):
        shown = quote_source(value) if isinstance(value, str) else repr(value)
        raise _malformed(path, PROJECT_ROOT_LINE, value=shown)
    if not is_utf8_text(value):  # realpath() would raise on it, uncoded
        raise _malformed(
            path, UNENCODABLE_LINE, registry_part="project_root", value=value
        )
    return Path(os.path.realpath(registry_dir(path) / value))


def _parse_elements(path: Path, raw: object) -> dict[tuple[str, str], RegistryEntry]:
    """The ``elements`` table, keyed by
    :func:`~pitloom.id_registry._types._element_key`."""
    if not isinstance(raw, dict):
        raise _malformed(path, ELEMENTS_LINE)
    elements: dict[tuple[str, str], RegistryEntry] = {}
    for type_name, names in sorted(raw.items()):
        if not isinstance(names, dict):
            raise _malformed(path, TYPE_TABLE_LINE, element_type=type_name)
        for name, record in sorted(names.items()):
            for text in (type_name, name):
                if not is_utf8_text(text):
                    raise _malformed(
                        path, UNENCODABLE_LINE, registry_part="key", value=text
                    )
            key = _element_key(type_name=type_name, name=name)
            if key in elements:
                raise _malformed(
                    path,
                    DUPLICATE_ENTRY_LINE,
                    element_type=key[0],
                    name=quote_source(key[1]),
                )
            elements[key] = _parse_entry(path, key, record)
    return elements


def _parse_entry(path: Path, key: tuple[str, str], record: object) -> RegistryEntry:
    """One entry: ``spdxId`` (a non-empty string) and an optional ``sha256``
    (a non-empty string when present; ``null`` and ``""`` are rejected)."""
    where = {"element_type": key[0], "name": quote_source(key[1])}
    if not isinstance(record, dict):
        raise _malformed(path, ENTRY_LINE, **where)
    unknown = sorted(set(record) - _ENTRY_KEYS)
    if unknown:
        raise CodedValueError(
            REGISTRY_UNKNOWN_KEY,
            line=UNKNOWN_ENTRY_KEY_LINE,
            file=path,
            value=_listed(unknown),
            **where,
        )
    spdx_id = record.get("spdxId")
    if not isinstance(spdx_id, str) or not spdx_id:
        raise _malformed(path, SPDX_ID_LINE, **where)
    if not is_utf8_text(spdx_id):
        raise _malformed(path, UNENCODABLE_LINE, registry_part="spdxId", value=spdx_id)
    if "sha256" not in record:
        return RegistryEntry(spdx_id=spdx_id)
    sha256 = record["sha256"]
    if not isinstance(sha256, str) or not sha256:
        raise _malformed(path, SHA256_LINE, **where)
    if not is_utf8_text(sha256):  # a save could not write it back
        raise _malformed(path, UNENCODABLE_LINE, registry_part="sha256", value=sha256)
    return RegistryEntry(spdx_id=spdx_id, sha256=sha256)


def _stored_project_root(target: Path, project_root: Path) -> str:
    """*project_root* relative to the directory of *target*, realpath on
    both sides, as POSIX text. Raises ``registry-unusable`` when there is no
    such path (two Windows drives) or the result would not load back."""
    base = registry_dir(target)
    root = Path(os.path.realpath(project_root))
    try:
        text = Path(relpath(root, base)).as_posix()
    except ValueError as exc:
        raise CodedValueError(
            REGISTRY_UNUSABLE,
            line=NO_RELATIVE_ROOT_LINE,
            file=target,
            path=root,
            failure=exc,
        ) from exc
    if not _is_relative_posix(text):
        raise CodedValueError(
            REGISTRY_UNUSABLE,
            line=ROOT_NOT_STORABLE_LINE,
            file=target,
            path=root,
            value=quote_source(text),
        )
    return text


def write_registry_file(
    target: Path,
    namespace: str,
    elements: dict[tuple[str, str], RegistryEntry],
    project_root: Path,
    id_counters: Counters,
) -> None:
    """Write a version 4 registry file to *target*: canonical JSON,
    indented, LF line endings and one trailing newline. Replaced atomically
    (:func:`~pitloom._sbom_io.replace_text_lf`): a run reading it meanwhile
    sees the old file or the new one, never part. A counter the loader
    would reject raises ``registry-malformed``, and nothing is written."""
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
