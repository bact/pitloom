# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials.

See Also:
    :mod:`pitloom.core._models_wheel` for wheel file scanning and header parsing.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4, uuid5

from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core._models_wheel import _resolve_file_header_extras, get_wheel_files
from pitloom.core._models_wheel_types import FileHeaderExtras
from pitloom.core.iri import doc_namespace, iri_segment
from pitloom.core.requirements import normalize_dependency_specifier

if TYPE_CHECKING:
    from pathlib import PurePath

    from pitloom.core.project import ProjectFile

# Fixed pitloom namespace UUID, stable across all versions.
# Derived from: uuid5(NAMESPACE_URL, "https://github.com/bact/pitloom")
# DO NOT CHANGE: it determines every generated SBOM document UUID.
PITLOOM_NS = UUID("aecb050b-c1a4-5c3f-aaa7-d8e12dee7e5b")

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 ...
#              (uuid, "Relationship")     -> 1, 2, 3 ...
_ID_COUNTERS: dict[tuple[str, str], int] = {}

# Numbers a caller has reserved per (doc_uuid, prefix) -- see
# reserve_spdx_ids() -- because an IdRegistry already assigned them within
# this same document's namespace. generate_spdx_id() skips any reserved
# number instead of re-minting it, so a registry-supplied id merged into
# this document can never collide with a freshly-minted one.
_RESERVED: dict[tuple[str, str], set[int]] = {}

__all__ = [
    "PITLOOM_NS",
    "FileHeaderExtras",
    "_ID_COUNTERS",
    "_build_merkle_tree",
    "_clear_doc_counters",
    "_resolve_file_header_extras",
    "archive_base_name",
    "build_pypi_purl",
    "build_relationship",
    "compute_doc_uuid",
    "generate_spdx_id",
    "get_wheel_files",
    "merkle_root",
    "merkle_root_of_files",
    "reserve_spdx_ids",
]


def build_pypi_purl(name: str, version: str | None) -> str:
    """Return a canonical ``pkg:pypi/<name>[@<version>]`` Package URL."""
    base = f"pkg:pypi/{canonicalize_name(name)}"
    if version and version != "unknown":
        return f"{base}@{version.replace('+', '%2B')}"
    return base


def _clear_doc_counters(doc_uuid: str) -> None:
    """Remove all ``_ID_COUNTERS``/``_RESERVED`` entries for *doc_uuid*."""
    for key in list(_ID_COUNTERS):
        if key[0] == doc_uuid:
            del _ID_COUNTERS[key]
    for key in list(_RESERVED):
        if key[0] == doc_uuid:
            del _RESERVED[key]


def _build_merkle_tree(leaf_hashes: list[bytes]) -> str:
    """Build a binary Merkle tree from *leaf_hashes* and return the root as hex."""
    nodes: list[bytes] = list(leaf_hashes)
    while len(nodes) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                combined = hashlib.sha256(nodes[i] + nodes[i + 1]).digest()
            else:
                combined = nodes[i]  # unpaired: promote unchanged
            next_level.append(combined)
        nodes = next_level
    return nodes[0].hex()


def merkle_root(leaves: Sequence[bytes]) -> str:
    """The hex root of the binary Merkle tree over *leaves*, in the order
    given: a pair hashes to ``sha256(left + right)``, an unpaired node is
    promoted unchanged, so one leaf is its own root.

    The one tree algorithm for a package and a dataset directory; the
    caller orders the leaves and decides what a leaf holds.

    Raises:
        ValueError: *leaves* is empty (there is no root to give).
    """
    if not leaves:
        raise ValueError("merkle_root() needs at least one leaf")
    return _build_merkle_tree(list(leaves))


def merkle_root_of_files(files: Iterable[ProjectFile]) -> str | None:
    """The package Merkle root of *files*, or ``None`` for no files.

    Files sorted by ``distribution_path``; a leaf is a file's raw SHA-256
    digest. A wheel's root is taken over its payload (see
    :func:`pitloom.extract.wheel.payload_files`). :func:`get_wheel_files`
    hashes the source files the build backend selects, so its root equals a
    built wheel's only while the build adds no payload of its own (shared
    data, scripts, generated or repaired files). Every file must carry a
    ``digest_sha256``.
    """
    ordered = sorted(files, key=lambda f: f.distribution_path)
    if not ordered:
        return None
    return merkle_root([bytes.fromhex(cast(str, f.digest_sha256)) for f in ordered])


_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?")


def _normalize_dep(dep: str) -> str:
    """*dep* as the SBOM shows it
    (:func:`~pitloom.core.requirements.normalize_dependency_specifier`),
    so every route's spelling seeds alike; a string that is not PEP 508
    with only its leading name normalised."""
    dep = normalize_dependency_specifier(dep.strip(), quiet=True)
    match = _DEP_NAME_RE.match(dep)
    if not match:
        return dep
    normalized_name = re.sub(r"[-_.]+", "-", match.group(0)).lower()
    return normalized_name + dep[match.end() :]


