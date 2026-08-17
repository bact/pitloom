# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry: a stable file/entity -> SPDX ID registry.

See also: :mod:`pitloom._ids_types` for registry dataclasses and file traversal.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._ids_types import (
    _DEFAULT_IDS_GENERATE_DIR_NAMES,
    _IGNORED_DIR_NAMES,
    _REGISTRY_VERSION,
    DEFAULT_REGISTRY_FILENAME,
    EntityEntry,
    FileEntry,
    _iter_files,
    _sha256_file,
    _sha256_from_verified_using,
    _type_id_prefix,
)

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_REGISTRY_FILENAME",
    "EntityEntry",
    "FileEntry",
    "IdRegistry",
    "_DEFAULT_IDS_GENERATE_DIR_NAMES",
    "_IGNORED_DIR_NAMES",
    "_REGISTRY_VERSION",
    "_default_ids_generate_paths",
    "_import_sbom_element",
    "_iter_files",
    "_load_or_create_registry",
    "_sha256_file",
    "_sha256_from_verified_using",
    "_type_id_prefix",
    "resolve_registry",
]


class IdRegistry:
    """A Loom ID registry: a stable file/entity -> SPDX ID registry,
    persisted as JSON.
    """

    def __init__(
        self,
        namespace: str,
        files: dict[str, FileEntry] | None = None,
        entities: dict[str, EntityEntry] | None = None,
        path: Path | None = None,
    ) -> None:
        self.namespace = namespace
        self.files: dict[str, FileEntry] = files if files is not None else {}
        self.entities: dict[str, EntityEntry] = entities if entities is not None else {}
        self.path = path

    @classmethod
    def new(cls, project_name: str, path: Path | None = None) -> IdRegistry:
        """Create a fresh, empty registry with a freshly minted namespace."""
        namespace = f"https://spdx.org/spdxdocs/{project_name}-{uuid4()}"
        return cls(namespace=namespace, path=path)

    @classmethod
    def load(cls, path: Path) -> IdRegistry:
        """Load a registry from *path*."""
        if not path.exists():
            raise FileNotFoundError(f"Registry file not found: {path}")
        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Registry {path} is not valid JSON: {exc}") from exc

        namespace = data.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            raise ValueError(f"Registry {path} is missing a valid 'namespace'")

        try:
            files = {
                str(rel_path): FileEntry(
                    spdx_id=str(entry["spdxId"]), sha256=str(entry["sha256"])
                )
                for rel_path, entry in data.get("files", {}).items()
            }
            entities = {
                str(name): EntityEntry(
                    type=str(entry["type"]), spdx_id=str(entry["spdxId"])
                )
                for name, entry in data.get("entities", {}).items()
            }
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"Registry {path} has a malformed entry: {exc}") from exc

        return cls(namespace=namespace, files=files, entities=entities, path=path)

    @staticmethod
    def find(start: Path | None = None) -> IdRegistry | None:
        """Walk upward from *start* (default: cwd) looking for ``loom-ids.json``."""
        current = (start or Path.cwd()).resolve()
        for directory in (current, *current.parents):
            candidate = directory / DEFAULT_REGISTRY_FILENAME
            if candidate.is_file():
                try:
                    return IdRegistry.load(candidate)
                except (ValueError, OSError) as exc:
                    log.warning("Ignoring invalid registry %s: %s", candidate, exc)
                    return None
        return None

    def lookup_file(self, path: str, sha256: str) -> str | None:
        """Return the registered ``spdxId`` for *path*."""
        entry = self.files.get(path)
        if entry is None or entry.sha256 != sha256:
            return None
        return entry.spdx_id

    def lookup_entity(self, name: str, type_name: str) -> str | None:
        """Return the registered ``spdxId`` for the named entity of *type_name*."""
        entry = self.entities.get(name)
        if entry is None or entry.type != type_name:
            return None
        return entry.spdx_id

    def _mint_id(self, prefix: str) -> str:
        """Mint the next stable ``#<prefix>-<n>`` id in this registry's namespace."""
        pattern = re.compile(
            rf"^{re.escape(self.namespace)}#{re.escape(prefix)}-(\d+)$"
        )
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
                "Registry: content changed for %s; minting a new spdxId (old: %s).",
                path,
                existing.spdx_id,
            )
        spdx_id = self._mint_id("File")
        self.files[path] = FileEntry(spdx_id=spdx_id, sha256=sha256)
        return spdx_id

    def register_entity(self, name: str, type_name: str) -> str:
        """Register (or reuse) a named entity and return its ``spdxId``."""
        existing = self.entities.get(name)
        if existing is not None:
            if existing.type != type_name:
                log.warning(
                    "Registry: entity %r already registered as type %r; "
                    "keeping its existing spdxId rather than minting a new "
                    "one for type %r.",
                    name,
                    existing.type,
                    type_name,
                )
            return existing.spdx_id
        spdx_id = self._mint_id(_type_id_prefix(type_name))
        self.entities[name] = EntityEntry(type=type_name, spdx_id=spdx_id)
        return spdx_id

    def generate(self, paths: list[Path], project_root: Path) -> None:
        """(Re-)index files under *paths* into this registry."""
        # pylint: disable=import-outside-toplevel,cyclic-import
        from pitloom.extract.ai_model import AiModelFormat, detect_ai_model_format

        for file_path in _iter_files(paths, project_root):
            try:
                sha256 = _sha256_file(file_path)
            except OSError as exc:
                log.warning("Registry: could not read %s: %s", file_path, exc)
                continue
            rel_path = file_path.relative_to(project_root).as_posix()
            self.register_file(rel_path, sha256)

            fmt = detect_ai_model_format(file_path)
            if fmt != AiModelFormat.UNKNOWN:
                self.register_entity(file_path.stem, "ai_AIPackage")

    def import_sbom(self, sbom_path: Path) -> None:
        """Harvest ids from an existing SPDX 3 JSON-LD SBOM into this registry."""
        object_set = spdx3.SHACLObjectSet()
        with open(sbom_path, "rb") as f:
            spdx3.JSONLDDeserializer().read(f, object_set)

        sorted_objects = sorted(
            object_set.objects, key=lambda o: getattr(o, "spdxId", None) or ""
        )

        if not self.files and not self.entities:
            for obj in sorted_objects:
                if isinstance(obj, spdx3.SpdxDocument) and obj.spdxId:
                    self.namespace = obj.spdxId
                    break

        for obj in sorted_objects:
            _import_sbom_element(self, obj)

    def save(self, path: Path | None = None) -> None:
        """Write this registry as JSON to *path*."""
        target = path or self.path
        if target is None:
            raise ValueError("No path given and registry has no default path")
        data = {
            "version": _REGISTRY_VERSION,
            "namespace": self.namespace,
            "files": {
                rel_path: {"spdxId": entry.spdx_id, "sha256": entry.sha256}
                for rel_path, entry in sorted(self.files.items())
            },
            "entities": {
                name: {"type": entry.type, "spdxId": entry.spdx_id}
                for name, entry in sorted(self.entities.items())
            },
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        self.path = target


def _import_sbom_element(registry: IdRegistry, obj: Any) -> None:
    """Harvest a single deserialized SBOM element into *registry*."""
    name = getattr(obj, "name", None)
    spdx_id = getattr(obj, "spdxId", None)
    if not name or not spdx_id:
        return

    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    if not compact_type:
        compact_type = type(obj).__name__

    if compact_type != "software_Package":
        sha256 = _sha256_from_verified_using(obj)
        if sha256 is not None:
            registry.files[name] = FileEntry(spdx_id=spdx_id, sha256=sha256)
            return

    if not compact_type or compact_type == "object":
        log.debug("Import: skipping %r (no SPDX 3 compact type)", name)
        return
    registry.entities[name] = EntityEntry(type=compact_type, spdx_id=spdx_id)


def resolve_registry(
    project_dir: Path,
    ids_file: str | Path | IdRegistry | None = None,
) -> IdRegistry | None:
    """Resolve the registry a project build should consult."""
    if isinstance(ids_file, IdRegistry):
        return ids_file
    if ids_file is not None:
        path = Path(ids_file)
        registry_path = path if path.is_absolute() else project_dir / path
        try:
            return IdRegistry.load(registry_path)
        except (FileNotFoundError, ValueError, OSError) as exc:
            log.warning("Could not load registry %s: %s", registry_path, exc)
            return None
    return IdRegistry.find(start=project_dir)


def _load_or_create_registry(
    registry_path: Path, project_dir_name: str
) -> IdRegistry | None:
    """Load existing registry from registry_path or return a new one."""
    if registry_path.exists():
        try:
            return IdRegistry.load(registry_path)
        # pylint: disable=broad-exception-caught
        except Exception as exc:
            print(
                f"ERROR: failed to load registry from {registry_path}: {exc}",
                file=sys.stderr,
            )
            return None

    namespace = f"https://spdx.org/spdxdocs/{project_dir_name}-{uuid4()}"
    return IdRegistry(namespace=namespace)


def _default_ids_generate_paths(project_dir: Path) -> list[Path]:
    """Return default candidate paths for `pitloom ids generate`."""
    return [
        project_dir / name
        for name in _DEFAULT_IDS_GENERATE_DIR_NAMES
        if (project_dir / name).exists()
    ]
