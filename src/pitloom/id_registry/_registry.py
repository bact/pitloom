# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``IdRegistry``: a Loom ID registry, one table keyed by ``(type, name)``.

See also: :mod:`pitloom.id_registry._types` for ``RegistryEntry`` and file
traversal, :mod:`pitloom.id_registry._format` for the file format,
:mod:`pitloom.id_registry._counters` for the id counters,
:mod:`pitloom.id_registry._generate` for indexing a project's files,
:mod:`pitloom.id_registry._persist` for rebasing and replaying changes,
:mod:`pitloom.id_registry._harvest` for SBOM-element harvest helpers,
:mod:`pitloom.id_registry._sbom_read` for reading an SBOM to import,
:mod:`pitloom.id_registry.resolve` for registry resolution.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.iri import doc_namespace, iri_segment, require_namespace_iri
from pitloom.core.walk_rules import same_path
from pitloom.id_registry._ambiguous import RecordedKeys
from pitloom.id_registry._counters import (
    MAX_ID_NUMBER,
    RESERVE_CEILING,
    Counters,
    id_number,
    merge_counters,
)
from pitloom.id_registry._format import (
    read_registry_file,
    registry_dir,
    write_registry_file,
)
from pitloom.id_registry._generate import index_files
from pitloom.id_registry._harvest import _harvest_elements, _sorted_by_spdx_id
from pitloom.id_registry._persist import (
    Rebase,
    added_ids,
    new_id_count,
    replay_changes,
)
from pitloom.id_registry._sbom_read import document_id, read_sbom_objects
from pitloom.id_registry._types import (
    DATASET_PACKAGE_TYPE,
    RegistryEntry,
    _element_key,
    _require_names,
    is_utf8_text,
    registry_file_error,
    type_id_prefix,
    unencodable_message,
)
from pitloom.id_registry.import_keys import (
    DATASET_PIN_GATED_INFO,
    import_keys,
    report_imported,
)
from pitloom.logging_config import loggable

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
        # The table and namespace as last read from or written to `path`:
        # what `rebase` tells this object's own changes apart by. None:
        # neither yet.
        self._on_disk: dict[tuple[str, str], RegistryEntry] | None = None
        self._on_disk_namespace: str | None = None
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
        :func:`~pitloom.id_registry._types.registry_file_error`; it never
        returns ``None``. Whether a registry exists at all is decided
        upstream, by :func:`~pitloom.id_registry.resolve.resolve_registry`.

        Raises:
            TypeError: *path* is not a ``str`` or ``os.PathLike`` (bytes
                included): a wrong argument, not a bad file.
        """
        if not isinstance(path, (str, os.PathLike)):
            raise TypeError(
                "ID registry file path must be a str or os.PathLike, "
                f"not {type(path).__name__}"
            )
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
        registry._on_disk_namespace = contents.namespace
        return registry

    def rebase(self) -> Rebase:
        """Re-read :attr:`path` and apply this object's own changes again on
        top (:func:`~pitloom.id_registry._persist.replay_changes`), so a
        save keeps what another run saved meanwhile.

        A change is a key whose entry differs from the table this object
        last read or wrote; for one that has read or written none, every
        entry is. The project root becomes the file's, and so does the
        namespace, unless this object changed the one it read (``id
        import`` adopting an SBOM's) and the file still has that one. The
        id counters merge by maximum, so neither run lowers one. With no
        file at :attr:`path` yet, the registry is left as it is.

        Raises:
            ValueError: the file cannot be loaded.
        """
        base = self._on_disk or {}
        if self.path is None or (
            self._on_disk is None and not os.path.exists(self.path)
        ):
            return Rebase(
                refused=0, pending=True, added=new_id_count(self.elements, base)
            )
        contents = read_registry_file(self.path)
        merged, refused = replay_changes(base, self.elements, contents.elements)
        self.elements.clear()
        self.elements.update(merged)
        if contents.namespace != self._on_disk_namespace or (
            self.namespace == self._on_disk_namespace
        ):
            self.namespace = contents.namespace
        self.project_root = contents.project_root
        self.id_counters = merge_counters(self.id_counters, contents.id_counters)
        self._reserve_held()
        self._on_disk = contents.elements
        self._on_disk_namespace = contents.namespace
        return Rebase(
            refused=refused,
            pending=merged != contents.elements
            or self.id_counters != contents.id_counters
            or self.namespace != contents.namespace,
            added=new_id_count(merged, base, contents.elements),
        )

    def get(self, type_name: str, name: str) -> RegistryEntry | None:
        """Return the entry for *name* under *type_name*, or ``None``."""
        return self.elements.get(_element_key(type_name=type_name, name=name))

    def lookup(
        self,
        type_name: str,
        names: Sequence[str],
        *,
        sha256: str | None = None,
        pin_without_hash: bool = False,
        miss_hashed: bool = False,
    ) -> str | None:
        """Return the ``spdxId`` of the first of *names* registered under
        *type_name*, or ``None``.

        With *sha256*, an entry recording the same SHA-256 (any case) is a
        hit; an entry with no hash is one only with *pin_without_hash* (an
        explicit pin, held for any content), so then only an entry
        recording another hash misses. Without *sha256*, the entry's hash is
        ignored (with *miss_hashed*, a hashed entry misses: no content vouches
        for it), and so is *pin_without_hash*. The first of *names* to hit wins."""
        _require_names(names)
        wanted = sha256.lower() if sha256 is not None else None
        for name in names:
            entry = self.get(type_name, name)
            if entry is None:
                continue
            if wanted is None:
                if miss_hashed and entry.sha256 is not None:
                    continue
                return entry.spdx_id
            if entry.sha256 == wanted or (pin_without_hash and entry.sha256 is None):
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
        """Return the number of distinct spdxIds."""
        return len({entry.spdx_id for entry in self.elements.values()})

    def root_dir(self) -> Path:
        """Return the project root, else the registry file's directory,
        else the current directory -- realpath'd (``OSError`` when that
        directory was deleted)."""
        if self.project_root is not None:
            return Path(os.path.realpath(self.project_root))
        if self.path is not None:
            return registry_dir(self.path)
        return Path(os.path.realpath(os.getcwd()))

    def promote_alias(self, type_name: str, old_key: str, new_key: str) -> bool:
        """Re-key the entry of *old_key* under *type_name* as *new_key*, its
        ``spdxId`` and SHA-256 kept (no mint, no counter); ``False`` and no
        change when *old_key* is not held, *new_key* is, or is not UTF-8."""
        old = _element_key(type_name=type_name, name=old_key)
        new = _element_key(type_name=type_name, name=new_key)
        if old not in self.elements or new in self.elements:
            return False
        if not is_utf8_text(new[1]):
            return False
        self.elements[new] = self.elements.pop(old)
        return True

    def reserve_id(self, spdx_id: str) -> None:
        """Never mint *spdx_id*: when it is ``<namespace>#<prefix>-<n>`` in
        this registry's namespace (:func:`~pitloom.id_registry._counters.id_number`),
        raise the prefix's counter to *n*. Any other id is ignored, and so
        is an *n* above
        :data:`~pitloom.id_registry._counters.RESERVE_CEILING`: an SBOM
        could otherwise use up every number. :meth:`_mint_id` skips such an
        id while the table holds it."""
        found = id_number(self.namespace, spdx_id)
        if (
            found is not None
            and self.id_counters.get(found[0], 0) < found[1] <= RESERVE_CEILING
        ):
            self.id_counters[found[0]] = found[1]

    def _reserve_held(self) -> None:
        """:meth:`reserve_id` every id the table holds, so one that leaves it
        is never minted again, even when set without a mint."""
        for entry in self.elements.values():
            self.reserve_id(entry.spdx_id)

    def _mint_id(self, prefix: str) -> str:
        """Mint the next ``#<prefix>-<n>`` id in this registry's namespace:
        one above the prefix's counter and every held id, never an id issued
        before. Raises ``ValueError`` for an empty *prefix*, and past
        :data:`~pitloom.id_registry._counters.MAX_ID_NUMBER`.

        *prefix* is raw: the library's :meth:`register` takes any compact
        type, so it passes through :func:`iri_segment` too.
        """
        if not prefix:
            raise ValueError("ID registry: no id prefix for an empty type name")
        prefix = iri_segment(prefix)
        self._reserve_held()
        held = {entry.spdx_id for entry in self.elements.values()}
        number = self.id_counters.get(prefix, 0) + 1
        while f"{self.namespace}#{prefix}-{number}" in held:
            number += 1  # a held id above RESERVE_CEILING
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
        ungated registration never erases a recorded hash. A dataset
        package pin with no hash given one: keep its id, record *sha256*
        (gated from now on), one ``INFO:``. A *sha256* that differs from
        the entry's, or (any other type) an entry with none: log ``content
        changed``, mint a new id and replace the entry.

        Raises:
            ValueError: *type_name* or *name* cannot be encoded as UTF-8
                (the file could never be saved).
        """
        for label, text in (("type name", type_name), ("name", name)):
            if not is_utf8_text(text):
                raise ValueError(unencodable_message(label, text))
        key = _element_key(type_name=type_name, name=name)
        given = sha256.lower() if sha256 is not None else None
        existing = self.elements.get(key)
        if existing is not None:
            if given is None or existing.sha256 == given:
                return existing.spdx_id
            if existing.sha256 is None and type_name == DATASET_PACKAGE_TYPE:
                log.info(DATASET_PIN_GATED_INFO, loggable(name))
                self.elements[key] = RegistryEntry(existing.spdx_id, given)
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
        self,
        paths: list[Path],
        project_root: Path,
        *,
        exclude: Path | None = None,
        explicit: bool = True,
    ) -> None:
        """(Re-)index files under *paths* into this registry, except the
        *exclude* file (the declared registry itself).

        Each file is registered as ``(software_File, path key, sha256)``
        (:func:`~pitloom.id_registry.keys.join_key` of the project's
        :func:`~pitloom.id_registry.keys.project_prefix` and the file's path
        from *project_root*). A file a project scan lists as an AI model
        also registers an ``ai_AIPackage`` under the same key and hash, so
        a retrained model (other bytes) gets a new id. A key new or held
        with other content whose one layout alias
        (:func:`~pitloom.id_registry.keys.alias_tail`) is a held key of the
        same type and hash takes over that entry, its id kept
        (:meth:`promote_alias`). Promotion is one way, from the shorter key
        to the longer; it is skipped when the shorter key is another walked
        file's or names a file or directory below the root. Files whose
        keys are equal once NFC-normalised are all left out, one ``WARNING:``.

        A path in *paths* that cannot be read or listed is a ``ValueError``
        naming it; with *explicit* false (default roots the caller chose,
        not the user) it is a ``WARNING:`` and the path is left out.
        """
        index_files(self, paths, project_root, exclude, explicit=explicit)

    def import_sbom(self, sbom_path: Path) -> frozenset[tuple[str, str]]:
        """Harvest ids from an existing SPDX 3 JSON-LD SBOM into this registry.

        Returns the keys not imported because the SBOM holds several
        elements under one key
        (:func:`~pitloom.id_registry._ambiguous._ambiguous_keys`). An empty
        registry adopts the SBOM's document id as its namespace when that
        is a namespace IRI, else keeps its own, one ``WARNING:``. The
        imported id wins, even over a content-gated entry. A file, a
        dataset package and a model are written under the key a run looks
        them up by (:func:`~pitloom.id_registry.import_keys.import_keys`,
        whose ``INFO:`` lines are logged for the elements written), any
        other element under its name; none moves an id another key of its
        type holds.
        """
        sorted_objects = read_sbom_objects(sbom_path)
        self._reserve_held()
        if not self.elements:
            namespace = document_id(sorted_objects)
            if namespace is not None:
                self._adopt_namespace(namespace)
        plan = import_keys(self, sorted_objects)
        skipped = _harvest_elements(self, sorted_objects, imported=True, keys=plan.keys)
        report_imported(self, plan)
        return skipped

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

    def harvest(
        self,
        object_set: spdx3.SHACLObjectSet,
        keys: RecordedKeys | None = None,
    ) -> tuple[int, bool]:
        """A run's auto-harvest: every named element in *object_set*, each
        under the key *keys* (spdxId -> (compact type, key), what the run's
        lookups recorded) holds for it when of its type, else its type and
        name (see :func:`~pitloom.id_registry._harvest._harvest_elements`).

        Returns ``(new_ids, changed)``: *new_ids* counts the distinct
        spdxIds new to the registry under keys new to it too (a replaced or
        moved id is an update); *changed* says whether anything changed, an
        id counter included: what a caller gates a ``save()`` on.
        """
        self._reserve_held()
        before, counters = dict(self.elements), dict(self.id_counters)
        _harvest_elements(
            self, _sorted_by_spdx_id(object_set), imported=False, keys=keys
        )
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
        self._on_disk_namespace = self.namespace
