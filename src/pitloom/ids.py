# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom ID registry: a stable file/entity -> SPDX ID registry.

A project's ``loom-ids.json`` gives the same physical file, or the same
named entity (e.g. an AI model), the same ``spdxId`` every time it is
referenced -- whether that reference comes from a ``pitloom.loom.run()``
fragment, the Hatchling build hook's own wheel-file scan, or the ``pitloom``
CLI.  Sharing one id across all of these is what lets
:func:`pitloom.assemble.spdx3.fragments.merge_fragments` unify elements from
independently generated fragments into a single connected AI-pipeline graph,
without ever resorting to name-based matching.

The registry is deliberately simple JSON so it can be inspected, diffed, and
(if needed) hand-edited::

    {
      "version": 1,
      "namespace": "https://spdx.org/spdxdocs/<project>-<uuid4>",
      "files": {
        "data/raw/pos.txt": {"spdxId": "<ns>#File-1", "sha256": "<hex>"}
      },
      "entities": {
        "sentimentdemo": {"type": "ai_AIPackage", "spdxId": "<ns>#AIPackage-1"}
      }
    }

Consultation (:meth:`IdRegistry.lookup_file`, :meth:`IdRegistry.lookup_entity`)
is read-only and used by ``pitloom.loom``, the Hatchling build hook, and the
CLI's project/model assembly paths.  Mutation (:meth:`IdRegistry.generate`,
:meth:`IdRegistry.import_sbom`) is reserved for the ``pitloom ids`` CLI
subcommands.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

log = logging.getLogger(__name__)

#: Default registry filename, resolved relative to a project root.
DEFAULT_REGISTRY_FILENAME = "loom-ids.json"

#: Directory names never descended into while indexing files for the registry.
_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".pyrefly_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".hatch",
        "fragments",
    }
)

_REGISTRY_VERSION = 1


@dataclass
class FileEntry:
    """A single registered file: its stable ``spdxId`` and content hash.

    ``sha256`` is normalised to lower-case in ``__post_init__``, so a
    registry entry loaded from a hand-edited ``loom-ids.json`` or imported
    from a foreign SBOM (either may use upper-case hex) still compares
    equal to the lower-case hex :func:`_sha256_file` always produces.
    """

    spdx_id: str
    sha256: str

    def __post_init__(self) -> None:
        self.sha256 = self.sha256.lower()


@dataclass
class EntityEntry:
    """A single registered named entity (e.g. an AI model) and its
    ``spdxId``."""

    type: str
    spdx_id: str


