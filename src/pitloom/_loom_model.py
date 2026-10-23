# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A loom model: declared during the run, resolved at its exit.

``set_model``/``use_model`` only record a declaration: the ``ai_AIPackage``
with a provisional id, its provenance, and ``path=`` made absolute. The
provenance is written at the call, so its annotations are numbered as the
calls happen; only their subject is bound at exit.

:meth:`LoomModels.resolve` runs in ``finalize()`` only, so a raising ``with``
block hashes, looks up and records nothing. A ``path=`` that is a regular
file is hashed, and the model is looked up gated by that hash. The key is
the file's path from the registry's project root
(:func:`~pitloom.id_registry.artifact_key`), so a renamed model or a
shared file stem keeps or gets its own id; the element's name stays the
declared one. A ``src/``/``lib/`` path also hits the held key of its
installed path with that hash (``CANONICAL`` layout alias: a wheel
minted it); the hit registers nothing. A file outside the root is keyed
by the name (one ``INFO:``, once per model, :data:`NAME_KEY_INFO`). A miss
is registered when the registry has a file and ``update-id-registry`` is
not false; :meth:`LoomModels.persist` saves it after the fragment is written.
Without a usable ``path=`` (none, not a file at exit, unreadable), the
model is looked up by name only, an entry recording a SHA-256 is a miss (no
content vouches for it), and nothing is registered.

See also: :mod:`pitloom._loom_active_run` (the run),
:mod:`pitloom._loom_dataset` (datasets) and
:mod:`pitloom.id_registry._persist` (the save).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_caller import (
    LOOM_PROVENANCE_CONFIG,
    _record_hyperparameter_provenance,
    registry_miss_callback,
    warn_registry_miss,
)
from pitloom._loom_dataset import name_key_reason
from pitloom.assemble.spdx3.provenance import emit_provenance
from pitloom.core.file_hash import HexDigests, file_digests
from pitloom.core.models import generate_spdx_id
from pitloom.core.path_probe import (
    UNREADABLE_FILE_WARNING,
    is_missing_errno,
    is_regular_file,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter, file_hashes
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    Alias,
    IdRegistry,
    IdRegistrySession,
    LookupKey,
    artifact_key,
    persist_registry,
    warn_no_registry_path,
)
from pitloom.logging_config import loggable, one_line

log = logging.getLogger("pitloom.loom")

__all__ = ["NAME_KEY_INFO", "NOT_A_FILE_WARNING", "NO_PATH_WARNING", "LoomModels"]

#: ``log.warning()`` format for a model declared without ``path=`` while a
#: registry is loaded. Argument: the model's name.
NO_PATH_WARNING = "loom: model %r has no path=; not hashed, looked up by name only"
#: ``log.warning()`` format for a ``path=`` that is not a regular file at
#: run exit. Arguments: the model's name, the path as given.
NOT_A_FILE_WARNING = (
    "loom: model %r: %s is not a file at exit; not hashed, looked up by name only"
)
#: ``log.info()`` format for a hashed model keyed by its name, its file
#: outside the registry's project root (or gone since it was hashed), once
#: per model per run. Arguments: the model's name, why
#: (:func:`~pitloom._loom_dataset.name_key_reason`).
NAME_KEY_INFO = "ID registry: model %s keyed by its name: %s"
#: The provisional spdxId of a declared model, numbered per run; replaced
#: at exit, before anything is written.
_PENDING_ID = "urn:pitloom:loom:pending-model-"


@dataclass
class _Declaration:
    """One ``set_model``/``use_model`` call."""

    name: str
    element: spdx3.ai_AIPackage
    generated: bool | None
    #: Absolute, as at the call; ``None``: no ``path=``.
    path: str | None
    #: As the caller gave it, for messages.
    given: str
    annotations: list[spdx3.Annotation] = field(default_factory=list)


def _warn_unreadable(given: str, exc: Exception) -> None:
    log.warning(
        UNREADABLE_FILE_WARNING, loggable(given), "for the model hash", one_line(exc)
    )


