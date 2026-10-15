# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistry``: a Loom ID registry, one table keyed by ``(type, name)``.

See also: :mod:`pitloom.id_registry._types` for ``RegistryEntry`` and file
traversal, :mod:`pitloom.id_registry._format` for the file format,
:mod:`pitloom.id_registry._counters` for the id counters,
:mod:`pitloom.id_registry._harvest` for SBOM-element harvest helpers,
:mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.iri import doc_namespace, iri_segment, require_namespace_iri
from pitloom.core.walk_rules import same_path
from pitloom.id_registry._counters import (
    MAX_ID_NUMBER,
    Counters,
    id_number,
    merge_counters,
)
from pitloom.id_registry._format import (
    read_registry_file,
    registry_dir,
    write_registry_file,
)
from pitloom.id_registry._harvest import _harvest_elements, _sorted_by_spdx_id
from pitloom.id_registry._persist import Rebase, added_ids, replay_changes
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    RegistryEntry,
    _element_key,
    _iter_files,
    _require_names,
    registry_file_error,
    sha256_file,
    type_id_prefix,
)

log = logging.getLogger("pitloom.id_registry")

__all__ = ["IdRegistry"]


class IdRegistry:
    """A Loom ID registry: stable spdxIds keyed by ``(compact type, name)``,
    persisted as JSON.

    Each entry may carry the element's SHA-256. Harvest records what an
    element has; a lookup decides whether the hash must match
    (:meth:`lookup`). :attr:`id_counters` keeps a retired id from being
    minted again (:meth:`reserve_id`).
    """

    def __init__(
        self,
        namespace: str,
        elements: dict[tuple[str, str], RegistryEntry] | None = None,
        path: Path | None = None,
        project_root: Path | None = None,
        *,
        id_counters: Counters | None = None,
    ) -> None:
        self.namespace = namespace
        #: Keyed by :func:`~pitloom.id_registry._types._element_key`.
        self.elements: dict[tuple[str, str], RegistryEntry] = (
            elements if elements is not None else {}
        )
        #: Id prefix -> the highest number minted or seen in
        #: :attr:`namespace`; never lowered, and never below a held id's.
        self.id_counters: Counters = dict(id_counters or {})
        self.path = path
        #: Absolute and realpath'd; ``None`` until set or saved.
        self.project_root: Path | None = (
            Path(os.path.realpath(project_root)) if project_root is not None else None
        )
        # The table as last read from or written to `path`: what `rebase`
        # tells this object's own changes apart by. None: neither yet.
        self._on_disk: dict[tuple[str, str], RegistryEntry] | None = None
        self._reserve_held()

    @classmethod
    def new(
        cls,
        project_name: str,
        path: Path | None = None,
        *,
        namespace: str | None = None,
        project_root: Path | None = None,
    ) -> IdRegistry:
        """Create a fresh, empty registry.

        The namespace is *namespace* (an absolute IRI without ``#``; a
        ``ValueError`` otherwise), else one minted from *project_name* and
        a random UUID4. It is fixed once the registry is created: the
        registry file is an input, so a committed one gives identical ids.
        A name-derived UUID would give two unrelated projects of one name the
        same ids.
        """
        if namespace is None:
            namespace = doc_namespace(project_name, str(uuid4()))
        else:
            require_namespace_iri(namespace)
        return cls(namespace=namespace, path=path, project_root=project_root)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> IdRegistry:
        """Load a registry from *path*.

        Every failure raises one ``ValueError`` via
        :func:`~pitloom.id_registry._types.registry_file_error` -- never
        returns ``None``. "Maybe there's a registry" is resolved upstream,
        by :func:`~pitloom.id_registry.resolve.resolve_registry`.
        """
        path = Path(path)
        contents = read_registry_file(path)
        registry = cls(
            namespace=contents.namespace,
            elements=dict(contents.elements),
            path=path,
            project_root=contents.project_root,
            id_counters=contents.id_counters,
        )
        registry._on_disk = contents.elements
        return registry

    def rebase(self) -> Rebase:
        """Re-read :attr:`path` and apply this object's own changes again on
        top (:func:`~pitloom.id_registry._persist.replay_changes`), so a
        save keeps what another run saved meanwhile.

        A change is a key whose entry differs from the table this object
        last read or wrote; for one that has read or written none, every
        entry is. The namespace and project root become the file's; the id
        counters merge by maximum, so neither run lowers one. With no file
        at :attr:`path` yet, the registry is left as it is.

        Raises:
            ValueError: the file no longer loads, or (never read) does not.
        """
        if self.path is None or (
            self._on_disk is None and not os.path.exists(self.path)
        ):
            return Rebase(refused=0, pending=True)
        contents = read_registry_file(self.path)
        merged, refused = replay_changes(
            self._on_disk or {}, self.elements, contents.elements
        )
        self.elements.clear()
        self.elements.update(merged)
        self.namespace = contents.namespace
        self.project_root = contents.project_root
        self.id_counters = merge_counters(self.id_counters, contents.id_counters)
        self._reserve_held()
        self._on_disk = contents.elements
        return Rebase(
            refused=refused,
            pending=merged != contents.elements
            or self.id_counters != contents.id_counters,
        )

    def get(self, type_name: str, name: str) -> RegistryEntry | None:
        """Return the entry for *name* under *type_name*, or ``None``."""
        return self.elements.get(_element_key(type_name=type_name, name=name))

    def lookup(
        self, type_name: str, names: Sequence[str], *, sha256: str | None = None
    ) -> str | None:
        """Return the ``spdxId`` of the first of *names* registered under
        *type_name*, or ``None``.

        With *sha256*, only an entry recording the same SHA-256 (any case)
        is a hit; an entry with no hash never is. Without it, the entry's
        hash is ignored. *names* are tried in order; the first hit wins.
        """
        _require_names(names)
        wanted = sha256.lower() if sha256 is not None else None
        for name in names:
            entry = self.get(type_name, name)
            if entry is None:
                continue
            if wanted is None or entry.sha256 == wanted:
                return entry.spdx_id
        return None

    def require_namespace(self, namespace: str) -> None:
        """Raise ``ValueError`` unless this registry's namespace is
        *namespace* (``id generate --namespace`` on an existing registry:
        silently keeping the old one would ignore the flag)."""
        if namespace != self.namespace:
            raise registry_file_error(
                self.path or Path(""),
                f"namespace {self.namespace} is not --namespace {namespace}; "
                "delete it to change the namespace",
            )

    def require_project_root(self, project_root: Path) -> None:
        """Raise ``ValueError`` unless this registry's project root
        (:meth:`root_dir`) is *project_root* (same directory, whatever the
        spelling): keys from two roots in one registry would not match."""
        root = self.root_dir()
        if not same_path(root, project_root):
            raise registry_file_error(
                self.path or Path(""),
                f"project root {root} is not {project_root}; "
                "delete it to change the project root",
            )

    def has_name(self, name: str) -> bool:
        """Return whether *name* is registered under any type, as given or
        as that type's own key form."""
        return any(
            key[1] == name or key == _element_key(type_name=key[0], name=name)
            for key in self.elements
        )

    def id_count(self) -> int:
        """Return the number of distinct spdxIds (a src-layout alias adds a
        key, not an id)."""
        return len({entry.spdx_id for entry in self.elements.values()})

    def root_dir(self) -> Path:
        """Return the project root, else the registry file's directory,
        else the current directory -- realpath'd."""
        if self.project_root is not None:
            return Path(os.path.realpath(self.project_root))
        if self.path is not None:
            return registry_dir(self.path)
        return Path(os.path.realpath(os.getcwd()))

    def reserve_id(self, spdx_id: str) -> None:
        """Never mint *spdx_id*: when it is ``<namespace>#<prefix>-<n>`` in
        this registry's namespace (:func:`~pitloom.id_registry._counters.id_number`),
        raise the prefix's counter to *n*. Any other id is ignored."""
        found = id_number(self.namespace, spdx_id)
        if found is not None and found[1] > self.id_counters.get(found[0], 0):
            self.id_counters[found[0]] = found[1]

    def _reserve_held(self) -> None:
        """:meth:`reserve_id` every id the table holds, so one that leaves it
        is never minted again, even when set without a mint."""
        for entry in self.elements.values():
            self.reserve_id(entry.spdx_id)

    def _mint_id(self, prefix: str) -> str:
        """Mint the next ``#<prefix>-<n>`` id in this registry's namespace:
        one above the prefix's counter and every held id, never an id issued
        before (I8). Raises ``ValueError`` past
        :data:`~pitloom.id_registry._counters.MAX_ID_NUMBER`.

        *prefix* is raw: ``loom id generate -e NAME:TYPE`` derives it from a
        user-given TYPE, so it passes through :func:`iri_segment` too.
        """
        prefix = iri_segment(prefix)
        self._reserve_held()
        number = self.id_counters.get(prefix, 0) + 1
        if number > MAX_ID_NUMBER:
            raise ValueError(
                f"ID registry: no {prefix} id left to mint in {self.namespace}"
            )
        self.id_counters[prefix] = number
        return f"{self.namespace}#{prefix}-{number}"

    def register(self, type_name: str, name: str, *, sha256: str | None = None) -> str:
        """Register *name* under *type_name* and return its ``spdxId``.

        No entry: mint (prefix :func:`type_id_prefix`) and store *sha256*.
        An entry and no *sha256*, or an equal one: reuse it unchanged, so an
        ungated registration never erases a recorded hash. A *sha256* that
        differs from the entry's, or an entry with none: log ``content
        changed``, mint a new id and replace the entry.
        """
        key = _element_key(type_name=type_name, name=name)
        given = sha256.lower() if sha256 is not None else None
        existing = self.elements.get(key)
        if existing is not None:
            if given is None or existing.sha256 == given:
                return existing.spdx_id
            log.info(
                "ID registry: content changed for %s; minting a new spdxId (old: %s).",
                name,
                existing.spdx_id,
            )
        spdx_id = self._mint_id(type_id_prefix(type_name))
        self.elements[key] = RegistryEntry(spdx_id=spdx_id, sha256=given)
        return spdx_id

    def generate(
        self, paths: list[Path], project_root: Path, *, exclude: Path | None = None
    ) -> None:
        """(Re-)index files under *paths* into this registry, except the
        *exclude* file (the declared registry itself).

        Each file is registered as ``(software_File, rel_path, sha256)``. A
        file a project scan lists as an AI model also registers its stem as
        an ``ai_AIPackage`` with the file's hash, so a retrained model (other
        bytes) gets a new id. A stem shared by several model files is
        registered with no hash (:meth:`register` given none): no one file
        stands for it, and a hash gate would re-mint on every run. An
        existing entry is left as is, a recorded hash included (D12), so a
        fresh registry and one with history can differ for that stem.
        """
        # pylint: disable=import-outside-toplevel,cyclic-import
        from pitloom.extract.ai_model import AiModelFormat, detect_ai_model_format
        from pitloom.extract.scanner import is_model_candidate_name

        models: dict[str, list[str]] = {}
        for file_path in _iter_files(paths, project_root, exclude):
            try:
                sha256 = sha256_file(file_path)
            except OSError as exc:
                log.warning("ID registry: could not read %s: %s", file_path, exc)
                continue
            rel_path = file_path.relative_to(project_root).as_posix()
            self.register(FILE_TYPE, rel_path, sha256=sha256)

            # The scan's rule (suffix filter, then header), so a model is
            # registered for the files a scan lists as models, and only those.
            if (
                is_model_candidate_name(file_path.name)
                and detect_ai_model_format(file_path) != AiModelFormat.UNKNOWN
            ):
                models.setdefault(file_path.stem, []).append(sha256)
        for stem, hashes in models.items():
            if len(hashes) == 1:
                self.register(AI_PACKAGE_TYPE, stem, sha256=hashes[0])
                continue
            log.info(
                "ID registry: %d model files share the name %s; "
                "its entry is left as is",
                len(hashes),
                stem,
            )
            self.register(AI_PACKAGE_TYPE, stem)

    def import_sbom(self, sbom_path: Path) -> frozenset[tuple[str, str]]:
        """Harvest ids from an existing SPDX 3 JSON-LD SBOM into this registry.

        Returns the keys not imported because the SBOM holds several
        elements under one key (see
        :func:`~pitloom.id_registry._ambiguous._ambiguous_keys`). An empty
        registry adopts the SBOM's document id as its namespace when that
        is a namespace IRI (:func:`~pitloom.core.iri.require_namespace_iri`);
        otherwise it keeps its own, with one ``WARNING:``. The imported id
        wins, even over a content-gated entry (``imported=True`` in
        :func:`~pitloom.id_registry._harvest._import_sbom_element`).
        """
        object_set = spdx3.SHACLObjectSet()
        with open(sbom_path, "rb") as f:
            spdx3.JSONLDDeserializer().read(f, object_set)

        sorted_objects = _sorted_by_spdx_id(object_set)
        self._reserve_held()

        if not self.elements:
            document = next(
                (o for o in sorted_objects if isinstance(o, spdx3.SpdxDocument)),
                None,
            )
            if document is not None and document.spdxId:
                self._adopt_namespace(str(document.spdxId))

        return _harvest_elements(self, sorted_objects, imported=True)

    def _adopt_namespace(self, namespace: str) -> None:
        """Take *namespace* as this registry's, if it can be one."""
        try:
            self.namespace = require_namespace_iri(namespace)
        except ValueError as exc:
            log.warning(
                "ID registry: not adopting the namespace %r: %s; keeping %s",
                namespace,
                exc,
                self.namespace,
            )

    def harvest(self, object_set: spdx3.SHACLObjectSet) -> tuple[int, bool]:
        """Harvest every named element in *object_set* into this registry.

        Used both by :meth:`import_sbom` and by SBOM generation itself,
        directly on a :class:`~pitloom.export.spdx3_json.Spdx3JsonExporter`'s
        in-memory object set.

        Returns ``(new_ids, changed)``: *new_ids* counts the distinct
        spdxIds the registry did not hold before, under keys it did not hold
        either (an id replacing a key's entry is an update, not an
        addition); *changed* says whether anything changed at all, an id
        counter included, and is what a caller gates a ``save()`` on --
        releasing a stale key while another claims its id changes the
        content without adding an id.
        """
        return self._harvest_sorted(_sorted_by_spdx_id(object_set))

    def _harvest_sorted(self, sorted_objects: list[Any]) -> tuple[int, bool]:
        """Harvest *sorted_objects* (see
        :func:`~pitloom.id_registry._harvest._sorted_by_spdx_id`)."""
        self._reserve_held()
        before, counters = dict(self.elements), dict(self.id_counters)
        _harvest_elements(self, sorted_objects, imported=False)
        changed = self.elements != before or self.id_counters != counters
        return added_ids(before, self.elements), changed

    def save(self, path: Path | None = None) -> None:
        """Write this registry as JSON to *path* (default: :attr:`path`).

        With no :attr:`project_root` yet, the registry file's directory
        becomes the project root. Raises ``ValueError`` when there is no
        path, or when the project root cannot be stored relative to it.
        """
        target = path or self.path
        if target is None:
            raise ValueError("No path given and registry has no default path")
        root = (
            self.project_root if self.project_root is not None else registry_dir(target)
        )
        self._reserve_held()
        write_registry_file(
            target, self.namespace, self.elements, root, self.id_counters
        )
        self.path = target
        self.project_root = root
        self._on_disk = dict(self.elements)