def _sha256_file(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*'s contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _type_id_prefix(type_name: str) -> str:
    """Return the SPDX ID fragment prefix for a SHACL type name.

    Strips a leading SPDX 3 profile namespace, e.g. ``"ai_AIPackage"`` ->
    ``"AIPackage"``, ``"dataset_DatasetPackage"`` -> ``"DatasetPackage"``,
    ``"software_Package"`` -> ``"Package"`` -- matching the prefix convention
    used throughout :func:`pitloom.core.models.generate_spdx_id`.
    """
    _, _, rest = type_name.partition("_")
    return rest or type_name


def _sha256_from_verified_using(obj: Any) -> str | None:
    """Return the SHA-256 hex digest from *obj*'s ``verifiedUsing`` list, or
    ``None`` if it carries no SHA-256 ``Hash``."""
    for h in getattr(obj, "verifiedUsing", None) or []:
        if getattr(h, "algorithm", None) == spdx3.HashAlgorithm.sha256:
            value = getattr(h, "hashValue", None)
            if value:
                return str(value)
    return None


class IdRegistry:
    """A Loom ID registry: a stable file/entity -> SPDX ID registry,
    persisted as JSON.

    Attributes:
        namespace: The SPDX document namespace new ids are minted under
            (``https://spdx.org/spdxdocs/<project>-<uuid>``). Ids imported
            from an existing SBOM keep their original namespace verbatim
            (they are stored as full id strings, not reconstructed).
        files: Project-root-relative POSIX path -> :class:`FileEntry`.
        entities: Entity name -> :class:`EntityEntry`.
        path: Filesystem path this registry was loaded from / saves to by
            default. ``None`` for a registry constructed in memory only.
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

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def new(cls, project_name: str, path: Path | None = None) -> IdRegistry:
        """Create a fresh, empty registry with a freshly minted namespace."""
        namespace = f"https://spdx.org/spdxdocs/{project_name}-{uuid4()}"
        return cls(namespace=namespace, path=path)

    @classmethod
    def load(cls, path: Path) -> IdRegistry:
        """Load a registry from *path*.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the file is not valid registry JSON.
        """
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
        """Walk upward from *start* (default: cwd) looking for
        ``loom-ids.json``.

        Returns:
            The loaded registry, or ``None`` if no registry file is found
            before reaching the filesystem root, or if the nearest one found
            fails to load (logged as a warning rather than raised, so a
            broken registry degrades to "no registry" instead of crashing
            an unrelated ``loom.run()``).
        """
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

    # ------------------------------------------------------------------
    # Lookup -- read-only consultation (loom SDK, build hook, CLI)
    # ------------------------------------------------------------------

    def lookup_file(self, path: str, sha256: str) -> str | None:
        """Return the registered ``spdxId`` for *path*, only when both the
        path and its content hash match a registry entry.

        A hash mismatch (the file changed since the registry entry was
        written) returns ``None`` -- the same as "not registered" -- rather
        than the stale id: changed content is different provenance truth,
        and callers are expected to warn and mint a fresh id in that case.
        """
        entry = self.files.get(path)
        if entry is None or entry.sha256 != sha256:
            return None
        return entry.spdx_id

    def lookup_entity(self, name: str, type_name: str) -> str | None:
        """Return the registered ``spdxId`` for the named entity of
        *type_name*, or ``None`` when not registered or registered under a
        different type."""
        entry = self.entities.get(name)
        if entry is None or entry.type != type_name:
            return None
        return entry.spdx_id

    # ------------------------------------------------------------------
    # Mutation -- reserved for the `pitloom ids` CLI
    # ------------------------------------------------------------------

    def _mint_id(self, prefix: str) -> str:
        """Mint the next stable ``#<prefix>-<n>`` id in this registry's
        namespace.

        ``n`` is one greater than the highest existing numeric suffix used
        for *prefix* across both ``files`` and ``entities``, so regenerating
        the registry never reuses or collides with an id already handed out.
        """
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
        """Register (or refresh) a file entry and return its ``spdxId``.

        Stable regeneration: an unchanged hash keeps the existing id
        unchanged; a changed hash mints a fresh id and replaces the entry
        (the content is different provenance truth, so the old id must not
        keep being handed out for it -- the change is logged).

        By design, not a gap: the registry stores only *current* identity,
        one hash/id per path -- the superseded hash and old spdxId are not
        retained anywhere after this call (only the transient log line
        above). A registry with identity history is a different, larger
        feature (versioned entries, "supersedes" links) that hasn't been
        designed; this method intentionally does not attempt it.
        """
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

        An existing entry for *name* is always reused verbatim, even if its
        recorded ``type`` differs from *type_name* -- a mismatch is logged
        rather than silently minting a second, parallel id for what a human
        almost certainly intends as the same entity.
        """
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
        """(Re-)index files under *paths* into this registry.

        Every regular file found is registered via :meth:`register_file`
        (stable regeneration: unchanged content keeps its id; changed
        content gets a fresh one).  Files whose magic bytes/extension
        identify them as AI model files (see
        :func:`pitloom.extract.ai_model.detect_ai_model_format`) also get an
        ``entities`` entry keyed by the file's stem -- e.g.
        ``models/sentimentdemo.bin`` registers an ``ai_AIPackage`` entity
        named ``"sentimentdemo"`` -- so a later ``loom.set_model()`` or
        ``loom model ... --registry`` invocation can look it up by name and
        share its ``spdxId`` rather than minting an unrelated one.

        Args:
            paths: Files or directories to index, resolved relative to
                *project_root* when not already absolute.
            project_root: Registry keys are stored as paths relative to
                this root, in POSIX form.
        """
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

    # ------------------------------------------------------------------
    # Import from an existing SBOM
    # ------------------------------------------------------------------

    def import_sbom(self, sbom_path: Path) -> None:
        """Harvest ids from an existing SPDX 3 JSON-LD SBOM into this registry.

        Every element in the graph with both a ``name`` and a ``spdxId`` is
        importable -- generically, not via a hardcoded type allowlist,
        since any element (``software_Package``, ``ai_AIPackage``,
        ``dataset_DatasetPackage``, ``software_File``, or a type pitloom
        does not otherwise model) can carry a stable id worth reusing. An
        element that also carries a SHA-256 ``verifiedUsing`` hash
        populates ``files`` (keyed by ``name`` -- for pitloom-generated
        SBOMs this is a project-root-relative path); everything else
        populates ``entities`` (keyed by ``name``, typed by the element's
        actual SPDX 3 compact type, e.g. ``"software_Package"``).  When
        this registry is still empty and the SBOM has a main
        ``SpdxDocument``, its namespace is adopted as this registry's
        namespace so subsequently minted ids read as part of the same
        document family as the imported ones.

        Elements missing the fields needed to key them (no ``name`` or no
        ``spdxId``) are skipped with a debug log rather than an error -- a
        foreign or hand-written SBOM may have gaps.
        """
        object_set = spdx3.SHACLObjectSet()
        with open(sbom_path, "rb") as f:
            spdx3.JSONLDDeserializer().read(f, object_set)

        # Sorted iteration: SHACLObjectSet.objects is an unordered set, and
        # if two elements share a name the last one written wins -- keep
        # that choice deterministic across runs.
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

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path | None = None) -> None:
        """Write this registry as JSON to *path* (default: :attr:`path`).

        Raises:
            ValueError: If neither *path* nor :attr:`path` is set.
        """
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
    """Harvest a single deserialized SBOM element into *registry*, when it
    carries both a ``name`` and a ``spdxId`` -- any SPDX 3 Element
    qualifies, not just a fixed set of types pitloom happens to name
    explicitly elsewhere (see :meth:`IdRegistry.import_sbom`)."""
    name = getattr(obj, "name", None)
    spdx_id = getattr(obj, "spdxId", None)
    if not name or not spdx_id:
        return

    get_compact_type = getattr(obj, "get_compact_type", None)
    compact_type = get_compact_type() if get_compact_type is not None else None
    if not compact_type:
        compact_type = type(obj).__name__

    # A bare software_Package (the main project package, or a dependency
    # package) can carry a verifiedUsing hash too (see document.py's
    # _build_main_package, which sets one from the wheel's Merkle root) --
    # that hash is content-integrity metadata about the whole package, not
    # a file-path lookup key, so it must not land in registry.files keyed
    # by the package's bare name. Subtypes like dataset_DatasetPackage are
    # unaffected: get_compact_type() reports their own specific type name,
    # never the literal "software_Package", so their hash still promotes
    # them to registry.files as before.
    if compact_type != "software_Package":
        sha256 = _sha256_from_verified_using(obj)
        if sha256 is not None:
            registry.files[name] = FileEntry(spdx_id=spdx_id, sha256=sha256)
            return

    if not compact_type or compact_type == "object":
        log.debug("Import: skipping %r (no SPDX 3 compact type)", name)
        return
    registry.entities[name] = EntityEntry(type=compact_type, spdx_id=spdx_id)


