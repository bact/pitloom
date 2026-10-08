# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistry``: a Loom ID registry, persisted as JSON.

See also: :mod:`pitloom.id_registry._types` for its dataclasses and file
traversal, :mod:`pitloom.id_registry._harvest` for SBOM-element harvest
helpers, :mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._sbom_io import open_text_lf
from pitloom.core.canonical_json import canonical_json_indented
from pitloom.core.iri import doc_namespace, iri_segment
from pitloom.id_registry._harvest import _harvest_elements, _sorted_by_spdx_id
from pitloom.id_registry._types import (
    _REGISTRY_VERSION,
    EntityEntry,
    FileEntry,
    _entity_key,
    _iter_files,
    _require_scalar_str,
    _type_id_prefix,
    registry_file_error,
    sha256_file,
)

log = logging.getLogger("pitloom.id_registry")

__all__ = ["IdRegistry"]


class IdRegistry:
    """A Loom ID registry: a stable file/entity -> SPDX ID registry,
    persisted as JSON.
    """

    def __init__(
        self,
        namespace: str,
        files: dict[str, FileEntry] | None = None,
        entities: dict[tuple[str, str], EntityEntry] | None = None,
        path: Path | None = None,
    ) -> None:
        self.namespace = namespace
        self.files: dict[str, FileEntry] = files if files is not None else {}
        #: Keyed by ``(type_name, name)`` -- a directory and a package (or
        #: any two entities of different SPDX 3 types) sharing one name are
        #: distinct entries, never overwriting each other.
        self.entities: dict[tuple[str, str], EntityEntry] = (
            entities if entities is not None else {}
        )
        self.path = path

    @classmethod
    def new(cls, project_name: str, path: Path | None = None) -> IdRegistry:
        """Create a fresh, empty registry with a freshly minted namespace."""
        namespace = doc_namespace(project_name, str(uuid4()))
        return cls(namespace=namespace, path=path)

    @classmethod
    def load(cls, path: Path) -> IdRegistry:
        """Load a registry from *path*.

        Every failure (missing, unreadable, malformed JSON, wrong shape,
        wrong version, malformed entry, duplicate) raises one ``ValueError``
        via :func:`~pitloom.id_registry._types.registry_file_error` --
        never returns ``None``. "Maybe there's a registry" is resolved
        upstream, by :func:`~pitloom.id_registry.resolve.resolve_registry`.
        """
        if not os.path.isfile(path):
            raise registry_file_error(path, "not found or not a file")
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            raise registry_file_error(path, f"cannot be read: {exc}") from exc

        try:
            data: Any = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise registry_file_error(path, f"not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise registry_file_error(path, "not a JSON object")

        namespace = data.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            raise registry_file_error(path, "missing a valid 'namespace'")

        version = data.get("version")
        if version != _REGISTRY_VERSION:
            raise registry_file_error(
                path,
                f"version {version!r}, expected {_REGISTRY_VERSION} (no "
                "migration support -- delete it and re-run `pitloom id "
                "generate` or `pitloom id import`)",
            )

        try:
            files = {
                str(rel_path): FileEntry(
                    spdx_id=_require_scalar_str(entry["spdxId"], "spdxId"),
                    sha256=_require_scalar_str(entry["sha256"], "sha256"),
                )
                for rel_path, entry in data.get("files", {}).items()
            }
            entities: dict[tuple[str, str], EntityEntry] = {}
            for type_name, names in data.get("entities", {}).items():
                for name, entry in names.items():
                    key = _entity_key(str(name), str(type_name))
                    if key in entities:
                        raise registry_file_error(
                            path, f"two {key[0]} entries for {key[1]!r}"
                        )
                    entities[key] = EntityEntry(
                        spdx_id=_require_scalar_str(entry["spdxId"], "spdxId")
                    )
        except (KeyError, TypeError, AttributeError) as exc:
            raise registry_file_error(path, f"malformed entry: {exc}") from exc

        return cls(namespace=namespace, files=files, entities=entities, path=path)

    def lookup_file(self, path: str, sha256: str) -> str | None:
        """Return the registered ``spdxId`` for *path*."""
        entry = self.files.get(path)
        return entry.spdx_id if entry is not None and entry.sha256 == sha256 else None

    def lookup_entity(self, name: str, type_name: str) -> str | None:
        """Return the registered ``spdxId`` for the named entity of *type_name*."""
        entry = self.entities.get(_entity_key(name, type_name))
        return entry.spdx_id if entry is not None else None

    def has_entity_named(self, name: str) -> bool:
        """Return whether *name* is registered under any type at all, as
        given or as the type's own key form (:func:`_entity_key`)."""
        return any(
            key[1] == name or key == _entity_key(name, key[0]) for key in self.entities
        )

    def _mint_id(self, prefix: str) -> str:
        """Mint the next stable ``#<prefix>-<n>`` id in this registry's namespace.

        *prefix* is raw: ``loom id generate -e NAME:TYPE`` derives it from a
        user-given TYPE, so it passes through :func:`iri_segment` too.
        """
        prefix = iri_segment(prefix)
        ns, pfx = re.escape(self.namespace), re.escape(prefix)
        pattern = re.compile(rf"^{ns}#{pfx}-(\d+)$")
        max_n = 0
        all_ids = [entry.spdx_id for entry in self.files.values()] + [
            entry.spdx_id for entry in self.entities.values()
        ]
        for spdx_id in all_ids:
            match = pattern.match(spdx_id)
            if match:
                max_n = max(max_n, int(match.group(1)))
        return f"{self.namespace}#{prefix}-{max_n + 1}"

    def register_file(self, path: str, sha256: str) -> str:
        """Register (or refresh) a file entry and return its ``spdxId``."""
        existing = self.files.get(path)
        if existing is not None and existing.sha256 == sha256:
            return existing.spdx_id
        if existing is not None:
            log.info(
                "ID registry: content changed for %s; minting a new spdxId (old: %s).",
                path,
                existing.spdx_id,
            )
        spdx_id = self._mint_id("File")
        self.files[path] = FileEntry(spdx_id=spdx_id, sha256=sha256)
        return spdx_id

    def register_entity(self, name: str, type_name: str) -> str:
        """Register (or reuse) a named entity and return its ``spdxId``.

        Keyed by ``(type_name, name)`` (see :func:`_entity_key` for the
        :data:`PACKAGE_ENTITY_TYPE` canonicalization applied to *name*): an
        entity already registered under *name* but a *different* type is a
        distinct entry, not a conflict -- both are kept, each looked up
        only by its own type.
        """
        key = _entity_key(name, type_name)
        existing = self.entities.get(key)
        if existing is not None:
            return existing.spdx_id
        spdx_id = self._mint_id(_type_id_prefix(type_name))
        self.entities[key] = EntityEntry(spdx_id=spdx_id)
        return spdx_id

    def generate(self, paths: list[Path], project_root: Path) -> None:
        """(Re-)index files under *paths* into this registry."""
        # pylint: disable=import-outside-toplevel,cyclic-import
        from pitloom.extract.ai_model import AiModelFormat, detect_ai_model_format
        from pitloom.extract.scanner import is_model_candidate_name

        for file_path in _iter_files(paths, project_root):
            try:
                sha256 = sha256_file(file_path)
            except OSError as exc:
                log.warning("ID registry: could not read %s: %s", file_path, exc)
                continue
            rel_path = file_path.relative_to(project_root).as_posix()
            self.register_file(rel_path, sha256)

            # The scan's rule (suffix filter, then header), so an entity is
            # registered for the files a scan lists as models, and only those.
            if (
                is_model_candidate_name(file_path.name)
                and detect_ai_model_format(file_path) != AiModelFormat.UNKNOWN
            ):
                self.register_entity(file_path.stem, "ai_AIPackage")

    def import_sbom(self, sbom_path: Path) -> frozenset[tuple[str, str]]:
        """Harvest ids from an existing SPDX 3 JSON-LD SBOM into this registry.

        Returns the ``entities`` keys not imported because the SBOM holds
        several elements under one name (see
        :func:`~pitloom.id_registry._ambiguous._ambiguous_entity_keys`).
        """
        object_set = spdx3.SHACLObjectSet()
        with open(sbom_path, "rb") as f:
            spdx3.JSONLDDeserializer().read(f, object_set)

        sorted_objects = _sorted_by_spdx_id(object_set)

        if not self.files and not self.entities:
            for obj in sorted_objects:
                if isinstance(obj, spdx3.SpdxDocument) and obj.spdxId:
                    self.namespace = obj.spdxId
                    break

        return _harvest_elements(self, sorted_objects)

    def harvest(self, object_set: spdx3.SHACLObjectSet) -> tuple[int, int, bool]:
        """Harvest every named element in *object_set* into this registry.

        Used both by :meth:`import_sbom` (after deserializing an existing
        SBOM from disk) and by SBOM generation itself, directly on a
        :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`'s in-memory
        object set -- no serialize/reparse round trip needed there, since
        every element already carries its assigned ``spdxId``.

        Returns ``(new_files, new_entities, changed)``: the first two are
        *net* count deltas (for a caller's own log message), the third is
        a proper "did anything actually change" signal a caller should
        gate a ``save()`` on instead --
        :func:`~pitloom.id_registry._harvest._release_stale_keys_for_id`
        can drop one stale key in the same pass that adds another, which
        nets to a zero size delta despite real content changing (the
        surviving key's id, or the stale key's removal, both need
        persisting); the net-count deltas alone cannot detect that case.
        """
        return self._harvest_sorted(_sorted_by_spdx_id(object_set))

    def _harvest_sorted(self, sorted_objects: list[Any]) -> tuple[int, int, bool]:
        """Harvest *sorted_objects* (see
        :func:`~pitloom.id_registry._harvest._sorted_by_spdx_id`).

        A name held by more than one element (see
        :func:`~pitloom.id_registry._ambiguous._ambiguous_entity_keys`) is
        not written.
        """
        before_files = dict(self.files)
        before_entities = dict(self.entities)
        _harvest_elements(self, sorted_objects)
        changed = self.files != before_files or self.entities != before_entities
        return (
            len(self.files) - len(before_files),
            len(self.entities) - len(before_entities),
            changed,
        )

    def save(self, path: Path | None = None) -> None:
        """Write this registry as JSON to *path*."""
        target = path or self.path
        if target is None:
            raise ValueError("No path given and registry has no default path")
        entities_by_type: dict[str, dict[str, dict[str, str]]] = {}
        for (type_name, name), entry in sorted(self.entities.items()):
            entities_by_type.setdefault(type_name, {})[name] = {"spdxId": entry.spdx_id}
        data = {
            "version": _REGISTRY_VERSION,
            "namespace": self.namespace,
            "files": {
                rel_path: {"spdxId": entry.spdx_id, "sha256": entry.sha256}
                for rel_path, entry in sorted(self.files.items())
            },
            "entities": entities_by_type,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with open_text_lf(target) as f:
            f.write(canonical_json_indented(data))
            f.write("\n")
        self.path = target