def _hash_model_file(name: str, path: str, given: str) -> HexDigests | None:
    """The SHA-256 and SHA-512 of the model file at *path* (one read), or
    ``None`` and one ``WARNING:`` when it is not a regular file at exit
    (gone included) or cannot be read. Read whole in chunks: no ceiling
    applies to a model."""
    try:
        if is_regular_file(Path(path)):
            return file_digests(path).hex()
    except ValueError as exc:  # a NUL: a name, not a path
        _warn_unreadable(given, exc)
        return None
    except OSError as exc:
        if not is_missing_errno(exc):
            _warn_unreadable(given, exc)
            return None
    log.warning(NOT_A_FILE_WARNING, name, loggable(given))
    return None


def _dictionary(hyperparameters: dict[str, str]) -> list[spdx3.DictionaryEntry]:
    """*hyperparameters* as ``ai_hyperparameter`` entries, in key order."""
    return [
        spdx3.DictionaryEntry(key=k, value=v)
        for k, v in sorted(hyperparameters.items())
    ]


class LoomModels:
    """The model declarations of one loom run, resolved at its exit."""

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        *,
        session: IdRegistrySession,
        exporter: Spdx3JsonExporter,
        creation_info: spdx3.CreationInfo,
        doc_uuid: str,
        update_id_registry: bool,
    ) -> None:
        self._session = session
        self._exporter = exporter
        self._creation_info = creation_info
        self._doc_uuid = doc_uuid
        self._update = update_id_registry
        self._declared: list[_Declaration] = []
        #: Ids registered by this run (``None``: a claim collision).
        self._recorded: list[str | None] = []
        #: (name, path) of the models said to be keyed by their name.
        self._name_keyed: set[tuple[str, str]] = set()

    # pylint: disable-next=too-many-arguments
    def declare(
        self,
        name: str,
        *,
        model_type: str | None,
        hyperparameters: dict[str, str] | None,
        generated: bool | None,
        path: str | os.PathLike[str] | None,
        caller_info: str,
    ) -> None:
        """Record a model declaration and write its provenance now."""
        element = spdx3.ai_AIPackage(
            spdxId=f"{_PENDING_ID}{len(self._declared) + 1}",
            name=name,
            creationInfo=self._creation_info,
        )
        if model_type is not None:
            element.ai_typeOfModel = [model_type]
        provenance: dict[str, str] = {"package": caller_info}
        if hyperparameters is not None:
            element.ai_hyperparameter = _dictionary(hyperparameters)
            _record_hyperparameter_provenance(provenance, hyperparameters, caller_info)
        declared = _Declaration(
            name=name,
            element=element,
            generated=generated,
            path=None if path is None else os.path.join(os.getcwd(), os.fspath(path)),
            given="" if path is None else os.fspath(path),
        )
        self._declared.append(declared)
        self._annotate(declared, provenance, name)

    def set_hyperparameters(
        self, hyperparameters: dict[str, str], caller_info: str
    ) -> None:
        """Replace the last declared model's hyperparameters, with their
        provenance."""
        if not self._declared:
            raise RuntimeError(
                "No model set. Call set_model() before set_model_hyperparameters()."
            )
        declared = self._declared[-1]
        declared.element.ai_hyperparameter = _dictionary(hyperparameters)
        provenance: dict[str, str] = {}
        _record_hyperparameter_provenance(provenance, hyperparameters, caller_info)
        self._annotate(declared, provenance, declared.name or "model")

    def _annotate(
        self, declared: _Declaration, provenance: dict[str, str], doc_name: str
    ) -> None:
        annotation = emit_provenance(
            subject=declared.element,
            provenance=provenance,
            creation_info=self._creation_info,
            doc_name=doc_name,
            doc_uuid=self._doc_uuid,
            exporter=self._exporter,
            provenance_config=LOOM_PROVENANCE_CONFIG,
        )
        if annotation is not None:
            declared.annotations.append(annotation)

    def resolve(self) -> tuple[spdx3.ai_AIPackage | None, bool | None]:
        """Resolve every declaration in order and add it to the document.

        Every ``path=`` is hashed first; then, when one was, the registry
        file is re-read, so an id another run saved meanwhile is reused,
        not minted again. Returns the last declaration's element and
        ``generated`` flag (the run's model), or ``(None, None)``.
        """
        found: dict[str, HexDigests] = {}
        digests = [self._digest(declared, found) for declared in self._declared]
        if found:
            self._refresh()
        for declared, digest in zip(self._declared, digests, strict=True):
            element = declared.element
            element.spdxId = self._spdx_id(
                declared, None if digest is None else digest.sha256
            )
            if digest is not None:
                element.verifiedUsing = file_hashes(digest)
            for annotation in declared.annotations:
                annotation.subject = element.spdxId
            self._exporter.add_package(element)
        if not self._declared:
            return None, None
        return self._declared[-1].element, self._declared[-1].generated

    def persist(self) -> None:
        """Save the ids this run registered
        (:func:`~pitloom.id_registry.persist_registry`); call it after the
        fragment is written."""
        registry = self._session.registry
        if registry is not None and self._recorded:
            # Two files outside the root sharing a name replace one entry.
            held = {entry.spdx_id for entry in registry.elements.values()}
            persist_registry(registry, len(held.intersection(self._recorded)), True)

    def _digest(
        self, declared: _Declaration, found: dict[str, HexDigests]
    ) -> HexDigests | None:
        """*declared*'s ``path=`` digests, each path read once (*found*)."""
        if declared.path is None:
            if self._session.registry is not None:
                log.warning(NO_PATH_WARNING, declared.name)
            return None
        if declared.path not in found:
            digest = _hash_model_file(declared.name, declared.path, declared.given)
            if digest is None:
                return None
            found[declared.path] = digest
        return found[declared.path]

    def _refresh(self) -> None:
        """Re-read the registry file when this run may write it; a failure
        is left for :meth:`persist`'s save to report."""
        registry = self._session.registry
        if registry is None or registry.path is None or not self._update:
            return
        try:
            registry.rebase()
        except (OSError, ValueError) as exc:
            log.debug("ID registry: not re-read before resolving models: %s", exc)

    def _spdx_id(self, declared: _Declaration, digest: str | None) -> str:
        """The model's id: from the registry (gated by *digest* when there
        is one), else registered on a gated miss, else minted."""
        session, name = self._session, declared.name
        registry = session.registry
        if registry is None or digest is None:
            lookup = LookupKey(name)
        else:
            lookup = artifact_key(
                registry, path=declared.path, name=name, alias=Alias.CANONICAL
            )
            if not lookup.path:
                self._info_name_key(declared)
        if digest is None:
            on_miss = registry_miss_callback(
                session, AI_PACKAGE_TYPE, name, unhashed=True
            )
            registered = session.lookup_key(
                name, AI_PACKAGE_TYPE, lookup, miss_hashed=True, on_miss=on_miss
            )
        else:
            missed: list[bool] = []
            registered = session.lookup_key(
                name,
                AI_PACKAGE_TYPE,
                lookup,
                sha256=digest,
                on_miss=lambda: missed.append(True),
            )
            if registry is not None and missed:
                registered = self._record(registry, name, lookup, digest)
        return registered or generate_spdx_id("AIPackage", name, self._doc_uuid)

    def _info_name_key(self, declared: _Declaration) -> None:
        """The one ``INFO:`` (:data:`NAME_KEY_INFO`) for a hashed model
        keyed by its name, once per name and path."""
        path = cast(str, declared.path)  # hashed: a path= was given
        if (declared.name, path) not in self._name_keyed:
            self._name_keyed.add((declared.name, path))
            log.info(NAME_KEY_INFO, loggable(declared.name), name_key_reason(path))

    def _record(
        self, registry: IdRegistry, name: str, lookup: LookupKey, digest: str
    ) -> str | None:
        """Register *lookup*'s key after a gated miss, or say why not and
        return ``None`` (the caller mints)."""
        if not self._update:
            warn_registry_miss(
                registry, AI_PACKAGE_TYPE, lookup.key, by_path=lookup.path
            )
            return None
        if registry.path is None:
            warn_no_registry_path()
            return None
        session = self._session
        spdx_id = session.register_id(name, AI_PACKAGE_TYPE, lookup.key, sha256=digest)
        if spdx_id is not None:
            session.record_key(spdx_id, AI_PACKAGE_TYPE, lookup.key)
        self._recorded.append(spdx_id)
        return spdx_id