def archive_base_name(path: PurePath | str) -> str:
    """The last component of *path*, split at ``/`` and ``\\`` on every OS,
    unchanged otherwise (no case folding): one wheel file name seeds the same
    ids wherever it was read."""
    return re.split(r"[\\/]", str(path))[-1]


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def compute_doc_uuid(
    name: str,
    version: str,
    dependencies: list[str],
    # pylint: disable-next=redefined-outer-name
    merkle_root: str | None = None,
    locked_dependencies: list[str] | None = None,
    locked_dependencies_provenance: str | None = None,
    identity_seed: str | None = None,
) -> str:
    """Compute a deterministic UUIDv5 for the SPDX document.

    *identity_seed* is folded in last when given (a wheel of unknown identity:
    its base file name), so two such wheels with one payload differ. ``None``
    leaves the seed unchanged.

    *locked_dependencies* (e.g. ``poetry.lock``-resolved transitive
    dependencies) and *locked_dependencies_provenance* (the resolved
    ``ProjectMetadata.provenance["locked_dependencies"]`` string, e.g.
    ``"Source: pylock.toml | Method: resolved_lockfile"``) are folded in when
    either is given, so documents with equal direct dependencies but different
    lock-resolved graphs, or different lock sources, get different UUIDs. The
    gate is "either given", not "*locked_dependencies* non-empty": a real
    lock that resolves to zero dependencies still differs, by its provenance,
    from no lock. With both omitted the seed is that of a document without
    locked dependencies.
    """
    normalized_deps = sorted(_normalize_dep(dep) for dep in dependencies)
    seed = "\x00".join([name, version, "\x00".join(normalized_deps)])
    if locked_dependencies or locked_dependencies_provenance:
        # Either argument: a lock with no dependencies still has a provenance.
        normalized_locked = sorted(
            _normalize_dep(dep) for dep in (locked_dependencies or [])
        )
        seed += "\x00" + "\x00".join(normalized_locked)
        if locked_dependencies_provenance:
            seed += "\x00" + locked_dependencies_provenance
    if merkle_root is not None:
        seed += "\x00" + merkle_root
    if identity_seed is not None:
        seed += "\x00identity-seed\x00" + identity_seed
    return str(uuid5(PITLOOM_NS, seed))


def generate_spdx_id(
    prefix: str, doc_name: str = "pitloom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices.

    *prefix* and *doc_name* are raw names: both pass through
    :func:`~pitloom.core.iri.iri_segment`, so the id is a valid IRI.
    """
    current_doc_uuid = doc_uuid or str(uuid4())
    namespace = doc_namespace(doc_name, current_doc_uuid)

    if prefix == "SpdxDocument":
        return namespace

    prefix = iri_segment(prefix)

    counter_key = (current_doc_uuid, prefix)
    reserved = _RESERVED.get(counter_key, ())
    seq_id = _ID_COUNTERS.get(counter_key, 0) + 1
    while seq_id in reserved:
        seq_id += 1
    _ID_COUNTERS[counter_key] = seq_id
    return f"{namespace}#{prefix}-{seq_id}"


def reserve_spdx_ids(doc_name: str, doc_uuid: str, spdx_ids: Iterable[str]) -> None:
    """Reserve every number *spdx_ids* already uses in (*doc_name*,
    *doc_uuid*)'s own document namespace, so a later :func:`generate_spdx_id`
    call for the same ``(doc_uuid, prefix)`` skips it instead of re-minting a
    duplicate.

    Intended for a registry auto-harvested from an earlier run of the exact
    same document (same name/version/dependencies -> same deterministic
    *doc_uuid*): the registry looks ids up by content hash/name first (see
    ``pitloom.id_registry.IdRegistry.lookup``), and only a
    lookup *miss* falls back to minting here -- without a reservation, a
    fresh mint doesn't know the registry already claimed a number in this
    same namespace and can hand out a duplicate. Call once per document,
    right after :func:`_clear_doc_counters`, before the first
    ``generate_spdx_id`` call for it. An id in a different namespace (a
    registry entry harvested from an unrelated document) is ignored -- only
    the ``prefix``/``n`` suffix matters, matched with a greedy prefix (e.g.
    ``AIPackage-my-model-3`` -> prefix ``AIPackage-my-model``, n=``3``).
    """
    namespace = doc_namespace(doc_name, doc_uuid)
    pattern = re.compile(rf"^{re.escape(namespace)}#(?P<prefix>.+)-(?P<n>\d+)$")
    for spdx_id in spdx_ids:
        match = pattern.match(spdx_id)
        if not match:
            continue
        counter_key = (doc_uuid, match.group("prefix"))
        _RESERVED.setdefault(counter_key, set()).add(int(match.group("n")))


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def build_relationship(
    from_id: str | None,
    to_ids: list[str],
    rel_type: str,
    doc_name: str,
    doc_uuid: str,
    creation_info: spdx3.CreationInfo,
    rel_class: type[spdx3.Relationship] = spdx3.Relationship,
    id_suffix: str | None = None,
    **kwargs: Any,
) -> spdx3.Relationship | None:
    """Helper to cleanly instantiate SPDX 3 Relationship objects."""
    if from_id is None:
        return None

    spdx_id = generate_spdx_id(
        id_suffix or "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return rel_class(
        spdxId=spdx_id,
        from_=from_id,
        to=to_ids,
        relationshipType=rel_type,
        creationInfo=creation_info,
        **kwargs,
    )
