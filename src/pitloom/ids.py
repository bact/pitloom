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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._ids_types import (
    _DEFAULT_IDS_GENERATE_DIR_NAMES,
    _IGNORED_DIR_NAMES,
    _REGISTRY_VERSION,
    DEFAULT_REGISTRY_FILENAME,
    EntityEntry,
    FileEntry,
    _iter_files,
    _sha256_from_verified_using,
    _type_id_prefix,
    sha256_file,
)
from pitloom._sbom_io import open_text_lf

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_REGISTRY_FILENAME",
    "DIRECTORY_ENTITY_TYPE",
    "EntityEntry",
    "FileEntry",
    "IdRegistry",
    "PACKAGE_ENTITY_TYPE",
    "_DEFAULT_IDS_GENERATE_DIR_NAMES",
    "_IGNORED_DIR_NAMES",
    "_REGISTRY_VERSION",
    "_default_ids_generate_paths",
    "_import_sbom_element",
    "_iter_files",
    "_load_or_create_registry",
    "_sha256_from_verified_using",
    "_type_id_prefix",
    "claim_registry_hit",
    "resolve_explicit_registry",
    "resolve_registry",
    "sha256_file",
]

#: The SPDX 3 compact type a directory is registered under (an
#: :class:`~spdx_python_model.bindings.v3_0_1.software_File` with
#: ``software_fileKind == directory`` -- there is no dedicated "directory"
#: SHACL type, so it shares ``software_File``'s compact type with a regular
#: file entry). Shared constant so a directory lookup/harvest never drifts
#: from a hand-typed literal.
DIRECTORY_ENTITY_TYPE = "software_File"

#: The SPDX 3 compact type a deployed dependency package (and a project's
#: own main package) is registered under -- shared by
#: :func:`~pitloom.assemble.spdx3._document_deployed._build_deployed_package`'s
#: lookup and :func:`_entity_key`'s canonicalization (see its docstring).
PACKAGE_ENTITY_TYPE = "software_Package"