def _iter_files(paths: list[Path], project_root: Path) -> Iterator[Path]:
    """Yield every regular file under *paths* (resolved relative to
    *project_root*), skipping ignored directory names and the registry file
    itself, in deterministic (sorted) order."""
    seen: set[Path] = set()

    for raw_path in paths:
        root = raw_path if raw_path.is_absolute() else project_root / raw_path
        if not root.exists():
            log.warning("Registry: path not found, skipping: %s", root)
            continue

        candidates: Iterable[Path]
        if root.is_file():
            candidates = [root]
        else:
            candidates = sorted(root.rglob("*"))

        for file_path in candidates:
            if not file_path.is_file():
                continue
            if any(part in _IGNORED_DIR_NAMES for part in file_path.parts):
                continue
            if file_path.name == DEFAULT_REGISTRY_FILENAME:
                continue
            if file_path in seen:
                continue
            seen.add(file_path)
            yield file_path


def resolve_registry(project_dir: Path, ids_file: str | None) -> IdRegistry | None:
    """Resolve the registry a project build should consult.

    Shared by the Hatchling build hook and the CLI project-assembly path
    (see :func:`~pitloom.assemble.generate_project_sbom`) so both use the exact same
    resolution rule as ``pitloom.loom``: an explicit ``[tool.pitloom]
    ids-file`` (``ids_file``) is loaded relative to *project_dir*; otherwise
    ``loom-ids.json`` is auto-discovered by walking up from
    *project_dir*. Any load failure is logged and degrades to "no registry"
    -- a missing or broken registry must never fail a build.

    Args:
        project_dir: Project root directory.
        ids_file: ``[tool.pitloom] ids-file`` value, or ``None``.

    Returns:
        The loaded :class:`IdRegistry`, or ``None`` if none is configured/found.
    """
    if ids_file is not None:
        registry_path = project_dir / ids_file
        try:
            return IdRegistry.load(registry_path)
        except (FileNotFoundError, ValueError, OSError) as exc:
            log.warning("Could not load registry %s: %s", registry_path, exc)
            return None
    return IdRegistry.find(start=project_dir)


__all__ = [
    "DEFAULT_REGISTRY_FILENAME",
    "EntityEntry",
    "FileEntry",
    "IdRegistry",
    "resolve_registry",
]