def _entity_key(name: str, type_name: str) -> tuple[str, str]:
    """Return the ``entities`` dict key for a named entity of *type_name*.

    The single place a :data:`PACKAGE_ENTITY_TYPE` entity's name is PEP 503
    canonicalized (:func:`packaging.utils.canonicalize_name`) -- every
    reader/writer of :attr:`IdRegistry.entities` for that type
    (:meth:`IdRegistry.register_entity`, :meth:`IdRegistry.lookup_entity`,
    harvest via :func:`_import_sbom_element`) goes through this, so a
    package's declared name (e.g. ``"PyYAML"``) and a lowercased lookup key
    (e.g. ``"pyyaml"``, from pipdeptree) always resolve to the identical
    entry. Every other entity type is keyed by its name verbatim.
    """
    if type_name == PACKAGE_ENTITY_TYPE:
        return (type_name, canonicalize_name(name))
    return (type_name, name)


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

        version = data.get("version")
        if version != _REGISTRY_VERSION:
            raise ValueError(
                f"Registry {path} has version {version!r}, expected "
                f"{_REGISTRY_VERSION} (no migration support -- delete it and "
                "re-run `pitloom ids generate` or `pitloom ids import`)"
            )

        try:
            files = {
                str(rel_path): FileEntry(
                    spdx_id=str(entry["spdxId"]), sha256=str(entry["sha256"])
                )
                for rel_path, entry in data.get("files", {}).items()
            }
            entities: dict[tuple[str, str], EntityEntry] = {}
            for type_name, names in data.get("entities", {}).items():
                for name, entry in names.items():
                    key = _entity_key(str(name), str(type_name))
                    if key in entities:
                        raise ValueError(
                            f"Registry {path} has two {key[0]} entries for {key[1]!r}"
                        )
                    entities[key] = EntityEntry(spdx_id=str(entry["spdxId"]))
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
                    log.warning(
                        "Registry: ignoring invalid file %s: %s", candidate, exc
                    )
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
        entry = self.entities.get(_entity_key(name, type_name))
        return entry.spdx_id if entry is not None else None

    def has_entity_named(self, name: str) -> bool:
        """Return whether *name* is registered under any type at all, as
        given or as the type's own key form (:func:`_entity_key`)."""
        return any(
            key[1] == name or key == _entity_key(name, key[0]) for key in self.entities
        )

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

        for file_path in _iter_files(paths, project_root):
            try:
                sha256 = sha256_file(file_path)
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

        sorted_objects = _sorted_by_spdx_id(object_set)

        if not self.files and not self.entities:
            for obj in sorted_objects:
                if isinstance(obj, spdx3.SpdxDocument) and obj.spdxId:
                    self.namespace = obj.spdxId
                    break

        self._harvest_sorted(sorted_objects)

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
        gate a ``save()`` on instead -- :func:`_release_stale_keys_for_id`
        can drop one stale key in the same pass that adds another, which
        nets to a zero size delta despite real content changing (the
        surviving key's id, or the stale key's removal, both need
        persisting); the net-count deltas alone cannot detect that case.
        """
        return self._harvest_sorted(_sorted_by_spdx_id(object_set))

    def _harvest_sorted(self, sorted_objects: list[Any]) -> tuple[int, int, bool]:
        """Harvest *sorted_objects* (see :func:`_sorted_by_spdx_id`).

        Shared by :meth:`harvest` and :meth:`import_sbom` -- the latter
        already needs a sorted list for its own namespace-seeding scan,
        so it reuses that same list here instead of sorting the object
        set twice.
        """
        before_files = dict(self.files)
        before_entities = dict(self.entities)
        index = _SpdxIdIndex.from_registry(self)
        for obj in sorted_objects:
            _import_sbom_element(self, obj, index)
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
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        self.path = target


def _sorted_by_spdx_id(object_set: spdx3.SHACLObjectSet) -> list[Any]:
    """Return *object_set*'s objects sorted by ``spdxId`` for deterministic
    iteration (``SHACLObjectSet.objects`` is an unordered set).

    Not canonical for SBOM output: this order never feeds hashed or
    serialized SBOM content -- unlike
    :func:`pitloom.assemble.spdx3._fragments_unify._canonical_merge_key`,
    whose order does determine SBOM output content. It is still
    load-bearing for :class:`IdRegistry` bookkeeping, though: when an
    imported SBOM carries more than one ``SpdxDocument`` element,
    :meth:`IdRegistry.import_sbom` takes the first one in this order as
    ``self.namespace`` (see its loop over ``sorted_objects``), and that
    namespace is itself persisted by :meth:`IdRegistry.save`. Changing
    this key is safe for the common single-document case, but can change
    which namespace gets picked -- and persisted -- for a multi-document
    input.
    """
    return sorted(object_set.objects, key=lambda o: getattr(o, "spdxId", None) or "")


def _is_files_path_alias(path_a: str, path_b: str) -> bool:
    """True if *path_a*/*path_b* are the intentional physical-path/
    distribution-path dual-keying for a single src/-layout file: their
    :class:`~pathlib.PurePosixPath` parts tail-match, one a strict suffix
    of the other (e.g. ``src/pkg/x.py`` vs ``pkg/x.py``) -- not merely two
    unrelated paths that happen to end in the same filename (e.g.
    ``demo/a/__init__.py`` vs ``demo/c/__init__.py``, whose last two parts
    already differ)."""
    parts_a = PurePosixPath(path_a).parts
    parts_b = PurePosixPath(path_b).parts
    shorter, longer = (
        (parts_a, parts_b) if len(parts_a) <= len(parts_b) else (parts_b, parts_a)
    )
    return bool(shorter) and longer[-len(shorter) :] == shorter


@dataclass
class _SpdxIdIndex:
    """``spdx_id -> keys`` reverse index for a registry's ``files``/
    ``entities`` tables, scoped to one :meth:`IdRegistry._harvest_sorted`
    pass and kept in sync as entries are added/removed during it.

    :func:`_release_stale_keys_for_id` uses this to find every OTHER key
    already sharing a given id in O(keys sharing that id), instead of
    scanning the whole ``files``/``entities`` table (and computing
    :func:`_is_files_path_alias` against every candidate, matching or
    not) on every harvested element -- O(harvested elements * registry
    size) over a full pass otherwise.
    """

    files: dict[str, set[str]] = field(default_factory=dict)
    entities: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def from_registry(cls, registry: IdRegistry) -> _SpdxIdIndex:
        """Build the index from *registry*'s current table contents."""
        files: dict[str, set[str]] = {}
        for path, file_entry in registry.files.items():
            files.setdefault(file_entry.spdx_id, set()).add(path)
        entities: dict[str, set[tuple[str, str]]] = {}
        for key, entity_entry in registry.entities.items():
            entities.setdefault(entity_entry.spdx_id, set()).add(key)
        return cls(files=files, entities=entities)

    def set_file(self, registry: IdRegistry, path: str, entry: FileEntry) -> None:
        """Write *entry* to ``registry.files[path]``, keeping this index
        in sync with both the old spdx_id (if *path* already had a
        different one) and the new one."""
        old = registry.files.get(path)
        if old is not None:
            self.files.get(old.spdx_id, set()).discard(path)
        registry.files[path] = entry
        self.files.setdefault(entry.spdx_id, set()).add(path)

    def drop_file(self, registry: IdRegistry, spdx_id: str, path: str) -> None:
        """Delete ``registry.files[path]``, keeping this index in sync."""
        del registry.files[path]
        self.files.get(spdx_id, set()).discard(path)

    def set_entity(
        self, registry: IdRegistry, key: tuple[str, str], entry: EntityEntry
    ) -> None:
        """Write *entry* to ``registry.entities[key]``, keeping this
        index in sync with both the old spdx_id (if *key* already had a
        different one) and the new one."""
        old = registry.entities.get(key)
        if old is not None:
            self.entities.get(old.spdx_id, set()).discard(key)
        registry.entities[key] = entry
        self.entities.setdefault(entry.spdx_id, set()).add(key)

    def drop_entity(
        self, registry: IdRegistry, spdx_id: str, key: tuple[str, str]
    ) -> None:
        """Delete ``registry.entities[key]``, keeping this index in sync."""
        del registry.entities[key]
        self.entities.get(spdx_id, set()).discard(key)


def _release_stale_keys_for_id(
    registry: IdRegistry,
    spdx_id: str,
    index: _SpdxIdIndex,
    *,
    files_key: str | None = None,
    files_sha256: str | None = None,
    entity_key: tuple[str, str] | None = None,
) -> None:
    """Enforce the one-key-per-id registry invariant before a harvested
    element claims *spdx_id*: drop any OTHER key, in either
    :attr:`IdRegistry.files` or :attr:`IdRegistry.entities`, that already
    holds this exact id but genuinely refers to something else.

    Two registry keys sharing one id is never legitimate for two
    *different* elements: a lookup by either key would hand back the same
    spdxId for what the caller treats as two distinct elements, so a
    later document that looks up both would emit one duplicate-id element
    instead of two. A stale key holding this id is itself evidence of an
    earlier harvest picking one arbitrary winner among several source
    elements that happened to share an id -- dropping it here stops that
    transient duplicate from calcifying into a permanent double-entry the
    next time this exact id is (re-)harvested.

    *index* is *registry*'s current ``spdx_id -> keys`` reverse index
    (:class:`_SpdxIdIndex`) -- every candidate this checks already shares
    *spdx_id*, so the more expensive sha256/alias check below only ever
    runs for genuine collision candidates, never the whole table.

    A *files* entry is only kept when BOTH its recorded ``sha256``
    matches *files_sha256* AND its path is a :func:`_is_files_path_alias`
    of *files_key* -- the intentional physical-path/distribution-path
    dual-keying for a single src/-layout file (see
    ``pitloom.core.project.project_relative_or_fallback``'s docstring and
    ``_add_package_files()``'s two-path lookup). Same content but
    unrelated paths (e.g. two different same-content empty
    ``__init__.py`` files) is NOT that alias and is dropped like any
    other stale key -- matching content alone is not sufficient evidence
    of the same file under two names. No alias case exists for entities,
    so any other entities key sharing the id is always dropped.
    *files_key*/*entity_key* is the key about to claim *spdx_id* and is
    excluded from its own removal either way.
    """
    for path in list(index.files.get(spdx_id, ())):
        if path == files_key:
            continue
        file_entry = registry.files[path]
        is_alias = (
            files_key is not None
            and file_entry.sha256 == files_sha256
            and _is_files_path_alias(path, files_key)
        )
        if not is_alias:
            index.drop_file(registry, spdx_id, path)
    for key in list(index.entities.get(spdx_id, ())):
        if key != entity_key:
            index.drop_entity(registry, spdx_id, key)


def claim_registry_hit(key: str, spdx_id: str, claimed: dict[str, str]) -> str | None:
    """Return *spdx_id* if nothing in *claimed* has claimed it yet,
    recording ``claimed[spdx_id] = key``; otherwise log one
    ``WARNING: Registry: ...`` naming both claimants and return ``None``
    (treated as a lookup miss by the caller, so it mints its own id
    instead).

    Shared by every ``_resolve_*_hits`` pre-resolution pass
    (:mod:`~pitloom.assemble.spdx3._document_files`,
    :mod:`~pitloom.assemble.spdx3.ai`,
    :mod:`~pitloom.assemble.spdx3._document_deployed`) so the same
    wording is used everywhere instead of being retyped per call site.
    Two distinct elements in one document both hitting the same
    registry-supplied id happens when a stale registry entry outlives the
    element it originally named (see
    ``working-docs/implementation/id-registry-autosync.md``'s
    first-claimant-wins section) -- reusing it for both would itself
    create the exact duplicate-spdxId bug this whole reservation
    mechanism exists to prevent, so only the first claimant (in whatever
    order the caller iterates, which must itself be deterministic) gets
    to reuse it; every later one falls back to a fresh mint.

    *claimed* is shared across every hit in one pre-resolution pass --
    and, in :func:`~pitloom.assemble.spdx3.document.build`, across
    files/directories/AI models together -- so the "first claimant" rule
    holds across all of them, not just within one resolver.
    """
    first_key = claimed.get(spdx_id)
    if first_key is not None:
        log.warning(
            "Registry: %s is registered for both %s and %s; %s gets a new id",
            spdx_id,
            first_key,
            key,
            key,
        )
        return None
    claimed[spdx_id] = key
    return spdx_id


def _import_sbom_element(
    registry: IdRegistry, obj: Any, index: _SpdxIdIndex | None = None
) -> None:
    """Harvest a single deserialized SBOM element into *registry*.

    The ``entities`` storage key goes through :func:`_entity_key`, same as
    every other reader/writer -- see its docstring for the
    :data:`PACKAGE_ENTITY_TYPE` canonicalization this applies. The
    element's own ``.name`` field (what the SBOM actually displays) is
    untouched; only the registry's storage key is canonicalized.

    A key that already maps to a *different* id keeps its own entry, but
    :func:`_release_stale_keys_for_id` is called afterwards so a
    newly-assigned id first drops any other key that already held it --
    see that function's docstring for why one id can never legitimately
    back two registry keys.

    *index* is the ``spdx_id -> keys`` reverse index
    :func:`_release_stale_keys_for_id` needs -- :meth:`IdRegistry._harvest_sorted`
    builds one and threads it through every element in its pass, so it's
    built once, not once per element. A direct caller (e.g. harvesting a
    single element outside a batch pass) can omit it and gets one freshly
    built from *registry*'s current contents, same result either way.
    """
    name = getattr(obj, "name", None)
    spdx_id = getattr(obj, "spdxId", None)
    if not name or not spdx_id:
        return
    if index is None:
        index = _SpdxIdIndex.from_registry(registry)

    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    if not compact_type:
        compact_type = type(obj).__name__

    if compact_type != PACKAGE_ENTITY_TYPE:
        sha256 = _sha256_from_verified_using(obj)
        if sha256 is not None:
            _release_stale_keys_for_id(
                registry, spdx_id, index, files_key=name, files_sha256=sha256
            )
            index.set_file(registry, name, FileEntry(spdx_id=spdx_id, sha256=sha256))
            return

    if not compact_type or compact_type == "object":
        log.debug("Import: skipping %r (no SPDX 3 compact type)", name)
        return
    key = _entity_key(name, compact_type)
    _release_stale_keys_for_id(registry, spdx_id, index, entity_key=key)
    index.set_entity(registry, key, EntityEntry(spdx_id=spdx_id))


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
            log.warning("Registry: could not load %s: %s", registry_path, exc)
            return None
    return IdRegistry.find(start=project_dir)


def resolve_explicit_registry(
    registry: str | Path | IdRegistry | None,
    ids_file: str | None,
) -> IdRegistry | None:
    """Resolve the registry for a target with no project of its own (a
    wheel, an installed environment, a model file).

    Only an explicit source counts: *registry* (``--registry``), else
    *ids_file* from an explicitly named config. Unlike
    :func:`resolve_registry`, this never searches for a ``loom-ids.json``
    -- one found near the current directory belongs to whatever project
    that is, not to this target. A relative path resolves against the
    current directory; :func:`pitloom.core.config_cascade.load_config_file`
    has already made a config's own ``ids-file`` absolute.
    """
    source = registry if registry is not None else ids_file
    if source is None:
        return None
    return resolve_registry(Path.cwd(), source)


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
